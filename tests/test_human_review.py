from __future__ import annotations

import httpx

from applypilot.database import init_db
from applypilot.human_review import FIXED_SHEET_COLUMNS, _build_rows, sync_human_review_jobs


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None


def test_sync_human_review_marks_rows_as_synced(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "review.db"
    monkeypatch.setenv("GOOGLE_SHEETS_WEBHOOK_URL", "https://example.com/webhook")
    monkeypatch.setenv("GOOGLE_SHEETS_WEBHOOK_SECRET", "secret")
    monkeypatch.setenv("GOOGLE_SHEETS_TIMEOUT_SEC", "3")

    captured: dict = {}

    def fake_post(url, json=None, headers=None, timeout=None, follow_redirects=False):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        captured["follow_redirects"] = follow_redirects
        return _FakeResponse()

    monkeypatch.setattr("applypilot.human_review.httpx.post", fake_post)

    conn = init_db(db_path=db_path)
    conn.execute(
        """
        INSERT INTO jobs(
            url, title, site, location, fit_score, score_reasoning, full_description,
            human_review_required, human_review_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "https://example.com/job",
            "Staff Engineer",
            "LinkedIn",
            "Remote",
            94,
            "python, api\nStrong overlap.",
            "desc",
            1,
            "score>=90",
        ),
    )
    conn.commit()

    result = sync_human_review_jobs(limit=10, db_path=str(db_path))
    assert result["status"] == "ok"
    assert result["synced"] == 1
    assert captured["url"] == "https://example.com/webhook"
    assert captured["headers"] == {"X-ApplyPilot-Secret": "secret"}
    assert captured["timeout"] == 3
    assert captured["follow_redirects"] is True
    assert captured["json"]["rows"][0]["job_url"] == "https://example.com/job"

    synced_at = conn.execute(
        "SELECT human_review_synced_at FROM jobs WHERE url = ?",
        ("https://example.com/job",),
    ).fetchone()[0]
    assert synced_at is not None


def test_sync_human_review_skips_when_webhook_missing(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "review.db"
    monkeypatch.delenv("GOOGLE_SHEETS_WEBHOOK_URL", raising=False)

    def fail_post(*args, **kwargs):  # pragma: no cover - should never be called
        raise AssertionError("httpx.post should not be called without a webhook URL")

    monkeypatch.setattr("applypilot.human_review.httpx.post", fail_post)

    conn = init_db(db_path=db_path)
    conn.execute(
        """
        INSERT INTO jobs(url, title, fit_score, human_review_required)
        VALUES (?, ?, ?, ?)
        """,
        ("https://example.com/job", "Staff Engineer", 94, 1),
    )
    conn.commit()

    result = sync_human_review_jobs(limit=10, db_path=str(db_path))

    assert result == {
        "status": "skipped",
        "synced": 0,
        "errors": 0,
        "message": "webhook not configured",
    }

    row = conn.execute(
        "SELECT human_review_synced_at, human_review_sync_error FROM jobs WHERE url = ?",
        ("https://example.com/job",),
    ).fetchone()
    assert row["human_review_synced_at"] is None
    assert row["human_review_sync_error"] is None


def test_sync_human_review_no_pending_jobs_does_not_post(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "review.db"
    monkeypatch.setenv("GOOGLE_SHEETS_WEBHOOK_URL", "https://example.com/webhook")

    def fail_post(*args, **kwargs):  # pragma: no cover - should never be called
        raise AssertionError("httpx.post should not be called without pending rows")

    monkeypatch.setattr("applypilot.human_review.httpx.post", fail_post)
    init_db(db_path=db_path)

    result = sync_human_review_jobs(limit=10, db_path=str(db_path))

    assert result == {
        "status": "ok",
        "synced": 0,
        "errors": 0,
        "message": "no pending human-review jobs",
    }


def test_sync_human_review_records_error_without_marking_synced(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "review.db"
    monkeypatch.setenv("GOOGLE_SHEETS_WEBHOOK_URL", "https://example.com/webhook")

    def fake_post(*args, **kwargs):
        request = httpx.Request("POST", "https://example.com/webhook")
        response = httpx.Response(500, request=request)
        raise httpx.HTTPStatusError("server error", request=request, response=response)

    monkeypatch.setattr("applypilot.human_review.httpx.post", fake_post)

    conn = init_db(db_path=db_path)
    conn.execute(
        """
        INSERT INTO jobs(url, title, fit_score, human_review_required)
        VALUES (?, ?, ?, ?)
        """,
        ("https://example.com/job", "Staff Engineer", 94, 1),
    )
    conn.commit()

    result = sync_human_review_jobs(limit=10, db_path=str(db_path))

    assert result["status"] == "error"
    assert result["synced"] == 0
    assert result["errors"] == 1
    assert "HTTPStatusError" in result["message"]

    row = conn.execute(
        "SELECT human_review_synced_at, human_review_sync_error FROM jobs WHERE url = ?",
        ("https://example.com/job",),
    ).fetchone()
    assert row["human_review_synced_at"] is None
    assert "HTTPStatusError" in row["human_review_sync_error"]


def test_build_rows_uses_fixed_schema_and_cover_letter_queue(tmp_path) -> None:
    cover_letter_path = tmp_path / "letter.txt"
    cover_letter_path.write_text("Dear Hiring Manager,\nTest letter", encoding="utf-8")

    rows = _build_rows(
        [
            {
                "url": "https://example.com/job",
                "application_url": "https://example.com/apply",
                "title": "Engineer",
                "site": "LinkedIn",
                "location": "Remote",
                "fit_score": 91,
                "score_reasoning": "python\nStrong fit",
                "human_review_reason": "cover_letter_required",
                "cover_letter_path": str(cover_letter_path),
                "discovered_at": "2026-01-01T00:00:00Z",
                "scored_at": "2026-01-01T01:00:00Z",
                "human_review_marked_at": "2026-01-01T02:00:00Z",
            }
        ]
    )

    row = rows[0]
    assert list(row.keys()) == FIXED_SHEET_COLUMNS
    assert row["review_queue"] == "Cover Letter Required"
    assert row["cover_letter_text"].startswith("Dear Hiring Manager")
