"""Agy backend tests: characterization of parsed output, prompt limit, and non-UTF-8 output.

Runs go through ``DriverRegistry`` against the fake ``agy`` launcher. The characterization
tests pin the HEAD outcome before the parser moves to the async Run API.
"""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

from tests.cli_stub import run_target, stub_cli

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

    assert result.outcome == "SUCCESS"
    assert record.exists()


def test_non_utf8_output_does_not_truncate_later_lines(tmp_path, monkeypatch):
    # "mid" then an invalid 0xff byte, then "d": the line after the bad byte and the next line must survive.
    stub_cli(monkeypatch, tmp_path, "agy", ["after"], raw_hex=["6d6964ff64"])

    result = _run(tmp_path)

    assert result.outcome == "SUCCESS"
    assert "after" in result.text
