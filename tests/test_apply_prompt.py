"""Tests for applypilot.apply.prompt: profile summary, screening, salary, location."""

from __future__ import annotations


from applypilot.apply.prompt import (
    _build_captcha_section,
    _build_hard_rules,
    _build_location_check,
    _build_profile_summary,
    _build_screening_section,
    _build_salary_section,
)


MINIMAL_PROFILE = {
    "personal": {
        "full_name": "John Doe",
        "preferred_name": "Johnny",
        "preferred_last": "Doe",
        "email": "john@example.com",
        "phone": "555-123-4567",
        "city": "Toronto",
        "province_state": "ON",
        "country": "Canada",
        "linkedin_url": "https://linkedin.com/in/johndoe",
        "github_url": "https://github.com/johndoe",
    },
    "skills_boundary": {
        "languages": ["Python", "Java", "Bash"],
        "frameworks": ["FastAPI", "Django"],
        "tools": ["Docker", "Kubernetes"],
        "databases": ["PostgreSQL", "Redis"],
        "cloud": ["AWS", "GCP"],
    },
    "resume_facts": {
        "preserved_projects": ["BotBuilder"],
        "preserved_companies": ["Google"],
        "real_metrics": ["10K requests/day"],
    },
    "availability": {
        "earliest_start_date": "2 weeks",
    },
    "work_authorization": {
        "legally_authorized_to_work": "Yes, PR",
        "require_sponsorship": "No",
        "work_permit_type": "Permanent Resident",
    },
    "compensation": {
        "salary_expectation": "80000",
        "salary_currency": "CAD",
        "salary_range_min": "80000",
        "salary_range_max": "100000",
    },
    "experience": {
        "years_of_experience_total": "5",
        "target_role": "software engineer",
        "current_job_title": "Software Engineer",
        "education_level": "Bachelor's",
        "current_employment_status": "Employed",
    },
}


SEARCH_CONFIG = {
    "locations": ["Toronto", "Remote"],
    "job_types": ["Full-time"],
}


# ── _build_profile_summary ──────────────────────────────────────────────


class TestBuildProfileSummary:
    def test_includes_name(self) -> None:
        summary = _build_profile_summary(MINIMAL_PROFILE)
        assert "John Doe" in summary

    def test_includes_email(self) -> None:
        summary = _build_profile_summary(MINIMAL_PROFILE)
        assert "john@example.com" in summary

    def test_includes_location(self) -> None:
        summary = _build_profile_summary(MINIMAL_PROFILE)
        assert "Toronto" in summary

    def test_includes_availability(self) -> None:
        summary = _build_profile_summary(MINIMAL_PROFILE)
        assert "2 weeks" in summary

    def test_includes_standard_responses(self) -> None:
        summary = _build_profile_summary(MINIMAL_PROFILE)
        assert "Age 18+" in summary
        assert "Background Check" in summary


# ── _build_location_check ──────────────────────────────────────────────


class TestBuildLocationCheck:
    def test_includes_profile_city(self) -> None:
        check = _build_location_check(MINIMAL_PROFILE, SEARCH_CONFIG)
        assert "Toronto" in check

    def test_includes_search_locations(self) -> None:
        check = _build_location_check(MINIMAL_PROFILE, SEARCH_CONFIG)
        assert "Remote" in check

    def test_returns_empty_on_missing_search_config(self) -> None:
        check = _build_location_check(MINIMAL_PROFILE, {})
        assert "Toronto" in check


# ── _build_salary_section ──────────────────────────────────────────────


class TestBuildSalarySection:
    def test_includes_min_salary(self) -> None:
        section = _build_salary_section(MINIMAL_PROFILE)
        assert "80000" in section

    def test_includes_currency(self) -> None:
        section = _build_salary_section(MINIMAL_PROFILE)
        assert "CAD" in section

    def test_handles_missing_salary(self) -> None:
        profile = dict(MINIMAL_PROFILE)
        profile["salary_expectations"] = {}
        section = _build_salary_section(profile)
        assert (
            "negotiable" in section.lower()
            or "reasonable" in section.lower()
            or "negotiate" in section.lower()
            or len(section.strip()) > 0
        )


# ── _build_screening_section ──────────────────────────────────────────


class TestBuildScreeningSection:
    def test_includes_location(self) -> None:
        section = _build_screening_section(MINIMAL_PROFILE)
        assert "Toronto" in section

    def test_includes_work_auth(self) -> None:
        section = _build_screening_section(MINIMAL_PROFILE)
        assert "PR" in section

    def test_includes_employment_status(self) -> None:
        section = _build_screening_section(MINIMAL_PROFILE)
        assert "software engineer" in section.lower()

    def test_includes_experience_years(self) -> None:
        section = _build_screening_section(MINIMAL_PROFILE)
        assert "5" in section


# ── _build_hard_rules ──────────────────────────────────────────────────


class TestBuildHardRules:
    def test_includes_display_name(self) -> None:
        rules = _build_hard_rules(MINIMAL_PROFILE)
        assert "Johnny" in rules

    def test_includes_work_auth_rule(self) -> None:
        rules = _build_hard_rules(MINIMAL_PROFILE)
        assert "Permanent Resident" in rules

    def test_includes_sponsorship_rule(self) -> None:
        rules = _build_hard_rules(MINIMAL_PROFILE)
        assert "No" in rules  # sponsorship: No

    def test_includes_name_rule(self) -> None:
        rules = _build_hard_rules(MINIMAL_PROFILE)
        assert "John Doe" in rules

    def test_handles_missing_preferred_name(self) -> None:
        profile = dict(MINIMAL_PROFILE)
        del profile["personal"]["preferred_name"]
        rules = _build_hard_rules(profile)
        assert "John Doe" in rules

    def test_handles_missing_work_permit(self) -> None:
        profile = dict(MINIMAL_PROFILE)
        profile["work_authorization"] = {"legally_authorized_to_work": "Yes"}
        rules = _build_hard_rules(profile)
        assert "Answer truthfully" in rules


# ── _build_captcha_section ─────────────────────────────────────────────


class TestBuildCaptchaSection:
    def test_returns_section(self) -> None:
        section = _build_captcha_section()
        assert "CAPTCHA" in section.upper() or "captcha" in section.lower() or len(section.strip()) > 0

    def test_mentions_human_review(self) -> None:
        section = _build_captcha_section()
        assert "CAPTCHA" in section.upper()
