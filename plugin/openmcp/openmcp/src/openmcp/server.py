"""Unified FastMCP server surface for agy, codex, and gemini backends."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, Literal

from mcp.server.fastmcp import FastMCP

from openmcp.backends.agy import AgyParams, execute as agy_execute
from openmcp.backends.codex import CodexParams, execute as codex_execute
from openmcp.backends.gemini import GeminiParams, execute as gemini_execute
from openmcp.logging_setup import configure as configure_logging, get_logger
from openmcp.retry import run_with_retry

configure_logging()
log = get_logger("server")

mcp = FastMCP("openmcp")

_ENV_AGY_MODEL_DEFAULT = "OPENMCP_AGY_MODEL_DEFAULT"
_ENV_CODEX_MODEL_DEFAULT = "OPENMCP_CODEX_MODEL_DEFAULT"
_ENV_GEMINI_MODEL_DEFAULT = "OPENMCP_GEMINI_MODEL_DEFAULT"
_ENV_CODEX_PROFILE_DEFAULT = "OPENMCP_CODEX_PROFILE_DEFAULT"
_ENV_GEMINI_ROUTE_TO_AGY = "OPENMCP_GEMINI_ROUTE_TO_AGY"
_ENV_AGY_REASONING_MODEL = "OPENMCP_AGY_REASONING_MODEL"
_ENV_CODEX_REASONING_MODEL = "OPENMCP_CODEX_REASONING_MODEL"
_ENV_GEMINI_REASONING_MODEL = "OPENMCP_GEMINI_REASONING_MODEL"
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
    env = _load_plugin_env()
    env.update(_load_openmcp_dotenv())
    env.update(os.environ)
    return env


def _env_truthy(name: str, env: Dict[str, str]) -> bool:
    return env.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _effective_backend(backend: Literal["agy", "codex", "gemini"], env: Dict[str, str]) -> Literal["agy", "codex", "gemini"]:
    if backend == "gemini" and _env_truthy(_ENV_GEMINI_ROUTE_TO_AGY, env):
        return "agy"
    return backend


def _resolve_model(
    backend: Literal["agy", "codex", "gemini"],
    model: str,
    reasoning: str,
    env: Dict[str, str],
) -> str:
    if model:
        return model
    if reasoning:
        if backend == "agy":
            base = env.get(_ENV_AGY_REASONING_MODEL, "")
            return f"{base}-{reasoning}" if base else ""
        if backend == "gemini":
            return env.get(_ENV_GEMINI_REASONING_MODEL, "")
        return env.get(_ENV_CODEX_REASONING_MODEL, "")
    if backend == "agy":
        return ""
    if backend == "gemini":
        return env.get(_ENV_GEMINI_MODEL_DEFAULT, "")
    return env.get(_ENV_CODEX_MODEL_DEFAULT, "")


def _resolve_profile(profile: str, env: Dict[str, str]) -> str:
    if profile:
        return profile
    return env.get(_ENV_CODEX_PROFILE_DEFAULT, "mcp-execution")

@mcp.tool(
    name="run",
    description=(
        "Run an agy, codex, or gemini backend with retry support. "
        "Retries reuse the previous SESSION_ID to preserve conversation context. "
        "Use reasoning mode only for narrow Q&A or cross-validation. "
        "Set debug=True to return the full backend payload; otherwise returns "
        "{success, SESSION_ID, error}."
    ),
)
async def run(
    backend: Literal["agy", "codex", "gemini"],
    PROMPT: str,
    cd: str,
    SESSION_ID: str = "",
    model: str = "",
    profile: str = "",
    reasoning: Literal["", "low", "medium", "high"] = "",
    max_retries: int = 0,
    retry_base_ms: int = 1000,
    debug: bool = False,
) -> Dict[str, Any]:
    """
    Run a backend agent.

    Args:
        backend: Backend to run.
        PROMPT: Prompt to execute.
        cd: Working directory for execution.
        SESSION_ID: Session ID to reuse. Leave empty to start a new session.
        model: Model to use. Leave empty to use the backend default.
        profile: Codex profile to use. Ignored when reasoning is set.
        reasoning: Reasoning effort. Leave empty to disable reasoning mode.
        max_retries: Maximum retry attempts for retryable backend failures.
        retry_base_ms: Base retry delay in milliseconds.
        debug: Return the full backend payload instead of the compact response.
    """

    cd_path = Path(cd)
    effective_env = _effective_env()
    effective_backend = _effective_backend(backend, effective_env)
    resolved_model = _resolve_model(effective_backend, model, reasoning, effective_env)
    resolved_profile = "" if reasoning else _resolve_profile(profile, effective_env)
    log.info(
        "run() backend=%s effective_backend=%s session_id=%s model=%s profile=%s reasoning=%s max_retries=%d debug=%s",
        backend, effective_backend, SESSION_ID or "<new>", resolved_model, resolved_profile, reasoning or "<off>", max_retries, debug,
    )
    try:
        if effective_backend == "agy":
            params = AgyParams(PROMPT=PROMPT, cd=cd_path, SESSION_ID=SESSION_ID, model=resolved_model)
            result = await run_with_retry(agy_execute, params, max_retries=max_retries, retry_base_ms=retry_base_ms)
        elif effective_backend == "codex":
            params = CodexParams(
                PROMPT=PROMPT,
                cd=cd_path,
                SESSION_ID=SESSION_ID,
                model=resolved_model,
                profile=resolved_profile,
                reasoning_effort=reasoning,
            )
            result = await run_with_retry(codex_execute, params, max_retries=max_retries, retry_base_ms=retry_base_ms)
        else:
            params = GeminiParams(PROMPT=PROMPT, cd=cd_path, SESSION_ID=SESSION_ID, model=resolved_model)
            result = await run_with_retry(gemini_execute, params, max_retries=max_retries, retry_base_ms=retry_base_ms)
    except asyncio.CancelledError:
        log.warning(
            "run(): CANCELLED by MCP host (notifications/cancelled or transport closed) "
            "backend=%s session_id=%s",
            backend, SESSION_ID or "<new>",
        )
        raise
    except Exception as exc:
        log.exception("run(): unhandled exception in %s backend", backend)
        return {"success": False, "SESSION_ID": SESSION_ID or "", "error": f"unhandled: {exc}"}

    log.info(
        "run() done backend=%s success=%s attempts=%s session_id=%s",
        backend, result.get("success"), result.get("attempts"), result.get("SESSION_ID", ""),
    )

    if debug:
        return result
    return {
        "success": result.get("success", False),
        "SESSION_ID": result.get("SESSION_ID", "") or "",
        "error": result.get("error", "") or "",
    }


__all__ = ["mcp", "run"]
