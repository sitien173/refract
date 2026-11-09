"""Agy backend tests: characterization of parsed output, prompt limit, and non-UTF-8 output.

Runs go through ``DriverRegistry`` against the fake ``agy`` launcher. The characterization
tests pin the HEAD outcome before the parser moves to the async Run API.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import types
from pathlib import Path

import pytest

from refract.backends import BackendParams, agy
from tests.cli_stub import run_target, stub_cli
from tests.telemetry_helpers import telemetry as _telemetry
from tests.telemetry_helpers import tokens as _tokens

USAGE_FIXTURE = Path(__file__).parent / "fixtures" / "usage" / "agy.jsonl"
CONVERSATION = "b658ef34-d18c-4294-b329-0ae5dee0157b"
PROMPT_LIMIT_BYTES = 100 * 1024


def _run(tmp_path: Path, **kwargs):
    return asyncio.run(run_target("agy", tmp_path, **kwargs))


def _step(text: str, *, step_index: int = 1, usage: dict | None = None, state: str = "ACTIVE") -> str:
    update = {"conversation_id": CONVERSATION, "step_index": step_index, "state": state, "step_type": "agent_response", "text_delta": text}
    if usage is not None:
        update["usage"] = usage
    return json.dumps({"event": "step_update", "step_update": update})


def _result(response: str, **fields: object) -> str:
    return json.dumps({"event": "result", "result": {"conversation_id": CONVERSATION, "status": "SUCCESS", "response": response, **fields}})


# --- Characterization ---


def test_recorded_stream_pins_text_session_and_telemetry(tmp_path, monkeypatch):
    stub_cli(monkeypatch, tmp_path, "agy", USAGE_FIXTURE.read_text(encoding="utf-8").splitlines())

    result = _run(tmp_path)

    assert result.outcome == "SUCCESS"
    assert result.text == "Step 1\nStep 2"
    assert result.session_id == "00000000-0000-0000-0000-000000000000"
    assert result.tokens["input"] == 14072
    assert result.tokens["output"] == 168


def test_plain_text_output_is_the_reply_and_stream_regex_supplies_session(tmp_path, monkeypatch):
    stub_cli(monkeypatch, tmp_path, "agy", ["PONG", f"Created conversation {CONVERSATION}"])

    result = _run(tmp_path)

    assert result.outcome == "SUCCESS"
    assert result.text == "PONG"
    assert result.session_id == CONVERSATION


def test_log_file_session_wins_over_stream_session(tmp_path, monkeypatch):
    log_id = "11111111-1111-1111-1111-111111111111"
    stub_cli(monkeypatch, tmp_path, "agy", [_step("hi"), f"Streaming conversation {CONVERSATION}", _result("hi")], log_text=f"Created conversation {log_id}")

    result = _run(tmp_path)

    assert result.session_id == log_id


def test_first_stream_regex_match_beats_last_conversation_id_field(tmp_path, monkeypatch):
    first = "22222222-2222-2222-2222-222222222222"
    stub_cli(monkeypatch, tmp_path, "agy", [f"Created conversation {first}", _step("hi"), _result("hi")])

    result = _run(tmp_path)

    assert result.session_id == first


def test_model_is_taken_from_last_event_that_carries_one(tmp_path, monkeypatch):
    stub_cli(monkeypatch, tmp_path, "agy", [
        json.dumps({"event": "x", "model": "agy-model-a"}),
        json.dumps({"event": "result", "result": {"conversation_id": CONVERSATION, "response": "ok", "model": "agy-model-b"}}),
    ])

    result = _run(tmp_path)

    assert result.model == "agy-model-b"


def test_nonzero_exit_keeps_partial_reply_as_execution_error(tmp_path, monkeypatch):
    stub_cli(monkeypatch, tmp_path, "agy", [_step("partial")], exit_code=2)

    result = _run(tmp_path)

    assert result.outcome == "RETRYABLE"
    assert result.error_code == "execution_error"
    assert result.error == "backend command exited with status 2"
    assert result.text == "partial"


def test_plain_fatal_token_is_not_classified_for_agy_output(tmp_path, monkeypatch):
    # HEAD: agy classifies only process errors, so text containing a fatal token stays OK.
    stub_cli(monkeypatch, tmp_path, "agy", ["not logged in"])

    result = _run(tmp_path)

    assert result.outcome == "SUCCESS"
    assert result.text == "not logged in"


def test_no_output_is_no_agent_messages_with_agy_wording(tmp_path, monkeypatch):
    stub_cli(monkeypatch, tmp_path, "agy", [])

    result = _run(tmp_path)

    assert result.outcome == "RETRYABLE"
    assert result.error_code == "no_agent_messages"
    assert result.error == "Failed to get `agent_messages` from the agy session."


def test_timeout_reports_seconds(tmp_path, monkeypatch):
    stub_cli(monkeypatch, tmp_path, "agy", [], sleep_s=30)

    result = _run(tmp_path, timeout_s=1)

    assert result.outcome == "RETRYABLE"
    assert result.error_code == "timeout"
    assert result.error == "agy subprocess timed out after 1s"


def test_cancel_before_start_is_cancelled(tmp_path, monkeypatch):
    stub_cli(monkeypatch, tmp_path, "agy", [_step("never")], sleep_s=30)
    cancel = threading.Event()
    cancel.set()

    result = _run(tmp_path, cancel_event=cancel)

    assert result.outcome == "CANCELLED"
    assert result.error_code == "cancelled"


def test_argv_carries_prompt_and_log_file(tmp_path, monkeypatch):
    record = tmp_path / "record.json"
    stub_cli(monkeypatch, tmp_path, "agy", ["ok"], record=record)

    _run(tmp_path, prompt="hello there", session_id=CONVERSATION)

    seen = json.loads(record.read_text(encoding="utf-8"))
    argv = seen["argv"]
    assert argv[argv.index("--print") + 1] == "hello there"
    assert argv[argv.index("--conversation") + 1] == CONVERSATION
    assert "--log-file" in argv
    assert seen["stdin"] == ""


# --- RED: prompt limit and non-UTF-8 output ---


def test_prompt_over_100_kib_fails_before_spawn(tmp_path, monkeypatch):
    record = tmp_path / "record.json"
    stub_cli(monkeypatch, tmp_path, "agy", ["never"], record=record)

    result = _run(tmp_path, prompt="a" * (PROMPT_LIMIT_BYTES + 1))

    assert result.outcome == "REQUEST_FATAL"
    assert result.error_code == "request_fatal"
    assert "100 KiB" in result.error
    assert not record.exists()


def test_prompt_limit_counts_utf8_bytes_not_characters(tmp_path, monkeypatch):
    record = tmp_path / "record.json"
    stub_cli(monkeypatch, tmp_path, "agy", ["never"], record=record)
    prompt = "€" * (PROMPT_LIMIT_BYTES // 3 + 1)  # 3 bytes per character, under 100 KiB in characters

    result = _run(tmp_path, prompt=prompt)

    assert result.error_code == "request_fatal"
    assert not record.exists()


def test_prompt_at_exactly_100_kib_is_spawned(tmp_path, monkeypatch):
    record = tmp_path / "record.json"
    stub_cli(monkeypatch, tmp_path, "agy", ["ok"], record=record)

    result = _run(tmp_path, prompt="a" * PROMPT_LIMIT_BYTES)

    if os.name == "nt":
        # Windows caps a command line at 32,767 characters, so a 100 KiB argv prompt fails before spawn.
        assert result.outcome == "REQUEST_FATAL"
        assert result.error_code == "request_fatal"
        assert "32767" in result.error
        assert not record.exists()
    else:
        assert result.outcome == "SUCCESS"
        assert record.exists()


def test_prompt_inside_the_windows_command_line_limit_is_spawned(tmp_path, monkeypatch):
    record = tmp_path / "record.json"
    stub_cli(monkeypatch, tmp_path, "agy", ["ok"], record=record)

    result = _run(tmp_path, prompt="a" * 20_000)

    assert result.outcome == "SUCCESS"
    assert record.exists()


def test_non_utf8_output_does_not_truncate_later_lines(tmp_path, monkeypatch):
    # "mid" then an invalid 0xff byte, then "d": the line after the bad byte and the next line must survive.
    stub_cli(monkeypatch, tmp_path, "agy", ["after"], raw_hex=["6d6964ff64"])

    result = _run(tmp_path)

    assert result.outcome == "SUCCESS"
    assert "after" in result.text


# --- Characterization: step usage, execute preflight ---


def _feed_updates(*updates: object, stream: bool = True) -> tuple[agy.AgyRun, list[dict]]:
    events: list[dict] = []

    async def sink(event: dict) -> None:
        events.append(event)

    run = agy.AgyRun(BackendParams(PROMPT="p", cd=Path(".")), sink if stream else None)

    async def go() -> None:
        for update in updates:
            await run.feed(json.dumps({"event": "step_update", "step_update": update}))

    asyncio.run(go())
    return run, events


def _done(usage: dict, **fields: object) -> dict:
    return {"step_type": "agent_response", "state": "DONE", "usage": usage, **fields}


@pytest.mark.parametrize(
    ("update", "tokens"),
    [
        pytest.param(
            _done({"input_tokens": 10, "output_tokens": 5, "thinking_tokens": 2, "context_window_size": 100}),
            _tokens(input=10, output=5, context_used=13, context_window=100),
            id="input-output-thinking-and-window",
        ),
        pytest.param(
            _done({"input_tokens": 10, "output_tokens": 5}),
            _tokens(input=10, output=5, context_used=15),
            id="no-thinking-no-window",
        ),
        pytest.param(
            _done({"input_tokens": 1, "output_tokens": 1, "thinking_tokens": 9}),
            _tokens(input=1, output=1),
            id="negative-context-is-skipped",
        ),
        pytest.param(
            _done({"cache_read_tokens": 4, "cache_write_tokens": 3}),
            _tokens(cache_read=4, cache_write=3),
            id="cache-only-has-no-context-used",
        ),
        pytest.param(
            _done({"input_tokens": 2}, model_context_window=50),
            _tokens(input=2, context_window=50),
            id="input-without-output-skips-context-used",
        ),
        pytest.param(
            _done({"input_tokens": 2, "output_tokens": 3}, context_window_size=64),
            _tokens(input=2, output=3, context_used=5, context_window=64),
            id="window-falls-back-to-the-update",
        ),
        pytest.param(
            _done({"input_tokens": 2, "output_tokens": 3, "model_context_window": 10, "context_window_size": 20}, context_window_size=30),
            _tokens(input=2, output=3, context_used=5, context_window=10),
            id="usage-model-window-wins",
        ),
    ],
)
def test_done_step_usage_updates_counters_and_emits_one_telemetry_event(update, tokens):
    run, events = _feed_updates(update)

    assert run.counters.as_dict() == tokens
    assert events == [{"kind": "telemetry.updated", "data": tokens}]


@pytest.mark.parametrize(
    "update",
    [
        pytest.param({"step_type": "agent_response", "state": "ACTIVE", "usage": {"input_tokens": 1}}, id="not-done"),
        pytest.param({"step_type": "agent_response", "state": "DONE", "usage": "x"}, id="usage-not-a-dict"),
        pytest.param({"step_type": "agent_response", "state": "DONE"}, id="no-usage"),
        pytest.param(_done({"input_tokens": -1, "output_tokens": True, "cache_read_tokens": "7"}), id="no-valid-counts"),
    ],
)
def test_step_without_usable_usage_leaves_counters_and_events_alone(update):
    run, events = _feed_updates(update)

    assert run.counters.as_dict() == _tokens()
    assert events == []


def test_non_dict_step_update_is_ignored():
    run, events = _feed_updates("not a dict", ["x"], None)

    assert run.counters.as_dict() == _tokens()
    assert run.session_id == ""
    assert events == []


def test_step_usage_without_a_sink_still_updates_counters():
    run, events = _feed_updates(_done({"input_tokens": 4, "output_tokens": 6}), stream=False)

    assert run.counters.as_dict() == _tokens(input=4, output=6, context_used=10)
    assert events == []


def test_step_ids_use_step_index_when_present_else_a_running_counter():
    run, _ = _feed_updates(
        _done({"input_tokens": 1}, step_index=7),
        _done({"input_tokens": 2}, step_index=7),
        _done({"input_tokens": 4}),
        _done({"input_tokens": 8}),
    )

    # Same index overwrites (2), then counter ids step_3 (4) and step_4 (8).
    assert run.counters.as_dict()["input"] == 14
    assert run.step_counter == 4


def test_agent_response_and_tool_steps_still_dispatch_before_usage():
    tool = {"step_type": "tool", "state": "ACTIVE", "tool_name": "ls", "tool_info": {"parameters": {"a": 1}}}
    done_tool = {"step_type": "tool", "state": "DONE", "tool_info": {"output": "out"}, "usage": {"input_tokens": 3}}
    run, events = _feed_updates(
        {"step_type": "agent_response", "text_delta": "hi", "conversation_id": "c-1"},
        tool,
        done_tool,
    )

    assert run.session_id == "c-1"
    assert run.assistant_deltas == ["hi"]
    assert [event["kind"] for event in events] == [
        "assistant.text.delta",
        "tool.started",
        "tool.completed",
        "telemetry.updated",
    ]
    assert events[2] == {"kind": "tool.completed", "entity_id": "tool-1", "data": {"status": "completed", "output": "out"}}
    assert events[3] == _telemetry(input=3)


def test_missing_workspace_fails_before_spawn(tmp_path):
    params = BackendParams(PROMPT="p", cd=tmp_path / "absent")

    result = asyncio.run(agy.execute(params))

    assert result.outcome == "FATAL"
    assert result.error_class == "bad_cd"
    assert str(tmp_path / "absent") in result.error


def test_unencodable_prompt_is_request_fatal_with_the_session(tmp_path):
    params = BackendParams(PROMPT="bad \ud800 prompt", cd=tmp_path, SESSION_ID="keep-me")

    result = asyncio.run(agy.execute(params))

    assert result.outcome == "FATAL"
    assert result.error_class == "request_fatal"
    assert result.SESSION_ID == "keep-me"
    assert result.error.startswith("prompt is not valid UTF-8:")


def test_new_session_argv_uses_new_project_and_log_file_order(tmp_path, monkeypatch):
    record = tmp_path / "record.json"
    stub_cli(monkeypatch, tmp_path, "agy", ["ok"], record=record)

    asyncio.run(agy.execute(BackendParams(PROMPT="hi", cd=tmp_path, args=["--flag"])))

    argv = json.loads(record.read_text(encoding="utf-8"))["argv"]
    assert "--conversation" not in argv
    assert argv[:3] == ["agy", "--dangerously-skip-permissions", "--flag"]
    assert argv[3:5] == ["--output-format", "stream-json"]
    assert argv[5] == "--log-file"
    assert argv[7:] == ["--new-project", "--print", "hi"]


def test_windows_command_line_over_the_limit_is_request_fatal_and_removes_the_log(tmp_path, monkeypatch):
    record = tmp_path / "record.json"
    stub_cli(monkeypatch, tmp_path, "agy", ["never"], record=record)
    monkeypatch.setattr(agy, "os", types.SimpleNamespace(name="nt", fspath=os.fspath))
    created: list[str] = []
    real_named = agy.tempfile.NamedTemporaryFile

    def tracking(*args, **kwargs):
        handle = real_named(*args, **kwargs)
        created.append(handle.name)
        return handle

    monkeypatch.setattr(agy.tempfile, "NamedTemporaryFile", tracking)

    result = asyncio.run(agy.execute(BackendParams(PROMPT="a" * 40_000, cd=tmp_path)))

    assert result.outcome == "FATAL"
    assert result.error_class == "request_fatal"
    assert "above the Windows limit of 32767 characters for a command line" in result.error
    assert not record.exists()
    assert len(created) == 1
    assert not Path(created[0]).exists()
