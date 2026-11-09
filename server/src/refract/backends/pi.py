"""Pi CLI backend using Pi's non-interactive JSON event stream."""

from __future__ import annotations

import asyncio
import os
import re
import time
from typing import Any

from refract.logging_setup import get_logger
from refract.telemetry import TokenCounters

from . import AsyncEventHandler, BackendParams, BackendResult, classify_backend_output, parse_json_object, preflight
from ._common import EventBuffer, is_fatal_line, read_usage, tool_started
from ._process import ProcessOutcome, run_process

log = get_logger("pi")

MAX_DIAGNOSTICS = 50
_PI_USAGE_KEYS = {"input_key": "input", "output_key": "output", "cache_read_key": "cacheRead", "cache_write_key": "cacheWrite"}
_CONTEXT_OVERFLOW_PATTERN = re.compile(r"\bcontext_length_exceeded\b")


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


def _is_context_overflow(diagnostic: str) -> bool:
    """Return True if diagnostic material matches the confirmed context overflow signature."""
    if not diagnostic:
        return False
    return bool(_CONTEXT_OVERFLOW_PATTERN.search(diagnostic))


def _event_model(event: dict[str, Any]) -> str | None:
    """Return the model named by one event: its assistant message, else its last assistant message."""
    msg = event.get("message")
    if isinstance(msg, dict) and msg.get("role") == "assistant":
        model = msg.get("model")
        if isinstance(model, str) and model:
            return model
    messages = event.get("messages")
    if isinstance(messages, list):
        for m in reversed(messages):
            if isinstance(m, dict) and m.get("role") == "assistant":
                model = m.get("model")
                if isinstance(model, str) and model:
                    return model
    return None


def _tool_call_id(event: dict[str, Any]) -> str:
    return str(event.get("toolCallId") or event.get("tool_call_id") or event.get("id") or "")


class PiRun:
    """Parse one Pi run line by line with bounded diagnostics. Raw lines are never retained.

    Diagnostics keep the first ``MAX_DIAGNOSTICS`` lines. The first fatal-token line and the first
    context-overflow line are also kept when they fall beyond that bound, so classification
    matches an unbounded run. Response IDs are kept only for usage de-duplication.
    """

    def __init__(self, params: BackendParams, on_event: AsyncEventHandler | None) -> None:
        self.params = params
        self.events = EventBuffer(on_event)
        self.session_id = ""
        self.agent_message = ""
        self.structured_error = ""
        self.diagnostics: list[str] = []
        self._fatal_kept = False
        self._overflow_kept = False
        self.model: str | None = None
        self.entity_counter = 0
        self.raw_to_entity: dict[str, str] = {}
        self.counters = TokenCounters()
        self.recorded_responses: set[str] = set()
        self.turn_counter = 0
        self.turn_completed_in_current_turn = False

    async def feed(self, line: str) -> None:
        event = parse_json_object(line.strip())
        if event is None:
            if line.strip():
                self._keep_diagnostic(line)
        else:
            model = _event_model(event)
            if model:
                self.model = model
            self._output(event)
            self._telemetry(event)
        await self.events.flush()

    def _keep_diagnostic(self, text: str) -> None:
        fatal = not self._fatal_kept and is_fatal_line(text)
        overflow = not self._overflow_kept and _is_context_overflow(text)
        if len(self.diagnostics) < MAX_DIAGNOSTICS or fatal or overflow:
            self.diagnostics.append(text)
            self._fatal_kept = self._fatal_kept or fatal
            self._overflow_kept = self._overflow_kept or overflow

    def _record_message_error(self, message: Any) -> None:
        if not isinstance(message, dict) or message.get("stopReason") != "error":
            return
        error = message.get("errorMessage")
        if isinstance(error, str) and error:
            self._keep_diagnostic(error)
            self.structured_error = error
        else:
            self.structured_error = "error"

    def _message_end(self, message: Any) -> None:
        text = _message_text(message)
        if text:
            self.agent_message = text
        self._record_message_error(message)

    def _agent_end(self, messages: Any) -> None:
        if not isinstance(messages, list):
            return
        for message in reversed(messages):
            if not self.structured_error:
                self._record_message_error(message)
            text = _message_text(message)
            if text:
                self.agent_message = text
                break

    def _output(self, event: dict[str, Any]) -> None:
        """Collect the final reply, session ID, and error diagnostics from one event."""
        event_type = event.get("type")
        if event_type == "session" and isinstance(event.get("id"), str):
            self.session_id = event["id"]
        if event_type in {"message_end", "message"}:
            self._message_end(event.get("message"))
        if event_type == "agent_end":
            self._agent_end(event.get("messages"))
        if event_type in {"error", "server_error"}:
            error = event.get("error") or event.get("message")
            if isinstance(error, str) and error:
                self._keep_diagnostic(error)

    def _telemetry(self, event: dict[str, Any]) -> None:
        event_type = event.get("type", "")
        if self.events.enabled:
            if event_type == "message_update":
                self._message_update(event)
            elif event_type == "text_delta":
                text = event.get("text")
                self._emit_text(text if isinstance(text, str) else event.get("delta"))
            elif event_type in {"tool_execution_start", "tool_call"}:
                self._start_tool(event)
            elif event_type in {"tool_execution_end", "tool_result"}:
                self._complete_tool(event)

        if event_type == "turn_start":
            self.turn_counter += 1
            self.turn_completed_in_current_turn = False
        elif event_type in ("message_end", "turn_end"):
            self._message_usage(event.get("message"))
        elif event_type in ("agent_end", "summary"):
            self._summary_usage(event.get("usage") or event.get("totalUsage"))

    def _emit(self, event: dict[str, Any]) -> None:
        self.events.emit(event)

    def _emit_text(self, text: Any) -> None:
        if isinstance(text, str) and text:
            self._emit({
                "kind": "assistant.text.delta",
                "entity_id": "msg-1",
                "data": {"text": text},
            })

    def _message_update(self, event: dict[str, Any]) -> None:
        update = event.get("assistantMessageEvent")
        if not isinstance(update, dict) or update.get("type") != "text_delta":
            return
        delta = update.get("delta")
        self._emit_text(delta if isinstance(delta, str) else update.get("text"))

    def _start_tool(self, event: dict[str, Any]) -> None:
        self.entity_counter += 1
        raw_id = _tool_call_id(event)
        entity_id = f"tool-{self.entity_counter}"
        if raw_id:
            self.raw_to_entity[raw_id] = entity_id
        tool_name = str(event.get("toolName") or event.get("tool_name") or event.get("tool") or event.get("name") or "")
        self._emit(tool_started(entity_id, "pi", tool_name, has_input="args" in event, tool_input=event.get("args")))

    def _complete_tool(self, event: dict[str, Any]) -> None:
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
        self._emit({
            "kind": "tool.completed",
            "entity_id": entity_id,
            "data": tool_data,
        })

    def _message_usage(self, msg: Any) -> None:
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            return
        resp_id = str(msg.get("responseId") or msg.get("id") or "")
        if resp_id:
            if resp_id in self.recorded_responses:
                return
            assigned_id = resp_id
        else:
            if self.turn_counter == 0:
                self.turn_counter = 1
                self.turn_completed_in_current_turn = False
            elif self.turn_completed_in_current_turn:
                return
            assigned_id = f"turn_{self.turn_counter}"
            if assigned_id in self.recorded_responses:
                return

        self.recorded_responses.add(assigned_id)
        self.turn_completed_in_current_turn = True

        u = msg.get("usage")
        if not isinstance(u, dict):
            return
        tok = read_usage(u, **_PI_USAGE_KEYS)
        if not tok.observed:
            return
        self.counters.record_response(
            assigned_id,
            input=tok.input,
            output=tok.output,
            cache_read=tok.cache_read,
            cache_write=tok.cache_write,
        )
        if tok.input is not None:
            self.counters.record_context(used=tok.input + (tok.output or 0))
        self._emit({"kind": "telemetry.updated", "data": self.counters.as_dict()})

    def _summary_usage(self, u: Any) -> None:
        if not isinstance(u, dict):
            return
        tok = read_usage(u, **_PI_USAGE_KEYS)
        if not tok.observed:
            return
        self.counters.record_totals(
            input=tok.input,
            output=tok.output,
            cache_read=tok.cache_read,
            cache_write=tok.cache_write,
        )
        self._emit({"kind": "telemetry.updated", "data": self.counters.as_dict()})

    def _apply_errors(self, result: BackendResult, command_error: str, command_error_class: str, error_text: str) -> None:
        # Precedence 1: Cancellation remains cancelled
        if command_error_class == "cancelled":
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
        elif self.structured_error:
            if result.outcome == "OK":
                result.outcome = "FATAL"
                result.error_class = command_error_class or "execution_error"
                result.error = self.structured_error or error_text
            elif command_error:
                result.outcome = "FATAL"
                result.error_class = command_error_class
                result.error = command_error
        # Precedence 5: Ordinary process failures remain execution_error
        elif command_error and result.outcome == "OK":
            result.outcome = "FATAL"
            result.error_class = command_error_class
            result.error = command_error

    def outcome(self, process: ProcessOutcome) -> BackendResult:
        """Normalize the parsed stream and the transport outcome into a backend result."""
        command_error, command_error_class = process.error, process.error_class
        if command_error_class == "timeout":
            command_error = f"pi subprocess timed out after {self.params.timeout_s}s"
        diagnostics = "\n".join(self.diagnostics).strip()
        session_id = self.session_id or self.params.SESSION_ID
        error_text = "\n".join(part for part in (command_error, diagnostics) if part).strip()
        result = classify_backend_output(
            backend_name="pi",
            agent_messages=self.agent_message,
            session_id=session_id,
            error_text=error_text,
            model=self.model,
        )

        result.tokens = self.counters.as_dict()
        self._apply_errors(result, command_error, command_error_class, error_text)
        return result


async def execute(
    params: BackendParams,
    *,
    cancel: asyncio.Event | None = None,
    on_event: AsyncEventHandler | None = None,
) -> BackendResult:
    """Execute a Pi non-interactive session and return a normalized result.

    A set ``on_event`` receives each normalized event in order. A set ``cancel`` kills the child process.
    """
    cd, failure = preflight(params, "pi", "Pi")
    if failure is not None:
        return failure
    # JSON mode is non-interactive and returns machine-readable session events.
    # It follows target arguments so result parsing cannot be overridden.
    cmd = ["pi", *params.args, "--mode", "json"]
    if params.SESSION_ID:
        cmd.extend(["--session", params.SESSION_ID])
    # The prompt goes on stdin: Pi reads piped stdin when no prompt argument is given.

    log.info(
        "pi.execute start cwd=%s session_id=%s prompt_len=%d args=%d timeout_s=%s",
        os.fspath(cd), params.SESSION_ID or "<new>",
        len(params.PROMPT), len(params.args), params.timeout_s or "<off>",
    )
    log.debug("pi command prepared args=%d", len(cmd))

    deadline = time.monotonic() + params.timeout_s if params.timeout_s and params.timeout_s > 0 else None
    run = PiRun(params, on_event)
    process = await run_process(cmd, params.PROMPT, params.env, os.fspath(cd), deadline, cancel, run.feed)
    result = run.outcome(process)
    if cancel is not None and cancel.is_set():
        result.outcome = "FATAL"
        result.error_class = "cancelled"
        result.error = "backend command cancelled"

    log.info(
        "pi.execute done outcome=%s session_id=%s error_class=%s msg_len=%d",
        result.outcome, result.SESSION_ID or "", result.error_class, len(result.agent_messages),
    )
    return result


__all__ = ["execute"]
