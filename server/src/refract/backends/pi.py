"""Pi CLI backend using Pi's non-interactive JSON event stream."""

from __future__ import annotations

import os
import re
import threading
from collections.abc import Generator
from typing import Any

from . import BackendParams, BackendResult, _usage_dict, classify_backend_output, classify_tool_activity, preflight
from ._shell import StreamOutcome, consume_stream, stream_shell_command_lines
from refract.logging_setup import get_logger

log = get_logger("pi")


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
        check_returncode=True,
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


_CONTEXT_OVERFLOW_PATTERN = re.compile(r"\bcontext_length_exceeded\b")


def _is_context_overflow(diagnostic: str) -> bool:
    """Return True if diagnostic material matches the confirmed context overflow signature."""
    if not diagnostic:
        return False
    return bool(_CONTEXT_OVERFLOW_PATTERN.search(diagnostic))


class _OutputParser:
    """Collect final replies and errors without mixing diagnostic output."""

    def __init__(self) -> None:
        self.session_id = ""
        self.agent_message = ""
        self.diagnostics: list[str] = []
        self.structured_error = ""

    def record_message_error(self, message: Any) -> None:
        if not isinstance(message, dict) or message.get("stopReason") != "error":
            return
        error = message.get("errorMessage")
        if isinstance(error, str) and error:
            self.diagnostics.append(error)
            self.structured_error = error
        else:
            self.structured_error = "error"

    def message_end(self, message: Any) -> None:
        text = _message_text(message)
        if text:
            self.agent_message = text
        self.record_message_error(message)

    def agent_end(self, messages: Any) -> None:
        if not isinstance(messages, list):
            return
        for message in reversed(messages):
            if not self.structured_error:
                self.record_message_error(message)
            text = _message_text(message)
            if text:
                self.agent_message = text
                break

    def on_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        if event_type == "session" and isinstance(event.get("id"), str):
            self.session_id = event["id"]
        if event_type in {"message_end", "message"}:
            self.message_end(event.get("message"))
        if event_type == "agent_end":
            self.agent_end(event.get("messages"))
        if event_type in {"error", "server_error"}:
            error = event.get("error") or event.get("message")
            if isinstance(error, str) and error:
                self.diagnostics.append(error)


def _extract_output(stream: StreamOutcome) -> tuple[str, str, str, str]:
    """Return Pi's final reply, session ID, non-JSON/error output, and structured error."""
    parser = _OutputParser()
    for line, event in zip(stream.lines, stream.events):
        if event is None:
            if line.strip():
                parser.diagnostics.append(line)
        else:
            parser.on_event(event)
    return parser.agent_message, parser.session_id, "\n".join(parser.diagnostics).strip(), parser.structured_error


def _usage_values(stream: StreamOutcome) -> dict[str, Any]:
    usage_values: dict[str, Any] = {}
    for event in stream.objects():
        msg = event.get("message")
        u = msg.get("usage") if isinstance(msg, dict) else None
        if isinstance(msg, dict) and isinstance(u, dict) and msg.get("role") == "assistant":
            usage_values = {"model_name": msg.get("model"), "input_tokens": u.get("input"), "output_tokens": u.get("output"), "cached_input_tokens": u.get("cacheRead")}
    return usage_values


def _tool_call_id(event: dict[str, Any]) -> str:
    return str(event.get("toolCallId") or event.get("tool_call_id") or event.get("id") or "")


class _EventParser:
    """Normalize Pi text deltas and correlate tool lifecycle events."""

    def __init__(self, params: BackendParams) -> None:
        self.params = params
        self.entity_counter = 0
        self.raw_to_entity: dict[str, str] = {}

    def emit(self, event: dict[str, Any]) -> None:
        if self.params.emitter is not None:
            self.params.emitter(event)

    def emit_text(self, text: Any) -> None:
        if isinstance(text, str) and text:
            self.emit({
                "kind": "assistant.text.delta",
                "entity_id": "msg-1",
                "data": {"text": text},
            })

    def message_update(self, event: dict[str, Any]) -> None:
        update = event.get("assistantMessageEvent")
        if not isinstance(update, dict) or update.get("type") != "text_delta":
            return
        delta = update.get("delta")
        self.emit_text(delta if isinstance(delta, str) else update.get("text"))

    def start_tool(self, event: dict[str, Any]) -> None:
        self.entity_counter += 1
        raw_id = _tool_call_id(event)
        entity_id = f"tool-{self.entity_counter}"
        if raw_id:
            self.raw_to_entity[raw_id] = entity_id
        tool_name = str(event.get("toolName") or event.get("tool_name") or event.get("tool") or event.get("name") or "")
        tool_data: dict[str, Any] = {
            "tool": tool_name,
            "activity": classify_tool_activity("pi", tool_name),
        }
        if "args" in event:
            tool_data["input"] = event["args"]
        self.emit({
            "kind": "tool.started",
            "entity_id": entity_id,
            "data": tool_data,
        })

    def complete_tool(self, event: dict[str, Any]) -> None:
        entity_id = self.raw_to_entity.get(_tool_call_id(event)) or f"tool-{self.entity_counter or 1}"
        is_error = event.get("isError")
        if is_error is True:
            status = "error"
        elif is_error is False:
            status = "completed"
        else:
            status = str(event.get("status", "completed"))
        tool_data: dict[str, Any] = {"status": status}
        if "result" in event:
            tool_data["output"] = event["result"]
        self.emit({
            "kind": "tool.completed",
            "entity_id": entity_id,
            "data": tool_data,
        })

    def on_event(self, event: dict[str, Any]) -> None:
        if self.params.emitter is None:
            return
        event_type = event.get("type", "")
        if event_type == "message_update":
            self.message_update(event)
        elif event_type == "text_delta":
            text = event.get("text")
            self.emit_text(text if isinstance(text, str) else event.get("delta"))
        elif event_type in {"tool_execution_start", "tool_call"}:
            self.start_tool(event)
        elif event_type in {"tool_execution_end", "tool_result"}:
            self.complete_tool(event)


def _apply_errors(
    result: BackendResult,
    params: BackendParams,
    stream: StreamOutcome,
    error_text: str,
    structured_error: str,
) -> None:
    command_error, command_error_class = stream.error, stream.error_class
    # Precedence 1: Cancellation remains cancelled
    if (params.cancel_event is not None and params.cancel_event.is_set()) or command_error_class == "cancelled":
        result.outcome = "FATAL"
        result.error_class = "cancelled"
        result.error = "backend command cancelled"
    # Precedence 2: Confirmed context overflow becomes context_overflow (overrides execution_error & partial output)
    elif _is_context_overflow(error_text):
        result.outcome = "FATAL"
        result.error_class = "context_overflow"
        result.error = error_text or "context_length_exceeded"
    # Precedence 3: Existing fatal authentication and model handling remains unchanged (fatal_backend)
    elif result.error_class == "fatal_backend":
        pass
    # Precedence 4: Other structured assistant failures remain failures (partial text cannot hide failure)
    elif structured_error:
        if result.outcome == "OK":
            result.outcome = "FATAL"
            result.error_class = command_error_class or "execution_error"
            result.error = structured_error or error_text
        elif command_error:
            result.outcome = "FATAL"
            result.error_class = command_error_class
            result.error = command_error
    # Precedence 5: Ordinary process failures remain execution_error
    elif command_error and result.outcome == "OK":
        result.outcome = "FATAL"
        result.error_class = command_error_class
        result.error = command_error


def execute(params: BackendParams) -> BackendResult:
    """Execute a Pi non-interactive session and return a normalized result."""
    cd, failure = preflight(params, "pi", "Pi")
    if failure is not None:
        return failure
    # JSON mode is non-interactive and returns machine-readable session events.
    # It follows target arguments so result parsing cannot be overridden.
    cmd = ["pi", *params.args, "--mode", "json"]
    if params.SESSION_ID:
        cmd.extend(["--session", params.SESSION_ID])
    cmd.append(params.PROMPT)

    log.info(
        "pi.execute start cwd=%s session_id=%s prompt_len=%d args=%d timeout_s=%s",
        os.fspath(cd), params.SESSION_ID or "<new>",
        len(params.PROMPT), len(params.args), params.timeout_s or "<off>",
    )
    log.debug("pi command prepared args=%d", len(cmd))

    parser = _EventParser(params)
    stream = consume_stream(run_shell_command, cmd, params, cwd=os.fspath(cd), name="pi", on_event=parser.on_event)
    command_error = stream.error
    agent_messages, extracted_session_id, diagnostics, structured_error = _extract_output(stream)
    session_id = extracted_session_id or params.SESSION_ID
    error_text = "\n".join(part for part in (command_error, diagnostics) if part).strip()
    result = classify_backend_output(
        backend_name="pi",
        agent_messages=agent_messages,
        session_id=session_id,
        error_text=error_text,
    )

    result.usage = _usage_dict(**_usage_values(stream))
    _apply_errors(result, params, stream, error_text, structured_error)
    log.info(
        "pi.execute done outcome=%s session_id=%s error_class=%s msg_len=%d",
        result.outcome, result.SESSION_ID or "", result.error_class, len(result.agent_messages),
    )
    return result


__all__ = ["execute", "run_shell_command"]
