"""Claude Code CLI backend using non-interactive print-mode JSON output."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generator

from openmcp.logging_setup import get_logger

from . import BackendResult, classify_backend_output
from ._shell import ShellCommandCancelled, ShellCommandFailed, stream_shell_command_lines

log = get_logger("claude")


@dataclass(slots=True)
class ClaudeParams:
    PROMPT: str
    cd: Path
    SESSION_ID: str = ""
    args: tuple[str, ...] = ()
    timeout_s: int = 0
    cancel_event: threading.Event | None = None


def run_shell_command(
    cmd: list[str],
    cwd: str | None = None,
    timeout_s: int = 0,
    cancel_event: threading.Event | None = None,
) -> Generator[str, None, None]:
    """Run Claude and yield its combined output one line at a time."""
    yield from stream_shell_command_lines(
        cmd,
        executable_name="claude",
        errors="replace",
        cwd=cwd,
        timeout_s=timeout_s,
        line_transform=lambda line: line.rstrip("\r\n"),
        terminate_wait_s=5,
        cancel_event=cancel_event,
        check_returncode=True,
    )


def _value_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return str(value)


def _extract_output(lines: list[str]) -> tuple[str, str, str, str]:
    """Return the final reply, session ID, diagnostics, and result error."""
    final_result: dict[str, Any] | None = None
    diagnostics: list[str] = []

    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            if line.strip():
                diagnostics.append(line.strip())
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            final_result = event

    if final_result is None:
        return "", "", "\n".join(diagnostics).strip(), ""

    agent_messages = _value_text(final_result.get("result"))
    session_id = final_result.get("session_id")
    if not isinstance(session_id, str):
        session_id = ""

    result_error = ""
    if final_result.get("is_error") or final_result.get("subtype") != "success":
        error_parts = [_value_text(final_result.get("result"))]
        status = _value_text(final_result.get("api_error_status"))
        if status:
            error_parts.append(f"api_error_status={status}")
        result_error = "\n".join(part for part in error_parts if part).strip()

    return agent_messages, session_id, "\n".join(diagnostics).strip(), result_error


def _execute_sync(params: ClaudeParams) -> BackendResult:
    """Execute a Claude Code print-mode session and normalize its result."""
    cd = Path(params.cd).expanduser().absolute()
    if not cd.is_dir():
        return BackendResult(
            outcome="FATAL",
            SESSION_ID="",
            agent_messages="",
            error=f"The workspace root directory `{cd}` does not exist or is not a directory. Please check the path and try again.",
            error_class="bad_cd",
        )
    if shutil.which("claude") is None:
        return BackendResult(
            outcome="FATAL",
            SESSION_ID="",
            agent_messages="",
            error="The `claude` CLI was not found on PATH. Please install Claude Code and ensure `claude` is available.",
            error_class="missing_cli",
        )

    cmd = [
        "claude",
        *params.args,
        "-p",
        "--permission-mode",
        "bypassPermissions",
        "--output-format",
        "json",
    ]
    if params.SESSION_ID:
        cmd.extend(["--resume", params.SESSION_ID])
    cmd.extend(["--", params.PROMPT])

    log.info(
        "claude.execute start cwd=%s session_id=%s prompt_len=%d args=%d timeout_s=%s",
        os.fspath(cd),
        params.SESSION_ID or "<new>",
        len(params.PROMPT),
        len(params.args),
        params.timeout_s or "<off>",
    )
    log.debug("claude command prepared args=%d", len(cmd))

    lines: list[str] = []
    command_error = ""
    command_error_class = ""
    try:
        for line in run_shell_command(
            cmd,
            cwd=os.fspath(cd),
            timeout_s=params.timeout_s,
            cancel_event=params.cancel_event,
        ):
            lines.append(line)
    except ShellCommandCancelled:
        command_error = "backend command cancelled"
        command_error_class = "cancelled"
        log.warning("claude subprocess cancelled")
    except subprocess.TimeoutExpired:
        command_error = f"claude subprocess timed out after {params.timeout_s}s"
        command_error_class = "timeout"
        log.warning("claude subprocess timeout after %ss", params.timeout_s)
    except ShellCommandFailed as exc:
        command_error = str(exc)
        command_error_class = "execution_error"
        log.warning("claude subprocess exited with status %d", exc.returncode)
    except Exception as exc:  # noqa: BLE001
        command_error = f"claude subprocess failed ({type(exc).__name__})"
        command_error_class = "execution_error"
        log.error("claude: unexpected error during stream type=%s", type(exc).__name__)

    agent_messages, extracted_session_id, diagnostics, result_error = _extract_output(lines)
    session_id = extracted_session_id or params.SESSION_ID
    error_text = "\n".join(
        part for part in (command_error, diagnostics, result_error) if part
    ).strip()
    result = classify_backend_output(
        backend_name="claude",
        agent_messages=agent_messages,
        session_id=session_id,
        error_text=error_text,
    )

    if result_error and not command_error:
        result.outcome = "FATAL"
        if result.error_class in {"", "warning", "no_agent_messages"}:
            result.error_class = "fatal_backend"
        result.error = result_error
    if command_error:
        result.outcome = "FATAL"
        result.error_class = command_error_class
        result.error = command_error
    if params.cancel_event is not None and params.cancel_event.is_set():
        result.outcome = "FATAL"
        result.error_class = "cancelled"
        result.error = "backend command cancelled"

    log.info(
        "claude.execute done outcome=%s session_id=%s error_class=%s msg_len=%d",
        result.outcome,
        result.SESSION_ID or "",
        result.error_class,
        len(result.agent_messages),
    )
    return result


async def execute(params: ClaudeParams) -> BackendResult:
    """Execute Claude without blocking the daemon event loop."""
    return await asyncio.to_thread(_execute_sync, params)


__all__ = ["ClaudeParams", "execute"]
