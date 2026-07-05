"""Tests for applypilot.scoring.validator: banned words, fabrication, structure checks."""

from __future__ import annotations


from applypilot.scoring.validator import (
    BANNED_WORDS,
    FABRICATION_WATCHLIST,
    LLM_LEAK_PHRASES,
    REQUIRED_SECTIONS,
    sanitize_text,
    validate_cover_letter,
    validate_json_fields,
    validate_tailored_resume,
)


# ── Shared Fixtures ──────────────────────────────────────────────────────

MINIMAL_PROFILE = {
    "personal": {
        "full_name": "John Doe",
        "email": "john@example.com",
        "phone": "555-123-4567",
        "city": "Toronto",
        "province_state": "ON",
        "country": "Canada",
        "linkedin_url": "https://linkedin.com/in/johndoe",
        "github_url": "https://github.com/johndoe",
    },
    "skills_boundary": {
        "languages": ["Python", "Bash"],
        "frameworks": ["FastAPI", "Django"],
        "databases": ["PostgreSQL", "Redis"],
    },
    "resume_facts": {
        "preserved_companies": ["Acme Corp", "StartupXYZ"],
        "preserved_projects": ["BotBuilder", "CI-Pipeline"],
        "preserved_school": "University of Waterloo",
        "real_metrics": [],
    },
    "experience": {
        "years_of_experience_total": 5,
        "education_level": "Bachelor's",
        "target_role": "Software Engineer",
    },
}


class TestSanitizeText:
    def test_replaces_em_dash(self) -> None:
        assert "hello, world" == sanitize_text("hello \u2014 world")

    def test_replaces_en_dash(self) -> None:
        assert "a-b" == sanitize_text("a\u2013b")

    def test_replaces_smart_quotes(self) -> None:
        assert 'He said "hello"' == sanitize_text('He said \u201chello\u201d')

    def test_replaces_smart_single_quotes(self) -> None:
        assert "It's" == sanitize_text("It\u2019s")

    def test_strips_whitespace(self) -> None:
        assert "clean" == sanitize_text("  clean  ")


class TestValidateJsonFields:
    def test_passes_with_all_required_fields(self) -> None:
        data = {
            "title": "Software Engineer",
            "summary": "5 years building APIs",
            "skills": {"Languages": "Python"},
            "experience": [
                {"header": "Engineer at Acme Corp", "bullets": ["Built API"]},
                {"header": "Dev at StartupXYZ", "bullets": ["Shipped MVP"]},
            ],
            "projects": [{"header": "BotBuilder", "bullets": ["Automated"]}],
            "education": "University of Waterloo | BSc",
        }
        result = validate_json_fields(data, MINIMAL_PROFILE)
        assert result["passed"]
        assert not result["errors"]

    def test_fails_missing_required_fields(self) -> None:
        data = {
            "title": "Software Engineer",
            "summary": "5 years building APIs",
            "skills": {"Languages": "Python"},
            "experience": [],
            "projects": [],
            "education": "",
        }
        result = validate_json_fields(data, MINIMAL_PROFILE)
        assert not result["passed"]
        assert any("Missing required field: education" in e for e in result["errors"])

    def test_fails_banned_words_strict_mode(self) -> None:
        data = {
            "title": "Software Engineer",
            "summary": "Passionate about building APIs",
            "skills": {"Languages": "Python"},
            "experience": [
                {"header": "Engineer at Acme Corp", "bullets": ["Spearheaded the API project"]}
            ],
            "projects": [{"header": "BotBuilder", "bullets": ["Built"]}],
            "education": "University of Waterloo | BSc",
        }
        result = validate_json_fields(data, MINIMAL_PROFILE, mode="strict")
        assert not result["passed"]
        assert any("Banned words" in e for e in result["errors"])

    def test_warns_banned_words_normal_mode(self) -> None:
        data = {
            "title": "Software Engineer",
            "summary": "Passionate about building APIs",
            "skills": {"Languages": "Python"},
            "experience": [
                {"header": "Engineer at Acme Corp", "bullets": ["Built"]},
                {"header": "Dev at StartupXYZ", "bullets": ["Shipped"]},
            ],
            "projects": [{"header": "BotBuilder", "bullets": ["Built"]}],
            "education": "University of Waterloo | BSc",
        }
        result = validate_json_fields(data, MINIMAL_PROFILE, mode="normal")
        assert result["passed"]
        assert any("Banned words" in w for w in result["warnings"])

    def test_ignores_banned_words_lenient_mode(self) -> None:
        data = {
            "title": "Software Engineer",
            "summary": "Passionate about building APIs",
            "skills": {"Languages": "Python"},
            "experience": [
                {"header": "Engineer at Acme Corp", "bullets": ["Spearheaded"]},
                {"header": "Dev at StartupXYZ", "bullets": ["Shipped"]},
            ],
            "projects": [{"header": "BotBuilder", "bullets": ["Built"]}],
            "education": "University of Waterloo | BSc",
        }
        result = validate_json_fields(data, MINIMAL_PROFILE, mode="lenient")
        assert result["passed"]
        assert not result["errors"]
        assert not result["warnings"]

    def test_fails_fabricated_skills(self) -> None:
        data = {
            "title": "Software Engineer",
            "summary": "5 years building APIs",
            "skills": {"Languages": "Python, Rust, Go"},
            "experience": [{"header": "Engineer at Acme Corp", "bullets": ["Built"]}],
            "projects": [{"header": "BotBuilder", "bullets": ["Built"]}],
            "education": "University of Waterloo | BSc",
        }
        result = validate_json_fields(data, MINIMAL_PROFILE)
        assert not result["passed"]
        assert any("Fabricated skill" in e for e in result["errors"])

    def test_fails_missing_company(self) -> None:
        data = {
            "title": "Software Engineer",
            "summary": "5 years",
            "skills": {"Languages": "Python"},
            "experience": [{"header": "Engineer at Totally Different", "bullets": ["Built"]}],
            "projects": [{"header": "BotBuilder", "bullets": ["Built"]}],
            "education": "University of Waterloo | BSc",
        }
        result = validate_json_fields(data, MINIMAL_PROFILE)
        assert not result["passed"]
        assert any("Acme Corp" in e for e in result["errors"])

    def test_fails_missing_school(self) -> None:
        data = {
            "title": "Software Engineer",
            "summary": "5 years",
            "skills": {"Languages": "Python"},
            "experience": [{"header": "Engineer at Acme Corp", "bullets": ["Built"]}],
            "projects": [{"header": "BotBuilder", "bullets": ["Built"]}],
            "education": "MIT | PhD",
        }
        result = validate_json_fields(data, MINIMAL_PROFILE)
        assert not result["passed"]
        assert any("Education" in e for e in result["errors"])

    def test_fails_llm_self_talk(self) -> None:
        data = {
            "title": "Software Engineer",
            "summary": "5 years of building APIs",
            "skills": {"Languages": "Python"},
            "experience": [
                {"header": "Engineer at Acme Corp", "bullets": ["Here is the corrected version"]}
            ],
            "projects": [{"header": "BotBuilder", "bullets": ["Built"]}],
            "education": "University of Waterloo | BSc",
        }
        result = validate_json_fields(data, MINIMAL_PROFILE)
        assert not result["passed"]
        assert any("LLM self-talk" in e for e in result["errors"])


class TestValidateTailoredResume:
    def _make_valid_resume(self) -> str:
        return """\
SUMMARY
5 years building APIs and automation tools.

TECHNICAL SKILLS
Languages: Python, Bash
Frameworks: FastAPI
Databases: PostgreSQL

EXPERIENCE
Software Engineer at Acme Corp
Python | 2020-2024
- Built REST APIs serving 10K requests/day

Developer at StartupXYZ
Python | 2018-2020
- Shipped MVP for early adopters

PROJECTS
BotBuilder - Automated workflow tool
Python | 2023
- Automated repetitive tasks

EDUCATION
University of Waterloo | BSc Computer Science
"""

    def test_passes_with_all_sections(self) -> None:
        result = validate_tailored_resume(self._make_valid_resume(), MINIMAL_PROFILE)
        assert result["passed"]
        assert not result["errors"]

    def test_fails_missing_section(self) -> None:
        resume = self._make_valid_resume().replace("SUMMARY", "OVERVIEW").replace(
            "TECHNICAL SKILLS", ""
        )
        result = validate_tailored_resume(resume, MINIMAL_PROFILE)
        assert not result["passed"]
        assert any("TECHNICAL SKILLS" in e for e in result["errors"])

    def test_fails_banned_words(self) -> None:
        resume = self._make_valid_resume().replace("5 years", "Passionate and dedicated")
        result = validate_tailored_resume(resume, MINIMAL_PROFILE)
        assert not result["passed"]
        assert any("Banned words" in e for e in result["errors"])

    def test_warns_missing_name(self) -> None:
        resume = self._make_valid_resume().replace("John", "")
        # Name check is warning only
        result = validate_tailored_resume(resume, MINIMAL_PROFILE)
        assert any("Name" in w for w in result["warnings"])

    def test_fails_missing_company(self) -> None:
        resume = self._make_valid_resume().replace("Acme Corp", "Acme")
        result = validate_tailored_resume(resume, MINIMAL_PROFILE)
        assert not result["passed"]
        assert any("Acme Corp" in e for e in result["errors"])

    def test_fails_fabricated_skills(self) -> None:
        resume = self._make_valid_resume().replace("Bash", "Rust, Go")
        result = validate_tailored_resume(resume, MINIMAL_PROFILE)
        assert not result["passed"]
        assert any("FABRICATED" in e for e in result["errors"])

    def test_fails_em_dash(self) -> None:
        resume = self._make_valid_resume().replace("5 years", "5\u20147 years")
        result = validate_tailored_resume(resume, MINIMAL_PROFILE)
        assert not result["passed"]
        assert any("em dash" in e for e in result["errors"])

    def test_fails_duplicate_sections(self) -> None:
        resume = self._make_valid_resume() + "\n\nSUMMARY\nAnother summary.\n"
        result = validate_tailored_resume(resume, MINIMAL_PROFILE)
        assert not result["passed"]
        assert any("appears" in e and "summary" in e.lower() for e in result["errors"])

    def test_detects_new_skills_not_in_original(self) -> None:
        original = self._make_valid_resume().replace("Python, Bash", "Python")
        tailored = self._make_valid_resume()  # has Bash (which is in original too)
        # But let's add a brand new one
        tailored = tailored.replace("Python, Bash", "Python, Rust")
        result = validate_tailored_resume(tailored, MINIMAL_PROFILE, original_text=original)
        # Rust is in fabrication watchlist
        assert any("New tool/skill appeared" in w for w in result["warnings"])

    def test_fails_llm_self_talk(self) -> None:
        resume = self._make_valid_resume().replace("5 years", "I am at a loss for words")
        result = validate_tailored_resume(resume, MINIMAL_PROFILE)
        assert not result["passed"]
        assert any("LLM self-talk" in e for e in result["errors"])

    def test_fails_missing_school(self) -> None:
        resume = self._make_valid_resume().replace("University of Waterloo", "MIT")
        result = validate_tailored_resume(resume, MINIMAL_PROFILE)
        assert not result["passed"]
        assert any("Education" in e for e in result["errors"])


class TestValidateCoverLetter:
    def _make_valid_letter(self) -> str:
        return "Dear Hiring Manager,\n\nI am writing to apply for the Software Engineer position."

    def test_passes_clean_letter(self) -> None:
        result = validate_cover_letter(self._make_valid_letter())
        assert result["passed"]
        assert not result["errors"]

    def test_fails_no_dear_prefix(self) -> None:
        result = validate_cover_letter("Hello Hiring Manager,\n\nI want this job.")
        assert not result["passed"]
        assert any("Dear" in e for e in result["errors"])

    def test_fails_banned_words_strict(self) -> None:
        letter = "Dear Hiring Manager,\n\nI am passionate about this role."
        result = validate_cover_letter(letter, mode="strict")
        assert not result["passed"]
        assert any("Banned words" in e for e in result["errors"])

    def test_warns_banned_words_normal(self) -> None:
        letter = "Dear Hiring Manager,\n\nI am passionate about this role."
        result = validate_cover_letter(letter, mode="normal")
        assert result["passed"]
        assert any("Banned words" in w for w in result["warnings"])

    def test_ignores_banned_words_lenient(self) -> None:
        letter = "Dear Hiring Manager,\n\nI am passionate about this role."
        result = validate_cover_letter(letter, mode="lenient")
        assert result["passed"]
        assert not result["errors"]

    def test_fails_too_long_strict(self) -> None:
        words = " ".join(["word"] * 260)
        letter = f"Dear Hiring Manager,\n\n{words}"
        result = validate_cover_letter(letter, mode="strict")
        assert not result["passed"]
        assert any("Too long" in e for e in result["errors"])

    def test_warns_long_normal(self) -> None:
        words = " ".join(["word"] * 280)
        letter = f"Dear Hiring Manager,\n\n{words}"
        result = validate_cover_letter(letter, mode="normal")
        assert result["passed"]
        assert any("Long" in w for w in result["warnings"])

    def test_no_word_count_check_lenient(self) -> None:
        words = " ".join(["word"] * 400)
        letter = f"Dear Hiring Manager,\n\n{words}"
        result = validate_cover_letter(letter, mode="lenient")
        assert result["passed"]

    def test_fails_em_dash(self) -> None:
        letter = "Dear Hiring Manager,\n\nI have 5\u20147 years experience."
        result = validate_cover_letter(letter)
        assert not result["passed"]
        assert any("em dash" in e for e in result["errors"])

    def test_fails_llm_self_talk(self) -> None:
        letter = "Dear Hiring Manager,\n\nHere is the corrected version of my letter."
        result = validate_cover_letter(letter)
        assert not result["passed"]
        assert any("LLM self-talk" in e for e in result["errors"])


class TestConstants:
    def test_banned_words_not_empty(self) -> None:
        assert len(BANNED_WORDS) > 20

    def test_fabrication_watchlist_has_entries(self) -> None:
        assert "c#" in FABRICATION_WATCHLIST
        assert "rust" in FABRICATION_WATCHLIST
        assert "django" in FABRICATION_WATCHLIST

    def test_llm_leak_phrases_not_empty(self) -> None:
        assert len(LLM_LEAK_PHRASES) > 5
        assert "i am sorry" in LLM_LEAK_PHRASES

    def test_required_sections_complete(self) -> None:
        assert REQUIRED_SECTIONS == {"SUMMARY", "TECHNICAL SKILLS", "EXPERIENCE", "PROJECTS", "EDUCATION"}
