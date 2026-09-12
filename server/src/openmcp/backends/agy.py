"""Transport-agnostic agy backend extracted from agymcp."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable, Generator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import BackendResult, classify_backend_output
from ._shell import ShellCommandCancelled, ShellCommandFailed, stream_shell_command_lines
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
    emitter: Callable[[dict[str, Any]], None] | None = None


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
        check_returncode=True,
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


def _execute_once(params: AgyParams, entity_state: dict[str, int] | None = None) -> BackendResult:
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

    if entity_state is None:
        entity_state = {"assistant": 0, "tool": 0}
    entity_state["assistant"] += 1
    current_assistant_id = f"msg-{entity_state['assistant']}"
    active_tool_id = ""

    cwd = os.fspath(cd)
    error_text = ""
    execution_error = False
    timed_out = False
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
            ]
            if params.emitter is not None:
                cmd.extend(["--output-format", "stream-json"])
            cmd.extend([
                "--log-file",
                tmp_log_path,
            ])
            if params.SESSION_ID:
                cmd.extend(["--conversation", params.SESSION_ID])
            else:
                cmd.append("--new-project")
            # Keep OpenMCP-owned transport arguments after target arguments:
            # callers may tune the CLI, but cannot replace the prompt or log.
            cmd.extend(["--print", params.PROMPT])
            stdout_lines: list[str] = []
            assistant_deltas: list[str] = []
            terminal_lines: list[str] = []
            unstructured_lines: list[str] = []
            structured_detected = False

            for line in run_shell_command(
                cmd,
                cwd=cwd,
                timeout_s=params.timeout_s,
                cancel_event=params.cancel_event,
            ):
                stdout_lines.append(line)
                stripped = line.strip()
                if not stripped:
                    continue

                event = None
                try:
                    event = json.loads(stripped)
                except json.JSONDecodeError:
                    pass

                if isinstance(event, dict):
                    structured_detected = True
                    evt_type = event.get("type", "")
                    if evt_type in {"assistant.text.delta", "assistant.message.delta", "text_delta"}:
                        val = event.get("text") if isinstance(event.get("text"), str) else event.get("delta")
                        if isinstance(val, str) and val:
                            assistant_deltas.append(val)
                            if params.emitter:
                                params.emitter({
                                    "kind": "assistant.text.delta",
                                    "entity_id": current_assistant_id,
                                    "data": {"text": val},
                                })
                    elif evt_type in {"assistant.message", "assistant_message", "message"}:
                        val = event.get("text") if isinstance(event.get("text"), str) else event.get("content")
                        if isinstance(val, str) and val:
                            terminal_lines.append(val)
                    elif evt_type == "result":
                        val = event.get("result")
                        if isinstance(val, str) and val:
                            terminal_lines.append(val)
                    elif evt_type in {"tool.started", "tool_started"}:
                        entity_state["tool"] += 1
                        active_tool_id = f"tool-{entity_state['tool']}"
                        tool_name = str(event.get("tool_name", "") or event.get("tool", ""))
                        tool_data: dict[str, Any] = {"tool": tool_name}
                        if "arguments" in event:
                            tool_data["input"] = event["arguments"]
                        elif "input" in event:
                            tool_data["input"] = event["input"]
                        elif "args" in event:
                            tool_data["input"] = event["args"]
                        if params.emitter:
                            params.emitter({
                                "kind": "tool.started",
                                "entity_id": active_tool_id,
                                "data": tool_data,
                            })
                    elif evt_type in {"tool.completed", "tool_completed"}:
                        status = str(event.get("status", "completed"))
                        tool_data = {"status": status}
                        if "output" in event:
                            tool_data["output"] = event["output"]
                        elif "result" in event:
                            tool_data["output"] = event["result"]
                        if params.emitter:
                            params.emitter({
                                "kind": "tool.completed",
                                "entity_id": active_tool_id or f"tool-{entity_state['tool'] or 1}",
                                "data": tool_data,
                            })
                        active_tool_id = ""
                else:
                    if _CONVERSATION_ID_RE.search(line):
                        continue
                    unstructured_lines.append(line)

            try:
                log_text = Path(tmp_log_path).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                log_text = ""

            if structured_detected:
                assistant_text = "".join(assistant_deltas).strip()
                terminal_text = "\n".join(terminal_lines).strip()
                if assistant_text and terminal_text:
                    agent_messages = f"{assistant_text}\n\n{terminal_text}"
                else:
                    agent_messages = terminal_text or assistant_text
            else:
                agent_messages = "\n".join(unstructured_lines).strip()
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
        timed_out = True
    except ShellCommandFailed as exc:
        log.warning("agy subprocess exited with status %d", exc.returncode)
        error_text = str(exc)
        execution_error = True
    except Exception as exc:  # noqa: BLE001
        # A subprocess exception may embed argv and therefore the prompt.
        log.error("agy: unexpected error during run type=%s", type(exc).__name__)
        error_text = str(exc)
        execution_error = True

    stdout_raw = "\n".join(stdout_lines)
    match = _CONVERSATION_ID_RE.search(log_text) or _CONVERSATION_ID_RE.search(stdout_raw)
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

    if timed_out:
        return BackendResult(
            outcome="FATAL",
            SESSION_ID=extracted_session_id,
            agent_messages=agent_messages,
            error=error_text or "agy subprocess timed out",
            error_class="timeout",
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
    entity_state = {"assistant": 0, "tool": 0}
    sig = inspect.signature(_execute_once)
    supports_entity_state = (
        "entity_state" in sig.parameters
        or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
    )
    result = (
        _execute_once(params, entity_state=entity_state)
        if supports_entity_state
        else _execute_once(params)
    )
    if result.outcome != "OK" or not result.SESSION_ID:
        return result

    merged_messages = result.agent_messages
    session_id = result.SESSION_ID
    continuations = 0
    while continuations < _AGY_MAX_CONTINUATIONS and _agy_has_pending_tasks(session_id, outer_started_at):
        continuations += 1
        log.info("agy: task.md has pending [ ] items; continuation %d/%d", continuations, _AGY_MAX_CONTINUATIONS)
        continue_started_at = time.time()
        continuation_params = AgyParams(
            PROMPT=_CONTINUE_PROMPT,
            cd=Path(params.cd),
            SESSION_ID=session_id,
            args=params.args,
            timeout_s=params.timeout_s,
            cancel_event=params.cancel_event,
            emitter=params.emitter,
        )
        continuation = (
            _execute_once(continuation_params, entity_state=entity_state)
            if supports_entity_state
            else _execute_once(continuation_params)
        )
        if continuation.outcome != "OK":
            log.warning("agy: continuation %d returned outcome=%s; stopping loop", continuations, continuation.outcome)
            continuation.agent_messages = (
                merged_messages + "\n\n" + (continuation.agent_messages or "")
            ).strip()
            continuation.SESSION_ID = continuation.SESSION_ID or session_id
            return continuation
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
