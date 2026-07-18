"""Direct single-backend execution, independent of the MCP daemon surface."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal

from openmcp.backends import BackendResult
from openmcp.backends.agy import AgyParams, execute as agy_execute
from openmcp.backends.codex import CodexParams, execute as codex_execute
from openmcp.backends.pi import PiParams, execute as pi_execute
from openmcp.environment import effective_env
from openmcp.logging_setup import get_logger
from openmcp.notify import emit_error, emit_finish, emit_start


log = get_logger("backend_runner")

BackendName = Literal["agy", "codex", "pi"]
ReasoningEffort = Literal["", "low", "medium", "high"]
_ENV_CODEX_MODEL_DEFAULT = "OPENMCP_CODEX_MODEL_DEFAULT"
_ENV_CODEX_PROFILE_DEFAULT = "OPENMCP_CODEX_PROFILE_DEFAULT"
_ENV_AGY_REASONING_MODEL = "OPENMCP_AGY_REASONING_MODEL"
_ENV_CODEX_REASONING_MODEL = "OPENMCP_CODEX_REASONING_MODEL"
_ENV_PI_MODEL_DEFAULT = "OPENMCP_PI_MODEL_DEFAULT"
_REASONING_MODEL_DEFAULTS = {
    "agy": "gemini-3.5-flash",
    "codex": "gpt-5.5",
}
_REASONING_MODEL_ENV = {
    "agy": _ENV_AGY_REASONING_MODEL,
    "codex": _ENV_CODEX_REASONING_MODEL,
}


def _reasoning_model(backend: Literal["agy", "codex"], env: dict[str, str]) -> str:
    return env.get(_REASONING_MODEL_ENV[backend], "") or _REASONING_MODEL_DEFAULTS[backend]


def _resolve_model(
    backend: BackendName,
    model: str,
    reasoning: ReasoningEffort,
    env: dict[str, str],
) -> str:
    if model:
        return model
    if reasoning:
        if backend == "agy":
            base = _reasoning_model("agy", env)
            return base if reasoning == "medium" else f"{base}-{reasoning}"
        if backend == "codex":
            return _reasoning_model("codex", env)
        return env.get(_ENV_PI_MODEL_DEFAULT, "")
    if backend == "agy":
        return ""
    if backend == "pi":
        return env.get(_ENV_PI_MODEL_DEFAULT, "")
    return env.get(_ENV_CODEX_MODEL_DEFAULT, "")


def _resolve_profile(profile: str, env: dict[str, str]) -> str:
    return profile or env.get(_ENV_CODEX_PROFILE_DEFAULT, "mcp_execution")


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
            "Pass an absolute path to avoid this.",
            cd_str,
        )
    return path


async def run(
    backend: BackendName,
    PROMPT: str,
    cd: str,
    SESSION_ID: str = "",
    model: str = "",
    profile: str = "",
    reasoning: ReasoningEffort = "",
    timeout_s: int = 0,
    *,
    agy_executor: Callable[[AgyParams], Awaitable[BackendResult]] = agy_execute,
    codex_executor: Callable[[CodexParams], Awaitable[BackendResult]] = codex_execute,
    pi_executor: Callable[[PiParams], Awaitable[BackendResult]] = pi_execute,
    emit_start_event: Callable[..., Awaitable[None]] = emit_start,
    emit_finish_event: Callable[..., Awaitable[None]] = emit_finish,
    emit_error_event: Callable[..., Awaitable[None]] = emit_error,
) -> dict[str, Any]:
    """Run one backend with direct-invocation defaults and notifications.

    The injected callables keep the runner independent of transports and make
    the compatibility facade in :mod:`openmcp.server` straightforward to test.
    """
    cd_path = _validate_cd(cd)
    if cd_path is None:
        return {
            "success": False,
            "SESSION_ID": SESSION_ID or "",
            "agent_messages": "",
            "error": f"cd must be a non-empty absolute path; got {cd!r}",
        }
    env = effective_env()
    resolved_model = _resolve_model(backend, model, reasoning, env)
    resolved_profile = "" if reasoning else _resolve_profile(profile, env)
    if backend != "codex":
        resolved_profile = ""
    if backend == "codex" and profile and model:
        log.info(
            "codex: profile=%r and model=%r both provided; model overrides the profile's model",
            profile,
            model,
        )
    if backend == "codex" and profile and reasoning:
        log.warning(
            "codex: profile=%r and reasoning=%r both provided; profile is ignored "
            "(reasoning takes precedence and selects its own model)",
            profile,
            reasoning,
        )
    log.info(
        "run() backend=%s session_id=%s model=%s profile=%s reasoning=%s timeout_s=%s",
        backend,
        SESSION_ID or "<new>",
        resolved_model,
        resolved_profile,
        reasoning or "<off>",
        timeout_s or "<off>",
    )
    try:
        await emit_start_event(
            backend=backend,
            session_id=SESSION_ID,
            model=resolved_model,
        )
        if backend == "agy":
            backend_result = await agy_executor(
                AgyParams(
                    PROMPT=PROMPT,
                    cd=cd_path,
                    SESSION_ID=SESSION_ID,
                    model=resolved_model,
                    timeout_s=timeout_s,
                )
            )
        elif backend == "codex":
            backend_result = await codex_executor(
                CodexParams(
                    PROMPT=PROMPT,
                    cd=cd_path,
                    SESSION_ID=SESSION_ID,
                    model=resolved_model,
                    profile=resolved_profile,
                    reasoning_effort=reasoning,
                    timeout_s=timeout_s,
                )
            )
        else:
            backend_result = await pi_executor(
                PiParams(
                    PROMPT=PROMPT,
                    cd=cd_path,
                    SESSION_ID=SESSION_ID,
                    model=resolved_model,
                    reasoning_effort=reasoning,
                    timeout_s=timeout_s,
                )
            )
        if backend_result.outcome == "OK":
            result = {
                "success": True,
                "SESSION_ID": backend_result.SESSION_ID,
                "agent_messages": backend_result.agent_messages,
            }
        else:
            result = {
                "success": False,
                "SESSION_ID": backend_result.SESSION_ID or "",
                "agent_messages": backend_result.agent_messages or "",
                "error": backend_result.error,
            }
    except asyncio.CancelledError:
        log.warning(
            "run(): cancelled by MCP host backend=%s session_id=%s",
            backend,
            SESSION_ID or "<new>",
        )
        raise
    except Exception as exc:
        log.exception("run(): unhandled exception in %s backend", backend)
        await emit_error_event(
            backend=backend,
            session_id=SESSION_ID,
            model=resolved_model,
            error=f"unhandled: {exc}",
        )
        return {
            "success": False,
            "SESSION_ID": SESSION_ID or "",
            "agent_messages": "",
            "error": f"unhandled: {exc}",
        }

    log.info(
        "run() done backend=%s success=%s session_id=%s",
        backend,
        result["success"],
        result["SESSION_ID"],
    )
    session_id = result["SESSION_ID"] or ""
    if result["success"]:
        await emit_finish_event(
            backend=backend,
            session_id=session_id,
            model=resolved_model,
        )
    else:
        await emit_error_event(
            backend=backend,
            session_id=session_id,
            model=resolved_model,
            error=result.get("error", "") or "",
        )
    return {
        "success": result["success"],
        "SESSION_ID": session_id,
        "agent_messages": result["agent_messages"] or "",
        "error": result.get("error", "") or "",
    }


__all__ = ["BackendName", "ReasoningEffort", "run"]
