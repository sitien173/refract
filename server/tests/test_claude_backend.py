"""Claude backend tests: characterization of parsed output, async transport, and bounded parser state.

The characterization section pins the parsed outcome of recorded stream-json lines
and the argv, stdin, and cwd sent to the CLI. It drives the real transport against
the fake ``claude`` launcher in ``tests/claude_cli.py``.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

from refract.backends import BackendParams
from refract.backends import claude
from refract.backends._process import ProcessOutcome
from refract.config import TargetConfig
from refract.drivers import DriverRegistry
from refract.telemetry import TokenCounters
from tests.claude_cli import stub_claude
from tests.telemetry_helpers import tokens as _tokens

USAGE_FIXTURE = Path(__file__).parent / "fixtures" / "usage" / "claude.jsonl"
SESSION_FIXTURE = "00000000-0000-0000-0000-000000000000"
CHARACTERIZED_KINDS: list[str] = [
    "assistant.text.delta",
    "telemetry.updated",
    "telemetry.updated",
    "assistant.text.delta",
    "telemetry.updated",
    "telemetry.updated",
    "telemetry.updated",
    "telemetry.updated",
]


def _result_line(**fields: object) -> str:
    return json.dumps({"type": "result", "subtype": "success", "is_error": False, **fields})


def _run(params: BackendParams, events: list[dict] | None = None):
    """Run the async Claude backend to completion, collecting ``on_event`` payloads when requested."""

    async def on_event(event: dict) -> None:
        events.append(event)

    return asyncio.run(claude.execute(params, on_event=on_event if events is not None else None))


def _gone(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        synchronize, query_limited = 0x00100000, 0x1000
        handle = kernel32.OpenProcess(synchronize | query_limited, 0, pid)
        if not handle:
            return True
        try:
            return kernel32.WaitForSingleObject(handle, 0) == 0
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


# --- Characterization: recorded fixtures and error precedence ---


def test_recorded_stream_pins_text_session_model_and_tokens(tmp_path, monkeypatch):
    stub_claude(monkeypatch, tmp_path, USAGE_FIXTURE.read_text(encoding="utf-8").splitlines())
    events: list[dict] = []

    result = _run(BackendParams(PROMPT="p", cd=tmp_path, SESSION_ID="resume-id"), events)

    assert result.outcome == "OK"
    assert result.error == ""
    assert result.error_class == ""
    assert result.agent_messages == "Turn 1 reply\nTurn 2 reply"
    assert result.SESSION_ID == SESSION_FIXTURE
    assert result.model == "claude-opus-5-5"

    assert result.tokens == {
        "context_used": 34060,
        "context_window": 200000,
        "input": 66291,
        "output": 14,
        "cache_read": 59855,
        "cache_write": 150,
    }

    assert events[0] == {"kind": "assistant.text.delta", "entity_id": "msg-0", "data": {"text": "Turn 1 reply"}}
    assert [event["kind"] for event in events] == CHARACTERIZED_KINDS


def test_resume_flag_and_prompt_on_stdin_are_pinned(tmp_path, monkeypatch):
    record = tmp_path / "record.json"
    stub_claude(monkeypatch, tmp_path, [_result_line(session_id="s", result="ok")], record=record)

    _run(BackendParams(PROMPT="line one\nline two", cd=tmp_path, SESSION_ID="resume-id", args=("--tools", "Read")))

    seen = json.loads(record.read_text(encoding="utf-8"))
    assert seen["argv"] == [
        "claude", "--tools", "Read", "-p", "--permission-mode", "bypassPermissions",
        "--output-format", "json", "--resume", "resume-id",
    ]
    assert seen["stdin"] == "line one\nline two"
    assert Path(seen["cwd"]).resolve() == tmp_path.resolve()


def test_streaming_argv_uses_stream_json_when_on_event_is_set(tmp_path, monkeypatch):
    record = tmp_path / "record.json"
    stub_claude(monkeypatch, tmp_path, [_result_line(session_id="s", result="ok")], record=record)

    _run(BackendParams(PROMPT="p", cd=tmp_path), events=[])

    assert json.loads(record.read_text(encoding="utf-8"))["argv"] == [
        "claude", "-p", "--permission-mode", "bypassPermissions",
        "--output-format", "stream-json", "--include-partial-messages",
    ]


def test_command_failure_takes_precedence_over_result_error(tmp_path, monkeypatch):
    stub_claude(monkeypatch, tmp_path, [_result_line(
        is_error=True, subtype="error_during_execution", result="boom", api_error_status=500,
    )], exit_code=2)

    result = _run(BackendParams(PROMPT="p", cd=tmp_path))

    assert result.outcome == "FATAL"
    assert result.error_class == "execution_error"
    assert result.error == "backend command exited with status 2"
    assert result.agent_messages == "boom"


def test_result_error_without_command_failure_is_fatal_backend(tmp_path, monkeypatch):
    stub_claude(monkeypatch, tmp_path, [_result_line(
        is_error=True, subtype="error_during_execution", result="boom", api_error_status=500,
    )])

    result = _run(BackendParams(PROMPT="p", cd=tmp_path))

    assert result.outcome == "FATAL"
    assert result.error_class == "fatal_backend"
    assert result.error == "boom\napi_error_status=500"


def test_fatal_token_in_diagnostic_line_is_fatal_backend(tmp_path, monkeypatch):
    stub_claude(monkeypatch, tmp_path, ["Error: invalid model `x`"])

    result = _run(BackendParams(PROMPT="p", cd=tmp_path))

    assert result.outcome == "FATAL"
    assert result.error_class == "fatal_backend"
    assert result.error == "Error: invalid model `x`"


def test_no_output_is_no_agent_messages(tmp_path, monkeypatch):
    stub_claude(monkeypatch, tmp_path, [])

    result = _run(BackendParams(PROMPT="p", cd=tmp_path))

    assert result.outcome == "FATAL"
    assert result.error_class == "no_agent_messages"
    assert result.error == "Failed to get output from the claude session."


def test_result_without_session_id_is_ok_with_warning(tmp_path, monkeypatch):
    stub_claude(monkeypatch, tmp_path, [_result_line(result="PONG")])

    result = _run(BackendParams(PROMPT="p", cd=tmp_path))

    assert result.outcome == "OK"
    assert result.SESSION_ID == ""
    assert result.agent_messages == "PONG"
    assert result.error == "warning: no SESSION_ID"
    assert result.error_class == "warning"


def test_timeout_maps_to_timeout_with_seconds(tmp_path, monkeypatch):
    stub_claude(monkeypatch, tmp_path, ["Claude diagnostic: startup"], sleep_s=30)

    result = _run(BackendParams(PROMPT="p", cd=tmp_path, timeout_s=1))

    assert result.outcome == "FATAL"
    assert result.error_class == "timeout"
    assert result.error == "claude subprocess timed out after 1s"


# --- Counter public method used by the telemetry guard ---


def test_counters_report_any_known_value():
    counters = TokenCounters()
    assert counters.has_any() is False

    counters.record_context(used=10)
    assert counters.has_any() is True


# --- Async transport: cancel and timeout reach the child ---


@pytest.mark.asyncio
async def test_async_cancel_event_kills_child_and_maps_cancelled(tmp_path, monkeypatch):
    pid_file = tmp_path / "pid"
    stub_claude(monkeypatch, tmp_path, ["started"], sleep_s=30, pid_file=pid_file)
    cancel = asyncio.Event()

    async def cancel_once_started() -> None:
        while not pid_file.exists():
            await asyncio.sleep(0.02)
        cancel.set()

    trigger = asyncio.create_task(cancel_once_started())
    started = time.monotonic()
    result = await asyncio.wait_for(
        claude.execute(BackendParams(PROMPT="p", cd=tmp_path), cancel=cancel), timeout=10,
    )
    await trigger

    assert result.outcome == "FATAL"
    assert result.error_class == "cancelled"
    assert result.error == "backend command cancelled"
    assert time.monotonic() - started < 5
    assert _gone(int(pid_file.read_text(encoding="utf-8")))


@pytest.mark.asyncio
async def test_async_timeout_kills_child_and_maps_timeout(tmp_path, monkeypatch):
    pid_file = tmp_path / "pid"
    stub_claude(monkeypatch, tmp_path, ["started"], sleep_s=30, pid_file=pid_file)

    started = time.monotonic()
    result = await asyncio.wait_for(
        claude.execute(BackendParams(PROMPT="p", cd=tmp_path, timeout_s=1)), timeout=10,
    )

    assert result.outcome == "FATAL"
    assert result.error_class == "timeout"
    assert result.error == "claude subprocess timed out after 1s"
    assert time.monotonic() - started < 8
    assert _gone(int(pid_file.read_text(encoding="utf-8")))


@pytest.mark.asyncio
async def test_driver_threading_cancel_reaches_claude_child(tmp_path, monkeypatch):
    pid_file = tmp_path / "pid"
    stub_claude(monkeypatch, tmp_path, ["started"], sleep_s=30, pid_file=pid_file)
    cancel_event = threading.Event()

    def cancel_once_started() -> None:
        while not pid_file.exists():
            time.sleep(0.02)
        cancel_event.set()

    threading.Thread(target=cancel_once_started, daemon=True).start()
    result = await asyncio.wait_for(
        DriverRegistry().execute(
            target=TargetConfig(id="claude", backend="claude"),
            prompt="p",
            cwd=tmp_path,
            session_id="",
            timeout_s=0,
            cancel_event=cancel_event,
        ),
        timeout=10,
    )

    assert result.outcome == "CANCELLED"
    assert result.error_code == "cancelled"
    assert _gone(int(pid_file.read_text(encoding="utf-8")))


@pytest.mark.asyncio
async def test_async_on_event_failure_fails_attempt(tmp_path, monkeypatch):
    stub_claude(monkeypatch, tmp_path, [
        json.dumps({
            "type": "stream_event",
            "event": {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "hi"}},
        }),
        _result_line(session_id="s", result="hi"),
    ])

    async def failing_sink(event: dict) -> None:
        raise RuntimeError("sink failed")

    result = await claude.execute(BackendParams(PROMPT="p", cd=tmp_path), on_event=failing_sink)

    assert result.outcome == "FATAL"
    assert result.error_class == "execution_error"
    assert result.error == "RuntimeError: sink failed"


# --- Bounded parser state ---


@pytest.mark.asyncio
async def test_parser_keeps_bounded_diagnostics_and_the_first_fatal_line():
    run = claude.ClaudeRun(BackendParams(PROMPT="p", cd=Path(".")), on_event=None)
    for index in range(claude.MAX_DIAGNOSTICS + 500):
        await run.feed(f"noise {index}")
    await run.feed("Error: not logged in")
    await run.feed("noise after fatal")

    assert len(run.diagnostics) <= claude.MAX_DIAGNOSTICS + 1
    assert "Error: not logged in" in run.diagnostics
    assert run.outcome(ProcessOutcome()).error_class == "fatal_backend"


# --- Characterization: result capacity and totals ---


def _feed_lines(*lines: str, stream: bool = True) -> tuple[claude.ClaudeRun, list[dict]]:
    events: list[dict] = []

    async def sink(event: dict) -> None:
        events.append(event)

    run = claude.ClaudeRun(BackendParams(PROMPT="p", cd=Path(".")), sink if stream else None)

    async def go() -> None:
        for line in lines:
            await run.feed(line)

    asyncio.run(go())
    return run, events


def _assistant_line(model: str) -> str:
    return json.dumps({"type": "assistant", "message": {"model": model}})


@pytest.mark.parametrize(
    ("lines", "window"),
    [
        pytest.param(
            [_result_line(modelUsage={"only": {"contextWindow": 200}})],
            200,
            id="single-model-without-active-model",
        ),
        pytest.param(
            [_assistant_line("b"), _result_line(modelUsage={"a": {"contextWindow": 100}, "b": {"contextWindow": 300}})],
            300,
            id="active-model-selects-its-entry",
        ),
        pytest.param(
            [_result_line(modelUsage={"a": {"contextWindow": 100}, "b": {"contextWindow": 300}})],
            None,
            id="several-models-without-active-model",
        ),
        pytest.param(
            [_assistant_line("zzz"), _result_line(modelUsage={"only": {"contextWindow": 200}})],
            None,
            id="active-model-missing-from-usage",
        ),
        pytest.param([_result_line(modelUsage={"only": "x"})], None, id="stats-not-a-dict"),
        pytest.param([_result_line(modelUsage={"only": {"contextWindow": 0}})], None, id="zero-window"),
        pytest.param([_result_line(modelUsage={"only": {"contextWindow": -5}})], None, id="negative-window"),
        pytest.param([_result_line(modelUsage={"only": {}})], None, id="no-window-key"),
        pytest.param([_result_line(modelUsage=["only"])], None, id="model-usage-not-a-dict"),
        pytest.param([_result_line(modelUsage={})], None, id="empty-model-usage"),
        pytest.param([_result_line()], None, id="no-model-usage"),
    ],
)
def test_result_capacity_comes_from_the_selected_model_usage_entry(lines, window):
    run, events = _feed_lines(*lines)

    assert run.counters.as_dict() == _tokens(context_window=window)
    expected = [{"kind": "telemetry.updated", "data": _tokens(context_window=window)}] if window else []
    assert events == expected


def test_result_usage_records_totals_then_capacity_with_one_event_each():
    usage = {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 2, "cache_creation_input_tokens": 1}
    run, events = _feed_lines(_result_line(usage=usage, modelUsage={"m": {"contextWindow": 500}}))

    totals = _tokens(input=13, output=5, cache_read=2, cache_write=1)
    assert events == [
        {"kind": "telemetry.updated", "data": totals},
        {"kind": "telemetry.updated", "data": {**totals, "context_window": 500}},
    ]
    assert run.counters.as_dict() == {**totals, "context_window": 500}


@pytest.mark.parametrize(
    "usage",
    [
        pytest.param("x", id="usage-not-a-dict"),
        pytest.param({}, id="empty-usage"),
    ],
)
def test_result_without_observed_usage_records_no_totals(usage):
    run, events = _feed_lines(_result_line(usage=usage))

    assert run.counters.as_dict() == _tokens()
    assert events == []


def test_result_usage_without_a_sink_still_records_totals_and_capacity():
    run, events = _feed_lines(
        _result_line(usage={"input_tokens": 3, "output_tokens": 4}, modelUsage={"m": {"contextWindow": 9}}),
        stream=False,
    )

    assert run.counters.as_dict() == _tokens(input=3, output=4, context_window=9)
    assert events == []


def test_result_with_a_malformed_count_is_observed_and_emits_empty_totals():
    run, events = _feed_lines(_result_line(usage={"input_tokens": -1}))

    assert run.counters.as_dict() == _tokens()
    assert events == [{"kind": "telemetry.updated", "data": _tokens()}]
