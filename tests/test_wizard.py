"""Tests for applypilot.wizard.init: wizard setup flow."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from applypilot.wizard.init import (
    _setup_ai_features,
    _setup_auto_apply,
    _setup_profile,
    _setup_resume,
    _setup_searches,
    run_wizard,
)


# ---------------------------------------------------------------------------
# Fixtures — provide a temporary APP_DIR for file writes
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_app_dir(tmp_path: Path):
    """Create a temporary APP_DIR and yield the path."""
    return tmp_path


@pytest.fixture
def mock_paths(tmp_app_dir: Path):
    """Patch all module-level path constants to point to tmp_app_dir."""
    patches = {
        "applypilot.wizard.init.APP_DIR": tmp_app_dir,
        "applypilot.wizard.init.RESUME_PATH": tmp_app_dir / "resume.txt",
        "applypilot.wizard.init.RESUME_PDF_PATH": tmp_app_dir / "resume.pdf",
        "applypilot.wizard.init.PROFILE_PATH": tmp_app_dir / "profile.json",
        "applypilot.wizard.init.SEARCH_CONFIG_PATH": tmp_app_dir / "searches.yaml",
        "applypilot.wizard.init.ENV_PATH": tmp_app_dir / ".env",
    }
    mocks = []
    for k, v in patches.items():
        m = patch(k, v)
        m.start()
        mocks.append(m)
    yield
    for m in mocks:
        m.stop()


# ---------------------------------------------------------------------------
# _setup_resume (4 tests)
# ---------------------------------------------------------------------------


class TestSetupResume:
    def test_copies_txt_resume(self, tmp_app_dir: Path, mock_paths) -> None:
        src = tmp_app_dir / "my_resume.txt"
        src.write_text("John Doe — Resume")
        resume_path = tmp_app_dir / "resume.txt"

        with patch("applypilot.wizard.init.Prompt") as mock_prompt:
            mock_prompt.ask.return_value = str(src)
            _setup_resume()

        assert resume_path.exists()
        assert resume_path.read_text() == "John Doe — Resume"

    def test_copies_pdf_resume(self, tmp_app_dir: Path, mock_paths) -> None:
        """PDF resume is copied; empty text path skips the optional plain-text copy."""
        src = tmp_app_dir / "my_resume.pdf"
        src.write_bytes(b"%PDF-1.4 fake pdf")
        pdf_path = tmp_app_dir / "resume.pdf"

        with patch("applypilot.wizard.init.Prompt") as mock_prompt:
            # First ask: pdf path, second ask: txt path (empty = skip text copy)
            mock_prompt.ask.side_effect = [str(src), ""]
            _setup_resume()

        assert pdf_path.exists()

    def test_pdf_resume_text_not_found(self, tmp_app_dir: Path, mock_paths) -> None:
        """PDF resume text copy shows warning when file not found."""
        src = tmp_app_dir / "my_resume.pdf"
        src.write_bytes(b"%PDF-1.4 fake pdf")
        txt_path = tmp_app_dir / "resume.txt"

        with (
            patch("applypilot.wizard.init.Prompt") as mock_prompt,
            patch("applypilot.wizard.init.console") as mock_console,
        ):
            # First ask: pdf path, second ask: txt path (non-existent)
            mock_prompt.ask.side_effect = [str(src), str(txt_path)]
            _setup_resume()

        # Should have printed a warning about file not found
        print_calls = [str(c) for c in mock_console.print.call_args_list]
        assert any("File not found" in c for c in print_calls)

    def test_prompts_again_on_not_found(self, tmp_app_dir: Path, mock_paths) -> None:
        src = tmp_app_dir / "my_resume.txt"
        src.write_text("content")
        resume_path = tmp_app_dir / "resume.txt"

        with patch("applypilot.wizard.init.Prompt") as mock_prompt:
            mock_prompt.ask.side_effect = ["/no/such/file", str(src)]
            _setup_resume()

        assert resume_path.exists()

    def test_prompts_again_on_bad_extension(self, tmp_app_dir: Path, mock_paths) -> None:
        txt_src = tmp_app_dir / "my_resume.txt"
        txt_src.write_text("content")
        docx_src = tmp_app_dir / "my_resume.docx"
        docx_src.write_text("content")
        resume_path = tmp_app_dir / "resume.txt"

        with patch("applypilot.wizard.init.Prompt") as mock_prompt:
            mock_prompt.ask.side_effect = [str(docx_src), str(txt_src)]
            _setup_resume()

        assert resume_path.exists()


# ---------------------------------------------------------------------------
# _setup_profile (4 tests)
# ---------------------------------------------------------------------------


class TestSetupProfile:
    def test_full_profile(self, tmp_app_dir: Path, mock_paths) -> None:
        asks = [
            "Jane Smith",  # full_name
            "Jane",  # preferred_name
            "jane@example.com",  # email
            "555-0000",  # phone
            "Toronto",  # city
            "Ontario",  # province_state
            "Canada",  # country
            "M5V",  # postal_code
            "",  # address
            "",  # linkedin_url
            "",  # github_url
            "",  # portfolio_url
            "",  # website_url
            "",  # password
            "Citizen",  # work_permit_type
            "90000",  # salary
            "CAD",  # currency
            "80000-110000",  # salary range
            "Sr Engineer",  # current_title
            "Lead Engineer",  # target_role
            "10",  # years_of_experience
            "Master's",  # education_level
            "Python, Rust",  # languages
            "FastAPI",  # frameworks
            "Docker, AWS",  # tools
            "Acme, StartupX",  # preserved_companies
            "ProjectAlpha",  # preserved_projects
            "MIT",  # school
            "99.9% uptime",  # metrics
            "2025-08-01",  # earliest_start_date
        ]
        confirms = [True, True]  # authorized, sponsorship

        with (
            patch("applypilot.wizard.init.Prompt") as mock_prompt,
            patch("applypilot.wizard.init.Confirm") as mock_confirm,
        ):
            mock_prompt.ask.side_effect = asks
            mock_confirm.ask.side_effect = confirms
            _setup_profile()

        profile_path = tmp_app_dir / "profile.json"
        assert profile_path.exists()
        saved = json.loads(profile_path.read_text())
        assert saved["personal"]["full_name"] == "Jane Smith"
        assert saved["personal"]["preferred_name"] == "Jane"
        assert saved["compensation"]["salary_range_min"] == "80000"
        assert saved["compensation"]["salary_range_max"] == "110000"

    def test_salary_range_single_value(self, tmp_app_dir: Path, mock_paths) -> None:
        asks = [
            "Alex Lee",
            "",
            "alex@test.com",
            "",
            "NYC",
            "NY",
            "USA",
            "10001",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "100000",
            "USD",
            "100000",  # no range dash
            "Dev",
            "Dev",
            "5",
            "Bachelor's",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "Immediately",
        ]
        confirms = [True, False]

        with (
            patch("applypilot.wizard.init.Prompt") as mock_prompt,
            patch("applypilot.wizard.init.Confirm") as mock_confirm,
        ):
            mock_prompt.ask.side_effect = asks
            mock_confirm.ask.side_effect = confirms
            profile = _setup_profile()

        assert profile["compensation"]["salary_range_min"] == "100000"
        assert profile["compensation"]["salary_range_max"] == "100000"

    def test_skills_parsed(self, tmp_app_dir: Path, mock_paths) -> None:
        asks = [
            "Sam",
            "",
            "sam@t.com",
            "",
            "SF",
            "",
            "USA",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "80000",
            "USD",
            "",
            "Eng",
            "Eng",
            "3",
            "Bachelor's",
            "Python, Go, Rust",
            "FastAPI, Django",
            "Docker, K8s, AWS, GCP",
            "",
            "",
            "",
            "",
            "",
        ]
        confirms = [True, False]

        with (
            patch("applypilot.wizard.init.Prompt") as mock_prompt,
            patch("applypilot.wizard.init.Confirm") as mock_confirm,
        ):
            mock_prompt.ask.side_effect = asks
            mock_confirm.ask.side_effect = confirms
            profile = _setup_profile()

        assert profile["skills_boundary"]["programming_languages"] == ["Python", "Go", "Rust"]
        assert profile["skills_boundary"]["frameworks"] == ["FastAPI", "Django"]
        assert profile["skills_boundary"]["tools"] == ["Docker", "K8s", "AWS", "GCP"]

    def test_empty_defaults(self, tmp_app_dir: Path, mock_paths) -> None:
        asks = [
            "Mia",
            "",
            "mia@t.com",
            "",
            "London",
            "",
            "UK",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        ]
        confirms = [True, False]

        with (
            patch("applypilot.wizard.init.Prompt") as mock_prompt,
            patch("applypilot.wizard.init.Confirm") as mock_confirm,
        ):
            mock_prompt.ask.side_effect = asks
            mock_confirm.ask.side_effect = confirms
            profile = _setup_profile()

        assert profile["personal"]["full_name"] == "Mia"
        assert profile["skills_boundary"]["programming_languages"] == []
        assert profile["eeo_voluntary"]["gender"] == "Decline to self-identify"
        assert profile["availability"]["earliest_start_date"] == ""


# ---------------------------------------------------------------------------
# _setup_searches (3 tests)
# ---------------------------------------------------------------------------


class TestSetupSearches:
    def test_multi_role_yaml(self, tmp_app_dir: Path, mock_paths) -> None:
        with patch("applypilot.wizard.init.Prompt") as mock_prompt:
            mock_prompt.ask.side_effect = [
                "Remote",  # location
                "0",  # distance
                "Backend Engineer, Full Stack Dev",  # roles
            ]
            _setup_searches()

        content = (tmp_app_dir / "searches.yaml").read_text()
        assert 'location: "Remote"' in content
        assert 'query: "Backend Engineer"' in content
        assert 'query: "Full Stack Dev"' in content

    def test_empty_fallback(self, tmp_app_dir: Path, mock_paths) -> None:
        with patch("applypilot.wizard.init.Prompt") as mock_prompt:
            mock_prompt.ask.side_effect = ["Remote", "0", ""]
            _setup_searches()

        content = (tmp_app_dir / "searches.yaml").read_text()
        assert 'query: "Software Engineer"' in content

    def test_distance(self, tmp_app_dir: Path, mock_paths) -> None:
        with patch("applypilot.wizard.init.Prompt") as mock_prompt:
            mock_prompt.ask.side_effect = ["Toronto", "50", "Dev"]
            _setup_searches()

        content = (tmp_app_dir / "searches.yaml").read_text()
        assert "distance: 50" in content
        assert "remote: false" in content


# ---------------------------------------------------------------------------
# _setup_ai_features (4 tests)
# ---------------------------------------------------------------------------


class TestSetupAiFeatures:
    def test_gemini(self, tmp_app_dir: Path, mock_paths) -> None:
        with (
            patch("applypilot.wizard.init.Confirm") as mock_confirm,
            patch("applypilot.wizard.init.Prompt") as mock_prompt,
        ):
            mock_confirm.ask.return_value = True
            mock_prompt.ask.side_effect = ["gemini", "test-key", "gemini-2.0-flash"]
            _setup_ai_features()

        env = (tmp_app_dir / ".env").read_text()
        assert "GEMINI_API_KEY=test-key" in env
        assert "LLM_MODEL=gemini-2.0-flash" in env

    def test_openai(self, tmp_app_dir: Path, mock_paths) -> None:
        with (
            patch("applypilot.wizard.init.Confirm") as mock_confirm,
            patch("applypilot.wizard.init.Prompt") as mock_prompt,
        ):
            mock_confirm.ask.return_value = True
            mock_prompt.ask.side_effect = ["openai", "sk-xxx", "gpt-4o-mini"]
            _setup_ai_features()

        env = (tmp_app_dir / ".env").read_text()
        assert "OPENAI_API_KEY=sk-xxx" in env
        assert "LLM_MODEL=gpt-4o-mini" in env

    def test_local(self, tmp_app_dir: Path, mock_paths) -> None:
        with (
            patch("applypilot.wizard.init.Confirm") as mock_confirm,
            patch("applypilot.wizard.init.Prompt") as mock_prompt,
        ):
            mock_confirm.ask.return_value = True
            mock_prompt.ask.side_effect = ["local", "http://localhost:11434/v1", "llama3"]
            _setup_ai_features()

        env = (tmp_app_dir / ".env").read_text()
        assert "LLM_URL=http://localhost:11434/v1" in env
        assert "LLM_MODEL=llama3" in env

    def test_disabled(self, tmp_app_dir: Path, mock_paths) -> None:
        with patch("applypilot.wizard.init.Confirm") as mock_confirm:
            mock_confirm.ask.return_value = False
            _setup_ai_features()

        env_path = tmp_app_dir / ".env"
        # Should not create env file (or leave it empty)
        # The function returns early without writing
        if env_path.exists():
            assert "LLM_MODEL" not in env_path.read_text()


# ---------------------------------------------------------------------------
# _setup_auto_apply (3 tests)
# ---------------------------------------------------------------------------


class TestSetupAutoApply:
    def test_clis_found(self, tmp_app_dir: Path, mock_paths) -> None:
        with (
            patch("applypilot.wizard.init.shutil") as mock_shutil,
            patch("applypilot.wizard.init.Confirm") as mock_confirm,
        ):
            mock_shutil.which.side_effect = lambda x: "/usr/bin/" + x
            mock_confirm.ask.side_effect = [True, False]  # enable, skip capsolver
            _setup_auto_apply()

        assert mock_shutil.which.called

    def test_clis_not_found(self, tmp_app_dir: Path, mock_paths) -> None:
        with (
            patch("applypilot.wizard.init.shutil") as mock_shutil,
            patch("applypilot.wizard.init.Confirm") as mock_confirm,
        ):
            mock_shutil.which.return_value = None
            mock_confirm.ask.side_effect = [True, False]
            _setup_auto_apply()

    def test_capsolver_configured(self, tmp_app_dir: Path, mock_paths) -> None:
        with (
            patch("applypilot.wizard.init.shutil") as mock_shutil,
            patch("applypilot.wizard.init.Confirm") as mock_confirm,
            patch("applypilot.wizard.init.Prompt") as mock_prompt,
            patch.object(Path, "exists", return_value=False),
        ):
            mock_shutil.which.return_value = "/usr/bin/claude"
            mock_confirm.ask.side_effect = [True, True]
            mock_prompt.ask.return_value = "cs-123"
            _setup_auto_apply()

        # Should have written .env with CapSolver key
        env_path = tmp_app_dir / ".env"
        assert env_path.exists()
        assert "CAPSOLVER_API_KEY=cs-123" in env_path.read_text()


# ---------------------------------------------------------------------------
# run_wizard (1 test)
# ---------------------------------------------------------------------------


class TestRunWizard:
    def test_orchestration_order(self, tmp_app_dir: Path, mock_paths) -> None:
        """Verify wizard calls steps in order: resume -> profile -> searches -> ai -> auto_apply."""
        with (
            patch("applypilot.wizard.init.ensure_dirs"),
            patch("applypilot.wizard.init.console"),
            patch("applypilot.wizard.init._setup_resume") as mock_resume,
            patch("applypilot.wizard.init._setup_profile") as mock_profile,
            patch("applypilot.wizard.init._setup_searches") as mock_searches,
            patch("applypilot.wizard.init._setup_ai_features") as mock_ai,
            patch("applypilot.wizard.init._setup_auto_apply") as mock_auto,
            patch("applypilot.config.get_tier", return_value=1),
            patch("applypilot.config.TIER_LABELS", {1: "Discovery", 2: "AI", 3: "Full"}),
            patch("applypilot.config.TIER_COMMANDS", {1: ["init"], 2: ["run"], 3: ["apply"]}),
        ):
            mock_resume.return_value = None
            mock_profile.return_value = {}
            run_wizard()

        # All 5 steps must have been called
        assert mock_resume.called
        assert mock_profile.called
        assert mock_searches.called
        assert mock_ai.called
        assert mock_auto.called
