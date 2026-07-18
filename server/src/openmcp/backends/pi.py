"""Pi CLI backend using Pi's non-interactive JSON event stream."""

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

from . import BackendResult, classify_backend_output
from ._shell import ShellCommandCancelled, stream_shell_command_lines
from openmcp.logging_setup import get_logger

log = get_logger("pi")


@dataclass(slots=True)
class PiParams:
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
    """Run Pi and yield its combined output one line at a time."""
    yield from stream_shell_command_lines(
        cmd,
        executable_name="pi",
        errors="replace",
        cwd=cwd,
        timeout_s=timeout_s,
        line_transform=lambda line: line.rstrip("\r\n"),
        terminate_wait_s=5,
        cancel_event=cancel_event,
    )


def _message_text(message: Any) -> str:
    """Extract text from Pi's AssistantMessage content representation."""
    if not isinstance(message, dict) or message.get("role") != "assistant":
        return ""
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text", "")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)


def _extract_output(lines: list[str]) -> tuple[str, str, str]:
    """Return Pi's final reply, session ID, and non-JSON/error output."""
    session_id = ""
    agent_message = ""
    diagnostics: list[str] = []
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            if line.strip():
                diagnostics.append(line)
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "session" and isinstance(event.get("id"), str):
            session_id = event["id"]
        if event.get("type") == "message_end":
            text = _message_text(event.get("message"))
            if text:
                agent_message = text
        if event.get("type") == "agent_end":
            messages = event.get("messages")
            if isinstance(messages, list):
                for message in reversed(messages):
                    text = _message_text(message)
                    if text:
                        agent_message = text
                        break
        if event.get("type") == "error":
            error = event.get("error") or event.get("message")
            if isinstance(error, str) and error:
                diagnostics.append(error)
    return agent_message, session_id, "\n".join(diagnostics).strip()


def _execute_sync(params: PiParams) -> BackendResult:
    """Execute a Pi non-interactive session and return a normalized result."""
    cd = Path(params.cd).expanduser().absolute()
    if not cd.is_dir():
        return BackendResult(
            outcome="FATAL",
            SESSION_ID="",
            agent_messages="",
            error=f"The workspace root directory `{cd}` does not exist or is not a directory. Please check the path and try again.",
            error_class="bad_cd",
        )
    if shutil.which("pi") is None:
        return BackendResult(
            outcome="FATAL",
            SESSION_ID="",
            agent_messages="",
            error="The `pi` CLI was not found on PATH. Please install Pi and ensure `pi` is available.",
            error_class="missing_cli",
        )
    # JSON mode is non-interactive and returns machine-readable session events.
    # It follows target arguments so result parsing cannot be overridden.
    cmd = ["pi", "--approve", *params.args, "--mode", "json"]
    if params.SESSION_ID:
        cmd.extend(["--session", params.SESSION_ID])
    cmd.append(params.PROMPT)

    log.info(
        "pi.execute start cwd=%s session_id=%s prompt_len=%d args=%d timeout_s=%s",
        os.fspath(cd), params.SESSION_ID or "<new>",
        len(params.PROMPT), len(params.args), params.timeout_s or "<off>",
    )
    log.debug("pi command prepared args=%d", len(cmd))

    lines: list[str] = []
    timeout_error = ""
    try:
        for line in run_shell_command(
            cmd,
            cwd=os.fspath(cd),
            timeout_s=params.timeout_s,
            cancel_event=params.cancel_event,
        ):
            lines.append(line)
    except ShellCommandCancelled:
        timeout_error = "cancelled"
        log.warning("pi subprocess cancelled")
    except subprocess.TimeoutExpired as exc:
        timeout_error = f"timeout: {exc}"
        log.warning("pi subprocess timeout after %ss", params.timeout_s)
    except Exception as exc:  # noqa: BLE001
        timeout_error = f"unexpected: {exc}"
        log.exception("pi: unexpected error during stream")

    agent_messages, extracted_session_id, diagnostics = _extract_output(lines)
    session_id = extracted_session_id or params.SESSION_ID
    error_text = "\n".join(part for part in (timeout_error, diagnostics) if part).strip()
    result = classify_backend_output(
        backend_name="pi",
        agent_messages=agent_messages,
        session_id=session_id,
        error_text=error_text,
    )
    if timeout_error and result.outcome == "OK":
        result.outcome = "FATAL"
        result.error_class = "timeout"
        result.error = timeout_error
    if params.cancel_event is not None and params.cancel_event.is_set():
        result.outcome = "FATAL"
        result.error_class = "cancelled"
        result.error = "backend command cancelled"
    log.info(
        "pi.execute done outcome=%s session_id=%s error_class=%s msg_len=%d",
        result.outcome, result.SESSION_ID or "", result.error_class, len(result.agent_messages),
    )
    return result


async def execute(params: PiParams) -> BackendResult:
    """Execute Pi without blocking the daemon event loop."""
    return await asyncio.to_thread(_execute_sync, params)


__all__ = ["PiParams", "execute"]
