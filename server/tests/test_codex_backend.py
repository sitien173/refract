"""Codex backend tests: parsed-outcome characterization, session-ID sources, and the Codex defects.

Characterization runs through ``DriverRegistry`` against the fake ``codex`` launcher, so the same
assertions hold for the sync and async backend. The defect tests are the RED set for step 3C.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from refract.backends import BackendParams, classify_tool_activity
from refract.backends.codex import CodexRun
from tests.cli_stub import run_target, stub_cli
from tests.telemetry_helpers import telemetry as _telemetry_event
from tests.telemetry_helpers import tokens as _tokens

USAGE_FIXTURE = Path(__file__).parent / "fixtures" / "usage" / "codex.jsonl"
FIXTURE_THREAD_ID = "00000000-0000-0000-0000-000000000000"
SESSION = "11111111-2222-3333-4444-555555555555"
OTHER = "66666666-7777-8888-9999-aaaaaaaaaaaa"


@pytest.fixture(autouse=True)
def _isolated_codex_home(tmp_path, monkeypatch) -> Path:
    """Point CODEX_HOME at an empty tree so no run reads the real ~/.codex."""
    home = tmp_path / "codex-home"
    (home / "sessions").mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(home))
    return home


def _run(tmp_path: Path, **kwargs):
    return asyncio.run(run_target("codex", tmp_path, **kwargs))


def _event(**fields: object) -> str:
    return json.dumps(fields)


def _thread(thread_id: str) -> str:
    return _event(type="thread.started", thread_id=thread_id)


def _message(text: str, item_id: str = "item_1") -> str:
    return _event(type="item.completed", item={"id": item_id, "type": "agent_message", "text": text})


def _turn(input_tokens: int = 1000, output_tokens: int = 50) -> str:
    return _event(type="turn.completed", usage={"input_tokens": input_tokens, "output_tokens": output_tokens})


def _rollout(home: Path, session_id: str, cwd: Path, *, records: list[dict] | None = None, subdir: str = "") -> Path:
    directory = home / "sessions" / subdir if subdir else home / "sessions"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"rollout_{session_id}.jsonl"
    lines = [{"type": "session_meta", "payload": {"id": session_id, "cwd": str(cwd)}}, *(records or [])]
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    return path


# --- Characterization: recorded stream, arguments, session sources, errors ---


def test_recorded_stream_pins_text_session_and_telemetry(tmp_path, monkeypatch):
    stub_cli(monkeypatch, tmp_path, "codex", USAGE_FIXTURE.read_text(encoding="utf-8").splitlines())

    result = _run(tmp_path)

    assert result.outcome == "SUCCESS"
    assert result.error == ""
    assert result.text == "Turn 1 replyTurn 2 reply"
    assert result.session_id == FIXTURE_THREAD_ID
    assert result.model is None
    assert result.tokens["input"] == 22000
    assert result.tokens["output"] == 50
    assert result.tokens["context_used"] == 12015


def test_resume_argv_and_prompt_delivery_are_pinned(tmp_path, monkeypatch):
    record = tmp_path / "record.json"
    stub_cli(monkeypatch, tmp_path, "codex", [_thread(SESSION), _message("ok")], record=record)

    asyncio.run(run_target("codex", tmp_path, prompt="the prompt", session_id=OTHER))

    payload = json.loads(record.read_text(encoding="utf-8"))
    argv = payload["argv"]
    assert argv[0] == "codex"
    assert argv[1:3] == ["exec", "--cd"]
    assert "--json" in argv
    assert Path(argv[argv.index("-o") + 1]).name.startswith("refract-codex-")
    assert argv[argv.index("resume") + 1] == OTHER
    assert argv[-1] == "-"
    assert payload["stdin"] == "the prompt"


def test_thread_started_wins_over_last_message_and_stdout_session_line(tmp_path, monkeypatch):
    stub_cli(
        monkeypatch,
        tmp_path,
        "codex",
        [_thread(SESSION), _message("reply"), f"session id: {OTHER}"],
        last_message=f"answer\nsession id: {OTHER}",
    )

    result = _run(tmp_path)

    assert result.session_id == SESSION
    assert result.text == f"answer\nsession id: {OTHER}"


def test_last_message_session_line_is_used_without_thread_event(tmp_path, monkeypatch):
    stub_cli(monkeypatch, tmp_path, "codex", [_message("reply")], last_message=f"answer\nsession id: {SESSION}")

    result = _run(tmp_path)

    assert result.outcome == "SUCCESS"
    assert result.session_id == SESSION


def test_stdout_session_line_is_used_without_thread_or_last_message(tmp_path, monkeypatch):
    stub_cli(monkeypatch, tmp_path, "codex", [_message("reply"), f"session id: {SESSION}"])

    result = _run(tmp_path)

    assert result.outcome == "SUCCESS"
    assert result.session_id == SESSION
    assert result.text == "reply"


def test_fresh_run_without_session_source_warns_and_stores_no_id(tmp_path, monkeypatch):
    stub_cli(monkeypatch, tmp_path, "codex", [_message("reply")])

    result = _run(tmp_path)

    assert result.outcome == "SUCCESS"
    assert result.session_id == ""
    assert result.error_code == "warning"


def test_last_message_file_is_answer_when_no_agent_item_exists(tmp_path, monkeypatch):
    stub_cli(monkeypatch, tmp_path, "codex", [_thread(SESSION)], last_message="from file")

    result = _run(tmp_path)

    assert result.outcome == "SUCCESS"
    assert result.text == "from file"
    assert result.session_id == SESSION


def test_blank_last_message_falls_back_to_agent_items(tmp_path, monkeypatch):
    stub_cli(monkeypatch, tmp_path, "codex", [_thread(SESSION), _message("from items")], last_message="  \n")

    result = _run(tmp_path)

    assert result.outcome == "SUCCESS"
    assert result.text == "from items"


def test_nonzero_exit_with_agent_message_is_execution_error(tmp_path, monkeypatch):
    stub_cli(monkeypatch, tmp_path, "codex", [_thread(SESSION), _message("partial")], exit_code=3)

    result = _run(tmp_path)

    assert result.outcome == "RETRYABLE"
    assert result.error_code == "execution_error"
    assert result.error == "backend command exited with status 3"
    assert result.text == "partial"


def test_nonzero_exit_with_fatal_diagnostic_stays_execution_error(tmp_path, monkeypatch):
    stub_cli(monkeypatch, tmp_path, "codex", ["error: unknown option, not logged in"], exit_code=2)

    result = _run(tmp_path)

    assert result.outcome == "RETRYABLE"
    assert result.error_code == "execution_error"
    assert result.error == "backend command exited with status 2"


def test_timeout_keeps_partial_text_and_timeout_class(tmp_path, monkeypatch):
    stub_cli(monkeypatch, tmp_path, "codex", [_thread(SESSION), _message("partial")], sleep_s=10)

    result = _run(tmp_path, timeout_s=1)

    assert result.outcome == "RETRYABLE"
    assert result.error_code == "timeout"
    assert result.error == "codex subprocess timed out after 1s"
    assert result.text == "partial"




def test_fatal_token_with_agent_message_does_not_fail_the_run(tmp_path, monkeypatch):
    stub_cli(monkeypatch, tmp_path, "codex", [_thread(SESSION), _message("reply"), "warning: not logged in earlier"])

    result = _run(tmp_path)

    assert result.outcome == "SUCCESS"
    assert result.text == "reply"


def test_rollout_of_exact_session_supplies_model_and_context(tmp_path, monkeypatch, _isolated_codex_home):
    _rollout(_isolated_codex_home, SESSION, tmp_path, records=[
        {"type": "event_msg", "payload": {"type": "session_configured", "model": "gpt-codex-test"}},
        {"type": "event_msg", "payload": {"type": "token_count", "info": {
            "last_token_usage": {"input_tokens": 900, "output_tokens": 90, "reasoning_output_tokens": 0},
            "model_context_window": 200000,
        }}},
    ])
    stub_cli(monkeypatch, tmp_path, "codex", [_thread(SESSION), _message("reply"), _turn(1000, 50)])

    result = _run(tmp_path)

    assert result.outcome == "SUCCESS"
    assert result.model == "gpt-codex-test"
    assert result.tokens["context_used"] == 990
    assert result.tokens["context_window"] == 200000


# --- RED for step 3C: Codex defects ---


def test_exit_zero_without_agent_message_is_request_fatal_and_never_returns_jsonl(tmp_path, monkeypatch):
    stub_cli(monkeypatch, tmp_path, "codex", [_thread(SESSION), _turn(1000, 50)], last_message="")

    result = _run(tmp_path)

    assert result.outcome == "REQUEST_FATAL"
    assert result.error_code == "request_fatal"
    assert result.error == "no agent message"
    assert result.text == ""


def test_blank_last_message_without_agent_message_is_request_fatal(tmp_path, monkeypatch):
    stub_cli(monkeypatch, tmp_path, "codex", [_thread(SESSION)], last_message="\n  \n")

    result = _run(tmp_path)

    assert result.outcome == "REQUEST_FATAL"
    assert result.error == "no agent message"
    assert result.text == ""

def test_fatal_token_in_diagnostic_without_agent_message_is_fatal_backend(tmp_path, monkeypatch):
    stub_cli(monkeypatch, tmp_path, "codex", ["Error: not logged in"])

    result = _run(tmp_path)

    assert result.outcome == "TARGET_FATAL"
    assert result.error_code == "fatal_backend"
    assert result.error == "Error: not logged in"

def test_resume_without_exact_session_source_stores_no_session_id(tmp_path, monkeypatch):
    stub_cli(monkeypatch, tmp_path, "codex", [_message("reply")])

    result = _run(tmp_path, session_id=OTHER)

    assert result.outcome == "SUCCESS"
    assert result.session_id == ""


# --- Characterization: CodexRun._on_event dispatch ---


def _codex_run(tmp_path: Path, *, session_id: str = "") -> tuple[CodexRun, list[dict], list[str]]:
    """Return a run, its emitted events, and the session ids the collector held at each poll."""
    emitted: list[dict] = []

    async def sink(event: dict) -> None:
        emitted.append(event)

    run = CodexRun(BackendParams(PROMPT="p", cd=tmp_path, SESSION_ID=session_id), tmp_path, tmp_path / "last.txt", sink)
    polled: list[str] = []
    run.collector.poll = lambda: polled.append(run.collector.session_id)
    return run, emitted, polled


def _feed(run: CodexRun, *events: dict) -> None:
    for event in events:
        asyncio.run(run.feed(json.dumps(event)))


def test_thread_started_sets_session_before_first_poll(tmp_path):
    run, emitted, polled = _codex_run(tmp_path)

    _feed(run, {"type": "thread.started", "thread_id": SESSION})

    assert run.thread_session_id == SESSION
    assert run.collector.session_id == SESSION
    assert polled == [SESSION]
    assert emitted == []


@pytest.mark.parametrize(
    "event",
    [
        pytest.param({"type": "thread.started"}, id="missing-thread-id"),
        pytest.param({"type": "thread.started", "thread_id": ""}, id="empty-thread-id"),
        pytest.param({"type": "other", "thread_id": SESSION}, id="other-event-type"),
    ],
)
def test_events_without_a_started_thread_keep_session_empty(tmp_path, event):
    run, _, polled = _codex_run(tmp_path)

    _feed(run, event)

    assert run.thread_session_id == ""
    assert run.collector.session_id == ""
    assert polled == [""]


@pytest.mark.parametrize(
    ("event", "poll_count"),
    [
        pytest.param({"type": "turn.completed", "usage": {"input_tokens": 1}}, 3, id="turn-completed"),
        pytest.param({"type": "thread.completed", "usage": {"input_tokens": 1}}, 3, id="thread-completed"),
        pytest.param({"type": "summary", "usage": {"input_tokens": 1}}, 3, id="summary"),
        pytest.param({"type": "turn.completed"}, 3, id="turn-completed-without-usage"),
        pytest.param({"type": "item.started", "item": {"type": "agent_message"}}, 1, id="item-started"),
        pytest.param({"type": "turn.started"}, 1, id="unrelated"),
    ],
)
def test_collector_is_polled_around_usage_events(tmp_path, event, poll_count):
    run, _, polled = _codex_run(tmp_path)

    _feed(run, event)

    assert len(polled) == poll_count


def test_item_started_emits_message_and_tool_start_events(tmp_path):
    run, emitted, _ = _codex_run(tmp_path)

    _feed(
        run,
        {"type": "item.started", "item": {"id": "a", "type": "agent_message"}},
        {"type": "item.started", "item": {"id": "t", "type": "tool_call", "name": "shell", "input": {"cmd": "ls"}}},
        {"type": "item.started", "item": {"id": "u", "type": "unknown"}},
    )

    assert emitted == [
        {"kind": "assistant.message.started", "entity_id": "msg-1", "data": {}},
        {
            "kind": "tool.started",
            "entity_id": "tool-2",
            "data": {"tool": "shell", "activity": classify_tool_activity("codex", "shell"), "input": {"cmd": "ls"}},
        },
    ]
    assert run.raw_to_entity == {"a": "msg-1", "t": "tool-2"}


def test_item_completed_emits_text_and_tool_completion_events(tmp_path):
    run, emitted, _ = _codex_run(tmp_path)

    _feed(
        run,
        {"type": "item.started", "item": {"id": "a", "type": "agent_message"}},
        {"type": "item.completed", "item": {"id": "a", "type": "agent_message", "text": "hi"}},
        {"type": "item.completed", "item": {"id": "t", "type": "tool_call", "output": "out"}},
    )

    assert emitted[1:] == [
        {"kind": "assistant.text.delta", "entity_id": "msg-1", "data": {"text": "hi"}},
        {"kind": "assistant.message.completed", "entity_id": "msg-1", "data": {}},
        {"kind": "tool.completed", "entity_id": "tool-1", "data": {"status": "completed", "output": "out"}},
    ]
    assert run.agent_messages == ["hi"]


@pytest.mark.parametrize("event_type", ["item.started", "item.completed"])
def test_non_object_item_is_ignored(tmp_path, event_type):
    run, emitted, _ = _codex_run(tmp_path)

    _feed(run, {"type": event_type, "item": "not an object"})

    assert emitted == []
    assert run.entity_counter == 0


@pytest.mark.parametrize(
    ("usage", "expected_event"),
    [
        pytest.param(
            {"input_tokens": 1000, "output_tokens": 50, "cached_input_tokens": 200, "cache_write_input_tokens": 7},
            _telemetry_event(context_used=1050, input=1000, output=50, cache_read=200, cache_write=7),
            id="full-usage",
        ),
        pytest.param(
            {"input_tokens": 1000, "output_tokens": 50, "reasoning_output_tokens": 20},
            _telemetry_event(context_used=1030, input=1000, output=50),
            id="reasoning-reduces-context",
        ),
        pytest.param(
            {"input_tokens": 1000, "cached_input_tokens": 5},
            _telemetry_event(input=1000, cache_read=5),
            id="no-output-no-context",
        ),
        pytest.param(
            {"input_tokens": 10, "output_tokens": 0, "reasoning_output_tokens": 50},
            _telemetry_event(input=10, output=0),
            id="negative-context-skipped",
        ),
        pytest.param({"reasoning_output_tokens": 3}, _telemetry_event(), id="reasoning-only-counts-as-usage"),
        pytest.param({"input_tokens": "x", "output_tokens": True}, None, id="non-integer-values"),
        pytest.param({}, None, id="empty-usage"),
    ],
)
def test_turn_completed_usage_updates_counters_and_emits(tmp_path, usage, expected_event):
    run, emitted, _ = _codex_run(tmp_path)

    _feed(run, {"type": "turn.completed", "usage": usage})

    assert emitted == ([] if expected_event is None else [expected_event])
    assert run.counters.as_dict() == (_tokens() if expected_event is None else expected_event["data"])
    assert run.turn_counter == (0 if expected_event is None else 1)


def test_turn_completed_without_usage_object_is_ignored(tmp_path):
    run, emitted, _ = _codex_run(tmp_path)

    _feed(run, {"type": "turn.completed", "usage": "x"}, {"type": "turn.completed"})

    assert emitted == []
    assert run.counters.as_dict() == _tokens()


def test_turn_completed_sums_consecutive_turns(tmp_path):
    run, emitted, _ = _codex_run(tmp_path)

    _feed(
        run,
        {"type": "turn.completed", "usage": {"input_tokens": 100, "output_tokens": 10}},
        {"type": "turn.completed", "usage": {"input_tokens": 200, "output_tokens": 20}},
    )

    assert emitted[-1] == _telemetry_event(context_used=220, input=300, output=30)


@pytest.mark.parametrize("flag", ["is_compacted", "has_verified_context", "budget_exhausted"])
def test_turn_completed_leaves_context_alone_when_rollout_owns_it(tmp_path, flag):
    run, emitted, _ = _codex_run(tmp_path)
    setattr(run.collector, flag, True)

    _feed(run, {"type": "turn.completed", "usage": {"input_tokens": 100, "output_tokens": 10}})

    assert emitted == [_telemetry_event(input=100, output=10)]


@pytest.mark.parametrize("event_type", ["thread.completed", "summary"])
def test_final_usage_records_totals_for_fresh_runs(tmp_path, event_type):
    run, emitted, _ = _codex_run(tmp_path)

    _feed(run, {"type": event_type, "usage": {"input_tokens": 900, "output_tokens": 40, "cached_input_tokens": 100, "cache_write_input_tokens": 3}})

    assert emitted == [_telemetry_event(input=900, output=40, cache_read=100, cache_write=3)]


def test_final_usage_totals_override_turn_sums_without_context(tmp_path):
    run, emitted, _ = _codex_run(tmp_path)

    _feed(
        run,
        {"type": "turn.completed", "usage": {"input_tokens": 100, "output_tokens": 10}},
        {"type": "thread.completed", "usage": {"input_tokens": 900, "output_tokens": 40}},
    )

    assert emitted[-1] == _telemetry_event(context_used=110, input=900, output=40)


@pytest.mark.parametrize(
    ("event", "session_id"),
    [
        pytest.param({"type": "thread.completed", "usage": {"input_tokens": 1}}, SESSION, id="resumed-run"),
        pytest.param({"type": "thread.completed", "usage": {"reasoning_output_tokens": 1}}, "", id="no-counted-fields"),
        pytest.param({"type": "thread.completed", "usage": "x"}, "", id="usage-not-object"),
        pytest.param({"type": "thread.completed"}, "", id="no-usage"),
    ],
)
def test_final_usage_without_totals_to_record_emits_nothing(tmp_path, event, session_id):
    run, emitted, _ = _codex_run(tmp_path, session_id=session_id)

    _feed(run, event)

    assert emitted == []
    assert run.counters.as_dict() == _tokens()
