"""Unified FastMCP server surface for agy and codex backends."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, Literal

from mcp.server.fastmcp import FastMCP

from openmcp.backends.agy import AgyParams, execute as agy_execute
from openmcp.backends.codex import CodexParams, execute as codex_execute
from openmcp.logging_setup import configure as configure_logging, get_logger
from openmcp.notify import emit_error, emit_finish, emit_start

configure_logging()
log = get_logger("server")

mcp = FastMCP("openmcp")

_ENV_CODEX_MODEL_DEFAULT = "OPENMCP_CODEX_MODEL_DEFAULT"
_ENV_CODEX_PROFILE_DEFAULT = "OPENMCP_CODEX_PROFILE_DEFAULT"
_ENV_AGY_REASONING_MODEL = "OPENMCP_AGY_REASONING_MODEL"
_ENV_CODEX_REASONING_MODEL = "OPENMCP_CODEX_REASONING_MODEL"

_REASONING_MODEL_DEFAULTS: Dict[str, str] = {
    "agy": "gemini-3.5-flash",
    "codex": "gpt-5.5",
}
_REASONING_MODEL_ENV: Dict[str, str] = {
    "agy": _ENV_AGY_REASONING_MODEL,
    "codex": _ENV_CODEX_REASONING_MODEL,
}
_PLUGIN_CONFIG_FILES = ("mcp_config.json", ".mcp.json", "mcp.json")


def _openmcp_env_file() -> Path:
    return Path.home() / ".openmcp" / ".env"


def _load_plugin_env() -> Dict[str, str]:
    plugin_env: Dict[str, str] = {}
    for config_name in _PLUGIN_CONFIG_FILES:
        config_path = Path.cwd() / config_name
        if not config_path.exists():
            continue
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Failed to read plugin config %s: %s", config_path.as_posix(), exc)
            continue
        server_env = (
            config.get("mcpServers", {})
            .get("openmcp", {})
            .get("env", {})
        )
        if not isinstance(server_env, dict):
            continue
        for key, value in server_env.items():
            if value is None:
                continue
            plugin_env[str(key)] = str(value)
    return plugin_env


def _load_openmcp_dotenv() -> Dict[str, str]:
    values: Dict[str, str] = {}
    try:
        lines = _openmcp_env_file().read_text(encoding="utf-8").splitlines()
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


def _effective_env() -> Dict[str, str]:
    # Precedence: process env > ~/.openmcp/.env > plugin config env.
    env = _load_plugin_env()
    env.update(_load_openmcp_dotenv())
    env.update(os.environ)
    return env


def _env_truthy(name: str, env: Dict[str, str]) -> bool:
    return env.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _reasoning_model(backend: str, env: Dict[str, str]) -> str:
    return env.get(_REASONING_MODEL_ENV[backend], "") or _REASONING_MODEL_DEFAULTS[backend]


def _resolve_model(
    backend: Literal["agy", "codex"],
    model: str,
    reasoning: str,
    env: Dict[str, str],
) -> str:
    if model:
        return model
    if reasoning:
        if backend == "agy":
            base = _reasoning_model("agy", env)
            # bare model id (no suffix) corresponds to Medium; preserve that
            return base if reasoning == "medium" else f"{base}-{reasoning}"
        return _reasoning_model(backend, env)
    if backend == "agy":
        return ""
    return env.get(_ENV_CODEX_MODEL_DEFAULT, "")


def _resolve_profile(profile: str, env: Dict[str, str]) -> str:
    if profile:
        return profile
    return env.get(_ENV_CODEX_PROFILE_DEFAULT, "mcp_execution")


def _validate_cd(cd: Any) -> Path | None:
    if cd is None:
        return None
    if isinstance(cd, Path):
        return cd if str(cd) else None
    cd_str = str(cd).strip()
    if not cd_str:
        return None
    path = Path(cd_str)
    if not path.is_absolute():
        log.warning(
            "run(): cd=%r is not absolute; resolving against current working directory. "
            "Pass an absolute path to avoid this.", cd_str,
        )
    return path


@mcp.tool(
    name="run",
    description=(
        "Run an agy or codex backend. "
        "Use reasoning mode only for narrow Q&A or cross-validation. "
        "Returns {success, SESSION_ID, agent_messages, error}."
    ),
)
async def run(
    backend: Literal["agy", "codex"],
    PROMPT: str,
    cd: str,
    SESSION_ID: str = "",
    model: str = "",
    profile: str = "",
    reasoning: Literal["", "low", "medium", "high"] = "",
    timeout_s: int = 0,
) -> Dict[str, Any]:
    """
    Run a backend agent.

    Args:
        backend: Backend to run.
        PROMPT: Prompt to execute.
        cd: Working directory for execution (must be an absolute path).
        SESSION_ID: Session ID to reuse. Leave empty to start a new session.
        model: Model to use. Leave empty to use the backend default.
        profile: Codex profile to use. When combined with model, the model
            argument overrides the profile's model field. When combined with
            reasoning, reasoning takes precedence and selects its own model.
        reasoning: Reasoning effort. Leave empty to disable reasoning mode.
        timeout_s: Overall subprocess timeout in seconds (0 = no timeout / backend default).
    """

    cd_path = _validate_cd(cd)
    if cd_path is None:
        return {
            "success": False,
            "SESSION_ID": SESSION_ID or "",
            "agent_messages": "",
            "error": f"cd must be a non-empty absolute path; got {cd!r}",
        }
    effective_env = _effective_env()
    resolved_model = _resolve_model(backend, model, reasoning, effective_env)
    resolved_profile = "" if reasoning else _resolve_profile(profile, effective_env)
    codex_model = resolved_model
    if backend == "codex" and profile and model:
        log.info(
            "codex: profile=%r and model=%r both provided; model overrides the profile's model",
            profile, model,
        )
    if backend == "codex" and profile and reasoning:
        log.warning(
            "codex: profile=%r and reasoning=%r both provided; profile is ignored "
            "(reasoning takes precedence and selects its own model)",
            profile, reasoning,
        )
    log.info(
        "run() backend=%s session_id=%s model=%s profile=%s reasoning=%s timeout_s=%s",
        backend, SESSION_ID or "<new>",
        codex_model if backend == "codex" else resolved_model,
        resolved_profile, reasoning or "<off>", timeout_s or "<off>",
    )
    try:
        await emit_start(
            backend=backend,
            session_id=SESSION_ID,
            model=resolved_model,
        )
        if backend == "agy":
            params = AgyParams(
                PROMPT=PROMPT,
                cd=cd_path,
                SESSION_ID=SESSION_ID,
                model=resolved_model,
                timeout_s=timeout_s,
            )
            backend_result = await agy_execute(params)
        else:
            params = CodexParams(
                PROMPT=PROMPT,
                cd=cd_path,
                SESSION_ID=SESSION_ID,
                model=codex_model,
                profile=resolved_profile,
                reasoning_effort=reasoning,
                timeout_s=timeout_s,
            )
            backend_result = await codex_execute(params)

        if backend_result.outcome == "OK":
            result = {
                "success": True,
                "SESSION_ID": backend_result.SESSION_ID,
                "agent_messages": backend_result.agent_messages,
            }
            if backend_result.error_class == "warning" and backend_result.error:
                result["warning"] = backend_result.error
        else:
            result = {
                "success": False,
                "SESSION_ID": backend_result.SESSION_ID or "",
                "agent_messages": backend_result.agent_messages or "",
                "error": backend_result.error,
            }
    except asyncio.CancelledError:
        log.warning(
            "run(): CANCELLED by MCP host (notifications/cancelled or transport closed) "
            "backend=%s session_id=%s",
            backend, SESSION_ID or "<new>",
        )
        raise
    except Exception as exc:
        log.exception("run(): unhandled exception in %s backend", backend)
        await emit_error(
            backend=backend,
            session_id=SESSION_ID,
            model=resolved_model,
            error=f"unhandled: {exc}",
        )
        return {"success": False, "SESSION_ID": SESSION_ID or "", "agent_messages": "", "error": f"unhandled: {exc}"}

    log.info(
        "run() done backend=%s success=%s session_id=%s",
        backend, result.get("success"), result.get("SESSION_ID", ""),
    )
    result_session_id = result.get("SESSION_ID", "") or ""
    if result.get("success", False):
        await emit_finish(
            backend=backend,
            session_id=result_session_id,
            model=resolved_model,
        )
    else:
        await emit_error(
            backend=backend,
            session_id=result_session_id,
            model=resolved_model,
            error=result.get("error", "") or "",
        )
    return {
        "success": result.get("success", False),
        "SESSION_ID": result_session_id,
        "agent_messages": result.get("agent_messages", "") or "",
        "error": result.get("error", "") or "",
    }


__all__ = ["mcp", "run"]
