"""Unified FastMCP server surface for agy, codex, and gemini backends."""

from __future__ import annotations

import asyncio
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


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _effective_backend(backend: Literal["agy", "codex", "gemini"]) -> Literal["agy", "codex", "gemini"]:
    if backend == "gemini" and _env_truthy(_ENV_GEMINI_ROUTE_TO_AGY):
        return "agy"
    return backend


def _resolve_model(backend: Literal["agy", "codex", "gemini"], model: str) -> str:
    if model:
        return model
    if backend == "agy":
        return os.environ.get(_ENV_AGY_MODEL_DEFAULT, "")
    if backend == "gemini":
        return os.environ.get(_ENV_GEMINI_MODEL_DEFAULT, "")
    return os.environ.get(_ENV_CODEX_MODEL_DEFAULT, "")


def _resolve_profile(profile: str) -> str:
    if profile:
        return profile
    return os.environ.get(_ENV_CODEX_PROFILE_DEFAULT, "mcp-execution")


@mcp.tool(
    name="run",
    description=(
        "Run an agy, codex, or gemini backend with retry support. "
        "When retries occur, SESSION_ID from the previous attempt is reused "
        "to preserve backend conversation continuity. "
        "Response shape depends on `debug`: when False (default), returns only "
        "{success, SESSION_ID, error} for token efficiency; when True, returns "
        "the full payload including agent_messages, attempts, and warning."
    ),
)
async def run(
    backend: Literal["agy", "codex", "gemini"],
    PROMPT: str,
    cd: Path,
    SESSION_ID: str = "",
    model: str = "",
    profile: str = "",
    max_retries: int = 0,
    retry_base_ms: int = 1000,
    debug: bool = False,
) -> Dict[str, Any]:
    """Dispatch a prompt to agy/codex/gemini backend with retry and SESSION_ID continuity."""
    effective_backend = _effective_backend(backend)
    resolved_model = _resolve_model(effective_backend, model)
    resolved_profile = _resolve_profile(profile)
    log.info(
        "run() backend=%s effective_backend=%s session_id=%s model=%s profile=%s max_retries=%d debug=%s",
        backend, effective_backend, SESSION_ID or "<new>", resolved_model, resolved_profile, max_retries, debug,
    )
    try:
        if effective_backend == "agy":
            params = AgyParams(PROMPT=PROMPT, cd=cd, SESSION_ID=SESSION_ID, model=resolved_model)
            result = await run_with_retry(agy_execute, params, max_retries=max_retries, retry_base_ms=retry_base_ms)
        elif effective_backend == "codex":
            params = CodexParams(
                PROMPT=PROMPT,
                cd=cd,
                SESSION_ID=SESSION_ID,
                model=resolved_model,
                profile=resolved_profile,
            )
            result = await run_with_retry(codex_execute, params, max_retries=max_retries, retry_base_ms=retry_base_ms)
        else:
            params = GeminiParams(PROMPT=PROMPT, cd=cd, SESSION_ID=SESSION_ID, model=resolved_model)
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
