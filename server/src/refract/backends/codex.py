"""Transport-agnostic codex backend (plain-text stdout mode)."""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
from collections.abc import Generator
from pathlib import Path
from typing import Any

from . import BackendParams, BackendResult, _usage_dict, classify_backend_output, classify_tool_activity, preflight
from ._shell import StreamOutcome, consume_stream, stream_shell_command_lines
from refract.logging_setup import get_logger
from refract.telemetry import TelemetryAccumulator

log = get_logger("codex")


def _as_int(val: Any) -> int | None:
    if isinstance(val, bool) or not isinstance(val, int) or val < 0:
        return None
    return val


def run_shell_command(
    cmd: list[str],
    cwd: str | None = None,
    timeout_s: int = 0,
    cancel_event: threading.Event | None = None,
    stdin_text: str | None = None,
    env: dict[str, str] | None = None,
) -> Generator[str, None, None]:
    """Execute a command and stream its stdout lines until EOF or timeout.

    A non-zero ``timeout_s`` enforces an overall wall-clock budget; on
    expiry the process is terminated and ``subprocess.TimeoutExpired``
    is raised after best-effort cleanup.
    """
    yield from stream_shell_command_lines(
        cmd,
        executable_name="codex",
        errors="replace",
        cwd=cwd,
        timeout_s=timeout_s,
        line_transform=lambda line: line.rstrip("\r\n"),
        terminate_wait_s=5,
        cancel_event=cancel_event,
        check_returncode=True,
        stdin_text=stdin_text,
        env=env,
    )


_SESSION_ID_STDOUT_RE = re.compile(
    r"^\s*session id:\s*([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_SESSION_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

def _extract_session_id_from_stdout(text: str) -> str:
    if not text:
        return ""
    match = _SESSION_ID_STDOUT_RE.search(text)
    return match.group(1) if match else ""


def _same_path(left: str, right: Path) -> bool:
    try:
        return Path(left).resolve() == right.resolve()
    except OSError:
        return os.path.normcase(os.path.abspath(left)) == os.path.normcase(
            os.path.abspath(os.fspath(right))
        )


def _extract_session_id_from_latest_session(cwd: Path, prompt: str, started_at: float) -> str:
    sessions_dir = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "sessions"
    if not sessions_dir.exists():
        return ""

    prompt_hint = prompt.strip().splitlines()[0][:80] if prompt.strip() else ""

    try:
        session_files = sorted(
            sessions_dir.rglob("*.jsonl"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return ""

    cwd_match_without_prompt = ""
    for session_path in session_files[:50]:
        try:
            stat = session_path.stat()
        except OSError:
            continue
        if stat.st_mtime < started_at - 30:
            break

        try:
            with session_path.open(encoding="utf-8", errors="ignore") as handle:
                first_line = handle.readline()
                head = handle.read(65536)
        except OSError:
            continue

        meta = {}
        for line in (first_line, *head.splitlines()[:10]):
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(parsed, dict):
                continue
            if parsed.get("type") == "session_meta":
                meta = parsed
                break
        if not meta:
            continue

        payload = meta.get("payload", {})
        if not isinstance(payload, dict):
            continue
        session_id = payload.get("id", "")
        session_cwd = payload.get("cwd", "")
        if (
            not session_id
            or not _SESSION_ID_RE.fullmatch(session_id)
            or not session_cwd
            or not _same_path(session_cwd, cwd)
        ):
            continue
        if prompt_hint and prompt_hint not in head:
            if not cwd_match_without_prompt:
                cwd_match_without_prompt = session_id
            continue
        return session_id

    return cwd_match_without_prompt


def _resolve_session_id(
    *,
    parsed_session_id: str,
    last_message: str,
    stdout_text: str,
    cwd: Path,
    prompt: str,
    started_at: float,
    fallback_session_id: str,
) -> tuple[str, str]:
    candidates = (
        ("stdout-jsonl:thread.started", parsed_session_id.strip),
        ("last-message:session-id-line", lambda: _extract_session_id_from_stdout(last_message)),
        ("stdout:session-id-line", lambda: _extract_session_id_from_stdout(stdout_text)),
        ("codex-jsonl", lambda: _extract_session_id_from_latest_session(cwd, prompt, started_at)),
        ("params:SESSION_ID", fallback_session_id.strip),
    )
    for source, resolve in candidates:
        value = resolve()
        if value:
            return value, source
    return "", ""


def _classify(*, agent_messages: str, session_id: str, error_text: str) -> BackendResult:
    return classify_backend_output(
        backend_name="codex",
        agent_messages=agent_messages,
        session_id=session_id,
        error_text=error_text,
    )


def _extract_output(stream: StreamOutcome) -> tuple[str, str]:
    """Return the thread ID and the concatenated agent messages from Codex JSONL."""
    session_id = ""
    agent_messages = ""
    for line, event in zip(stream.lines, stream.events):
        if event is None:
            if line.strip():
                log.debug("codex: skipping non-JSON stdout line len=%d", len(line.strip()))
            continue
        event_type = event.get("type", "")
        if event_type == "thread.started" and event.get("thread_id"):
            session_id = str(event.get("thread_id"))
            continue
        if event_type != "item.completed":
            continue
        item = event.get("item", {})
        if isinstance(item, dict) and item.get("type") == "agent_message" and item.get("text"):
            agent_messages += str(item.get("text"))
    return session_id, agent_messages


def _usage_values(stream: StreamOutcome) -> dict[str, Any]:
    usage_values: dict[str, Any] = {}
    for event in stream.objects():
        if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
            u = event["usage"]
            usage_values = {"input_tokens": u.get("input_tokens"), "output_tokens": u.get("output_tokens"), "cached_input_tokens": u.get("cached_input_tokens")}
    return usage_values


def _read_last_message(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        log.warning("codex: could not read --output-last-message file %s: %s", path, exc)
        return ""
    finally:
        try:
            path.unlink()
        except OSError:
            pass


class _EventParser:
    """Normalize Codex item lifecycle events and correlate entity IDs."""

    def __init__(self, params: BackendParams) -> None:
        self.params = params
        self.entity_counter = 0
        self.raw_to_entity: dict[str, str] = {}
        self.accumulator = TelemetryAccumulator()
        self.turn_counter = 0

    def emit(self, event: dict[str, Any]) -> None:
        if self.params.emitter is not None:
            self.params.emitter(event)

    def start_item(self, item: dict[str, Any], raw_id: str) -> None:
        item_type = item.get("type", "")
        if item_type == "agent_message":
            self.entity_counter += 1
            entity_id = f"msg-{self.entity_counter}"
            if raw_id:
                self.raw_to_entity[raw_id] = entity_id
            self.emit({
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
            self.emit({
                "kind": "tool.started",
                "entity_id": entity_id,
                "data": tool_data,
            })

    def complete_item(self, item: dict[str, Any], raw_id: str) -> None:
        item_type = item.get("type", "")
        if item_type == "agent_message":
            entity_id = self.raw_to_entity.get(raw_id) or f"msg-{self.entity_counter or 1}"
            msg_text = str(item.get("text", ""))
            if msg_text:
                self.emit({
                    "kind": "assistant.text.delta",
                    "entity_id": entity_id,
                    "data": {"text": msg_text},
                })
            self.emit({
                "kind": "assistant.message.completed",
                "entity_id": entity_id,
                "data": {},
            })
        elif item_type == "tool_call":
            entity_id = self.raw_to_entity.get(raw_id) or f"tool-{self.entity_counter or 1}"
            tool_data = {"status": str(item.get("status", "completed"))}
            if "output" in item:
                tool_data["output"] = item["output"]
            self.emit({
                "kind": "tool.completed",
                "entity_id": entity_id,
                "data": tool_data,
            })

    def on_event(self, parsed: dict[str, Any]) -> None:
        event_type = parsed.get("type", "")
        item = parsed.get("item", {})
        if isinstance(item, dict):
            raw_id = str(item.get("id", ""))
            if event_type == "item.started":
                self.start_item(item, raw_id)
            elif event_type == "item.completed":
                self.complete_item(item, raw_id)

        if event_type == "turn.completed":
            u = parsed.get("usage")
            if isinstance(u, dict):
                try:
                    raw_in = _as_int(u.get("input_tokens"))
                    cached_in = _as_int(u.get("cached_input_tokens"))
                    cw = _as_int(u.get("cache_write_input_tokens"))
                    raw_out = _as_int(u.get("output_tokens"))
                    reasoning_out = _as_int(u.get("reasoning_output_tokens"))
                    if any(v is not None for v in (raw_in, cached_in, cw, raw_out, reasoning_out)):
                        # Codex input_tokens already includes cached_input_tokens
                        norm_in = raw_in
                        norm_out = raw_out
                        self.turn_counter += 1
                        turn_id = f"turn_{self.turn_counter}"
                        self.accumulator.record_consumption(
                            attempt=1,
                            invocation=1,
                            response_id=turn_id,
                            input_tokens=norm_in,
                            output_tokens=norm_out,
                            cache_read_tokens=cached_in,
                            cache_write_tokens=cw,
                            source="turn",
                            quality="reported",
                        )
                        ctx_used = None
                        if norm_in is not None and norm_out is not None:
                            try:
                                val = norm_in + norm_out - (reasoning_out or 0)
                                if val >= 0:
                                    ctx_used = val
                                    self.accumulator.record_context_snapshot(
                                        used_tokens=ctx_used,
                                        source="derived",
                                        quality="derived",
                                    )
                            except Exception:
                                log.warning("codex: could not derive context snapshot", exc_info=True)

                        if self.params.emitter is not None:
                            self.params.emitter({
                                "kind": "telemetry.updated",
                                "data": {
                                    "response_id": turn_id,
                                    "input_tokens": norm_in,
                                    "output_tokens": norm_out,
                                    "cache_read_tokens": cached_in,
                                    "cache_write_tokens": cw,
                                    "source": "turn",
                                    "quality": "reported",
                                },
                            })
                            if ctx_used is not None:
                                self.params.emitter({
                                    "kind": "telemetry.updated",
                                    "data": {
                                        "context_used_tokens": ctx_used,
                                        "source": "derived",
                                        "quality": "derived",
                                    },
                                })
                except Exception:
                    log.warning("codex: turn usage processing failed", exc_info=True)
        elif event_type in ("thread.completed", "summary"):
            u = parsed.get("usage")
            if isinstance(u, dict):
                raw_in = _as_int(u.get("input_tokens"))
                cached_in = _as_int(u.get("cached_input_tokens"))
                cw = _as_int(u.get("cache_write_input_tokens"))
                raw_out = _as_int(u.get("output_tokens"))
                if any(v is not None for v in (raw_in, cached_in, cw, raw_out)):
                    norm_in = raw_in
                    norm_out = raw_out
                    self.accumulator.reconcile_cumulative(
                        attempt=1,
                        invocation=1,
                        total_input=norm_in,
                        total_output=norm_out,
                        cache_read=cached_in,
                        cache_write=cw,
                        source="result",
                        quality="reported",
                    )
                    if self.params.emitter is not None:
                        self.params.emitter({
                            "kind": "telemetry.updated",
                            "data": {
                                "total_input_tokens": norm_in,
                                "total_output_tokens": norm_out,
                                "cache_read_tokens": cached_in,
                                "cache_write_tokens": cw,
                                "source": "result",
                                "quality": "reported",
                            },
                        })


def _agent_messages(last_message: str, parsed_agent_messages: str, stdout_text: str) -> str:
    last_message_text = last_message.strip()
    parsed_agent_messages = parsed_agent_messages.strip()
    if last_message_text:
        agent_messages = last_message_text
        source = "last_message_file"
    elif parsed_agent_messages:
        agent_messages = parsed_agent_messages
        source = "stdout_jsonl_fallback"
    else:
        agent_messages = stdout_text
        source = "stdout_fallback"
    log.debug(
        "codex: last_message_len=%d parsed_msg_len=%d stdout_len=%d using=%s",
        len(last_message), len(parsed_agent_messages), len(stdout_text), source,
    )
    return agent_messages


def execute(params: BackendParams) -> BackendResult:
    """Execute a Codex CLI session and return normalized backend result."""
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

    started_at = time.time()
    parser = _EventParser(params)

    stream = consume_stream(
        run_shell_command, cmd, params, cwd=os.fspath(cd), name="codex", on_event=parser.on_event, stdin_text=params.PROMPT,
    )
    stdout_text = "\n".join(stream.lines)
    parsed_session_id, parsed_agent_messages = _extract_output(stream)
    last_message = _read_last_message(last_message_path)

    last_message_text = last_message.strip()
    agent_messages = _agent_messages(last_message, parsed_agent_messages, stdout_text)

    session_id, session_id_source = _resolve_session_id(
        parsed_session_id=parsed_session_id,
        last_message=last_message,
        stdout_text=stdout_text,
        cwd=cd,
        prompt=params.PROMPT,
        started_at=started_at,
        fallback_session_id=params.SESSION_ID,
    )

    if session_id_source:
        log.info("codex: resolved session id via %s", session_id_source)
    else:
        log.warning(
            "codex: no session id found from stdout/session-file/params "
            "(last_msg_len=%d stdout_len=%d).",
            len(last_message), len(stdout_text),
        )

    # error_text carries only true error signal — not the entire stdout when it
    # also happened to be the agent's message. Stdout is only surfaced when we
    # genuinely have no agent output to attribute as success.
    error_text = stream.error
    if not agent_messages.strip() and stdout_text and not last_message_text:
        if error_text:
            error_text = f"{error_text}\n\n[stdout]\n{stdout_text}".strip()
        else:
            error_text = stdout_text

    result = _classify(
        agent_messages=agent_messages,
        session_id=session_id,
        error_text=error_text,
    )
    if stream.error:
        result.outcome = "FATAL"
        result.error_class = stream.error_class
        result.error = stream.error
    result.usage = _usage_dict(**_usage_values(stream))
    result.agent_messages = agent_messages
    if parser.accumulator._has_any_consumption or parser.accumulator._context_used_tokens.value is not None:
        result.telemetry = parser.accumulator.snapshot().model_dump(mode="json")
    log.info(
        "codex.execute done outcome=%s session_id=%s error_class=%s msg_len=%d",
        result.outcome,
        result.SESSION_ID or "",
        result.error_class,
        len(result.agent_messages),
    )
    if result.error:
        log.warning(
            "codex.execute returned error class=%s len=%d",
            result.error_class,
            len(result.error),
        )
    return result


__all__ = ["execute", "run_shell_command"]
