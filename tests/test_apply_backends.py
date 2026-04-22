from __future__ import annotations

from applypilot import config
from applypilot.apply import agent_backends


def test_build_opencode_config_includes_playwright_and_gmail() -> None:
    cfg = agent_backends.build_opencode_config(9222)

    assert cfg["$schema"] == "https://opencode.ai/config.json"
    assert cfg["mcp"]["playwright"]["type"] == "local"
    assert cfg["mcp"]["playwright"]["enabled"] is True
    assert cfg["mcp"]["playwright"]["command"][0] == "npx"
    assert "--cdp-endpoint=http://localhost:9222" in cfg["mcp"]["playwright"]["command"]
    assert cfg["mcp"]["gmail"]["command"] == ["npx", "-y", "@gongrzhe/server-gmail-autoauth-mcp"]
    assert cfg["permission"]["gmail_delete_email"] == "deny"


def test_build_agent_command_for_opencode_uses_one_shot_json_mode(tmp_path) -> None:
    cmd = agent_backends.build_agent_command(
        backend="opencode",
        model="anthropic/claude-sonnet-4-5",
        config_path=tmp_path / "opencode.json",
        prompt="Apply to this job",
    )

    assert cmd[:2] == ["opencode", "run"]
    assert "--format" in cmd and "json" in cmd
    assert "--dangerously-skip-permissions" in cmd
    assert cmd[-1] == "Apply to this job"


def test_build_agent_env_for_opencode_sets_custom_config(tmp_path) -> None:
    cfg_path = tmp_path / "runtime.json"
    env = agent_backends.build_agent_env("opencode", cfg_path)

    assert env["OPENCODE_CONFIG"] == str(cfg_path)


def test_render_manual_command_for_opencode_uses_opencode_config(tmp_path) -> None:
    command = agent_backends.render_manual_command(
        backend="opencode",
        model="anthropic/claude-sonnet-4-5",
        prompt_file=tmp_path / "prompt.txt",
        config_path=tmp_path / "runtime.json",
    )

    assert command.startswith("OPENCODE_CONFIG=")
    assert "opencode run --format json" in command
    assert "--dangerously-skip-permissions" in command


def test_get_tier_recognizes_opencode_backend(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(config, "load_env", lambda: None)
    monkeypatch.setattr(config.shutil, "which", lambda name: "/usr/bin/opencode" if name == "opencode" else None)
    monkeypatch.setattr(config, "get_chrome_path", lambda: "/usr/bin/google-chrome")

    assert config.get_tier() == 3
