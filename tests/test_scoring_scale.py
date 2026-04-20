from __future__ import annotations

import sqlite3

from applypilot.database import get_connection, get_jobs_by_stage, init_db
from applypilot.scoring.scorer import _parse_score_response


def test_parse_score_response_clamps_to_100() -> None:
    parsed = _parse_score_response(
        "SCORE: 145\nKEYWORDS: python, automation\nREASONING: Excellent alignment."
    )
    assert parsed["score"] == 100
    assert parsed["keywords"] == "python, automation"


def test_init_db_migrates_legacy_scores_only_on_upgrade(tmp_path) -> None:
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE jobs (
            url TEXT PRIMARY KEY,
            title TEXT,
            salary TEXT,
            description TEXT,
            location TEXT,
            site TEXT,
            strategy TEXT,
            discovered_at TEXT,
            full_description TEXT,
            application_url TEXT,
            detail_scraped_at TEXT,
            detail_error TEXT,
            fit_score INTEGER,
            score_reasoning TEXT,
            scored_at TEXT,
            tailored_resume_path TEXT,
            tailored_at TEXT,
            tailor_attempts INTEGER DEFAULT 0,
            cover_letter_path TEXT,
            cover_letter_at TEXT,
            cover_attempts INTEGER DEFAULT 0,
            applied_at TEXT,
            apply_status TEXT,
            apply_error TEXT,
            apply_attempts INTEGER DEFAULT 0,
            agent_id TEXT,
            last_attempted_at TEXT,
            apply_duration_ms INTEGER,
            apply_task_id TEXT,
            verification_confidence TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO jobs(url, title, fit_score, full_description) VALUES (?, ?, ?, ?)",
        ("https://example.com/job", "Legacy Job", 8, "desc"),
    )
    conn.commit()
    conn.close()

    init_db(db_path=db_path)
    upgraded = get_connection(db_path)
    score = upgraded.execute("SELECT fit_score FROM jobs WHERE url = ?", ("https://example.com/job",)).fetchone()[0]
    assert score == 80


def test_pending_tailor_excludes_human_review_jobs(tmp_path) -> None:
    db_path = tmp_path / "jobs.db"
    conn = init_db(db_path=db_path)
    conn.execute(
        "INSERT INTO jobs(url, title, full_description, fit_score, human_review_required) VALUES (?, ?, ?, ?, ?)",
        ("https://example.com/human", "Human Review Job", "desc", 95, 1),
    )
    conn.execute(
        "INSERT INTO jobs(url, title, full_description, fit_score, human_review_required) VALUES (?, ?, ?, ?, ?)",
        ("https://example.com/auto", "Auto Job", "desc", 80, 0),
    )
    conn.commit()

    jobs = get_jobs_by_stage(conn=conn, stage="pending_tailor", min_score=70, limit=10)
    assert [job["url"] for job in jobs] == ["https://example.com/auto"]
