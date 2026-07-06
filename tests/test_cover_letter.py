"""Tests for applypilot.scoring.cover_letter: generation helpers, persistence."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


from applypilot.scoring.cover_letter import (
    _build_cover_letter_prompt,
    _strip_preamble,
    generate_cover_letter,
    run_cover_letters,
)


MINIMAL_PROFILE = {
    "personal": {
        "full_name": "John Doe",
        "preferred_name": "Johnny",
        "email": "john@example.com",
        "phone": "555-123-4567",
        "city": "Toronto",
    },
    "skills_boundary": {
        "languages": ["Python", "Bash"],
        "frameworks": ["FastAPI"],
        "tools": ["Docker"],
    },
    "resume_facts": {
        "preserved_projects": ["BotBuilder", "CI-Pipeline"],
        "real_metrics": ["10K requests/day", "50% faster builds"],
    },
}


# ── _build_cover_letter_prompt ──────────────────────────────────────────


class TestBuildCoverLetterPrompt:
    def test_includes_sign_off_name(self) -> None:
        prompt = _build_cover_letter_prompt(MINIMAL_PROFILE)
        assert "Johnny" in prompt
        assert 'Sign off: just "Johnny"' in prompt

    def test_includes_skills_boundary(self) -> None:
        prompt = _build_cover_letter_prompt(MINIMAL_PROFILE)
        assert "Python" in prompt
        assert "Bash" in prompt
        assert "FastAPI" in prompt
        assert "Docker" in prompt

    def test_includes_preserved_projects(self) -> None:
        prompt = _build_cover_letter_prompt(MINIMAL_PROFILE)
        assert "BotBuilder" in prompt
        assert "CI-Pipeline" in prompt

    def test_includes_real_metrics(self) -> None:
        prompt = _build_cover_letter_prompt(MINIMAL_PROFILE)
        assert "10K requests/day" in prompt
        assert "50% faster builds" in prompt

    def test_includes_banned_words(self) -> None:
        prompt = _build_cover_letter_prompt(MINIMAL_PROFILE)
        assert "BANNED" in prompt
        # Should include at least some banned words
        assert "passionate" in prompt.lower() or "spearhead" in prompt.lower()

    def test_includes_structure_instructions(self) -> None:
        prompt = _build_cover_letter_prompt(MINIMAL_PROFILE)
        assert "3 short paragraphs" in prompt
        assert "Under 250 words" in prompt
        assert "PARAGRAPH 1" in prompt
        assert "PARAGRAPH 2" in prompt
        assert "PARAGRAPH 3" in prompt

    def test_includes_voice_instructions(self) -> None:
        prompt = _build_cover_letter_prompt(MINIMAL_PROFILE)
        assert "Write like a real engineer" in prompt
        assert "NEVER narrate" in prompt or "NEVER hedge" in prompt

    def test_falls_back_to_full_name(self) -> None:
        profile = {
            "personal": {"full_name": "Jane Smith"},
            "skills_boundary": {},
            "resume_facts": {},
        }
        prompt = _build_cover_letter_prompt(profile)
        assert "Jane Smith" in prompt
        assert 'Sign off: just "Jane Smith"' in prompt

    def test_handles_empty_skills_boundary(self) -> None:
        profile = {
            "personal": {"full_name": "Alex Lee"},
            "skills_boundary": {},
            "resume_facts": {},
        }
        prompt = _build_cover_letter_prompt(profile)
        assert "the tools listed in the resume" in prompt

    def test_handles_empty_resume_facts(self) -> None:
        profile = {
            "personal": {"full_name": "Alex Lee"},
            "skills_boundary": {"languages": ["Python"]},
            "resume_facts": {},
        }
        prompt = _build_cover_letter_prompt(profile)
        assert "Python" in prompt


# ── _strip_preamble ─────────────────────────────────────────────────────


class TestStripPreamble:
    def test_removes_preamble_before_dear(self) -> None:
        text = "Here is your cover letter:\n\nDear Hiring Manager,\nNice to meet you."
        result = _strip_preamble(text)
        assert result.startswith("Dear Hiring Manager,")

    def test_keeps_text_starting_with_dear(self) -> None:
        text = "Dear Hiring Team,\nHope this finds you well."
        result = _strip_preamble(text)
        assert result == text

    def test_handles_no_preamble(self) -> None:
        text = "Dear Sir or Madam,\nBest regards."
        result = _strip_preamble(text)
        assert result == text

    def test_case_insensitive_dear(self) -> None:
        text = "Here's the letter:\n\ndear hiring manager,\nHello!"
        result = _strip_preamble(text)
        assert result.startswith("dear hiring manager,")

    def test_handles_empty_text(self) -> None:
        result = _strip_preamble("")
        assert result == ""

    def test_handles_no_dear(self) -> None:
        text = "Hello there,\nJust writing in."
        result = _strip_preamble(text)
        assert result == text


# ── generate_cover_letter_for_job ────────────────────────────────────────


class TestGenerateCoverLetterForJob:
    def test_generates_and_persists_letter(self, tmp_path) -> None:
        """generate_cover_letter_for_job generates, saves, and returns artifacts."""
        from applypilot.scoring.cover_letter import generate_cover_letter_for_job

        resume_file = tmp_path / "resume1.txt"
        resume_file.write_text("My resume content")

        job = {
            "title": "Backend Eng",
            "site": "Indeed",
            "location": "NYC",
            "full_description": "Python needed",
            "tailored_resume_path": str(resume_file),
        }

        with (
            patch("applypilot.scoring.cover_letter.load_profile", return_value=MINIMAL_PROFILE),
            patch("applypilot.scoring.cover_letter.RESUME_PATH", resume_file),
            patch("applypilot.scoring.cover_letter.generate_cover_letter") as mock_gen,
            patch("applypilot.scoring.cover_letter.save_cover_letter_artifacts") as mock_save,
        ):
            mock_gen.return_value = "Dear Hiring Manager,\nGreat letter.\nJohnny"
            mock_save.return_value = {"path": "/tmp/cover.txt", "pdf_path": "/tmp/cover.pdf"}

            result = generate_cover_letter_for_job(job)

        assert result["text"] == "Dear Hiring Manager,\nGreat letter.\nJohnny"
        assert result["path"] == "/tmp/cover.txt"
        assert result["pdf_path"] == "/tmp/cover.pdf"

    def test_raises_on_missing_resume_text(self, tmp_path) -> None:
        """generate_cover_letter_for_job raises if resume text file not found."""
        from applypilot.scoring.cover_letter import generate_cover_letter_for_job
        import pytest as _pytest

        job = {
            "title": "Backend Eng",
            "site": "Indeed",
            "location": "NYC",
            "full_description": "Python needed",
            "tailored_resume_path": str(tmp_path / "no_such" / "resume.txt"),
        }

        with (
            patch("applypilot.scoring.cover_letter.load_profile", return_value=MINIMAL_PROFILE),
            patch("applypilot.scoring.cover_letter.RESUME_PATH", tmp_path / "resume.txt"),
        ):
            (tmp_path / "resume.txt").write_text("resume")
            with _pytest.raises(FileNotFoundError, match="Resume text not found"):
                generate_cover_letter_for_job(job)


# ── generate_cover_letter ────────────────────────────────────────────────


class TestGenerateCoverLetter:
    def test_generates_letter_on_first_try(self) -> None:
        job = {"title": "Backend Eng", "site": "Indeed", "location": "NYC", "full_description": "Python needed"}

        with patch("applypilot.scoring.cover_letter.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.return_value = "Dear Hiring Manager,\nI built something great.\nJohnny"
            mock_get_client.return_value = mock_client

            with patch("applypilot.scoring.cover_letter.validate_cover_letter") as mock_validate:
                mock_validate.return_value = {"passed": True, "errors": [], "warnings": []}
                letter = generate_cover_letter("resume text", job, MINIMAL_PROFILE)

        assert "Dear Hiring Manager" in letter

    def test_retries_on_validation_failure(self) -> None:
        job = {"title": "Backend Eng", "site": "Indeed", "location": "NYC", "full_description": "Python needed"}

        with patch("applypilot.scoring.cover_letter.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.side_effect = [
                "Dear Hiring Manager,\nFirst try.\nJohnny",
                "Dear Hiring Manager,\nSecond try.\nJohnny",
            ]
            mock_get_client.return_value = mock_client

            with patch("applypilot.scoring.cover_letter.validate_cover_letter") as mock_validate:
                mock_validate.side_effect = [
                    {"passed": False, "errors": ["too short"], "warnings": []},
                    {"passed": True, "errors": [], "warnings": []},
                ]
                letter = generate_cover_letter("resume text", job, MINIMAL_PROFILE, max_retries=3)

        assert mock_client.chat.call_count == 2
        assert "Second try" in letter

    def test_returns_last_attempt_if_all_fail(self) -> None:
        job = {"title": "Backend Eng", "site": "Indeed", "location": "NYC", "full_description": "Python needed"}

        with patch("applypilot.scoring.cover_letter.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.side_effect = [
                "Dear Hiring Manager,\nAttempt 1.\nJohnny",
                "Dear Hiring Manager,\nAttempt 2.\nJohnny",
                "Dear Hiring Manager,\nAttempt 3.\nJohnny",
            ]
            mock_get_client.return_value = mock_client

            with patch("applypilot.scoring.cover_letter.validate_cover_letter") as mock_validate:
                mock_validate.return_value = {"passed": False, "errors": ["too short"], "warnings": []}
                letter = generate_cover_letter("resume text", job, MINIMAL_PROFILE, max_retries=2)

        assert mock_client.chat.call_count == 3
        assert "Attempt 3" in letter


# ── run_cover_letters (4 tests) ──────────────────────────────────────────


class TestRunCoverLetters:
    @patch("applypilot.scoring.cover_letter.get_connection")
    @patch("applypilot.scoring.cover_letter.RESUME_PATH")
    @patch("applypilot.scoring.cover_letter.load_profile")
    @patch("applypilot.scoring.cover_letter.generate_cover_letter")
    @patch("applypilot.scoring.cover_letter.save_cover_letter_artifacts")
    @patch("applypilot.scoring.cover_letter.COVER_LETTER_DIR")
    def test_generates_two_letters_and_updates_db(
        self, mock_dir, mock_save, mock_gen, mock_load, mock_resume, mock_get_conn
    ) -> None:
        """Generate 2 cover letters and verify DB updates."""
        mock_resume.read_text.return_value = "My resume"
        mock_load.return_value = MINIMAL_PROFILE

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            {
                "url": "https://j1.com",
                "title": "Job1",
                "site": "Indeed",
                "location": "NYC",
                "fit_score": 85,
                "tailored_resume_path": "/tmp/resume1.txt",
                "full_description": "desc1",
            },
            {
                "url": "https://j2.com",
                "title": "Job2",
                "site": "LinkedIn",
                "location": "SF",
                "fit_score": 92,
                "tailored_resume_path": "/tmp/resume2.txt",
                "full_description": "desc2",
            },
        ]
        mock_get_conn.return_value = mock_conn

        mock_gen.return_value = "Dear Hiring Manager,\nGreat letter.\nJohnny"
        mock_save.return_value = {"path": "/tmp/cover.txt", "pdf_path": None}

        result = run_cover_letters(min_score=70)

        assert result["generated"] == 2
        assert result["errors"] == 0
        assert "elapsed" in result
        assert mock_gen.call_count == 2

    @patch("applypilot.scoring.cover_letter.get_connection")
    @patch("applypilot.scoring.cover_letter.RESUME_PATH")
    @patch("applypilot.scoring.cover_letter.load_profile")
    @patch("applypilot.scoring.cover_letter.generate_cover_letter")
    @patch("applypilot.scoring.cover_letter.save_cover_letter_artifacts")
    @patch("applypilot.scoring.cover_letter.COVER_LETTER_DIR")
    def test_error_increments_attempts(
        self, mock_dir, mock_save, mock_gen, mock_load, mock_resume, mock_get_conn
    ) -> None:
        """Errors should increment cover_attempts without saving path."""
        mock_resume.read_text.return_value = "My resume"
        mock_load.return_value = MINIMAL_PROFILE

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            {
                "url": "https://j1.com",
                "title": "Job1",
                "site": "Indeed",
                "location": "NYC",
                "fit_score": 85,
                "tailored_resume_path": "/tmp/resume1.txt",
                "full_description": "desc1",
            },
            {
                "url": "https://j2.com",
                "title": "Job2",
                "site": "LinkedIn",
                "location": "SF",
                "fit_score": 90,
                "tailored_resume_path": "/tmp/resume2.txt",
                "full_description": "desc2",
            },
        ]
        mock_get_conn.return_value = mock_conn

        # First job succeeds, second fails
        mock_gen.side_effect = [
            "Dear Hiring Manager,\nGreat.\nJohnny",
            RuntimeError("timeout"),
        ]
        mock_save.return_value = {"path": "/tmp/cover.txt", "pdf_path": None}

        result = run_cover_letters(min_score=70)

        assert result["generated"] == 1
        assert result["errors"] == 1

    @patch("applypilot.scoring.cover_letter.get_connection")
    @patch("applypilot.scoring.cover_letter.RESUME_PATH")
    @patch("applypilot.scoring.cover_letter.load_profile")
    @patch("applypilot.scoring.cover_letter.generate_cover_letter")
    def test_no_jobs(self, mock_gen, mock_load, mock_resume, mock_get_conn) -> None:
        """No jobs needing cover letters returns immediately."""
        mock_resume.read_text.return_value = "resume"
        mock_load.return_value = MINIMAL_PROFILE

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_get_conn.return_value = mock_conn

        result = run_cover_letters(min_score=70)

        assert result["generated"] == 0
        assert result["errors"] == 0
        assert result["elapsed"] == 0.0
        mock_gen.assert_not_called()

    @patch("applypilot.scoring.cover_letter.get_connection")
    @patch("applypilot.scoring.cover_letter.RESUME_PATH")
    @patch("applypilot.scoring.cover_letter.load_profile")
    @patch("applypilot.scoring.cover_letter.generate_cover_letter")
    @patch("applypilot.scoring.cover_letter.save_cover_letter_artifacts")
    @patch("applypilot.scoring.cover_letter.COVER_LETTER_DIR")
    def test_min_score_filter(self, mock_dir, mock_save, mock_gen, mock_load, mock_resume, mock_get_conn) -> None:
        """Jobs below min_score should not be processed."""
        mock_resume.read_text.return_value = "resume"
        mock_load.return_value = MINIMAL_PROFILE

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = [
            {
                "url": "https://j1.com",
                "title": "Job1",
                "site": "Indeed",
                "location": "NYC",
                "fit_score": 85,
                "tailored_resume_path": "/tmp/resume1.txt",
                "full_description": "desc1",
            },
        ]
        mock_get_conn.return_value = mock_conn
        mock_gen.return_value = "Dear Hiring Manager,\nGreat.\nJohnny"
        mock_save.return_value = {"path": "/tmp/cover.txt", "pdf_path": None}

        result = run_cover_letters(min_score=80)

        # With min_score=80, job with score 85 should be processed
        assert result["generated"] == 1
