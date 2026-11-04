"""Pi backend tests: characterization of parsed output, prompt delivery, and bounded parser state.

Characterization runs through ``DriverRegistry`` against the fake ``pi`` launcher, so the same
assertions hold for the sync and async backend. Only the prompt delivery changes in this step.
"""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

from tests.cli_stub import run_target, stub_cli

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
