"""Transport-agnostic agy backend extracted from agymcp."""

from __future__ import annotations

import os
import re
import tempfile
import threading
from collections.abc import Generator
from pathlib import Path
from typing import Any

from . import BackendParams, BackendResult, _usage_dict, classify_backend_output, classify_tool_activity, preflight
from ._shell import StreamOutcome, consume_stream, stream_shell_command_lines
from refract.logging_setup import get_logger

log = get_logger("agy")

_ASSISTANT_TEXT_DELTA = "assistant.text.delta"
_UUID_PATTERN = r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
_CONVERSATION_ID_RE = re.compile(rf"(?:Created|Streaming) conversation {_UUID_PATTERN}")


def run_shell_command(
    cmd: list[str],
    cwd: str | None = None,
    timeout_s: int = 0,
    cancel_event: threading.Event | None = None,
    stdin_text: str | None = None,
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
        stdin_text=stdin_text,
    )


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


def _usage_values(stream: StreamOutcome) -> dict[str, Any]:
    usage_values: dict[str, Any] = {}
    for event in stream.objects():
        payload = event.get("result") if event.get("event") == "result" else None
        u = payload.get("usage") if isinstance(payload, dict) else None
        if isinstance(u, dict):
            usage_values = {"input_tokens": u.get("input_tokens"), "output_tokens": u.get("output_tokens"), "cached_input_tokens": u.get("cache_read_tokens")}
    return usage_values


def _read_log(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


class _EventParser:
    """Track agy's conversation, assistant text, and tool lifecycle."""

    def __init__(self, params: BackendParams) -> None:
        self.params = params
        self.tool_counter = 0
        self.active_tool_id = ""
        self.assistant_deltas: list[str] = []
        self.terminal_lines: list[str] = []
        self.session_id = ""
        self.final_response = ""

    def emit(self, kind: str, entity_id: str, data: dict[str, Any]) -> None:
        if self.params.emitter:
            self.params.emitter({"kind": kind, "entity_id": entity_id, "data": data})

    def start_tool(self, tool_name: str, tool_input: Any, has_input: bool) -> None:
        self.tool_counter += 1
        self.active_tool_id = f"tool-{self.tool_counter}"
        tool_data: dict[str, Any] = {
            "tool": tool_name,
            "activity": classify_tool_activity("agy", tool_name),
        }
        if has_input:
            tool_data["input"] = tool_input
        self.emit("tool.started", self.active_tool_id, tool_data)

    def complete_tool(self, tool_data: dict[str, Any]) -> None:
        self.emit("tool.completed", self.active_tool_id or f"tool-{self.tool_counter or 1}", tool_data)
        self.active_tool_id = ""

    def update_session(self, event: dict[str, Any]) -> None:
        conversation_id = event.get("conversation_id")
        if isinstance(conversation_id, str) and conversation_id:
            self.session_id = conversation_id

    def append_delta(self, value: Any) -> None:
        if isinstance(value, str) and value:
            self.assistant_deltas.append(value)
            self.emit(_ASSISTANT_TEXT_DELTA, "msg-1", {"text": value})

    def append_terminal(self, value: Any) -> None:
        if isinstance(value, str) and value:
            self.terminal_lines.append(value)

    def tool_update(self, update: dict[str, Any]) -> None:
        tool_info = update.get("tool_info")
        if not isinstance(tool_info, dict):
            tool_info = {}
        state = update.get("state", "")
        if state == "ACTIVE":
            tool_name = str(update.get("tool_name", "") or tool_info.get("name", ""))
            self.start_tool(tool_name, tool_info.get("parameters"), "parameters" in tool_info)
        elif state == "DONE":
            tool_data: dict[str, Any] = {"status": "completed"}
            if "output" in tool_info:
                tool_data["output"] = tool_info["output"]
            self.complete_tool(tool_data)

    def step_update(self, update: Any) -> None:
        if not isinstance(update, dict):
            return
        self.update_session(update)
        step_type = update.get("step_type", "")
        if step_type == "agent_response":
            self.append_delta(update.get("text_delta"))
        elif step_type == "tool":
            self.tool_update(update)

    def result(self, result: Any) -> None:
        if not isinstance(result, dict):
            return
        self.update_session(result)
        response = result.get("response")
        if isinstance(response, str) and response:
            self.final_response = response

    def legacy_tool_completed(self, event: dict[str, Any]) -> None:
        tool_data = {"status": str(event.get("status", "completed"))}
        if "output" in event:
            tool_data["output"] = event["output"]
        elif "result" in event:
            tool_data["output"] = event["result"]
        self.complete_tool(tool_data)

    def legacy_event(self, event: dict[str, Any]) -> None:
        evt_type = event.get("type", "")
        if evt_type in {_ASSISTANT_TEXT_DELTA, "assistant.message.delta", "text_delta"}:
            value = event.get("text") if isinstance(event.get("text"), str) else event.get("delta")
            self.append_delta(value)
        elif evt_type in {"assistant.message", "assistant_message", "message"}:
            value = event.get("text") if isinstance(event.get("text"), str) else event.get("content")
            self.append_terminal(value)
        elif evt_type == "result":
            self.append_terminal(event.get("result"))
        elif evt_type in {"tool.started", "tool_started"}:
            tool_name = str(event.get("tool_name", "") or event.get("tool", ""))
            self.start_tool(tool_name, event.get("arguments"), "arguments" in event)
        elif evt_type in {"tool.completed", "tool_completed"}:
            self.legacy_tool_completed(event)

    def on_event(self, event: dict[str, Any]) -> None:
        self.update_session(event)
        current_evt = event.get("event", "")
        if current_evt == "step_update":
            self.step_update(event.get("step_update"))
        elif current_evt == "result":
            self.result(event.get("result"))
        else:
            self.legacy_event(event)

    def agent_messages(self, stream: StreamOutcome) -> str:
        if not any(event is not None for event in stream.events):
            return "\n".join(
                line for line in stream.lines if line.strip() and not _CONVERSATION_ID_RE.search(line)
            ).strip()
        assistant_text = "".join(self.assistant_deltas).strip()
        terminal_text = "\n".join(self.terminal_lines).strip()
        if self.final_response:
            return self.final_response.strip()
        if assistant_text and terminal_text:
            return f"{assistant_text}\n\n{terminal_text}"
        return terminal_text or assistant_text


def execute(params: BackendParams) -> BackendResult:
    """Execute one agy CLI session and return normalized backend result."""
    cd, failure = preflight(params, "agy", "Antigravity CLI")
    if failure is not None:
        return failure

    cwd = os.fspath(cd)
    log.info(
        "agy.execute start cwd=%s session_id=%s prompt_len=%d args=%d",
        cwd,
        params.SESSION_ID or "<new>",
        len(params.PROMPT),
        len(params.args),
    )

    with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as tmp:
        tmp_log_path = tmp.name
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
    # Keep Refract-owned transport arguments after target arguments:
    # callers may tune the CLI, but cannot replace the prompt or log.
    cmd.extend(["--print", params.PROMPT])

    parser = _EventParser(params)
    stream = consume_stream(run_shell_command, cmd, params, cwd=cwd, name="agy", on_event=parser.on_event)
    log_text = _read_log(tmp_log_path)
    agent_messages = parser.agent_messages(stream)

    match = _CONVERSATION_ID_RE.search(log_text) or _CONVERSATION_ID_RE.search("\n".join(stream.lines))
    extracted_session_id = (
        match.group(1) if match else parser.session_id or params.SESSION_ID
    )
    if extracted_session_id:
        log.info("agy: resolved session id: %s", extracted_session_id)
    else:
        log.warning("agy: no session id found in log or params")

    if stream.error:
        return BackendResult(
            outcome="FATAL",
            SESSION_ID=extracted_session_id,
            agent_messages=agent_messages,
            error=stream.error,
            error_class=stream.error_class,
        )

    result = _classify_output(agent_messages, extracted_session_id, "")
    result.usage = _usage_dict(**_usage_values(stream))
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


__all__ = ["execute", "run_shell_command"]
