"""Claude Code CLI backend using non-interactive print-mode JSON output."""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Generator
from typing import Any

from refract.logging_setup import get_logger

from . import BackendParams, BackendResult, _usage_dict, classify_backend_output, classify_tool_activity, preflight
from ._shell import StreamOutcome, consume_stream, stream_shell_command_lines

log = get_logger("claude")


def run_shell_command(
    cmd: list[str],
    cwd: str | None = None,
    timeout_s: int = 0,
    cancel_event: threading.Event | None = None,
    stdin_text: str | None = None,
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
        stdin_text=stdin_text,
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


def _unwrap(event: dict[str, Any]) -> dict[str, Any]:
    inner = event.get("event")
    return inner if event.get("type") == "stream_event" and isinstance(inner, dict) else event


def _final_result(stream: StreamOutcome) -> dict[str, Any] | None:
    final_result: dict[str, Any] | None = None
    for event in stream.objects():
        event = _unwrap(event)
        if event.get("type") == "result":
            final_result = event
    return final_result


def _extract_output(stream: StreamOutcome) -> tuple[str, str, str, str]:
    """Return the final reply, session ID, diagnostics, and result error."""
    diagnostics = [
        line.strip() for line, event in zip(stream.lines, stream.events)
        if event is None and line.strip()
    ]
    final_result = _final_result(stream)
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


def _usage_values(stream: StreamOutcome) -> dict[str, Any]:
    final_result = _final_result(stream)
    if final_result is None:
        return {}
    model_usage = final_result.get("modelUsage")
    model = next(iter(model_usage)) if isinstance(model_usage, dict) and model_usage else None
    stats = model_usage.get(model, {}) if model else {}
    usage = final_result.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    return {
        "model_name": model,
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "cached_input_tokens": usage.get("cache_read_input_tokens"),
        "context_window_max": stats.get("contextWindow") if isinstance(stats, dict) else None,
    }


class _EventParser:
    """Normalize Claude content blocks while tracking the active tool."""

    def __init__(self, params: BackendParams) -> None:
        self.params = params
        self.entity_counter = 0
        self.active_tool_id = ""

    def emit(self, event: dict[str, Any]) -> None:
        if self.params.emitter is not None:
            self.params.emitter(event)

    def text_delta(self, event: dict[str, Any]) -> None:
        delta = event.get("delta", {})
        if not isinstance(delta, dict) or delta.get("type") != "text_delta":
            return
        text = delta.get("text", "")
        if text:
            self.emit({
                "kind": "assistant.text.delta",
                "entity_id": f"msg-{event.get('index', 0)}",
                "data": {"text": text},
            })

    def start_tool(self, event: dict[str, Any]) -> None:
        cb = event.get("content_block", {})
        if not isinstance(cb, dict) or cb.get("type") != "tool_use":
            return
        self.entity_counter += 1
        self.active_tool_id = f"tool-{self.entity_counter}"
        tool_name = str(cb.get("name", ""))
        tool_data: dict[str, Any] = {
            "tool": tool_name,
            "activity": classify_tool_activity("claude", tool_name),
        }
        if "input" in cb:
            tool_data["input"] = cb["input"]
        self.emit({
            "kind": "tool.started",
            "entity_id": self.active_tool_id,
            "data": tool_data,
        })

    def complete_tool(self) -> None:
        if self.active_tool_id:
            self.emit({
                "kind": "tool.completed",
                "entity_id": self.active_tool_id,
                "data": {"status": "completed"},
            })
            self.active_tool_id = ""

    def on_event(self, raw_event: dict[str, Any]) -> None:
        if self.params.emitter is None:
            return
        event = _unwrap(raw_event)
        evt_type = event.get("type")
        if evt_type == "content_block_delta":
            self.text_delta(event)
        elif evt_type == "content_block_start":
            self.start_tool(event)
        elif evt_type == "content_block_stop":
            self.complete_tool()


def execute(params: BackendParams) -> BackendResult:
    """Execute a Claude Code print-mode session and normalize its result."""
    cd, failure = preflight(params, "claude", "Claude Code")
    if failure is not None:
        return failure

    cmd = [
        "claude",
        *params.args,
        "-p",
        "--permission-mode",
        "bypassPermissions",
    ]
    if params.emitter is not None:
        cmd.extend([
            "--output-format",
            "stream-json",
            "--include-partial-messages",
        ])
    else:
        cmd.extend([
            "--output-format",
            "json",
        ])
    if params.SESSION_ID:
        cmd.extend(["--resume", params.SESSION_ID])
    # The prompt goes on stdin: print mode reads it there when no prompt argument is given.

    log.info(
        "claude.execute start cwd=%s session_id=%s prompt_len=%d args=%d timeout_s=%s",
        os.fspath(cd),
        params.SESSION_ID or "<new>",
        len(params.PROMPT),
        len(params.args),
        params.timeout_s or "<off>",
    )
    log.debug("claude command prepared args=%d", len(cmd))

    parser = _EventParser(params)

    stream = consume_stream(
        run_shell_command, cmd, params, cwd=os.fspath(cd), name="claude", on_event=parser.on_event, stdin_text=params.PROMPT,
    )
    command_error, command_error_class = stream.error, stream.error_class
    agent_messages, extracted_session_id, diagnostics, result_error = _extract_output(stream)
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

    result.usage = _usage_dict(**_usage_values(stream))
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


__all__ = ["execute", "run_shell_command"]
