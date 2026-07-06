"""Tests for applypilot.scoring.tailor: JSON extraction, resume assembly, prompts."""

from __future__ import annotations

import pytest

from applypilot.scoring.tailor import (
    assemble_resume_text,
    extract_json,
    _build_tailor_prompt,
    _build_judge_prompt,
)

MINIMAL_PROFILE = {
    "personal": {
        "full_name": "John Doe",
        "email": "john@example.com",
        "phone": "555-123-4567",
        "city": "Toronto",
        "linkedin_url": "https://linkedin.com/in/johndoe",
        "github_url": "https://github.com/johndoe",
    },
    "skills_boundary": {
        "languages": ["Python", "Bash"],
        "frameworks": ["FastAPI", "Django"],
        "databases": ["PostgreSQL", "Redis"],
        "tools": ["Docker", "GitHub Actions"],
    },
    "resume_facts": {
        "preserved_companies": ["Acme Corp"],
        "preserved_projects": ["BotBuilder"],
        "preserved_school": "University of Waterloo",
        "real_metrics": ["10K requests/day"],
    },
    "experience": {
        "education_level": "Bachelor's",
    },
}


class TestExtractJson:
    def test_direct_parse(self) -> None:
        data = extract_json('{"key": "value"}')
        assert data == {"key": "value"}

    def test_direct_parse_nested(self) -> None:
        data = extract_json('{"skills": {"Languages": "Python"}, "title": "Engineer"}')
        assert data["skills"]["Languages"] == "Python"
        assert data["title"] == "Engineer"

    def test_markdown_json_fences(self) -> None:
        raw = '```json\n{"key": "value"}\n```'
        data = extract_json(raw)
        assert data == {"key": "value"}

    def test_markdown_fences_no_lang(self) -> None:
        raw = '```\n{"key": "value"}\n```'
        data = extract_json(raw)
        assert data == {"key": "value"}

    def test_find_outermost_braces(self) -> None:
        raw = 'Here is your JSON: {"title": "Engineer", "summary": "Good"} plus extra text'
        data = extract_json(raw)
        assert data["title"] == "Engineer"

    def test_raises_on_invalid_json(self) -> None:
        with pytest.raises(ValueError, match="No valid JSON found"):
            extract_json("no json here at all")

    def test_raises_on_mismatched_braces(self) -> None:
        with pytest.raises(ValueError, match="No valid JSON found"):
            extract_json("just text {")

    def test_handles_multiple_fences(self) -> None:
        raw = '```json\n{"wrong": "data"}\n```\n\n```json\n{"right": "data"}\n```'
        data = extract_json(raw)
        # extract_json returns the first valid JSON found
        assert data == {"wrong": "data"}

    def test_strips_whitespace(self) -> None:
        data = extract_json('  \n  {"key": "value"}  \n  ')
        assert data == {"key": "value"}


class TestAssembleResumeText:
    def test_produces_formatted_output(self) -> None:
        data = {
            "title": "Senior Software Engineer",
            "summary": "5 years building APIs and automation tools",
            "skills": {"Languages": "Python, Bash", "Databases": "PostgreSQL"},
            "experience": [
                {
                    "header": "Software Engineer at Acme Corp",
                    "subtitle": "Python | 2020-2024",
                    "bullets": ["Built REST APIs", "Deployed to AWS"],
                }
            ],
            "projects": [
                {
                    "header": "BotBuilder",
                    "subtitle": "Python | 2023",
                    "bullets": ["Automated workflows"],
                }
            ],
            "education": "University of Waterloo | BSc",
        }
        text = assemble_resume_text(data, MINIMAL_PROFILE)

        # Check header injected from profile
        assert "John Doe" in text
        assert "john@example.com" in text
        assert "555-123-4567" in text

        # Check sections present
        assert "SUMMARY" in text
        assert "TECHNICAL SKILLS" in text
        assert "EXPERIENCE" in text
        assert "PROJECTS" in text
        assert "EDUCATION" in text

        # Check content
        assert "Built REST APIs" in text
        assert "Senior Software Engineer" in text
        assert "University of Waterloo" in text

    def test_sanitizes_em_dashes(self) -> None:
        data = {
            "title": "Senior\u2014Software Engineer",
            "summary": "5\u20147 years experience",
            "skills": {"Languages": "Python\u2013Bash"},
            "experience": [{"header": "Engineer at Acme Corp", "bullets": ["Built\u2014deployed"]}],
            "projects": [],
            "education": "University of Waterloo",
        }
        text = assemble_resume_text(data, MINIMAL_PROFILE)
        assert "\u2014" not in text
        assert "\u2013" not in text

    def test_handles_empty_contact_info(self) -> None:
        profile = {
            "personal": {"full_name": "Jane Doe"},
            "skills_boundary": {},
            "resume_facts": {"preserved_school": "MIT"},
            "experience": {},
        }
        data = {
            "title": "Engineer",
            "summary": "Summary here",
            "skills": {},
            "experience": [],
            "projects": [],
            "education": "MIT",
        }
        text = assemble_resume_text(data, profile)
        assert "Jane Doe" in text
        assert "SUMMARY" in text
        assert "Engineer" in text


class TestBuildTailorPrompt:
    def test_includes_skills_boundary(self) -> None:
        prompt = _build_tailor_prompt(MINIMAL_PROFILE)
        assert "Python" in prompt
        assert "FastAPI" in prompt
        assert "PostgreSQL" in prompt

    def test_includes_preserved_companies(self) -> None:
        prompt = _build_tailor_prompt(MINIMAL_PROFILE)
        assert "Acme Corp" in prompt

    def test_includes_preserved_projects(self) -> None:
        prompt = _build_tailor_prompt(MINIMAL_PROFILE)
        assert "BotBuilder" in prompt

    def test_includes_banned_words_list(self) -> None:
        prompt = _build_tailor_prompt(MINIMAL_PROFILE)
        assert "passionate" in prompt
        assert "spearheaded" in prompt

    def test_includes_school(self) -> None:
        prompt = _build_tailor_prompt(MINIMAL_PROFILE)
        assert "University of Waterloo" in prompt

    def test_includes_json_template(self) -> None:
        prompt = _build_tailor_prompt(MINIMAL_PROFILE)
        assert '"title"' in prompt
        assert '"summary"' in prompt
        assert '"skills"' in prompt
        assert '"experience"' in prompt
        assert '"projects"' in prompt
        assert '"education"' in prompt


class TestBuildJudgePrompt:
    def test_includes_allowed_skills(self) -> None:
        prompt = _build_judge_prompt(MINIMAL_PROFILE)
        assert "Python" in prompt
        assert "Bash" in prompt

    def test_includes_real_metrics(self) -> None:
        prompt = _build_judge_prompt(MINIMAL_PROFILE)
        assert "10K requests/day" in prompt

    def test_includes_fabrication_rules(self) -> None:
        prompt = _build_judge_prompt(MINIMAL_PROFILE)
        assert "FABRICATION" in prompt.upper()
        assert "VERDICT" in prompt
