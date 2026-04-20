from __future__ import annotations

from applypilot.database import init_db
from applypilot.human_review import promote_job_to_cover_letter_human_review


def test_handoff_cover_letter_required_marks_human_review(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "apply.db"
    conn = init_db(db_path=db_path)
    conn.execute(
        """
        INSERT INTO jobs(
            url, title, site, full_description, tailored_resume_path, fit_score,
            apply_status, human_review_required
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "https://example.com/job",
            "Engineer",
            "LinkedIn",
            "desc",
            str(tmp_path / "resume.txt"),
            82,
            "in_progress",
            0,
        ),
    )
    conn.commit()

    monkeypatch.setattr(
        "applypilot.scoring.cover_letter.generate_cover_letter_for_job",
        lambda job: {"text": "Dear Hiring Manager", "path": str(tmp_path / "letter.txt"), "pdf_path": None},
    )

    sync_calls: list[list[str]] = []

    def fake_sync(limit=100, urls=None, db_path=None):
        sync_calls.append(urls or [])
        return {"status": "ok", "message": "synced", "synced": len(urls or []), "errors": 0}

    monkeypatch.setattr("applypilot.human_review.sync_human_review_jobs", fake_sync)

    result = promote_job_to_cover_letter_human_review(
        {
            "url": "https://example.com/job",
            "title": "Engineer",
            "site": "LinkedIn",
            "tailored_resume_path": str(tmp_path / "resume.pdf"),
        },
        db_path=str(db_path),
    )

    row = conn.execute(
        """
        SELECT human_review_required, human_review_reason,
               cover_letter_path, human_review_synced_at
        FROM jobs WHERE url = ?
        """,
        ("https://example.com/job",),
    ).fetchone()

    assert row["human_review_required"] == 1
    assert row["human_review_reason"] == "cover_letter_required"
    assert row["cover_letter_path"] == str(tmp_path / "letter.txt")
    assert row["human_review_synced_at"] is None
    assert sync_calls == [["https://example.com/job"]]
    assert result["text"] == "Dear Hiring Manager"
