"""Claude Code CLI backend using non-interactive print-mode JSON output."""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

from refract.logging_setup import get_logger
from refract.telemetry import TokenCounters

from . import (
    AsyncEventHandler,
    BackendParams,
    BackendResult,
    classify_backend_output,
    parse_json_object,
    preflight,
)
from ._common import TokenUsage, as_int, is_fatal_line, read_usage, tool_started
from ._process import ProcessOutcome, run_process

log = get_logger("claude")

MAX_DIAGNOSTICS = 50
_RESULT_FIELDS = ("result", "session_id", "is_error", "subtype", "api_error_status", "modelUsage")
_NO_USAGE = TokenUsage(input=None, output=None, cache_read=None, cache_write=None, observed=False)
_TELEMETRY_UPDATED = "telemetry.updated"


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


class ClaudeRun:
    """Parse one Claude run line by line with bounded state. Raw lines are never retained.

    Diagnostics keep the first ``MAX_DIAGNOSTICS`` lines. The first fatal-token line is
    also kept when it falls beyond that bound, so the classification matches an unbounded run.
    """

    def __init__(self, params: BackendParams, on_event: AsyncEventHandler | None) -> None:
        self.params = params
        self.on_event = on_event
        self.entity_counter = 0
        self.active_tool_id = ""
        self.counters = TokenCounters()
        self.active_model: str = ""
        self.response_counter = 0
        self.diagnostics: list[str] = []
        self._fatal_diagnostic_kept = False
        self.result: dict[str, Any] | None = None

    async def feed(self, line: str) -> None:
        stripped = line.strip()
        event = parse_json_object(stripped)
        if event is None:
            if stripped:
                self._keep_diagnostic(stripped)
            return
        inner = _unwrap(event)
        if inner.get("type") == "result":
            self.result = {key: inner.get(key) for key in _RESULT_FIELDS}
        await self._parse(event)

    def _keep_diagnostic(self, line: str) -> None:
        fatal = not self._fatal_diagnostic_kept and is_fatal_line(line)
        if len(self.diagnostics) < MAX_DIAGNOSTICS or fatal:
            self.diagnostics.append(line)
            self._fatal_diagnostic_kept = self._fatal_diagnostic_kept or fatal

    async def _emit(self, event: dict[str, Any]) -> None:
        if self.on_event is not None:
            await self.on_event(event)

    async def _text_delta(self, event: dict[str, Any]) -> None:
        delta = event.get("delta", {})
        if not isinstance(delta, dict) or delta.get("type") != "text_delta":
            return
        text = delta.get("text", "")
        if text:
            await self._emit({
                "kind": "assistant.text.delta",
                "entity_id": f"msg-{event.get('index', 0)}",
                "data": {"text": text},
            })

    async def _start_tool(self, event: dict[str, Any]) -> None:
        cb = event.get("content_block", {})
        if not isinstance(cb, dict) or cb.get("type") != "tool_use":
            return
        self.entity_counter += 1
        self.active_tool_id = f"tool-{self.entity_counter}"
        tool_name = str(cb.get("name", ""))
        await self._emit(tool_started(self.active_tool_id, "claude", tool_name, has_input="input" in cb, tool_input=cb.get("input")))

    async def _complete_tool(self) -> None:
        if self.active_tool_id:
            await self._emit({
                "kind": "tool.completed",
                "entity_id": self.active_tool_id,
                "data": {"status": "completed"},
            })
            self.active_tool_id = ""

    async def _parse(self, raw_event: dict[str, Any]) -> None:
        event = _unwrap(raw_event)
        evt_type = event.get("type")

        if self.on_event is not None:
            if evt_type == "content_block_delta":
                await self._text_delta(event)
            elif evt_type == "content_block_start":
                await self._start_tool(event)
            elif evt_type == "content_block_stop":
                await self._complete_tool()

        if evt_type == "assistant":
            await self._assistant(event)
        elif evt_type == "result":
            await self._result(event)

    async def _assistant(self, event: dict[str, Any]) -> None:
        message = event.get("message")
        if not isinstance(message, dict):
            return
        model = message.get("model")
        if isinstance(model, str) and model:
            self.active_model = model
        msg_id = message.get("id")
        usage = message.get("usage")
        if not isinstance(usage, dict):
            return
        tok = read_usage(usage)
        if not tok.observed:
            return

        resp_id = str(msg_id) if msg_id else f"msg-{self.response_counter + 1}"
        self.response_counter += 1
        self.counters.record_response(
            resp_id,
            input=tok.input,
            output=tok.output,
            cache_read=tok.cache_read,
            cache_write=tok.cache_write,
        )
        if self.on_event is not None:
            await self._emit({"kind": _TELEMETRY_UPDATED, "data": self.counters.as_dict()})
        if tok.input is not None:
            self.counters.record_context(used=tok.input + (tok.output or 0))
            if self.on_event is not None:
                await self._emit({"kind": _TELEMETRY_UPDATED, "data": self.counters.as_dict()})

    def _context_capacity(self, event: dict[str, Any]) -> int | None:
        model_usage = event.get("modelUsage")
        if not isinstance(model_usage, dict):
            return None
        target_model = self.active_model
        if not target_model and len(model_usage) == 1:
            target_model = next(iter(model_usage))
        if not target_model or target_model not in model_usage:
            return None
        stats = model_usage[target_model]
        if not isinstance(stats, dict):
            return None
        cap = as_int(stats.get("contextWindow"))
        return cap if cap and cap > 0 else None

    async def _result(self, event: dict[str, Any]) -> None:
        capacity = self._context_capacity(event)

        usage = event.get("usage")
        tok = read_usage(usage) if isinstance(usage, dict) else _NO_USAGE
        if tok.observed:
            self.counters.record_totals(
                input=tok.input,
                output=tok.output,
                cache_read=tok.cache_read,
                cache_write=tok.cache_write,
            )
            if self.on_event is not None:
                await self._emit({"kind": _TELEMETRY_UPDATED, "data": self.counters.as_dict()})
        if capacity is not None:
            self.counters.record_context(window=capacity)
            if self.on_event is not None:
                await self._emit({"kind": _TELEMETRY_UPDATED, "data": self.counters.as_dict()})

    def _extract(self) -> tuple[str, str, str, str]:
        """Return the final reply, session ID, diagnostics, and result error."""
        diagnostics = "\n".join(self.diagnostics).strip()
        final = self.result
        if final is None:
            return "", "", diagnostics, ""

        agent_messages = _value_text(final.get("result"))
        session_id = final.get("session_id")
        if not isinstance(session_id, str):
            session_id = ""

        result_error = ""
        if final.get("is_error") or final.get("subtype") != "success":
            error_parts = [_value_text(final.get("result"))]
            status = _value_text(final.get("api_error_status"))
            if status:
                error_parts.append(f"api_error_status={status}")
            result_error = "\n".join(part for part in error_parts if part).strip()

        return agent_messages, session_id, diagnostics, result_error

    def _model(self) -> str | None:
        final = self.result
        if final is not None:
            model_usage = final.get("modelUsage")
            if isinstance(model_usage, dict) and model_usage:
                if self.active_model and self.active_model in model_usage:
                    return self.active_model
                first = next(iter(model_usage))
                if isinstance(first, str) and first:
                    return first
        return self.active_model or None

    def outcome(self, process: ProcessOutcome) -> BackendResult:
        """Normalize the parsed stream and the transport outcome into a backend result."""
        agent_messages, extracted_session_id, diagnostics, result_error = self._extract()
        session_id = extracted_session_id or self.params.SESSION_ID
        command_error, command_error_class = process.error, process.error_class
        if command_error_class == "timeout":
            command_error = f"claude subprocess timed out after {self.params.timeout_s}s"
        error_text = "\n".join(
            part for part in (command_error, diagnostics, result_error) if part
        ).strip()
        result = classify_backend_output(
            backend_name="claude",
            agent_messages=agent_messages,
            session_id=session_id,
            error_text=error_text,
            model=self._model(),
        )

        result.tokens = self.counters.as_dict()
        if result_error and not command_error:
            result.outcome = "FATAL"
            if result.error_class in {"", "warning", "no_agent_messages"}:
                result.error_class = "fatal_backend"
            result.error = result_error
        if command_error:
            result.outcome = "FATAL"
            result.error_class = command_error_class
            result.error = command_error
        return result


async def execute(
    params: BackendParams,
    *,
    cancel: asyncio.Event | None = None,
    on_event: AsyncEventHandler | None = None,
) -> BackendResult:
    """Execute a Claude Code print-mode session and normalize its result.

    A set ``on_event`` selects stream-json output and receives each normalized event in order.
    A set ``cancel`` kills the child process.
    """
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
    if on_event is not None:
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

    deadline = time.monotonic() + params.timeout_s if params.timeout_s and params.timeout_s > 0 else None
    run = ClaudeRun(params, on_event)
    process = await run_process(cmd, params.PROMPT, params.env, os.fspath(cd), deadline, cancel, run.feed)
    result = run.outcome(process)
    if cancel is not None and cancel.is_set():
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


__all__ = ["MAX_DIAGNOSTICS", "ClaudeRun", "execute"]
