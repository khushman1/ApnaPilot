"""Backend helpers for autonomous apply agents."""

from __future__ import annotations

import json
import os
import shlex
import shutil
from pathlib import Path
from typing import Any

from applypilot import config

APPLY_BACKENDS = ("claude", "opencode")
DEFAULT_APPLY_BACKEND = "claude"
DEFAULT_CLAUDE_MODEL = "haiku"
DEFAULT_OPENCODE_MODEL = "anthropic/claude-sonnet-4-5"

_GMAIL_DANGEROUS_TOOLS = (
    "draft_email",
    "modify_email",
    "delete_email",
    "download_attachment",
    "batch_modify_emails",
    "batch_delete_emails",
    "create_label",
    "update_label",
    "delete_label",
    "get_or_create_label",
    "list_email_labels",
    "create_filter",
    "list_filters",
    "get_filter",
    "delete_filter",
)


def normalize_backend(value: str | None) -> str:
    """Normalize a requested backend to a supported identifier."""
    backend = (value or DEFAULT_APPLY_BACKEND).strip().lower()
    if backend in APPLY_BACKENDS:
        return backend
    return DEFAULT_APPLY_BACKEND


def backend_binary(backend: str) -> str:
    """Return the executable name for a backend."""
    backend = normalize_backend(backend)
    return "claude" if backend == "claude" else "opencode"


def backend_label(backend: str) -> str:
    """User-facing backend name."""
    backend = normalize_backend(backend)
    return "Claude Code" if backend == "claude" else "OpenCode"


def backend_available(backend: str) -> bool:
    """Check if a backend CLI is installed."""
    return shutil.which(backend_binary(backend)) is not None


def any_apply_backend_available() -> bool:
    """Check whether any supported auto-apply backend is installed."""
    return any(backend_available(backend) for backend in APPLY_BACKENDS)


def backend_model_help(backend: str) -> str:
    """Return backend-specific model help text."""
    backend = normalize_backend(backend)
    if backend == "opencode":
        return "provider/model syntax, for example anthropic/claude-sonnet-4-5"
    return "Claude model shorthand, for example haiku or sonnet"


def get_default_model(backend: str) -> str:
    """Return the default model for a backend."""
    backend = normalize_backend(backend)
    if backend == "opencode":
        return DEFAULT_OPENCODE_MODEL
    return DEFAULT_CLAUDE_MODEL


def get_opencode_permission_policy() -> dict[str, str]:
    """Permission overrides for OpenCode tools."""
    return {f"gmail_{tool_name}": "deny" for tool_name in _GMAIL_DANGEROUS_TOOLS}


def get_claude_disallowed_tools() -> str:
    """Comma-separated list of Gmail tools Claude must not use."""
    return ",".join(f"mcp__gmail__{tool_name}" for tool_name in _GMAIL_DANGEROUS_TOOLS)


def build_claude_mcp_config(cdp_port: int) -> dict[str, Any]:
    """Build Claude Code MCP config for a specific Chrome worker."""
    return {
        "mcpServers": {
            "playwright": {
                "command": "npx",
                "args": [
                    "@playwright/mcp@latest",
                    f"--cdp-endpoint=http://localhost:{cdp_port}",
                    f"--viewport-size={config.DEFAULTS['viewport']}",
                ],
            },
            "gmail": {
                "command": "npx",
                "args": ["-y", "@gongrzhe/server-gmail-autoauth-mcp"],
            },
        }
    }


def build_opencode_config(cdp_port: int) -> dict[str, Any]:
    """Build OpenCode config with local MCP servers and Gmail restrictions."""
    return {
        "$schema": "https://opencode.ai/config.json",
        "mcp": {
            "playwright": {
                "type": "local",
                "enabled": True,
                "command": [
                    "npx",
                    "@playwright/mcp@latest",
                    f"--cdp-endpoint=http://localhost:{cdp_port}",
                    f"--viewport-size={config.DEFAULTS['viewport']}",
                ],
            },
            "gmail": {
                "type": "local",
                "enabled": True,
                "command": ["npx", "-y", "@gongrzhe/server-gmail-autoauth-mcp"],
            },
        },
        "permission": get_opencode_permission_policy(),
    }


def build_backend_config(backend: str, cdp_port: int) -> dict[str, Any]:
    """Build the runtime config file contents for a backend."""
    backend = normalize_backend(backend)
    if backend == "opencode":
        return build_opencode_config(cdp_port)
    return build_claude_mcp_config(cdp_port)


def config_filename(backend: str, worker_id: int) -> str:
    """Return the runtime config filename for a backend worker."""
    backend = normalize_backend(backend)
    if backend == "opencode":
        return f".opencode-apply-{worker_id}.json"
    return f".mcp-apply-{worker_id}.json"


def build_agent_command(backend: str, model: str, config_path: Path, prompt: str) -> list[str]:
    """Build the subprocess command for an apply agent backend."""
    backend = normalize_backend(backend)
    if backend == "opencode":
        return [
            "opencode",
            "run",
            "--format",
            "json",
            "--model",
            model,
            "--dangerously-skip-permissions",
            prompt,
        ]

    return [
        "claude",
        "--model",
        model,
        "-p",
        "--mcp-config",
        str(config_path),
        "--permission-mode",
        "bypassPermissions",
        "--no-session-persistence",
        "--disallowedTools",
        get_claude_disallowed_tools(),
        "--output-format",
        "stream-json",
        "--verbose",
        "-",
    ]


def build_agent_env(backend: str, config_path: Path) -> dict[str, str]:
    """Build the environment for an apply agent subprocess."""
    backend = normalize_backend(backend)
    env = os.environ.copy()
    if backend == "claude":
        env.pop("CLAUDECODE", None)
        env.pop("CLAUDE_CODE_ENTRYPOINT", None)
    else:
        env["OPENCODE_CONFIG"] = str(config_path)
    return env


def render_manual_command(backend: str, model: str, prompt_file: Path, config_path: Path) -> str:
    """Render a shell command for manual backend debugging."""
    backend = normalize_backend(backend)
    quoted_model = shlex.quote(model)
    quoted_prompt = shlex.quote(str(prompt_file))
    quoted_config = shlex.quote(str(config_path))
    if backend == "opencode":
        return (
            f"OPENCODE_CONFIG={quoted_config} "
            f"opencode run --format json --model {quoted_model} "
            f"--dangerously-skip-permissions \"$(cat {quoted_prompt})\""
        )
    return (
        f"claude --model {quoted_model} -p "
        f"--mcp-config {quoted_config} "
        f"--permission-mode bypassPermissions < {quoted_prompt}"
    )


def write_backend_config(backend: str, worker_id: int, cdp_port: int, target_dir: Path | None = None) -> Path:
    """Write a backend runtime config file and return its path."""
    base_dir = target_dir or config.APP_DIR
    path = base_dir / config_filename(backend, worker_id)
    path.write_text(json.dumps(build_backend_config(backend, cdp_port)), encoding="utf-8")
    return path
