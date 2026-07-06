"""Tests for applypilot.config: paths, platform detection, tier gating."""

from __future__ import annotations

import os
import platform
from pathlib import Path

import pytest

from applypilot import config


class TestGetChromePath:
    def test_env_var_override(self, monkeypatch, tmp_path) -> None:
        fake = tmp_path / "my-chrome"
        fake.touch()
        monkeypatch.setenv("CHROME_PATH", str(fake))
        assert config.get_chrome_path() == str(fake)

    def test_env_var_missing_file_fallback(self, monkeypatch) -> None:
        monkeypatch.setenv("CHROME_PATH", "/no/such/chrome")

        system = platform.system()
        if system == "Linux":
            monkeypatch.setattr(
                "applypilot.config.shutil.which",
                lambda name: str(Path("/usr/bin/google-chrome")) if name == "google-chrome" else None,
            )
        elif system == "Darwin":
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome").touch()
        else:
            monkeypatch.setattr(
                "applypilot.config.shutil.which",
                lambda name: (
                    str(Path("C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"))
                    if name == "google-chrome"
                    else None
                ),
            )

        path = config.get_chrome_path()
        assert path is not None and path != ""

    def test_raises_when_not_found(self, monkeypatch) -> None:
        monkeypatch.delenv("CHROME_PATH", raising=False)
        monkeypatch.setattr(
            "applypilot.config.shutil.which",
            lambda name: None,
        )
        # Touch candidate paths for Darwin/Windows so .exists() is reliable
        system = platform.system()
        if system == "Darwin":
            (Path("/Applications/Google Chrome.app/Contents/MacOS") / "Google Chrome").touch()
        elif system == "Windows":
            (Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Google/Chrome/Application").mkdir(
                parents=True, exist_ok=True
            )

        with pytest.raises(FileNotFoundError, match="Chrome/Chromium not found"):
            config.get_chrome_path()


class TestGetChromeUserData:
    def test_returns_platform_default(self) -> None:
        path = config.get_chrome_user_data()
        assert isinstance(path, Path)
        system = platform.system()
        if system == "Windows":
            assert "Chrome" in str(path)
        elif system == "Darwin":
            assert "Application Support" in str(path)
        else:
            assert ".config" in str(path)


class TestEnsureDirs:
    def test_creates_all_required_directories(self, tmp_path, monkeypatch) -> None:
        base = tmp_path / "ap"
        monkeypatch.setattr(config, "APP_DIR", base)
        monkeypatch.setattr(config, "TAILORED_DIR", base / "tailored_resumes")
        monkeypatch.setattr(config, "COVER_LETTER_DIR", base / "cover_letters")
        monkeypatch.setattr(config, "LOG_DIR", base / "logs")
        monkeypatch.setattr(config, "CHROME_WORKER_DIR", base / "chrome-workers")
        monkeypatch.setattr(config, "APPLY_WORKER_DIR", base / "apply-workers")
        config.ensure_dirs()

        for name in ["tailored_resumes", "cover_letters", "logs", "chrome-workers", "apply-workers"]:
            assert (base / name).is_dir()


class TestGetIntEnv:
    def test_parses_integer(self, monkeypatch) -> None:
        monkeypatch.setenv("TEST_INT_VAL", "42")
        assert config.get_int_env("TEST_INT_VAL", 0) == 42

    def test_returns_default_on_missing(self, monkeypatch) -> None:
        monkeypatch.delenv("TEST_INT_VAL", raising=False)
        assert config.get_int_env("TEST_INT_VAL", 99) == 99

    def test_returns_default_on_non_integer(self, monkeypatch) -> None:
        monkeypatch.setenv("TEST_INT_VAL", "abc")
        assert config.get_int_env("TEST_INT_VAL", 99) == 99

    def test_returns_default_on_empty_string(self, monkeypatch) -> None:
        monkeypatch.setenv("TEST_INT_VAL", "")
        assert config.get_int_env("TEST_INT_VAL", 99) == 99


class TestGetHumanReviewScore:
    def test_clamps_to_valid_range(self, monkeypatch) -> None:
        monkeypatch.setenv("HUMAN_REVIEW_SCORE", "0")
        assert config.get_human_review_score() == 1

        monkeypatch.setenv("HUMAN_REVIEW_SCORE", "150")
        assert config.get_human_review_score() == 100

    def test_uses_default_when_missing(self, monkeypatch) -> None:
        monkeypatch.delenv("HUMAN_REVIEW_SCORE", raising=False)
        assert config.get_human_review_score() == config.DEFAULTS["human_review_score"]


class TestGetApplyBackend:
    def test_returns_valid_backend(self, monkeypatch) -> None:
        monkeypatch.setenv("APPLYPILOT_APPLY_BACKEND", "opencode")
        assert config.get_apply_backend() == "opencode"

    def test_falls_back_to_default_on_invalid(self, monkeypatch) -> None:
        monkeypatch.setenv("APPLYPILOT_APPLY_BACKEND", "unknown_backend")
        assert config.get_apply_backend() == "claude"

    def test_case_insensitive(self, monkeypatch) -> None:
        monkeypatch.setenv("APPLYPILOT_APPLY_BACKEND", "CLAUDE  ")
        assert config.get_apply_backend() == "claude"


class TestTierDetection:
    def test_tier_1_no_llm_key(self, monkeypatch) -> None:
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("LLM_URL", raising=False)
        assert config.get_tier() == 1

    def test_tier_2_with_gemini_key(self, monkeypatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("LLM_URL", raising=False)
        monkeypatch.setattr(
            config.shutil,
            "which",
            lambda name: None,
        )
        assert config.get_tier() == 2

    def test_tier_3_with_all_deps(self, monkeypatch) -> None:
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setattr(
            config.shutil,
            "which",
            lambda name: "/usr/bin/claude" if name == "claude" else None,
        )
        monkeypatch.setattr(config, "get_chrome_path", lambda: "/usr/bin/google-chrome")
        assert config.get_tier() == 3


class TestConstants:
    def test_defaults_contain_expected_keys(self) -> None:
        expected_keys = {
            "min_score",
            "human_review_score",
            "max_apply_attempts",
            "max_tailor_attempts",
            "poll_interval",
            "apply_timeout",
            "viewport",
            "google_sheets_timeout_sec",
        }
        assert set(config.DEFAULTS.keys()) == expected_keys

    def test_apply_backends_tuple(self) -> None:
        assert config.APPLY_BACKENDS == ("claude", "opencode")

    def test_tier_labels(self) -> None:
        assert config.TIER_LABELS[1] == "Discovery"
        assert config.TIER_LABELS[3] == "Full Auto-Apply"


class TestPathConstants:
    def test_app_dir_uses_env_or_default(self, tmp_path, monkeypatch) -> None:
        import applypilot.config as cfg

        original_app = cfg.APP_DIR
        original_db = cfg.DB_PATH
        cfg.APP_DIR = tmp_path / "custom"
        cfg.DB_PATH = tmp_path / "custom" / "applypilot.db"
        try:
            assert cfg.DB_PATH == tmp_path / "custom" / "applypilot.db"
            assert (cfg.DB_PATH.parent / "test.db").parent == tmp_path / "custom"
        finally:
            cfg.APP_DIR = original_app
            cfg.DB_PATH = original_db


class TestBlockedSites:
    def test_load_blocked_sites_empty_default(self, tmp_path, monkeypatch) -> None:
        cfg_dir = tmp_path / "config"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(config, "CONFIG_DIR", cfg_dir)
        (cfg_dir / "sites.yaml").write_text("", encoding="utf-8")
        sites, patterns = config.load_blocked_sites()
        assert sites == set()
        assert patterns == []

    def test_load_blocked_sites_with_entries(self, tmp_path, monkeypatch) -> None:
        cfg_dir = tmp_path / "config"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(config, "CONFIG_DIR", cfg_dir)
        (cfg_dir / "sites.yaml").write_text(
            "blocked:\n  sites:\n    - Monster\n  url_patterns:\n    - /jobs/us/\n",
            encoding="utf-8",
        )
        sites, patterns = config.load_blocked_sites()
        assert "Monster" in sites
        assert "/jobs/us/" in patterns


class TestIsManualATS:
    def test_returns_false_for_none_url(self) -> None:
        assert config.is_manual_ats(None) is False
        assert config.is_manual_ats("") is False

    def test_matches_manual_ats_domain(self, tmp_path, monkeypatch) -> None:
        cfg_dir = tmp_path / "config"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(config, "CONFIG_DIR", cfg_dir)
        (cfg_dir / "sites.yaml").write_text(
            "manual_ats:\n  - 'lever'\n  - 'workday'\n",
            encoding="utf-8",
        )
        assert config.is_manual_ats("https://jobs.example.com/apply") is False
        assert config.is_manual_ats("https://lever.example.com/apply") is True
        assert config.is_manual_ats("https://workday.example.com/apply") is True
