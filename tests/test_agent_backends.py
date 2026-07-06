"""Tests for applypilot.apply.agent_backends: config building, commands, backends."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from applypilot.apply.agent_backends import (
    DEFAULT_APPLY_BACKEND,
    DEFAULT_CLAUDE_MODEL,
    DEFAULT_OPENCODE_MODEL,
    any_apply_backend_available,
    backend_available,
    backend_binary,
    backend_label,
    build_agent_command,
    build_agent_env,
    build_backend_config,
    build_claude_mcp_config,
    build_opencode_config,
    config_filename,
    get_claude_disallowed_tools,
    get_default_model,
    get_opencode_permission_policy,
    normalize_backend,
    render_manual_command,
    write_backend_config,
)


# ── normalize_backend ────────────────────────────────────────────────────


class TestNormalizeBackend:
    def test_normalizes_claude(self) -> None:
        assert normalize_backend("Claude") == "claude"

    def test_normalizes_opencode(self) -> None:
        assert normalize_backend("OpenCode") == "opencode"

    def test_defaults_to_claude_for_unknown(self) -> None:
        assert normalize_backend("unknown") == DEFAULT_APPLY_BACKEND

    def test_handles_none(self) -> None:
        assert normalize_backend(None) == DEFAULT_APPLY_BACKEND

    def test_strips_whitespace(self) -> None:
        assert normalize_backend("  claude  ") == "claude"


# ── backend helpers ──────────────────────────────────────────────────────


class TestBackendHelpers:
    def test_backend_binary_claude(self) -> None:
        assert backend_binary("claude") == "claude"

    def test_backend_binary_opencode(self) -> None:
        assert backend_binary("opencode") == "opencode"

    def test_backend_label_claude(self) -> None:
        assert backend_label("claude") == "Claude Code"

    def test_backend_label_opencode(self) -> None:
        assert backend_label("opencode") == "OpenCode"

    def test_default_model_claude(self) -> None:
        assert get_default_model("claude") == DEFAULT_CLAUDE_MODEL

    def test_default_model_opencode(self) -> None:
        assert get_default_model("opencode") == DEFAULT_OPENCODE_MODEL


# ── Permission helpers ───────────────────────────────────────────────────


class TestPermissionHelpers:
    def test_opencode_permission_policy(self) -> None:
        policy = get_opencode_permission_policy()
        assert "gmail_draft_email" in policy
        assert policy["gmail_draft_email"] == "deny"
        assert len(policy) > 5  # many gmail tools

    def test_claude_disallowed_tools(self) -> None:
        tools = get_claude_disallowed_tools()
        assert "mcp__gmail__draft_email" in tools
        assert "," in tools


# ── Claude MCP config ───────────────────────────────────────────────────


class TestBuildClaudeMcpConfig:
    def test_contains_playwright_server(self) -> None:
        config = build_claude_mcp_config(9222)
        assert "playwright" in config["mcpServers"]

    def test_playwright_cdp_endpoint(self) -> None:
        config = build_claude_mcp_config(9222)
        args = config["mcpServers"]["playwright"]["args"]
        assert "--cdp-endpoint=http://localhost:9222" in args

    def test_contains_gmail_server(self) -> None:
        config = build_claude_mcp_config(9222)
        assert "gmail" in config["mcpServers"]

    def test_viewport_size(self) -> None:
        config = build_claude_mcp_config(9222)
        args = config["mcpServers"]["playwright"]["args"]
        assert any("viewport-size" in arg for arg in args)


# ── OpenCode config ──────────────────────────────────────────────────────


class TestBuildOpenCodeConfig:
    def test_contains_schema(self) -> None:
        config = build_opencode_config(9333)
        assert "$schema" in config

    def test_playwright_local(self) -> None:
        config = build_opencode_config(9333)
        pw = config["mcp"]["playwright"]
        assert pw["type"] == "local"
        assert pw["enabled"] is True
        assert "--cdp-endpoint=http://localhost:9333" in pw["command"]

    def test_contains_permission(self) -> None:
        config = build_opencode_config(9333)
        assert "permission" in config
        assert "gmail_draft_email" in config["permission"]


# ── build_backend_config ─────────────────────────────────────────────────


class TestBuildBackendConfig:
    def test_builds_claude_config(self) -> None:
        config = build_backend_config("claude", 9222)
        assert "mcpServers" in config

    def test_builds_opencode_config(self) -> None:
        config = build_backend_config("opencode", 9333)
        assert "$schema" in config


# ── config_filename ──────────────────────────────────────────────────────


class TestConfigFilename:
    def test_claude_filename(self) -> None:
        assert config_filename("claude", 1) == ".mcp-apply-1.json"

    def test_opencode_filename(self) -> None:
        assert config_filename("opencode", 3) == ".opencode-apply-3.json"

    def test_worker_id_isolation(self) -> None:
        f1 = config_filename("claude", 1)
        f2 = config_filename("claude", 2)
        assert f1 != f2


# ── build_agent_command ──────────────────────────────────────────────────


class TestBuildAgentCommand:
    def test_claude_command(self) -> None:
        cmd = build_agent_command("claude", "sonnet", Path("/tmp/config.json"), "prompt")
        assert cmd[0] == "claude"
        assert "--model" in cmd
        assert "sonnet" in cmd
        assert "--mcp-config" in cmd
        assert "/tmp/config.json" in cmd
        assert "--disallowedTools" in cmd

    def test_opencode_command(self) -> None:
        cmd = build_agent_command("opencode", "anthropic/claude-sonnet-4-5", Path("/tmp/config.json"), "prompt")
        assert cmd[0] == "opencode"
        assert "--format" in cmd
        assert "json" in cmd
        assert "--model" in cmd
        assert "--dangerously-skip-permissions" in cmd

    def test_opencode_command_includes_prompt(self) -> None:
        cmd = build_agent_command("opencode", "test", Path("/tmp/c.json"), "my prompt")
        assert "my prompt" in cmd


# ── build_agent_env ──────────────────────────────────────────────────────


class TestBuildAgentEnv:
    def test_claude_env_cleans_claude_vars(self) -> None:
        with patch("os.environ", {"PATH": "/usr/bin", "CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "test"}):
            env = build_agent_env("claude", Path("/tmp/c.json"))
            assert "CLAUDECODE" not in env
            assert "CLAUDE_CODE_ENTRYPOINT" not in env
            assert "PATH" in env

    def test_opencode_env_sets_config(self) -> None:
        with patch("os.environ", {"PATH": "/usr/bin"}):
            env = build_agent_env("opencode", Path("/tmp/my-config.json"))
            assert env["OPENCODE_CONFIG"] == "/tmp/my-config.json"


# ── render_manual_command ────────────────────────────────────────────────


class TestRenderManualCommand:
    def test_claude_render(self) -> None:
        cmd = render_manual_command("claude", "haiku", Path("/tmp/prompt.txt"), Path("/tmp/config.json"))
        assert "claude" in cmd
        assert "--model haiku" in cmd
        assert "prompt.txt" in cmd
        assert "config.json" in cmd

    def test_opencode_render(self) -> None:
        cmd = render_manual_command("opencode", "anthropic/claude-sonnet-4-5", Path("/tmp/p.txt"), Path("/tmp/c.json"))
        assert "opencode" in cmd
        assert "OPENCODE_CONFIG" in cmd


# ── write_backend_config ────────────────────────────────────────────────


class TestWriteBackendConfig:
    def test_writes_claude_config(self, tmp_path: Path) -> None:
        path = write_backend_config("claude", 1, 9222, tmp_path)
        assert path.exists()
        assert "mcpServers" in path.read_text()

    def test_writes_opencode_config(self, tmp_path: Path) -> None:
        path = write_backend_config("opencode", 2, 9333, tmp_path)
        assert path.exists()
        assert "$schema" in path.read_text()


# ── backend_available ────────────────────────────────────────────────────


class TestBackendAvailable:
    @patch("shutil.which")
    def test_claude_available(self, mock_which) -> None:
        mock_which.return_value = "/usr/bin/claude"
        assert backend_available("claude") is True

    @patch("shutil.which")
    def test_opencode_available(self, mock_which) -> None:
        mock_which.return_value = "/usr/bin/opencode"
        assert backend_available("opencode") is True

    @patch("shutil.which")
    def test_claude_not_available(self, mock_which) -> None:
        mock_which.return_value = None
        assert backend_available("claude") is False

    @patch("shutil.which")
    def test_any_available(self, mock_which) -> None:
        mock_which.return_value = "/usr/bin/claude"
        assert any_apply_backend_available() is True
