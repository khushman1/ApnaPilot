"""Tests for applypilot.scoring.tailor: extract_json, tailor_resume, run_tailoring."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from applypilot.scoring.tailor import (
    assemble_resume_text,
    extract_json,
    run_tailoring,
    tailor_resume,
)


# ── extract_json ────────────────────────────────────────────────────────


class TestExtractJson:
    def test_parses_plain_json(self) -> None:
        raw = '{"title": "Engineer", "summary": "Experienced"}'
        result = extract_json(raw)
        assert result["title"] == "Engineer"

    def test_parses_json_fenced(self) -> None:
        raw = 'Here\'s the JSON:\n\n```json\n{"title": "SWE"}\n```'
        result = extract_json(raw)
        assert result["title"] == "SWE"

    def test_parses_fenced_without_lang(self) -> None:
        raw = '```  \n{"title": "Dev"}\n```'
        result = extract_json(raw)
        assert result["title"] == "Dev"

    def test_parses_curly_braces(self) -> None:
        raw = 'Here is the answer: {"title": "SWE", "summary": "Good"}. Let me know!'
        result = extract_json(raw)
        assert result["title"] == "SWE"

    def test_raises_on_invalid(self) -> None:
        with pytest.raises(ValueError, match="No valid JSON"):
            extract_json("no json here at all")

    def test_ignores_bad_fenced_then_finds_good(self) -> None:
        raw = '```json\n{invalid\n```\n\n```json\n{"title": "SWE"}\n```'
        result = extract_json(raw)
        assert result["title"] == "SWE"

    def test_parses_nested_json(self) -> None:
        raw = '{"skills": {"languages": "Python", "tools": "Docker"}}'
        result = extract_json(raw)
        assert result["skills"]["languages"] == "Python"


# ── assemble_resume_text ────────────────────────────────────────────────


class TestAssembleResumeText:
    def test_builds_full_resume(self) -> None:
        data = {
            "title": "Senior Software Engineer",
            "summary": "Experienced in Python and Go.",
            "skills": {"Languages": "Python, Go", "Tools": "Docker"},
            "experience": [
                {
                    "header": "SWE at Google",
                    "subtitle": "Python | 2020-2024",
                    "bullets": ["Built APIs", "Led team"],
                }
            ],
            "projects": [
                {
                    "header": "MyBot",
                    "subtitle": "Python | 2023",
                    "bullets": ["Automated tasks"],
                }
            ],
            "education": "UW | BSc CS",
        }
        profile = {"personal": {"full_name": "John Doe", "email": "john@test.com", "phone": "555-123"}}
        text = assemble_resume_text(data, profile)
        assert "John Doe" in text
        assert "Senior Software Engineer" in text
        assert "john@test.com" in text
        assert "Built APIs" in text
        assert "Automated tasks" in text
        assert "UW | BSc CS" in text

    def test_sanitizes_text(self) -> None:
        data = {
            "title": "Engineer",
            "summary": "Using em\u2014dashes",
            "skills": {},
            "experience": [],
            "projects": [],
            "education": "UW",
        }
        profile = {"personal": {"full_name": "John"}}
        text = assemble_resume_text(data, profile)
        assert "\u2014" not in text  # em dash should be sanitized

    def test_handles_empty_skills(self) -> None:
        data = {
            "title": "SWE",
            "summary": "Builder.",
            "skills": {},
            "experience": [],
            "projects": [],
            "education": "UW",
        }
        profile = {"personal": {"full_name": "John"}}
        text = assemble_resume_text(data, profile)
        assert "TECHNICAL SKILLS" in text


# ── tailor_resume ──────────────────────────────────────────────────────


class TestTailorResume:
    def test_approves_on_first_try(self) -> None:
        job = {
            "title": "SWE",
            "site": "Google",
            "location": "Toronto",
            "full_description": "Build things.",
        }
        profile = {
            "personal": {"full_name": "John"},
            "skills_boundary": {},
            "resume_facts": {},
        }
        with patch("applypilot.scoring.tailor.get_client") as mock_get_client:
            mock_client = MagicMock()
            # First call: tailor LLM returns JSON
            # Second call: judge LLM returns PASS
            mock_client.chat.side_effect = [
                '{"title": "SWE", "summary": "Builder", "skills": {"Languages": "Python"}, "experience": [{"header": "SWE at Google", "bullets": ["Built APIs"]}], "projects": [{"header": "Bot", "bullets": ["Automated tasks"]}], "education": "UW"}',
                "VERDICT: PASS\n\nISSUES: none",
            ]
            mock_get_client.return_value = mock_client

            tailored, report = tailor_resume("Resume", job, profile)
            assert "Builder" in tailored
            assert report["status"] == "approved"
            assert report["attempts"] == 1
            assert mock_client.chat.call_count == 2

    def test_retries_on_validation_failure(self) -> None:
        job = {
            "title": "SWE",
            "site": "Google",
            "full_description": "Build things.",
        }
        profile = {
            "personal": {"full_name": "John"},
            "skills_boundary": {"languages": ["Python"]},
            "resume_facts": {"preserved_companies": ["Google"]},
        }
        with patch("applypilot.scoring.tailor.get_client") as mock_get_client:
            mock_client = MagicMock()
            # First: invalid JSON
            # Second: good JSON, then judge
            mock_client.chat.side_effect = [
                "not json",
                '{"title": "SWE", "summary": "Builder", "skills": {"Languages": "Python"}, "experience": [{"header": "SWE at Google", "bullets": ["Built APIs"]}], "projects": [{"header": "Bot", "bullets": ["Automated tasks"]}], "education": "UW"}',
                "VERDICT: PASS\n\nISSUES: none",
            ]
            mock_get_client.return_value = mock_client

            tailored, report = tailor_resume("Resume", job, profile, max_retries=2)
            assert report["attempts"] == 2
            assert report["status"] == "approved"

    def test_lenient_mode_skips_judge(self) -> None:
        job = {"title": "SWE", "site": "Co", "full_description": "Test"}
        profile = {
            "personal": {"full_name": "John"},
            "skills_boundary": {},
            "resume_facts": {},
        }
        with patch("applypilot.scoring.tailor.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.return_value = '{"title": "SWE", "summary": "Builder", "skills": {"Languages": "Python"}, "experience": [{"header": "SWE at Google", "bullets": ["Built APIs"]}], "projects": [{"header": "Bot", "bullets": ["Automated tasks"]}], "education": "UW"}'
            mock_get_client.return_value = mock_client

            tailored, report = tailor_resume("Resume", job, profile, validation_mode="lenient")
            assert report["status"] == "approved"
            assert report["judge"] == {"verdict": "SKIPPED", "passed": True, "issues": "none"}

    def test_exhausted_retries_returns_last(self) -> None:
        job = {"title": "SWE", "site": "Co", "full_description": "Test"}
        profile = {
            "personal": {"full_name": "John"},
            "skills_boundary": {},
            "resume_facts": {},
        }
        with patch("applypilot.scoring.tailor.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.chat.return_value = '{"title": "SWE", "summary": "Builder", "skills": {"Languages": "Python"}, "experience": [{"header": "SWE at Google", "bullets": ["Built APIs"]}], "projects": [{"header": "Bot", "bullets": ["Automated tasks"]}], "education": "UW"}'
            mock_get_client.return_value = mock_client

            tailored, report = tailor_resume("Resume", job, profile, max_retries=2)
            assert report["attempts"] == 3

    def test_judge_failure_retries_in_strict_mode(self) -> None:
        job = {"title": "SWE", "site": "Co", "full_description": "Test"}
        profile = {
            "personal": {"full_name": "John"},
            "skills_boundary": {},
            "resume_facts": {},
        }
        with patch("applypilot.scoring.tailor.get_client") as mock_get_client:
            mock_client = MagicMock()
            # Attempt 1: tailor JSON → judge FAIL
            # Attempt 2: tailor JSON → judge PASS
            mock_client.chat.side_effect = [
                '{"title": "SWE", "summary": "Builder", "skills": {"Languages": "Python"}, "experience": [{"header": "SWE at Google", "bullets": ["Built APIs"]}], "projects": [{"header": "Bot", "bullets": ["Automated tasks"]}], "education": "UW"}',
                "VERDICT: FAIL\n\nISSUES: too generic",
                '{"title": "SWE", "summary": "Builder of things", "skills": {"Languages": "Python"}, "experience": [{"header": "SWE at Google", "bullets": ["Built APIs"]}], "projects": [{"header": "Bot", "bullets": ["Automated tasks"]}], "education": "UW"}',
                "VERDICT: PASS\n\nISSUES: none",
            ]
            mock_get_client.return_value = mock_client

            tailored, report = tailor_resume("Resume", job, profile, max_retries=3, validation_mode="strict")
            assert report["status"] == "approved"
            assert mock_client.chat.call_count == 4


# ── run_tailoring ──────────────────────────────────────────────────────


class TestRunTailoring:
    def test_returns_zero_when_no_jobs(self) -> None:
        with patch("applypilot.scoring.tailor.get_connection") as mock_get_conn:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchall.return_value = []
            mock_get_conn.return_value = mock_conn

            with patch("applypilot.scoring.tailor.load_profile") as mock_profile:
                mock_profile.return_value = {
                    "personal": {"full_name": "John"},
                    "skills_boundary": {},
                    "resume_facts": {},
                }
                with patch("applypilot.scoring.tailor.RESUME_PATH") as mock_resume:
                    mock_resume.read_text.return_value = "Resume text"
                    result = run_tailoring()
                    assert result["approved"] == 0

    def test_processes_jobs(self, tmp_path) -> None:
        with patch("applypilot.scoring.tailor.get_connection") as mock_get_conn:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchall.return_value = [
                {
                    "title": "SWE",
                    "site": "Google",
                    "location": "Toronto",
                    "full_description": "Build things.",
                    "url": "https://example.com/1",
                    "fit_score": 85,
                    "tailored_resume_path": None,
                    "tailor_attempts": 0,
                }
            ]
            mock_get_conn.return_value = mock_conn

            with patch("applypilot.scoring.tailor.load_profile") as mock_profile:
                mock_profile.return_value = {
                    "personal": {"full_name": "John"},
                    "skills_boundary": {},
                    "resume_facts": {},
                }
                with patch("applypilot.scoring.tailor.RESUME_PATH") as mock_resume:
                    mock_resume.read_text.return_value = "Resume text"
                    with patch("applypilot.scoring.tailor.TAILORED_DIR", tmp_path):
                        with patch("applypilot.scoring.tailor.tailor_resume") as mock_tailor:
                            mock_tailor.return_value = (
                                "Tailored resume text",
                                {"status": "approved", "attempts": 1},
                            )
                            result = run_tailoring(min_score=70)
                            assert result["approved"] == 1
