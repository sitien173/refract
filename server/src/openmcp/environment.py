"""Environment resolution shared by optional runtime integrations."""

from __future__ import annotations

import json
import os
from pathlib import Path

from openmcp.logging_setup import get_logger


log = get_logger("environment")
_PLUGIN_CONFIG_FILES = ("mcp_config.json", ".mcp.json", "mcp.json")


def openmcp_env_file() -> Path:
    """Return the optional per-user environment file path."""
    return Path.home() / ".openmcp" / ".env"


def load_plugin_env() -> dict[str, str]:
    """Load OpenMCP environment values declared by an MCP client."""
    plugin_env: dict[str, str] = {}
    for config_name in _PLUGIN_CONFIG_FILES:
        config_path = Path.cwd() / config_name
        if not config_path.exists():
            continue
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Failed to read plugin config %s: %s", config_path.as_posix(), exc)
            continue
        server_env = config.get("mcpServers", {}).get("openmcp", {}).get("env", {})
        if not isinstance(server_env, dict):
            continue
        for key, value in server_env.items():
            if value is not None:
                plugin_env[str(key)] = str(value)
    return plugin_env


def load_openmcp_dotenv() -> dict[str, str]:
    """Load simple KEY=VALUE entries from ``~/.openmcp/.env``."""
    values: dict[str, str] = {}
    try:
        lines = openmcp_env_file().read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def effective_env() -> dict[str, str]:
    """Resolve environment values: process > OpenMCP dotenv > plugin config."""
    env = load_plugin_env()
    env.update(load_openmcp_dotenv())
    env.update(os.environ)
    return env


def env_truthy(name: str, env: dict[str, str]) -> bool:
    """Return whether an environment value uses a supported truthy spelling."""
    return env.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


__all__ = [
    "effective_env",
    "env_truthy",
    "load_openmcp_dotenv",
    "load_plugin_env",
    "openmcp_env_file",
]
