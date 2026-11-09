"""Pi backend tests: characterization of parsed output, prompt delivery, and bounded parser state.

Characterization runs through ``DriverRegistry`` against the fake ``pi`` launcher, so the same
assertions hold for the sync and async backend. Only the prompt delivery changes in this step.
"""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

import pytest

from refract.backends import BackendParams, pi
from tests.cli_stub import run_target, stub_cli
from tests.telemetry_helpers import tokens as _tokens

USAGE_FIXTURE = Path(__file__).parent / "fixtures" / "usage" / "pi.jsonl"
SESSION_FIXTURE = "00000000-0000-0000-0000-000000000000"


def _run(tmp_path: Path, **kwargs):
    return asyncio.run(run_target("pi", tmp_path, **kwargs))


def _event(**fields: object) -> str:
    return json.dumps(fields)


def _assistant_message(text: str, **fields: object) -> str:
    return _event(type="message_end", message={"role": "assistant", "content": [{"type": "text", "text": text}], **fields})


# --- Characterization: recorded stream, error precedence, arguments ---


def test_recorded_stream_pins_text_session_and_model(tmp_path, monkeypatch):
    stub_cli(monkeypatch, tmp_path, "pi", USAGE_FIXTURE.read_text(encoding="utf-8").splitlines())

    result = _run(tmp_path, session_id="resume-id")

    assert result.outcome == "SUCCESS"
    assert result.error == ""
    assert result.text == "OK"
    assert result.session_id == SESSION_FIXTURE
    assert result.model == "gpt-6.1-sol"
    assert set(result.tokens) == {"context_used", "context_window", "input", "output", "cache_read", "cache_write"}


def test_recorded_stream_pins_telemetry(tmp_path, monkeypatch):
    stub_cli(monkeypatch, tmp_path, "pi", USAGE_FIXTURE.read_text(encoding="utf-8").splitlines())

    tokens = _run(tmp_path).tokens

    assert tokens["input"] is not None
    assert tokens["output"] is not None


def test_resume_flag_and_json_mode_are_pinned(tmp_path, monkeypatch):
    record = tmp_path / "record.json"
    stub_cli(monkeypatch, tmp_path, "pi", [_assistant_message("ok", model="m")], record=record)

    _run(tmp_path, session_id="resume-id")

    argv = json.loads(record.read_text(encoding="utf-8"))["argv"]
    assert argv[0] == "pi"
    assert argv[argv.index("--mode") + 1] == "json"
    assert argv[argv.index("--session") + 1] == "resume-id"
    assert "--approve" in argv


def test_session_event_supplies_session_id(tmp_path, monkeypatch):
    stub_cli(monkeypatch, tmp_path, "pi", [
        _event(type="session", id="pi-sess-1"),
        _assistant_message("hello"),
    ])

    result = _run(tmp_path)

    assert result.outcome == "SUCCESS"
    assert result.session_id == "pi-sess-1"
    assert result.text == "hello"


def test_structured_error_with_partial_text_is_execution_error(tmp_path, monkeypatch):
    stub_cli(monkeypatch, tmp_path, "pi", [
        _assistant_message("partial"),
        _event(type="message_end", message={"role": "assistant", "content": [], "stopReason": "error", "errorMessage": "rate limited"}),
    ])

    result = _run(tmp_path)

    assert result.outcome == "RETRYABLE"
    assert result.error_code == "execution_error"
    assert result.error == "rate limited"
    assert result.text == "partial"


def test_command_failure_with_text_is_execution_error(tmp_path, monkeypatch):
    stub_cli(monkeypatch, tmp_path, "pi", [_assistant_message("reply")], exit_code=3)

    result = _run(tmp_path, session_id="s")

    assert result.outcome == "RETRYABLE"
    assert result.error_code == "execution_error"
    assert result.error == "backend command exited with status 3"
    assert result.text == "reply"


def test_fatal_token_in_diagnostic_line_is_fatal_backend(tmp_path, monkeypatch):
    stub_cli(monkeypatch, tmp_path, "pi", ["Error: not logged in"])

    result = _run(tmp_path)

    assert result.outcome == "TARGET_FATAL"
    assert result.error_code == "fatal_backend"
    assert result.error == "Error: not logged in"


def test_context_overflow_signature_is_context_overflow(tmp_path, monkeypatch):
    stub_cli(monkeypatch, tmp_path, "pi", [_assistant_message("partial"), "context_length_exceeded"], exit_code=1)

    result = _run(tmp_path)

    assert result.outcome == "RETRYABLE"
    assert result.error_code == "context_overflow"
    assert result.error == "backend command exited with status 1\ncontext_length_exceeded"
    assert result.text == "partial"


def test_no_output_is_no_agent_messages(tmp_path, monkeypatch):
    stub_cli(monkeypatch, tmp_path, "pi", [])

    result = _run(tmp_path)

    assert result.outcome == "RETRYABLE"
    assert result.error_code == "no_agent_messages"
    assert result.error == "Failed to get output from the pi session."


def test_timeout_without_reply_is_no_agent_messages_with_timeout_text(tmp_path, monkeypatch):
    # Pinned HEAD precedence: precedence 5 applies only to OK results, so a timeout with no reply keeps no_agent_messages.
    stub_cli(monkeypatch, tmp_path, "pi", ["Pi diagnostic: startup"], sleep_s=30)

    result = _run(tmp_path, timeout_s=1)

    assert result.outcome == "RETRYABLE"
    assert result.error_code == "no_agent_messages"
    assert result.error == "Failed to get output from the pi session. pi subprocess timed out after 1s\nPi diagnostic: startup"


def test_cancel_before_start_is_cancelled(tmp_path, monkeypatch):
    stub_cli(monkeypatch, tmp_path, "pi", [_assistant_message("never")], sleep_s=30)
    cancel = threading.Event()
    cancel.set()

    result = _run(tmp_path, cancel_event=cancel)

    assert result.outcome == "CANCELLED"
    assert result.error_code == "cancelled"
    assert result.error == "backend command cancelled"


# --- RED: prompt delivery and non-UTF-8 output ---


def test_prompt_is_sent_on_stdin_not_argv(tmp_path, monkeypatch):
    record = tmp_path / "record.json"
    stub_cli(monkeypatch, tmp_path, "pi", [_assistant_message("ok")], record=record)
    prompt = "line one\nline two with --flag-looking text"

    _run(tmp_path, prompt=prompt)

    seen = json.loads(record.read_text(encoding="utf-8"))
    assert prompt not in seen["argv"]
    assert seen["stdin"] == prompt


# --- Characterization: event model and per-message usage ---


def _feed_lines(*lines: str) -> tuple[pi.PiRun, list[dict]]:
    events: list[dict] = []

    async def sink(event: dict) -> None:
        events.append(event)

    run = pi.PiRun(BackendParams(PROMPT="p", cd=Path(".")), sink)

    async def go() -> None:
        for line in lines:
            await run.feed(line)

    asyncio.run(go())
    return run, events


def _assistant(**fields: object) -> dict:
    return {"role": "assistant", **fields}


@pytest.mark.parametrize(
    ("event", "model"),
    [
        pytest.param({"message": _assistant(model="m1")}, "m1", id="assistant-message"),
        pytest.param({"message": {"role": "user", "model": "u"}}, None, id="non-assistant-message"),
        pytest.param({"message": _assistant(model="")}, None, id="empty-message-model"),
        pytest.param({"message": _assistant(model=3)}, None, id="non-string-message-model"),
        pytest.param({"message": "text"}, None, id="message-not-a-dict"),
        pytest.param(
            {"message": _assistant(model="first"), "messages": [_assistant(model="later")]},
            "first",
            id="message-wins-over-messages",
        ),
        pytest.param(
            {"messages": [_assistant(model="a"), _assistant(model="b")]},
            "b",
            id="last-assistant-in-messages",
        ),
        pytest.param(
            {"messages": [_assistant(model="a"), {"role": "user", "model": "u"}, "x", _assistant()]},
            "a",
            id="skips-non-assistant-non-dict-and-modelless-entries",
        ),
        pytest.param(
            {"message": _assistant(model=""), "messages": [_assistant(model="fallback")]},
            "fallback",
            id="empty-message-model-falls-back-to-messages",
        ),
        pytest.param({"messages": [_assistant(model="")]}, None, id="messages-with-empty-model"),
        pytest.param({"messages": "x"}, None, id="messages-not-a-list"),
        pytest.param({}, None, id="no-message-fields"),
    ],
)
def test_event_model_picks_the_assistant_model(event, model):
    assert pi._event_model(event) == model


def _end(message: object) -> str:
    return _event(type="message_end", message=message)


def _usage_event(data: dict) -> dict:
    return {"kind": "telemetry.updated", "data": data}


def test_assistant_usage_records_the_response_and_context_once():
    run, events = _feed_lines(_end(_assistant(responseId="r1", usage={"input": 10, "output": 5})))

    expected = _tokens(input=10, output=5, context_used=15)
    assert run.counters.as_dict() == expected
    assert events == [_usage_event(expected)]
    assert run.recorded_responses == {"r1"}


def test_repeated_response_id_is_ignored():
    run, events = _feed_lines(
        _end(_assistant(responseId="r1", usage={"input": 10, "output": 5})),
        _end(_assistant(responseId="r1", usage={"input": 99, "output": 99})),
    )

    assert run.counters.as_dict() == _tokens(input=10, output=5, context_used=15)
    assert len(events) == 1


def test_id_is_used_when_response_id_is_missing_and_distinct_ids_sum():
    run, events = _feed_lines(
        _end(_assistant(id="a", usage={"input": 1, "output": 1})),
        _end(_assistant(id="b", usage={"input": 2, "output": 2})),
    )

    assert run.recorded_responses == {"a", "b"}
    assert run.counters.as_dict() == _tokens(input=3, output=3, context_used=4)
    assert len(events) == 2


def test_message_without_an_id_uses_turn_one_and_a_second_one_in_the_turn_is_ignored():
    run, events = _feed_lines(
        _end(_assistant(usage={"input": 1, "output": 1})),
        _end(_assistant(usage={"input": 50, "output": 50})),
    )

    assert run.recorded_responses == {"turn_1"}
    assert run.turn_counter == 1
    assert run.counters.as_dict() == _tokens(input=1, output=1, context_used=2)
    assert len(events) == 1


def test_each_turn_start_allows_one_message_without_an_id():
    run, events = _feed_lines(
        _event(type="turn_start"),
        _end(_assistant(usage={"input": 1, "output": 1})),
        _event(type="turn_start"),
        _end(_assistant(usage={"input": 2, "output": 2})),
    )

    assert run.recorded_responses == {"turn_1", "turn_2"}
    assert run.counters.as_dict() == _tokens(input=3, output=3, context_used=4)
    assert len(events) == 2


def test_turn_id_already_recorded_by_a_response_id_is_ignored():
    run, events = _feed_lines(
        _event(type="turn_start"),
        _end(_assistant(responseId="turn_1", usage={"input": 1, "output": 1})),
        _end(_assistant(usage={"input": 7, "output": 7})),
    )

    assert run.recorded_responses == {"turn_1"}
    assert run.counters.as_dict() == _tokens(input=1, output=1, context_used=2)
    assert len(events) == 1


@pytest.mark.parametrize(
    "message",
    [
        pytest.param(_assistant(responseId="r1", usage="x"), id="usage-not-a-dict"),
        pytest.param(_assistant(responseId="r1"), id="no-usage"),
        pytest.param(_assistant(responseId="r1", usage={}), id="unobserved-usage"),
    ],
)
def test_message_without_usable_usage_is_marked_recorded_but_emits_nothing(message):
    run, events = _feed_lines(_end(message), _end(_assistant(responseId="r1", usage={"input": 4})))

    assert run.recorded_responses == {"r1"}
    assert run.counters.as_dict() == _tokens()
    assert events == []


@pytest.mark.parametrize(
    "message",
    [
        pytest.param({"role": "user", "responseId": "r1", "usage": {"input": 1}}, id="user-role"),
        pytest.param("text", id="not-a-dict"),
    ],
)
def test_non_assistant_message_is_not_recorded(message):
    run, events = _feed_lines(_end(message))

    assert run.recorded_responses == set()
    assert run.turn_counter == 0
    assert events == []


def test_output_only_usage_records_no_context_used():
    run, events = _feed_lines(_end(_assistant(responseId="r1", usage={"output": 5})))

    assert run.counters.as_dict() == _tokens(output=5)
    assert events == [_usage_event(_tokens(output=5))]


def test_turn_end_events_record_usage_like_message_end():
    run, _ = _feed_lines(_event(type="turn_end", message=_assistant(responseId="r9", usage={"input": 2, "output": 3})))

    assert run.counters.as_dict() == _tokens(input=2, output=3, context_used=5)
