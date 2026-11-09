"""Codex CLI backend: Codex JSONL on stdout, the final message in a file, and an exact session ID."""

from __future__ import annotations

import asyncio
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any

from refract.logging_setup import get_logger
from refract.telemetry import TokenCounters

from . import AsyncEventHandler, BackendParams, BackendResult, classify_backend_output, classify_tool_activity, parse_json_object, preflight
from ._common import EventBuffer, as_int, is_fatal_line, read_and_unlink
from ._process import ProcessOutcome, run_process
from .codex_rollout import _CodexRolloutCollector

log = get_logger("codex")

MAX_DIAGNOSTICS = 50
_SESSION_ID_STDOUT_RE = re.compile(
    r"^\s*session id:\s*([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _session_id_line(text: str) -> str:
    """Return the ID of the first ``session id: <uuid>`` line in ``text``, or ""."""
    match = _SESSION_ID_STDOUT_RE.search(text)
    return match.group(1) if match else ""


def _resolve_session_id(thread_session_id: str, last_message: str, stdout_session_id: str) -> tuple[str, str]:
    """Return the first exact session ID and its source. No exact source returns ("", "")."""
    candidates = (
        ("stdout-jsonl:thread.started", thread_session_id.strip()),
        ("last-message:session-id-line", _session_id_line(last_message)),
        ("stdout:session-id-line", stdout_session_id),
    )
    for source, value in candidates:
        if value:
            return value, source
    return "", ""


def _classify(*, agent_messages: str, session_id: str, error_text: str, model: str | None) -> BackendResult:
    """Classify a codex run. Empty output without a fatal token is ``request_fatal``, never the raw stream."""
    result = classify_backend_output(
        backend_name="codex",
        agent_messages=agent_messages,
        session_id=session_id,
        error_text=error_text,
        model=model,
    )
    if result.error_class == "no_agent_messages":
        return BackendResult(
            outcome="FATAL",
            SESSION_ID=session_id,
            agent_messages="",
            error="no agent message",
            error_class="request_fatal",
            model=model,
        )
    return result


class CodexRun:
    """Parse one Codex run line by line with bounded state. Raw lines are never retained.

    The answer is the last-message file when it has text, else the concatenated ``agent_message``
    items. Diagnostics keep the first ``MAX_DIAGNOSTICS`` non-JSON lines and the first fatal-token
    line, so classification matches an unbounded run when there is no agent output.
    """

    def __init__(self, params: BackendParams, cwd: Path, last_message_path: Path, on_event: AsyncEventHandler | None) -> None:
        self.params = params
        self.last_message_path = last_message_path
        self.events = EventBuffer(on_event)
        self.thread_session_id = ""
        self.stdout_session_id = ""
        self.agent_messages: list[str] = []
        self.diagnostics: list[str] = []
        self._fatal_kept = False
        self.entity_counter = 0
        self.raw_to_entity: dict[str, str] = {}
        self.counters = TokenCounters()
        self.turn_counter = 0
        self.collector = _CodexRolloutCollector(
            cwd=cwd,
            session_id=str(params.SESSION_ID or ""),
            counters=self.counters,
            emitter=self.events.emit,
        )

    async def feed(self, line: str) -> None:
        if not self.stdout_session_id:
            self.stdout_session_id = _session_id_line(line)
        event = parse_json_object(line)
        if event is None:
            if line.strip():
                self._keep_diagnostic(line)
        else:
            self._on_event(event)
        await self.events.flush()

    def _keep_diagnostic(self, text: str) -> None:
        fatal = not self._fatal_kept and is_fatal_line(text)
        if len(self.diagnostics) < MAX_DIAGNOSTICS or fatal:
            self.diagnostics.append(text)
            self._fatal_kept = self._fatal_kept or fatal

    def _start_item(self, item: dict[str, Any], raw_id: str) -> None:
        item_type = item.get("type", "")
        if item_type == "agent_message":
            self.entity_counter += 1
            entity_id = f"msg-{self.entity_counter}"
            if raw_id:
                self.raw_to_entity[raw_id] = entity_id
            self.events.emit({
                "kind": "assistant.message.started",
                "entity_id": entity_id,
                "data": {},
            })
        elif item_type == "tool_call":
            self.entity_counter += 1
            entity_id = f"tool-{self.entity_counter}"
            if raw_id:
                self.raw_to_entity[raw_id] = entity_id
            tool_name = str(item.get("name", ""))
            tool_data: dict[str, Any] = {
                "tool": tool_name,
                "activity": classify_tool_activity("codex", tool_name),
            }
            if "input" in item:
                tool_data["input"] = item["input"]
            self.events.emit({
                "kind": "tool.started",
                "entity_id": entity_id,
                "data": tool_data,
            })

    def _complete_item(self, item: dict[str, Any], raw_id: str) -> None:
        item_type = item.get("type", "")
        if item_type == "agent_message":
            if item.get("text"):
                self.agent_messages.append(str(item.get("text")))
            entity_id = self.raw_to_entity.get(raw_id) or f"msg-{self.entity_counter or 1}"
            msg_text = str(item.get("text", ""))
            if msg_text:
                self.events.emit({
                    "kind": "assistant.text.delta",
                    "entity_id": entity_id,
                    "data": {"text": msg_text},
                })
            self.events.emit({
                "kind": "assistant.message.completed",
                "entity_id": entity_id,
                "data": {},
            })
        elif item_type == "tool_call":
            entity_id = self.raw_to_entity.get(raw_id) or f"tool-{self.entity_counter or 1}"
            tool_data = {"status": str(item.get("status", "completed"))}
            if "output" in item:
                tool_data["output"] = item["output"]
            self.events.emit({
                "kind": "tool.completed",
                "entity_id": entity_id,
                "data": tool_data,
            })

    def _on_event(self, parsed: dict[str, Any]) -> None:
        event_type = parsed.get("type", "")
        if event_type == "thread.started" and parsed.get("thread_id"):
            self.thread_session_id = str(parsed.get("thread_id"))
            self.collector.set_session_id(str(parsed.get("thread_id")))
        self.collector.poll()

        item = parsed.get("item", {})
        if isinstance(item, dict):
            raw_id = str(item.get("id", ""))
            if event_type == "item.started":
                self._start_item(item, raw_id)
            elif event_type == "item.completed":
                self._complete_item(item, raw_id)

        if event_type == "turn.completed":
            self.collector.poll()
            u = parsed.get("usage")
            if isinstance(u, dict):
                try:
                    raw_in = as_int(u.get("input_tokens"))
                    cached_in = as_int(u.get("cached_input_tokens"))
                    cw = as_int(u.get("cache_write_input_tokens"))
                    raw_out = as_int(u.get("output_tokens"))
                    reasoning_out = as_int(u.get("reasoning_output_tokens"))
                    if any(v is not None for v in (raw_in, cached_in, cw, raw_out, reasoning_out)):
                        # Codex input_tokens already includes cached_input_tokens
                        norm_in = raw_in
                        norm_out = raw_out
                        self.turn_counter += 1
                        turn_id = f"turn_{self.turn_counter}"
                        self.counters.record_response(
                            turn_id,
                            input=norm_in,
                            output=norm_out,
                            cache_read=cached_in,
                            cache_write=cw,
                        )
                        if norm_in is not None and norm_out is not None:
                            try:
                                val = norm_in + norm_out - (reasoning_out or 0)
                                if val >= 0 and not self.collector.is_compacted and not self.collector.has_verified_context and not self.collector.budget_exhausted:
                                    self.counters.record_context(used=val)
                            except Exception:
                                log.warning("codex: could not derive context snapshot", exc_info=True)

                        self.events.emit({"kind": "telemetry.updated", "data": self.counters.as_dict()})
                except Exception:
                    log.warning("codex: turn usage processing failed", exc_info=True)
            self.collector.poll()
        elif event_type in ("thread.completed", "summary"):
            self.collector.poll()
            u = parsed.get("usage")
            if isinstance(u, dict):
                raw_in = as_int(u.get("input_tokens"))
                cached_in = as_int(u.get("cached_input_tokens"))
                cw = as_int(u.get("cache_write_input_tokens"))
                raw_out = as_int(u.get("output_tokens"))
                if any(v is not None for v in (raw_in, cached_in, cw, raw_out)):
                    norm_in = raw_in
                    norm_out = raw_out
                    if not self.params.SESSION_ID:
                        self.counters.record_totals(
                            input=norm_in,
                            output=norm_out,
                            cache_read=cached_in,
                            cache_write=cw,
                        )
                        self.events.emit({"kind": "telemetry.updated", "data": self.counters.as_dict()})
            self.collector.poll()

    def outcome(self, process: ProcessOutcome) -> BackendResult:
        """Normalize the parsed stream and the transport outcome into a backend result."""
        last_message = read_and_unlink(self.last_message_path, errors="replace")
        last_message_text = last_message.strip()
        agent_messages = last_message_text or "".join(self.agent_messages).strip()

        command_error, command_error_class = process.error, process.error_class
        if command_error_class == "timeout":
            command_error = f"codex subprocess timed out after {self.params.timeout_s}s"

        session_id, session_id_source = _resolve_session_id(self.thread_session_id, last_message, self.stdout_session_id)
        if session_id:
            log.info("codex: resolved session id via %s", session_id_source)
            self.collector.set_session_id(session_id)
            self.collector.poll()
        else:
            log.warning("codex: no exact session id from thread, last-message, or stdout (last_msg_len=%d)", len(last_message))

        # Diagnostics stand in for the error text only when the run produced no agent output.
        error_text = command_error
        if not agent_messages:
            diagnostics = "\n".join(self.diagnostics).strip()
            error_text = "\n".join(part for part in (command_error, diagnostics) if part)

        result = _classify(
            agent_messages=agent_messages,
            session_id=session_id,
            error_text=error_text,
            model=self.collector.model_name,
        )
        if command_error:
            result.outcome = "FATAL"
            result.error_class = command_error_class
            result.error = command_error
        result.agent_messages = agent_messages
        result.tokens = self.counters.as_dict()
        return result


async def execute(
    params: BackendParams,
    *,
    cancel: asyncio.Event | None = None,
    on_event: AsyncEventHandler | None = None,
) -> BackendResult:
    """Execute a Codex CLI session and return a normalized result.

    A set ``on_event`` receives each normalized event in order. A set ``cancel`` kills the child process.
    """
    cd, failure = preflight(params, "codex", "Codex CLI")
    if failure is not None:
        return failure

    with tempfile.NamedTemporaryFile(
        prefix="refract-codex-", suffix=".txt", delete=False
    ) as tmp:
        last_message_path = Path(tmp.name)

    cmd = [
        "codex",
        "exec",
        "--cd",
        os.fspath(cd),
        "--yolo",
        *params.args,
        # JSONL and the final-message file are Refract's result protocol.
        "--json",
        "-o",
        str(last_message_path),
    ]

    if params.SESSION_ID:
        cmd.extend(["resume", str(params.SESSION_ID)])

    # "-" makes codex exec read the prompt from stdin.
    cmd.append("-")

    log.info(
        "codex.execute start cwd=%s session_id=%s prompt_len=%d args=%d timeout_s=%s",
        os.fspath(cd),
        params.SESSION_ID or "<new>",
        len(params.PROMPT),
        len(params.args),
        params.timeout_s or "<off>",
    )
    log.debug("codex command prepared args=%d", len(cmd))

    deadline = time.monotonic() + params.timeout_s if params.timeout_s and params.timeout_s > 0 else None
    run = CodexRun(params, cd, last_message_path, on_event)
    process = await run_process(cmd, params.PROMPT, params.env, os.fspath(cd), deadline, cancel, run.feed)
    result = run.outcome(process)
    if cancel is not None and cancel.is_set():
        result.outcome = "FATAL"
        result.error_class = "cancelled"
        result.error = "backend command cancelled"

    log.info(
        "codex.execute done outcome=%s session_id=%s error_class=%s msg_len=%d",
        result.outcome,
        result.SESSION_ID or "",
        result.error_class,
        len(result.agent_messages),
    )
    return result


__all__ = ["execute"]
