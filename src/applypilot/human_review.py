"""Human-review queue export for high-relevance jobs."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx

from applypilot.config import DEFAULTS, get_human_review_score, get_int_env
from applypilot.database import get_connection

log = logging.getLogger(__name__)

FIXED_SHEET_COLUMNS = [
    "job_url",
    "application_url",
    "title",
    "source_site",
    "location",
    "fit_score",
    "score_reasoning",
    "human_review_reason",
    "cover_letter_text",
    "review_queue",
    "review_status",
    "review_owner",
    "human_notes",
    "discovered_at",
    "scored_at",
    "handoff_at",
    "updated_at",
]


def webhook_configured() -> bool:
    """Return True when the Google Sheets webhook is configured."""
    return bool(os.environ.get("GOOGLE_SHEETS_WEBHOOK_URL"))


def _select_unsynced_jobs(
    limit: int = 100,
    urls: list[str] | None = None,
    db_path: str | None = None,
) -> list[dict]:
    """Return unsynced human-review jobs from the database."""
    conn = get_connection(db_path)
    query = (
        "SELECT url, application_url, title, site, location, fit_score, score_reasoning, "
        "discovered_at, scored_at, human_review_reason, human_review_marked_at, cover_letter_path "
        "FROM jobs WHERE COALESCE(human_review_required, 0) = 1 "
        "AND human_review_synced_at IS NULL"
    )
    params: list[object] = []

    if urls:
        placeholders = ",".join("?" * len(urls))
        query += f" AND url IN ({placeholders})"
        params.extend(urls)

    query += " ORDER BY fit_score DESC, scored_at DESC"
    if limit > 0:
        query += " LIMIT ?"
        params.append(limit)

    rows = conn.execute(query, params).fetchall()
    if not rows:
        return []

    columns = rows[0].keys()
    return [dict(zip(columns, row)) for row in rows]


def _read_cover_letter_text(job: dict) -> str:
    """Read direct cover-letter text for human-review rows when present."""
    cl_path = job.get("cover_letter_path")
    if not cl_path:
        return ""
    path = Path(cl_path)
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        log.debug("Failed reading cover letter text from %s", path, exc_info=True)
        return ""


def _queue_for_job(job: dict) -> str:
    """Return the target sheet tab / review queue for a human-review job."""
    reason = (job.get("human_review_reason") or "").lower()
    if reason == "cover_letter_required":
        return "Cover Letter Required"
    return "Human Review"


def _build_rows(jobs: list[dict]) -> list[dict]:
    """Serialize DB jobs for the Apps Script webhook."""
    rows: list[dict] = []
    updated_at = datetime.now(timezone.utc).isoformat()
    for job in jobs:
        row = {
            "job_url": job["url"],
            "application_url": job.get("application_url") or "",
            "title": job.get("title") or "",
            "source_site": job.get("site") or "",
            "location": job.get("location") or "",
            "fit_score": job.get("fit_score"),
            "score_reasoning": job.get("score_reasoning") or "",
            "human_review_reason": job.get("human_review_reason") or f"score>={get_human_review_score()}",
            "cover_letter_text": _read_cover_letter_text(job),
            "review_queue": _queue_for_job(job),
            "discovered_at": job.get("discovered_at") or "",
            "scored_at": job.get("scored_at") or "",
            "review_status": "pending",
            "review_owner": "",
            "human_notes": "",
            "handoff_at": job.get("human_review_marked_at") or "",
            "updated_at": updated_at,
        }
        rows.append({key: row.get(key, "") for key in FIXED_SHEET_COLUMNS})
    return rows


def _mark_synced(urls: list[str], db_path: str | None = None) -> None:
    """Mark human-review rows as synced."""
    if not urls:
        return
    conn = get_connection(db_path)
    placeholders = ",".join("?" * len(urls))
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        f"UPDATE jobs SET human_review_synced_at = ?, human_review_sync_error = NULL "
        f"WHERE url IN ({placeholders})",
        [now] + urls,
    )
    conn.commit()


def _mark_sync_error(urls: list[str], error: str, db_path: str | None = None) -> None:
    """Persist the last human-review sync error for the given jobs."""
    if not urls:
        return
    conn = get_connection(db_path)
    placeholders = ",".join("?" * len(urls))
    conn.execute(
        f"UPDATE jobs SET human_review_sync_error = ? WHERE url IN ({placeholders})",
        [error[:500]] + urls,
    )
    conn.commit()


def sync_human_review_jobs(
    limit: int = 100,
    urls: list[str] | None = None,
    db_path: str | None = None,
) -> dict:
    """Sync unsynced human-review jobs to a Google Sheets Apps Script webhook."""
    if not webhook_configured():
        return {"status": "skipped", "synced": 0, "errors": 0, "message": "webhook not configured"}

    jobs = _select_unsynced_jobs(limit=limit, urls=urls, db_path=db_path)
    if not jobs:
        return {"status": "ok", "synced": 0, "errors": 0, "message": "no pending human-review jobs"}

    webhook_url = os.environ["GOOGLE_SHEETS_WEBHOOK_URL"]
    secret = os.environ.get("GOOGLE_SHEETS_WEBHOOK_SECRET", "")
    timeout = max(1, get_int_env("GOOGLE_SHEETS_TIMEOUT_SEC", DEFAULTS["google_sheets_timeout_sec"]))
    payload = {"secret": secret, "columns": FIXED_SHEET_COLUMNS, "rows": _build_rows(jobs)}
    job_urls = [job["url"] for job in jobs]

    try:
        response = httpx.post(
            webhook_url,
            json=payload,
            headers={"X-ApplyPilot-Secret": secret} if secret else None,
            timeout=timeout,
        )
        response.raise_for_status()
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        _mark_sync_error(job_urls, message, db_path=db_path)
        log.error("Human-review sync failed: %s", message)
        return {"status": "error", "synced": 0, "errors": len(job_urls), "message": message}

    _mark_synced(job_urls, db_path=db_path)
    log.info("Synced %d human-review job(s) to Google Sheets.", len(job_urls))
    return {"status": "ok", "synced": len(job_urls), "errors": 0, "message": "synced"}


def promote_job_to_cover_letter_human_review(
    job: dict,
    db_path: str | None = None,
    sync_now: bool = True,
) -> dict:
    """Generate a cover letter and move a job into the cover-letter review queue."""
    from applypilot.scoring.cover_letter import generate_cover_letter_for_job

    saved = generate_cover_letter_for_job(job)
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection(db_path)
    conn.execute(
        """
        UPDATE jobs
        SET cover_letter_path = ?,
            cover_letter_at = ?,
            cover_attempts = COALESCE(cover_attempts, 0) + 1,
            human_review_required = 1,
            human_review_reason = 'cover_letter_required',
            human_review_marked_at = ?,
            human_review_synced_at = NULL,
            human_review_sync_error = NULL
        WHERE url = ?
        """,
        (saved["path"], now, now, job["url"]),
    )
    conn.commit()

    sync_result = {"status": "skipped", "message": "sync disabled", "synced": 0, "errors": 0}
    if sync_now:
        sync_result = sync_human_review_jobs(limit=1, urls=[job["url"]], db_path=db_path)

    return {"sync_result": sync_result, **saved}
