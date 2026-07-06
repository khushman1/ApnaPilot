"""Tests for applypilot.config: YAML loading, environment, tier detection, score thresholds."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch


from applypilot.config import (
    DEFAULTS,
    APPLY_BACKENDS,
    get_apply_backend,
    get_human_review_score,
    get_int_env,
    get_tier,
    is_manual_ats,
    load_blocked_sites,
    load_blocked_sso,
    load_base_urls,
    load_search_config,
    load_sites_config,
    ensure_dirs,
)


# ── DEFAULTS ─────────────────────────────────────────────────────────────


class TestDefaults:
    def test_min_score_default(self) -> None:
        assert DEFAULTS["min_score"] == 70

    def test_human_review_score_default(self) -> None:
        assert DEFAULTS["human_review_score"] == 90

    def test_apply_backends(self) -> None:
        assert APPLY_BACKENDS == ("claude", "opencode")

    def test_viewport_default(self) -> None:
        assert "x" in DEFAULTS["viewport"]  # format is "WxH"


# ── get_int_env ─────────────────────────────────────────────────────────


class TestGetIntEnv:
    def test_returns_default_when_not_set(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            assert get_int_env("NONEXISTENT_VAR_XYZ", 42) == 42

    def test_returns_int_when_set(self) -> None:
        with patch.dict(os.environ, {"TEST_INT_VAR": "99"}):
            assert get_int_env("TEST_INT_VAR", 42) == 99

    def test_returns_default_on_empty_string(self) -> None:
        with patch.dict(os.environ, {"TEST_INT_VAR": ""}):
            assert get_int_env("TEST_INT_VAR", 42) == 42

    def test_returns_default_on_invalid_value(self) -> None:
        with patch.dict(os.environ, {"TEST_INT_VAR": "not_a_number"}):
            assert get_int_env("TEST_INT_VAR", 42) == 42


# ── get_human_review_score ──────────────────────────────────────────────


class TestGetHumanReviewScore:
    def test_returns_default(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            # Remove the var if set
            os.environ.pop("HUMAN_REVIEW_SCORE", None)
            assert get_human_review_score() == DEFAULTS["human_review_score"]

    def test_clamps_to_100(self) -> None:
        with patch.dict(os.environ, {"HUMAN_REVIEW_SCORE": "150"}):
            assert get_human_review_score() == 100

    def test_clamps_to_1(self) -> None:
        with patch.dict(os.environ, {"HUMAN_REVIEW_SCORE": "-10"}):
            assert get_human_review_score() == 1


# ── get_apply_backend ───────────────────────────────────────────────────


class TestGetApplyBackend:
    def test_returns_claude_default(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("APPLYPILOT_APPLY_BACKEND", None)
            assert get_apply_backend() == "claude"

    def test_returns_opencode_when_set(self) -> None:
        with patch.dict(os.environ, {"APPLYPILOT_APPLY_BACKEND": "opencode"}):
            assert get_apply_backend() == "opencode"

    def test_falls_back_on_invalid(self) -> None:
        with patch.dict(os.environ, {"APPLYPILOT_APPLY_BACKEND": "unknown_backend"}):
            assert get_apply_backend() == "claude"


# ── YAML Loading ─────────────────────────────────────────────────────────


class TestLoadSitesConfig:
    def test_loads_sites_yaml(self) -> None:
        config = load_sites_config()
        assert isinstance(config, dict)

    def test_has_manual_ats(self) -> None:
        config = load_sites_config()
        # May be empty in dev, but should be a list
        assert isinstance(config.get("manual_ats", []), list)

    def test_has_blocked(self) -> None:
        config = load_sites_config()
        assert "blocked" in config or config == {}


class TestIsManualAts:
    def test_returns_false_for_none(self) -> None:
        assert is_manual_ats(None) is False

    def test_returns_false_for_empty(self) -> None:
        assert is_manual_ats("") is False

    def test_returns_false_for_regular_url(self) -> None:
        assert is_manual_ats("https://boards.greenhouse.io/job/123") is False


class TestLoadBlockedSites:
    def test_returns_tuple(self) -> None:
        sites, patterns = load_blocked_sites()
        assert isinstance(sites, set)
        assert isinstance(patterns, list)


class TestLoadBlockedSso:
    def test_returns_list(self) -> None:
        domains = load_blocked_sso()
        assert isinstance(domains, list)


class TestLoadBaseUrls:
    def test_returns_dict(self) -> None:
        urls = load_base_urls()
        assert isinstance(urls, dict)


class TestLoadSearchConfig:
    def test_returns_dict(self) -> None:
        config = load_search_config()
        assert isinstance(config, dict)


# ── Tier Detection ──────────────────────────────────────────────────────


class TestGetTier:
    def test_tier_1_without_llm(self) -> None:
        env = dict(os.environ)
        for key in ("GEMINI_API_KEY", "OPENAI_API_KEY", "LLM_URL"):
            env.pop(key, None)
        with patch.dict(os.environ, env, clear=True):
            tier = get_tier()
            assert tier == 1

    def test_tier_2_with_llm(self) -> None:
        env = dict(os.environ)
        env["GEMINI_API_KEY"] = "test-key"
        with patch.dict(os.environ, env, clear=True):
            with patch("applypilot.config.get_chrome_path", side_effect=FileNotFoundError):
                with patch("shutil.which", return_value=None):
                    tier = get_tier()
                    assert tier == 2

    def test_tier_3_with_llm_and_backend(self) -> None:
        env = dict(os.environ)
        env["GEMINI_API_KEY"] = "test-key"
        with patch.dict(os.environ, env, clear=True):
            with patch("applypilot.config.get_chrome_path", return_value=Path("/usr/bin/chrome")):
                with patch("shutil.which", return_value="/usr/bin/claude"):
                    tier = get_tier()
                    assert tier == 3


# ── ensure_dirs ──────────────────────────────────────────────────────────


class TestEnsureDirs:
    def test_creates_directories(self, tmp_path: Path) -> None:
        from applypilot import config as cfg

        # Override paths to use tmp_path
        orig = cfg.APP_DIR
        cfg.APP_DIR = tmp_path / "applypilot"
        try:
            # Recompute derived dirs
            cfg.TAILORED_DIR = cfg.APP_DIR / "tailored_resumes"
            cfg.COVER_LETTER_DIR = cfg.APP_DIR / "cover_letters"
            cfg.LOG_DIR = cfg.APP_DIR / "logs"
            cfg.CHROME_WORKER_DIR = cfg.APP_DIR / "chrome-workers"
            cfg.APPLY_WORKER_DIR = cfg.APP_DIR / "apply-workers"

            ensure_dirs()
            assert cfg.APP_DIR.exists()
        finally:
            cfg.APP_DIR = orig
