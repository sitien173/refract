"""Transport-agnostic agy backend extracted from agymcp."""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from refract.logging_setup import get_logger
from refract.processes import prepare_command
from refract.telemetry import TokenCounters

from . import AsyncEventHandler, BackendParams, BackendResult, classify_backend_output, parse_json_object, preflight
from ._common import EventBuffer, as_int, read_and_unlink, tool_started
from ._process import ProcessOutcome, run_process

log = get_logger("agy")

PROMPT_LIMIT_BYTES = 100 * 1024
WINDOWS_COMMAND_LINE_LIMIT_CHARS = 32767
_ASSISTANT_TEXT_DELTA = "assistant.text.delta"
_UUID_PATTERN = r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
_CONVERSATION_ID_RE = re.compile(rf"(?:Created|Streaming) conversation {_UUID_PATTERN}")


def _classify_output(agent_messages: str, session_id: str, error_text: str, model: str | None = None) -> BackendResult:
    result = classify_backend_output(
        backend_name="agy",
        agent_messages=agent_messages,
        session_id=session_id,
        error_text=error_text,
        model=model,
    )
    # Preserve historical "no_agent_messages" wording for back-compat with
    # tests that read the error string verbatim.
    if result.error_class == "no_agent_messages":
        extra = f" {error_text.strip()}" if error_text.strip() else ""
        result.error = f"Failed to get `agent_messages` from the agy session.{extra}".strip()
    return result


def _event_model(event: dict[str, Any]) -> str | None:
    """Return the model named by one event: its top-level ``model``, else its ``result.model``."""
    m = event.get("model")
    if isinstance(m, str) and m:
        return m
    res = event.get("result")
    if isinstance(res, dict):
        m = res.get("model")
        if isinstance(m, str) and m:
            return m
    return None


def _read_log(path: str) -> str:
    return read_and_unlink(Path(path), errors="ignore")


def _request_fatal(params: BackendParams, message: str) -> BackendResult:
    return BackendResult(
        outcome="FATAL",
        SESSION_ID=params.SESSION_ID,
        agent_messages="",
        error=message,
        error_class="request_fatal",
    )


class AgyRun:
    """Track agy's conversation, assistant text, and tool lifecycle with bounded state.

    Plain-text lines are kept only until the first JSON event arrives, because they are the
    reply only for a run that emits no events. Raw lines are never retained otherwise.
    """

    def __init__(self, params: BackendParams, on_event: AsyncEventHandler | None) -> None:
        self.params = params
        self.events = EventBuffer(on_event)
        self.tool_counter = 0
        self.step_counter = 0
        self.active_tool_id = ""
        self.assistant_deltas: list[str] = []
        self.terminal_lines: list[str] = []
        self.session_id = ""
        self.stream_session_id = ""
        self.final_response = ""
        self.counters = TokenCounters()
        self.model: str | None = None
        self.saw_event = False
        self.plain_lines: list[str] = []

    async def feed(self, line: str) -> None:
        stripped = line.strip()
        match = _CONVERSATION_ID_RE.search(stripped)
        if match and not self.stream_session_id:
            self.stream_session_id = match.group(1)
        event = parse_json_object(stripped)
        if event is None:
            if stripped and match is None and not self.saw_event:
                self.plain_lines.append(stripped)
        else:
            self.saw_event = True
            self.plain_lines.clear()
            model = _event_model(event)
            if model:
                self.model = model
            self._dispatch(event)
        await self.events.flush()

    def _emit(self, kind: str, entity_id: str, data: dict[str, Any]) -> None:
        self.events.emit({"kind": kind, "entity_id": entity_id, "data": data})

    def _start_tool(self, tool_name: str, tool_input: Any, has_input: bool) -> None:
        self.tool_counter += 1
        self.active_tool_id = f"tool-{self.tool_counter}"
        self.events.emit(tool_started(self.active_tool_id, "agy", tool_name, has_input=has_input, tool_input=tool_input))

    def _complete_tool(self, tool_data: dict[str, Any]) -> None:
        self._emit("tool.completed", self.active_tool_id or f"tool-{self.tool_counter or 1}", tool_data)
        self.active_tool_id = ""

    def _update_session(self, event: dict[str, Any]) -> None:
        conversation_id = event.get("conversation_id")
        if isinstance(conversation_id, str) and conversation_id:
            self.session_id = conversation_id

    def _append_delta(self, value: Any) -> None:
        if isinstance(value, str) and value:
            self.assistant_deltas.append(value)
            self._emit(_ASSISTANT_TEXT_DELTA, "msg-1", {"text": value})

    def _append_terminal(self, value: Any) -> None:
        if isinstance(value, str) and value:
            self.terminal_lines.append(value)

    def _tool_update(self, update: dict[str, Any]) -> None:
        tool_info = update.get("tool_info")
        if not isinstance(tool_info, dict):
            tool_info = {}
        state = update.get("state", "")
        if state == "ACTIVE":
            tool_name = str(update.get("tool_name", "") or tool_info.get("name", ""))
            self._start_tool(tool_name, tool_info.get("parameters"), "parameters" in tool_info)
        elif state == "DONE":
            tool_data: dict[str, Any] = {"status": "completed"}
            if "output" in tool_info:
                tool_data["output"] = tool_info["output"]
            self._complete_tool(tool_data)

    def _step_update(self, update: Any) -> None:
        if not isinstance(update, dict):
            return
        self._update_session(update)
        step_type = update.get("step_type", "")
        if step_type == "agent_response":
            self._append_delta(update.get("text_delta"))
        elif step_type == "tool":
            self._tool_update(update)

        state = update.get("state", "")
        u = update.get("usage")
        if state == "DONE" and isinstance(u, dict):
            raw_in = as_int(u.get("input_tokens"))
            raw_out = as_int(u.get("output_tokens"))
            cr = as_int(u.get("cache_read_tokens"))
            cw = as_int(u.get("cache_write_tokens"))
            if any(v is not None for v in (raw_in, raw_out, cr, cw)):
                norm_in = raw_in
                norm_out = raw_out
                self.step_counter += 1
                step_idx = update.get("step_index")
                step_id = f"step_{step_idx}" if step_idx is not None else f"step_{self.step_counter}"
                self.counters.record_response(
                    step_id,
                    input=norm_in,
                    output=norm_out,
                    cache_read=cr,
                    cache_write=cw,
                )
                win_size = as_int(
                    u.get("model_context_window")
                    or u.get("context_window_size")
                    or update.get("model_context_window")
                    or update.get("context_window_size")
                )
                if norm_in is not None and norm_out is not None:
                    try:
                        thinking = as_int(u.get("thinking_tokens"))
                        val = norm_in + norm_out - (thinking or 0)
                        if val >= 0:
                            self.counters.record_context(used=val)
                    except Exception:
                        pass
                if win_size is not None:
                    self.counters.record_context(window=win_size)
                if self.events.enabled:
                    self.events.emit({"kind": "telemetry.updated", "data": self.counters.as_dict()})

    def _result(self, result: Any) -> None:
        if not isinstance(result, dict):
            return
        self._update_session(result)
        response = result.get("response")
        if isinstance(response, str) and response:
            self.final_response = response
        u = result.get("usage")
        if isinstance(u, dict):
            raw_in = as_int(u.get("input_tokens"))
            raw_out = as_int(u.get("output_tokens"))
            cr = as_int(u.get("cache_read_tokens"))
            cw = as_int(u.get("cache_write_tokens"))
            if any(v is not None for v in (raw_in, raw_out, cr, cw)):
                norm_in = raw_in
                norm_out = raw_out
                self.counters.record_totals(
                    input=norm_in,
                    output=norm_out,
                    cache_read=cr,
                    cache_write=cw,
                )
                if self.events.enabled:
                    self.events.emit({"kind": "telemetry.updated", "data": self.counters.as_dict()})
            win_size = as_int(u.get("model_context_window") or u.get("context_window_size"))
            if win_size is not None:
                self.counters.record_context(window=win_size)
                if self.events.enabled:
                    self.events.emit({"kind": "telemetry.updated", "data": self.counters.as_dict()})

    def _legacy_tool_completed(self, event: dict[str, Any]) -> None:
        tool_data = {"status": str(event.get("status", "completed"))}
        if "output" in event:
            tool_data["output"] = event["output"]
        elif "result" in event:
            tool_data["output"] = event["result"]
        self._complete_tool(tool_data)

    def _legacy_event(self, event: dict[str, Any]) -> None:
        evt_type = event.get("type", "")
        if evt_type in {_ASSISTANT_TEXT_DELTA, "assistant.message.delta", "text_delta"}:
            value = event.get("text") if isinstance(event.get("text"), str) else event.get("delta")
            self._append_delta(value)
        elif evt_type in {"assistant.message", "assistant_message", "message"}:
            value = event.get("text") if isinstance(event.get("text"), str) else event.get("content")
            self._append_terminal(value)
        elif evt_type == "result":
            self._append_terminal(event.get("result"))
        elif evt_type in {"tool.started", "tool_started"}:
            tool_name = str(event.get("tool_name", "") or event.get("tool", ""))
            self._start_tool(tool_name, event.get("arguments"), "arguments" in event)
        elif evt_type in {"tool.completed", "tool_completed"}:
            self._legacy_tool_completed(event)

    def _dispatch(self, event: dict[str, Any]) -> None:
        self._update_session(event)
        current_evt = event.get("event", "")
        if current_evt == "step_update":
            self._step_update(event.get("step_update"))
        elif current_evt == "result":
            self._result(event.get("result"))
        else:
            self._legacy_event(event)

    def _agent_messages(self) -> str:
        if not self.saw_event:
            return "\n".join(self.plain_lines).strip()
        assistant_text = "".join(self.assistant_deltas).strip()
        terminal_text = "\n".join(self.terminal_lines).strip()
        if self.final_response:
            return self.final_response.strip()
        if assistant_text and terminal_text:
            return f"{assistant_text}\n\n{terminal_text}"
        return terminal_text or assistant_text

    def outcome(self, process: ProcessOutcome, log_text: str = "") -> BackendResult:
        """Normalize the parsed stream, the log file text, and the transport outcome into a backend result."""
        agent_messages = self._agent_messages()
        match = _CONVERSATION_ID_RE.search(log_text)
        session_id = match.group(1) if match else (self.stream_session_id or self.session_id or self.params.SESSION_ID)
        if session_id:
            log.info("agy: resolved session id: %s", session_id)
        else:
            log.warning("agy: no session id found in log or params")

        command_error, command_error_class = process.error, process.error_class
        if command_error_class == "timeout":
            command_error = f"agy subprocess timed out after {self.params.timeout_s}s"
        if command_error:
            result = BackendResult(
                outcome="FATAL",
                SESSION_ID=session_id,
                agent_messages=agent_messages,
                error=command_error,
                error_class=command_error_class,
                model=self.model,
            )
        else:
            result = _classify_output(agent_messages, session_id, "", model=self.model)
        result.tokens = self.counters.as_dict()
        return result


async def execute(
    params: BackendParams,
    *,
    cancel: asyncio.Event | None = None,
    on_event: AsyncEventHandler | None = None,
) -> BackendResult:
    """Execute one agy CLI session and return normalized backend result.

    A set ``on_event`` receives each normalized event in order. A set ``cancel`` kills the child process.
    The prompt is passed in argv, so prompts above ``PROMPT_LIMIT_BYTES`` fail before spawn,
    and on Windows so do command lines above ``WINDOWS_COMMAND_LINE_LIMIT_CHARS``.
    """
    cd, failure = preflight(params, "agy", "Antigravity CLI")
    if failure is not None:
        return failure
    try:
        prompt_bytes = len(params.PROMPT.encode("utf-8"))
    except UnicodeEncodeError as exc:
        return _request_fatal(params, f"prompt is not valid UTF-8: {exc}")
    if prompt_bytes > PROMPT_LIMIT_BYTES:
        return _request_fatal(
            params,
            f"agy prompt is {prompt_bytes} bytes, above the 100 KiB ({PROMPT_LIMIT_BYTES} bytes) limit for the prompt argument",
        )

    cwd = os.fspath(cd)
    log.info(
        "agy.execute start cwd=%s session_id=%s prompt_len=%d args=%d timeout_s=%s",
        cwd,
        params.SESSION_ID or "<new>",
        len(params.PROMPT),
        len(params.args),
        params.timeout_s or "<off>",
    )

    with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as tmp:
        tmp_log_path = tmp.name
    cmd = [
        "agy",
        "--dangerously-skip-permissions",
        *params.args,
        "--output-format",
        "stream-json",
    ]
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

    if os.name == "nt":
        # Measure the line CreateProcess receives: the resolved launcher after prepare_command, quoted as subprocess quotes it.
        try:
            command = prepare_command([shutil.which(cmd[0]) or cmd[0], *cmd[1:]])
        except OSError:
            command = cmd  # run_process reports the launcher failure
        line_chars = len(subprocess.list2cmdline(command))
        if line_chars > WINDOWS_COMMAND_LINE_LIMIT_CHARS:
            Path(tmp_log_path).unlink(missing_ok=True)
            return _request_fatal(
                params,
                f"agy command line is {line_chars} characters, above the Windows limit of {WINDOWS_COMMAND_LINE_LIMIT_CHARS} characters for a command line",
            )

    deadline = time.monotonic() + params.timeout_s if params.timeout_s and params.timeout_s > 0 else None
    run = AgyRun(params, on_event)
    process = await run_process(cmd, None, params.env, cwd, deadline, cancel, run.feed)
    result = run.outcome(process, _read_log(tmp_log_path))
    if cancel is not None and cancel.is_set():
        result.outcome = "FATAL"
        result.error_class = "cancelled"
        result.error = "backend command cancelled"

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


__all__ = ["execute"]
