"""Transport-agnostic agy backend extracted from agymcp."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from . import BackendResult, classify_backend_output
from ._shell import ShellCommandCancelled, stream_shell_command_lines
from openmcp.logging_setup import get_logger

log = get_logger("agy")

_BRAIN_PATH = Path.home() / ".gemini" / "antigravity-cli" / "brain"
_CONTINUE_PROMPT = "Continue your work. Complete any remaining `[ ]` task items."
_AGY_MAX_CONTINUATIONS = 3
_UNCHECKED_RE = re.compile(r"^\s*-\s*`?\[\s\]`?\s", re.MULTILINE)


@dataclass(slots=True)
class AgyParams:
    PROMPT: str
    cd: Path
    SESSION_ID: str = ""
    args: tuple[str, ...] = ()
    timeout_s: int = 0
    cancel_event: threading.Event | None = None


_UUID_PATTERN = r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
_CONVERSATION_ID_RE = re.compile(rf"(?:Created|Streaming) conversation {_UUID_PATTERN}")


def run_shell_command(
    cmd: list[str],
    cwd: str | None = None,
    timeout_s: int = 0,
    cancel_event: threading.Event | None = None,
) -> Generator[str, None, None]:
    """Execute a command and stream its output line-by-line (non-Windows / fallback)."""
    yield from stream_shell_command_lines(
        cmd,
        executable_name="agy",
        cwd=cwd,
        timeout_s=timeout_s,
        line_transform=lambda line: line.strip(),
        terminate_wait_s=10,
        suppress_stdout_close_errors=True,
        cancel_event=cancel_event,
    )


def _agy_has_pending_tasks(session_id: str, started_at: float) -> bool:
    """True iff task.md was created/updated this turn AND still has `[ ]` items."""
    if not session_id:
        return False
    task_path = _BRAIN_PATH / session_id / "task.md"
    meta_path = _BRAIN_PATH / session_id / "task.md.metadata.json"
    if not task_path.exists():
        return False

    updated_at: float | None = None
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            iso = str(meta.get("updatedAt", "")).strip()
            if iso:
                normalized = iso
                if normalized.endswith("Z"):
                    normalized = f"{normalized[:-1]}+00:00"
                normalized = re.sub(
                    r"\.(\d{6})\d+(?=(?:[+-]\d{2}:\d{2})$)",
                    r".\1",
                    normalized,
                )
                dt = datetime.fromisoformat(normalized)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                updated_at = dt.timestamp()
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            updated_at = None
    if updated_at is None:
        try:
            updated_at = task_path.stat().st_mtime
        except OSError:
            return False
    if updated_at < started_at - 2:
        return False
    try:
        content = task_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return bool(_UNCHECKED_RE.search(content))


def _classify_output(agent_messages: str, session_id: str, error_text: str) -> BackendResult:
    result = classify_backend_output(
        backend_name="agy",
        agent_messages=agent_messages,
        session_id=session_id,
        error_text=error_text,
    )
    # Preserve historical "no_agent_messages" wording for back-compat with
    # tests that read the error string verbatim.
    if result.error_class == "no_agent_messages":
        extra = f" {error_text.strip()}" if error_text.strip() else ""
        result.error = f"Failed to get `agent_messages` from the agy session.{extra}".strip()
    return result


def _execute_once(params: AgyParams) -> BackendResult:
    """Execute one agy CLI session and return normalized backend result."""
    cd = Path(params.cd).expanduser().absolute()
    if not cd.is_dir():
        return BackendResult(
            outcome="FATAL",
            SESSION_ID="",
            agent_messages="",
            error=f"The workspace root directory `{cd}` does not exist or is not a directory. Please check the path and try again.",
            error_class="bad_cd",
        )

    agy_binary = shutil.which("agy")
    if agy_binary is None:
        return BackendResult(
            outcome="FATAL",
            SESSION_ID="",
            agent_messages="",
            error="The `agy` CLI was not found on PATH. Please install Antigravity CLI and ensure `agy` is available.",
            error_class="missing_cli",
        )

    cwd = os.fspath(cd)
    error_text = ""
    execution_error = False
    agent_messages = ""
    log_text = ""

    log.info(
        "agy.execute start cwd=%s session_id=%s prompt_len=%d args=%d",
        cwd,
        params.SESSION_ID or "<new>",
        len(params.PROMPT),
        len(params.args),
    )

    try:
        with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as tmp:
            tmp_log_path = tmp.name
        try:
            cmd = [
                "agy",
                "--dangerously-skip-permissions",
                *params.args,
                "--log-file",
                tmp_log_path,
            ]
            if params.SESSION_ID:
                cmd.extend(["--conversation", params.SESSION_ID])
            # Keep OpenMCP-owned transport arguments after target arguments:
            # callers may tune the CLI, but cannot replace the prompt or log.
            cmd.extend(["--print", params.PROMPT])
            stdout_lines = list(
                run_shell_command(
                    cmd,
                    cwd=cwd,
                    timeout_s=params.timeout_s,
                    cancel_event=params.cancel_event,
                )
            )
            try:
                log_text = Path(tmp_log_path).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                log_text = ""
            # The CLI's actual reply is printed to stdout; --log-file only
            # captures internal server diagnostics (and, incidentally, the
            # "Created/Streaming conversation <id>" lines used below to
            # resolve the session id). Prefer stdout, fall back to the log
            # only if the CLI printed nothing there.
            stdout_text = "\n".join(stdout_lines).strip()
            agent_messages = stdout_text or log_text
        finally:
            try:
                os.unlink(tmp_log_path)
            except OSError:
                pass
    except ShellCommandCancelled:
        log.warning("agy subprocess cancelled")
        error_text = "backend command cancelled"
    except subprocess.TimeoutExpired as exc:
        log.warning("agy subprocess timeout after %ss", params.timeout_s)
        error_text = f"timeout: {exc}"
    except Exception as exc:  # noqa: BLE001
        # A subprocess exception may embed argv and therefore the prompt.
        log.error("agy: unexpected error during run type=%s", type(exc).__name__)
        error_text = str(exc)
        execution_error = True

    match = _CONVERSATION_ID_RE.search(log_text) or _CONVERSATION_ID_RE.search(agent_messages)
    extracted_session_id = match.group(1) if match else params.SESSION_ID
    if extracted_session_id:
        log.info("agy: resolved session id: %s", extracted_session_id)
    else:
        log.warning("agy: no session id found in log or params")

    if params.cancel_event is not None and params.cancel_event.is_set():
        return BackendResult(
            outcome="FATAL",
            SESSION_ID=extracted_session_id,
            agent_messages=agent_messages,
            error="backend command cancelled",
            error_class="cancelled",
        )

    if execution_error:
        return BackendResult(
            outcome="FATAL",
            SESSION_ID=extracted_session_id,
            agent_messages=agent_messages,
            error=error_text or "agy execution failed",
            error_class="execution_error",
        )

    result = _classify_output(agent_messages, extracted_session_id, error_text)
    log.info(
        "agy.execute done outcome=%s session_id=%s error_class=%s msg_len=%d",
        result.outcome,
        result.SESSION_ID or "",
        result.error_class,
        len(result.agent_messages),
    )
    if result.error:
        log.warning(
            "agy.execute returned error class=%s len=%d",
            result.error_class,
            len(result.error),
        )
    return result


def _execute_sync(params: AgyParams) -> BackendResult:
    """Execute an agy CLI session and continue while current-turn tasks remain pending."""
    outer_started_at = time.time()
    result = _execute_once(params)
    if result.outcome != "OK" or not result.SESSION_ID:
        return result

    merged_messages = result.agent_messages
    session_id = result.SESSION_ID
    continuations = 0
    while continuations < _AGY_MAX_CONTINUATIONS and _agy_has_pending_tasks(session_id, outer_started_at):
        continuations += 1
        log.info("agy: task.md has pending [ ] items; continuation %d/%d", continuations, _AGY_MAX_CONTINUATIONS)
        continue_started_at = time.time()
        continuation = _execute_once(
            AgyParams(
                PROMPT=_CONTINUE_PROMPT,
                cd=Path(params.cd),
                SESSION_ID=session_id,
                args=params.args,
                timeout_s=params.timeout_s,
                cancel_event=params.cancel_event,
            )
        )
        if continuation.outcome != "OK":
            log.warning("agy: continuation %d returned outcome=%s; stopping loop", continuations, continuation.outcome)
            result.agent_messages = (merged_messages + "\n\n" + (continuation.agent_messages or "")).strip()
            result.error = continuation.error or result.error
            return result
        if continuation.SESSION_ID:
            session_id = continuation.SESSION_ID
        merged_messages = (merged_messages + "\n\n" + continuation.agent_messages).strip()
        outer_started_at = continue_started_at

    if continuations and _agy_has_pending_tasks(session_id, outer_started_at):
        log.warning("agy: pending [ ] items remain after %d continuations; returning partial", continuations)

    result.agent_messages = merged_messages
    result.SESSION_ID = session_id
    return result


async def execute(params: AgyParams) -> BackendResult:
    """Execute agy without blocking the daemon event loop."""
    return await asyncio.to_thread(_execute_sync, params)


__all__ = ["AgyParams", "execute"]
