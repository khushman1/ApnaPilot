"""Tests for applypilot.scoring.cover_letter: generation helpers, persistence."""

from __future__ import annotations

from pathlib import Path

from applypilot.scoring.cover_letter import _build_cover_letter_prompt, _strip_preamble


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
