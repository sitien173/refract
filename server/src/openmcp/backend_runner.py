"""Direct single-backend execution, independent of the MCP daemon surface."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Literal

from openmcp.backends import BackendResult
from openmcp.backends.agy import AgyParams, execute as agy_execute
from openmcp.backends.claude import ClaudeParams, execute as claude_execute
from openmcp.backends.codex import CodexParams, execute as codex_execute
from openmcp.backends.pi import PiParams, execute as pi_execute
from openmcp.logging_setup import get_logger


log = get_logger("backend_runner")

BackendName = Literal["agy", "codex", "pi", "claude"]


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
    timeout_s: int = 0,
    *,
    agy_executor: Callable[[AgyParams], Awaitable[BackendResult]] = agy_execute,
    codex_executor: Callable[[CodexParams], Awaitable[BackendResult]] = codex_execute,
    pi_executor: Callable[[PiParams], Awaitable[BackendResult]] = pi_execute,
    claude_executor: Callable[[ClaudeParams], Awaitable[BackendResult]] = claude_execute,
) -> dict[str, Any]:
    """Run one backend with the harness CLI's default execution settings.

    Target policy belongs to durable orchestration and is intentionally absent
    here. The injected executors keep this compatibility runner transport-only
    and straightforward to test.
    """
    cd_path = _validate_cd(cd)
    if cd_path is None:
        return {
            "success": False,
            "SESSION_ID": SESSION_ID or "",
            "agent_messages": "",
            "error": f"cd must be a non-empty path; got {cd!r}",
        }
    log.info(
        "run() backend=%s session_id=%s timeout_s=%s",
        backend,
        SESSION_ID or "<new>",
        timeout_s or "<off>",
    )
    try:
        if backend == "agy":
            backend_result = await agy_executor(
                AgyParams(
                    PROMPT=PROMPT,
                    cd=cd_path,
                    SESSION_ID=SESSION_ID,
                    timeout_s=timeout_s,
                )
            )
        elif backend == "codex":
            backend_result = await codex_executor(
                CodexParams(
                    PROMPT=PROMPT,
                    cd=cd_path,
                    SESSION_ID=SESSION_ID,
                    timeout_s=timeout_s,
                )
            )
        elif backend == "pi":
            backend_result = await pi_executor(
                PiParams(
                    PROMPT=PROMPT,
                    cd=cd_path,
                    SESSION_ID=SESSION_ID,
                    args=("--approve",),
                    timeout_s=timeout_s,
                )
            )
        elif backend == "claude":
            backend_result = await claude_executor(
                ClaudeParams(
                    PROMPT=PROMPT,
                    cd=cd_path,
                    SESSION_ID=SESSION_ID,
                    timeout_s=timeout_s,
                )
            )
        else:
            return {
                "success": False,
                "SESSION_ID": SESSION_ID or "",
                "agent_messages": "",
                "error": f"unsupported backend: {backend}",
            }
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
        # Executor exceptions can include a subprocess argv containing PROMPT.
        log.error(
            "run(): unhandled backend exception backend=%s type=%s",
            backend,
            type(exc).__name__,
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
    return {
        "success": result["success"],
        "SESSION_ID": session_id,
        "agent_messages": result["agent_messages"] or "",
        "error": result.get("error", "") or "",
    }


__all__ = ["BackendName", "run"]
