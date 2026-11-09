"""Codex backend tests: parsed-outcome characterization, session-ID sources, and the Codex defects.

Characterization runs through ``DriverRegistry`` against the fake ``codex`` launcher, so the same
assertions hold for the sync and async backend. The defect tests are the RED set for step 3C.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from tests.cli_stub import run_target, stub_cli

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
