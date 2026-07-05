"""Tests for applypilot.scoring.cover_letter: generation, persistence, batch."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from applypilot.scoring.cover_letter import (
    generate_cover_letter,
    generate_cover_letter_for_job,
    save_cover_letter_artifacts,
)


# ── generate_cover_letter ───────────────────────────────────────────────

class TestGenerateCoverLetter:
    def test_returns_letter(self) -> None:
        profile = {
            "personal": {"full_name": "John"},
            "skills_boundary": {},
            "resume_facts": {},
        }
        job = {
            "title": "SWE",
            "site": "Google",
            "location": "Toronto",
            "full_description": "Build things.",
        }
        with patch("applypilot.scoring.cover_letter.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.return_value = "Dear Hiring Manager,\nI'm excited to apply.\nBest, John"
            mock_get_client.return_value = mock_client

            letter = generate_cover_letter("Resume text", job, profile)
            assert "Dear Hiring Manager" in letter

    def test_strips_preamble(self) -> None:
        profile = {
            "personal": {"full_name": "John"},
            "skills_boundary": {},
            "resume_facts": {},
        }
        job = {
            "title": "SWE",
            "site": "Google",
            "full_description": "Build things.",
        }
        with patch("applypilot.scoring.cover_letter.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.return_value = "Here's your letter:\n\nDear Team,\nHello!"
            mock_get_client.return_value = mock_client

            letter = generate_cover_letter("Resume text", job, profile)
            assert "Here's your letter" not in letter
            assert "Dear Team" in letter

    def test_retries_on_validation_failure(self) -> None:
        profile = {
            "personal": {"full_name": "John"},
            "skills_boundary": {},
            "resume_facts": {},
        }
        job = {
            "title": "SWE",
            "site": "Google",
            "full_description": "Build things.",
        }
        with patch("applypilot.scoring.cover_letter.get_client") as mock_get_client:
            mock_client = MagicMock()
            # First attempt: too short (fails validation)
            # Second attempt: good
            mock_client.chat.side_effect = [
                "Hi,\nBest",
                "Dear Hiring Manager,\n\nI am writing to express my strong interest in the Software Engineer role at Google.\n\nWith my background in Python development and API design, I believe I would be a great fit for your team.\n\nBest regards,\nJohn",
            ]
            mock_get_client.return_value = mock_client

            generate_cover_letter("Resume text", job, profile, max_retries=2)
            assert mock_client.chat.call_count == 2

    def test_returns_last_attempt_on_failure(self) -> None:
        profile = {
            "personal": {"full_name": "John"},
            "skills_boundary": {},
            "resume_facts": {},
        }
        job = {
            "title": "SWE",
            "site": "Google",
            "full_description": "Build things.",
        }
        with patch("applypilot.scoring.cover_letter.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.return_value = "Dear Team,\nNice to meet you.\nBest, John"
            mock_get_client.return_value = mock_client

            letter = generate_cover_letter("Resume text", job, profile, max_retries=0)
            assert "Dear Team" in letter

    def test_passes_validation_mode(self) -> None:
        profile = {
            "personal": {"full_name": "John"},
            "skills_boundary": {},
            "resume_facts": {},
        }
        job = {
            "title": "SWE",
            "site": "Google",
            "full_description": "Build things.",
        }
        with patch("applypilot.scoring.cover_letter.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.return_value = "Dear Team,\nNice to meet you.\nBest, John"
            mock_get_client.return_value = mock_client

            # In lenient mode, even a short letter should pass
            letter = generate_cover_letter("Resume text", job, profile, validation_mode="lenient")
            assert letter  # non-empty


# ── save_cover_letter_artifacts ─────────────────────────────────────────

class TestSaveCoverLetterArtifacts:
    def test_saves_text_file(self, tmp_path: Path) -> None:
        job = {"title": "Software Engineer", "site": "Google"}
        letter = "Dear Hiring Manager,\nBest, John"

        with patch("applypilot.scoring.cover_letter.COVER_LETTER_DIR", tmp_path):
            result = save_cover_letter_artifacts(job, letter)
            assert Path(result["path"]).exists()
            assert "Dear Hiring Manager" in Path(result["path"]).read_text()

    def test_returns_path_dict(self, tmp_path: Path) -> None:
        job = {"title": "SWE", "site": "Meta"}
        letter = "Dear Team,\nBest."

        with patch("applypilot.scoring.cover_letter.COVER_LETTER_DIR", tmp_path):
            result = save_cover_letter_artifacts(job, letter)
            assert "path" in result
            assert "pdf_path" in result


# ── generate_cover_letter_for_job ───────────────────────────────────────

class TestGenerateCoverLetterForJob:
    def test_generates_and_saves(self, tmp_path: Path) -> None:
        resume_path = tmp_path / "resume.txt"
        resume_path.write_text("Python | Java | Docker")

        job = {
            "title": "SWE",
            "site": "Google",
            "location": "Toronto",
            "full_description": "Build things.",
            "tailored_resume_path": str(resume_path),
        }

        with patch("applypilot.scoring.cover_letter.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.return_value = "Dear Team,\nBest."
            mock_get_client.return_value = mock_client

            with patch("applypilot.scoring.cover_letter.COVER_LETTER_DIR", tmp_path):
                with patch("applypilot.scoring.cover_letter.load_profile") as mock_profile:
                    mock_profile.return_value = {
                        "personal": {"full_name": "John"},
                        "skills_boundary": {},
                        "resume_facts": {},
                    }
                    result = generate_cover_letter_for_job(job)
                    assert "text" in result
                    assert "path" in result

    def test_raises_on_missing_resume(self, tmp_path: Path) -> None:
        job = {
            "title": "SWE",
            "site": "Google",
            "full_description": "Build things.",
        }
        with pytest.raises(FileNotFoundError):
            generate_cover_letter_for_job(job)
