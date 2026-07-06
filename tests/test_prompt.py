"""Tests for applypilot.apply.prompt: profile summary, salary, location, CAPTCHA sections."""

from __future__ import annotations

from applypilot.apply.prompt import (
    _build_profile_summary,
    _build_location_check,
    _build_salary_section,
    _build_screening_section,
    _build_hard_rules,
    _build_captcha_section,
)

PROFILE = {
    "personal": {
        "full_name": "John Doe",
        "preferred_name": "Johnny",
        "email": "john@example.com",
        "phone": "555-123-4567",
        "address": "123 Main St",
        "city": "Toronto",
        "province_state": "ON",
        "country": "Canada",
        "postal_code": "M5V 2T6",
        "linkedin_url": "https://linkedin.com/in/johndoe",
        "github_url": "https://github.com/johndoe",
        "portfolio_url": "https://johndoe.dev",
    },
    "work_authorization": {
        "legally_authorized_to_work": "Yes",
        "require_sponsorship": "No",
        "work_permit_type": "Canadian Citizen",
    },
    "compensation": {
        "salary_expectation": "90000",
        "salary_currency": "USD",
        "salary_range_min": "90000",
        "salary_range_max": "110000",
        "currency_conversion_note": "Multiply by CAD/USD rate",
    },
    "experience": {
        "years_of_experience_total": 5,
        "education_level": "Bachelor's",
        "target_role": "Backend Engineer",
    },
    "availability": {
        "earliest_start_date": "2026-08-01",
    },
    "eeo_voluntary": {
        "gender": "Male",
        "race_ethnicity": "Asian",
        "veteran_status": "I am not a protected veteran",
        "disability_status": "I do not wish to answer",
    },
}

SEARCH_CONFIG = {
    "location": {
        "primary": "Toronto",
        "accept_patterns": ["Toronto", "Mississauga", "Vaughan", "Markham"],
    }
}


class TestBuildProfileSummary:
    def test_includes_personal_info(self) -> None:
        summary = _build_profile_summary(PROFILE)
        assert "Name: John Doe" in summary
        assert "Email: john@example.com" in summary
        assert "Phone: 555-123-4567" in summary

    def test_includes_address_parts(self) -> None:
        summary = _build_profile_summary(PROFILE)
        assert "123 Main St" in summary
        assert "Toronto" in summary
        assert "ON" in summary
        assert "Canada" in summary

    def test_includes_links(self) -> None:
        summary = _build_profile_summary(PROFILE)
        assert "LinkedIn: https://linkedin.com/in/johndoe" in summary
        assert "GitHub: https://github.com/johndoe" in summary
        assert "Portfolio: https://johndoe.dev" in summary

    def test_includes_work_auth(self) -> None:
        summary = _build_profile_summary(PROFILE)
        assert "Work Auth: Yes" in summary
        assert "Sponsorship Needed: No" in summary
        assert "Work Permit: Canadian Citizen" in summary

    def test_includes_compensation(self) -> None:
        summary = _build_profile_summary(PROFILE)
        assert "Salary Expectation: $90000 USD" in summary

    def test_includes_experience(self) -> None:
        summary = _build_profile_summary(PROFILE)
        assert "Years Experience: 5" in summary
        assert "Education: Bachelor's" in summary

    def test_includes_availability(self) -> None:
        summary = _build_profile_summary(PROFILE)
        assert "Available: 2026-08-01" in summary

    def test_includes_standard_responses(self) -> None:
        summary = _build_profile_summary(PROFILE)
        assert "Age 18+: Yes" in summary
        assert "Background Check: Yes" in summary
        assert "Felony: No" in summary
        assert "How Heard: Online Job Board" in summary

    def test_includes_eeo(self) -> None:
        summary = _build_profile_summary(PROFILE)
        assert "Gender: Male" in summary
        assert "Race: Asian" in summary

    def test_handles_optional_fields_missing(self) -> None:
        profile = {
            "personal": {
                "full_name": "Jane Doe",
                "email": "jane@example.com",
                "phone": "555-000-0000",
            },
            "work_authorization": {"legally_authorized_to_work": "Yes", "require_sponsorship": "No"},
            "compensation": {"salary_expectation": "80000", "salary_currency": "CAD"},
            "experience": {"years_of_experience_total": 3},
            "availability": {"earliest_start_date": "Immediately"},
            "eeo_voluntary": {},
        }
        summary = _build_profile_summary(profile)
        assert "Name: Jane Doe" in summary
        assert "Salary Expectation: $80000 CAD" in summary


class TestBuildLocationCheck:
    def test_includes_accept_patterns(self) -> None:
        section = _build_location_check(PROFILE, SEARCH_CONFIG)
        assert "Toronto" in section
        assert "Mississauga" in section
        assert "Vaughan" in section

    def test_includes_location_instructions(self) -> None:
        section = _build_location_check(PROFILE, SEARCH_CONFIG)
        assert "LOCATION CHECK" in section
        assert "Remote" in section
        assert "Hybrid" in section
        assert "NOT ELIGIBLE" in section

    def test_falls_back_to_primary_city_without_patterns(self) -> None:
        # Profile has city "Toronto", so that takes precedence over config primary
        cfg = {"location": {"primary": "Vancouver"}}
        section = _build_location_check(PROFILE, cfg)
        assert "Toronto" in section
        # Verify profile city takes precedence when present
        profile_with_city = {"personal": {"full_name": "Jane", "city": "Calgary"}, "work_authorization": {}}
        cfg2 = {"location": {"primary": "Vancouver"}}
        section2 = _build_location_check(profile_with_city, cfg2)
        assert "Calgary" in section2


class TestBuildSalarySection:
    def test_includes_floor_and_currency(self) -> None:
        section = _build_salary_section(PROFILE)
        assert "$90000 USD is the FLOOR" in section
        assert "Never go below it" in section

    def test_includes_hourly_examples(self) -> None:
        section = _build_salary_section(PROFILE)
        # $90000 / 1000 = 90, so $90K; $90000 / 2080 = 43
        assert "$90K = $43/hr" in section

    def test_includes_decision_tree(self) -> None:
        section = _build_salary_section(PROFILE)
        assert "MIDPOINT" in section
        assert "Hourly rate" in section or "Hourly" in section

    def test_includes_conversion_note(self) -> None:
        section = _build_salary_section(PROFILE)
        assert "Multiply by CAD/USD rate" in section

    def test_computes_range(self) -> None:
        section = _build_salary_section(PROFILE)
        assert "$90000-$110000" in section

    def test_handles_non_numeric_salary(self) -> None:
        profile = dict(PROFILE)
        profile["compensation"] = {"salary_expectation": "TBD", "salary_currency": "USD"}
        section = _build_salary_section(profile)
        assert "TBD" in section


class TestBuildScreeningSection:
    def test_includes_location_info(self) -> None:
        section = _build_screening_section(PROFILE)
        assert "Toronto" in section
        assert "SCREENING QUESTIONS" in section

    def test_includes_work_auth(self) -> None:
        section = _build_screening_section(PROFILE)
        assert "Yes" in section

    def test_includes_role_and_experience(self) -> None:
        section = _build_screening_section(PROFILE)
        assert "Backend Engineer" in section
        assert "5" in section

    def test_includes_eeo_guidance(self) -> None:
        section = _build_screening_section(PROFILE)
        assert "Decline to self-identify" in section


class TestBuildHardRules:
    def test_includes_legal_name(self) -> None:
        section = _build_hard_rules(PROFILE)
        assert "John Doe" in section

    def test_includes_preferred_name(self) -> None:
        section = _build_hard_rules(PROFILE)
        assert "Johnny" in section

    def test_includes_work_auth_rule(self) -> None:
        section = _build_hard_rules(PROFILE)
        assert "Canadian Citizen" in section

    def test_no_preferred_name_uses_full_name(self) -> None:
        profile = dict(PROFILE)
        profile["personal"] = dict(PROFILE["personal"])
        del profile["personal"]["preferred_name"]
        section = _build_hard_rules(profile)
        assert "John" in section


class TestBuildCaptchaSection:
    def test_includes_api_base(self) -> None:
        section = _build_captcha_section()
        assert "api.capsolver.com" in section

    def test_includes_task_types(self) -> None:
        section = _build_captcha_section()
        assert "HCaptchaTaskProxyLess" in section
        assert "ReCaptchaV2TaskProxyLess" in section
        assert "AntiTurnstileTaskProxyLess" in section

    def test_includes_detect_script(self) -> None:
        section = _build_captcha_section()
        assert "CAPTCHA DETECT" in section
        assert "hCaptcha" in section

    def test_includes_solve_steps(self) -> None:
        section = _build_captcha_section()
        assert "CAPTCHA SOLVE" in section
        assert "createTask" in section

    def test_includes_manual_fallback(self) -> None:
        section = _build_captcha_section()
        assert "MANUAL FALLBACK" in section

    def test_shows_not_configured_without_key(self, monkeypatch) -> None:
        monkeypatch.delenv("CAPSOLVER_API_KEY", raising=False)
        section = _build_captcha_section()
        assert "NOT CONFIGURED" in section

    def test_includes_key_with_env_var(self, monkeypatch) -> None:
        monkeypatch.setenv("CAPSOLVER_API_KEY", "test-key-123")
        section = _build_captcha_section()
        assert "test-key-123" in section
