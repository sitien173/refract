"""Characterization of ``DriverRegistry.execute``: argv, outcomes, stream events, and process-group recording.

Every case launches a fake CLI through ``stub_cli`` and asserts only what ``execute`` returns, what the
fake received, and what ``on_event`` saw. The suite does not import backend modules, so it holds
across a change of implementation behind ``DriverRegistry``.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from refract.config import TargetConfig
from refract.drivers import DriverRegistry, DriverResult
from tests.cli_stub import stub_cli

BACKENDS = ("claude", "codex", "pi", "agy")
EMPTY_TOKENS = {"context_used": None, "context_window": None, "input": None, "output": None, "cache_read": None, "cache_write": None}
STREAM_TOKENS = {"context_used": None, "context_window": None, "input": 3, "output": 4, "cache_read": None, "cache_write": None}
SUMMED_TOKENS = {**STREAM_TOKENS, "context_used": 7}
AGY_SESSION = "12345678-1234-1234-1234-123456789abc"
TIMEOUT_S = 5
CANCEL_FALLBACK_S = 30.0
# Pause after the last expected event so a trailing line that emits no event is read before cancel.
CANCEL_GRACE_S = 0.5


def _json(**fields: Any) -> str:
    return json.dumps(fields)


# Representative success streams per backend, as each CLI prints them.
STREAMS: dict[str, list[str]] = {
    "claude": [
        _json(type="stream_event", event={"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hi"}, "index": 0}),
        _json(type="stream_event", event={"type": "content_block_start", "content_block": {"type": "tool_use", "id": "t1", "name": "Read", "input": {"p": "x"}}}),
        _json(type="stream_event", event={"type": "content_block_stop", "index": 1}),
        _json(type="result", subtype="success", is_error=False, result="Final", session_id="s-1", usage={"input_tokens": 3, "output_tokens": 4}),
    ],
    "codex": [
        _json(type="thread.started", thread_id="th-1"),
        _json(type="item.completed", item={"type": "agent_message", "id": "m1", "text": "Final"}),
        _json(type="turn.completed", usage={"input_tokens": 3, "output_tokens": 4}),
    ],
    "pi": [
        _json(type="session", id="pi-1"),
        _json(type="message_update", assistantMessageEvent={"type": "text_delta", "delta": "Hi"}),
        _json(type="tool_execution_start", toolCallId="p1", toolName="grep", args={}),
        _json(type="tool_execution_end", toolCallId="p1", isError=False, result="r"),
        _json(type="message_end", message={"role": "assistant", "content": [{"type": "text", "text": "Final"}], "usage": {"input": 3, "output": 4}}),
    ],
    "agy": [
        f"Created conversation {AGY_SESSION}",
        _json(event="step_update", step_update={"conversation_id": AGY_SESSION, "step_index": 1, "state": "ACTIVE", "step_type": "agent_response", "text_delta": "Hi"}),
        _json(event="result", result={"conversation_id": AGY_SESSION, "status": "SUCCESS", "response": "Final"}),
    ],
}

# What each success stream yields.
SUCCESS: dict[str, dict[str, Any]] = {
    "claude": {"session_id": "s-1", "text": "Final", "tokens": STREAM_TOKENS},
    "codex": {"session_id": "th-1", "text": "Final", "tokens": SUMMED_TOKENS},
    "pi": {"session_id": "pi-1", "text": "Final", "tokens": SUMMED_TOKENS},
    "agy": {"session_id": AGY_SESSION, "text": "Final", "tokens": EMPTY_TOKENS},
}

EVENTS: dict[str, list[dict[str, Any]]] = {
    "claude": [
        {"kind": "assistant.text.delta", "entity_id": "msg-1", "data": {"text": "Hi"}},
        {"kind": "tool.started", "entity_id": "tool-1", "data": {"tool": "Read", "activity": "tool_call", "input": {"p": "x"}}},
        {"kind": "telemetry.updated", "data": STREAM_TOKENS},
    ],
    "codex": [
        {"kind": "assistant.text.delta", "entity_id": "msg-1", "data": {"text": "Final"}},
        {"kind": "assistant.message.completed", "entity_id": "msg-1", "data": {}},
        {"kind": "telemetry.updated", "data": SUMMED_TOKENS},
    ],
    "pi": [
        {"kind": "assistant.text.delta", "entity_id": "msg-1", "data": {"text": "Hi"}},
        {"kind": "tool.started", "entity_id": "tool-1", "data": {"tool": "grep", "activity": "tool_call", "input": {}}},
        {"kind": "tool.completed", "entity_id": "tool-1", "data": {"status": "completed"}},
        {"kind": "telemetry.updated", "data": SUMMED_TOKENS},
    ],
    "agy": [
        {"kind": "assistant.text.delta", "entity_id": "msg-1", "data": {"text": "Hi"}},
    ],
}

# Output a CLI prints when it is not logged in, with the exit status it uses.
AUTH_OUTPUT: dict[str, list[str]] = {
    "claude": [_json(type="result", subtype="success", is_error=True, result="Invalid API key · Please run /login", session_id="s-1", api_error_status=401)],
    "codex": ["ERROR: Not logged in. Run `codex login`"],
    "pi": ["Error: No API key found for anthropic. Use /login"],
    "agy": ["Error: not logged in, authentication failed"],
}


@dataclass
class Run:
    result: DriverResult
    events: list[dict[str, Any]]
    pgids: list[int]
    record: Path

    @property
    def received(self) -> dict[str, Any]:
        return json.loads(self.record.read_text(encoding="utf-8"))


async def _execute(
    backend: str,
    cwd: Path,
    *,
    target: TargetConfig | None = None,
    session_id: str = "",
    timeout_s: int = 0,
    cancel_after_events: int | None = None,
    pgids: list[int],
    events: list[dict[str, Any]],
) -> DriverResult:
    cancel = threading.Event()
    loop = asyncio.get_running_loop()

    async def on_event(event: dict[str, Any]) -> None:
        events.append(event)
        if len(events) == cancel_after_events:
            loop.call_later(CANCEL_GRACE_S, cancel.set)

    if cancel_after_events is not None:
        # Safety net only: the cancel normally fires once every expected event has arrived.
        loop.call_later(CANCEL_FALLBACK_S, cancel.set)

    async def on_spawn(pgid: int) -> None:
        pgids.append(pgid)

    return await DriverRegistry().execute(
        target=target or TargetConfig(id=backend, backend=backend),
        prompt="PROMPT",
        cwd=cwd,
        session_id=session_id,
        timeout_s=timeout_s,
        cancel_event=cancel,
        on_event=on_event,
        on_spawn=on_spawn,
    )


def run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    backend: str,
    lines: list[str] | None = None,
    *,
    cwd: Path | None = None,
    stub: bool = True,
    exit_code: int = 0,
    sleep_s: float = 0.0,
    **kwargs: Any,
) -> Run:
    record = tmp_path / "record.json"
    if stub:
        stub_cli(monkeypatch, tmp_path, backend, lines or [], exit_code=exit_code, sleep_s=sleep_s, record=record)
    pgids: list[int] = []
    events: list[dict[str, Any]] = []
    result = asyncio.run(_execute(backend, cwd or tmp_path, pgids=pgids, events=events, **kwargs))
    return Run(result, events, pgids, record)


def _mask(argv: list[str], cwd: Path) -> list[str]:
    """Replace per-run values: the workspace after ``--cd`` and temp file paths after ``-o`` or ``--log-file``."""
    masked = list(argv)
    for flag, placeholder in (("--cd", "<cwd>"), ("-o", "<tmp>"), ("--log-file", "<tmp>")):
        if flag in masked:
            index = masked.index(flag) + 1
            if flag == "--cd":
                assert masked[index] == os.fspath(cwd)
            masked[index] = placeholder
    return masked


# --- argv ---

POLICY = {"model": "m1", "reasoning": "high", "system_prompt": "sp"}

ARGV_CASES = [
    pytest.param("claude", {}, "", ["claude", "-p", "--output-format", "stream-json", "--include-partial-messages", "--permission-mode", "bypassPermissions"], id="claude-default"),
    pytest.param(
        "claude",
        {**POLICY, "args": ("--user-flag",)},
        "",
        ["claude", "-p", "--output-format", "stream-json", "--include-partial-messages", "--system-prompt", "sp", "--model", "m1", "--effort", "high", "--permission-mode", "bypassPermissions", "--user-flag"],
        id="claude-policy-and-user-args",
    ),
    pytest.param("claude", {}, "sess", ["claude", "-p", "--output-format", "stream-json", "--include-partial-messages", "--resume", "sess", "--permission-mode", "bypassPermissions"], id="claude-resume"),
    pytest.param("codex", {}, "", ["codex", "exec", "--json", "-o", "<tmp>", "--yolo", "-"], id="codex-default"),
    pytest.param(
        "codex",
        {**POLICY, "args": ("--user-flag",)},
        "",
        ["codex", "exec", "--json", "-o", "<tmp>", "--yolo", "--user-flag", "--model", "m1", "-c", 'model_reasoning_effort="high"', "-"],
        id="codex-policy-and-user-args",
    ),
    pytest.param(
        "codex",
        {"backend_profile": "prof", "model": 'm"1'},
        "",
        ["codex", "exec", "--json", "-o", "<tmp>", "--yolo", "--profile", "prof", "--model", 'm"1', "-c", 'model="m\\"1"', "-"],
        id="codex-backend-profile",
    ),
    pytest.param(
        "codex",
        {"backend_profile": "prof", "model": "m1", "reasoning": "high"},
        "",
        [
            "codex", "exec", "--json", "-o", "<tmp>", "--yolo", "--profile", "prof", "--model", "m1", "-c", 'model="m1"',
            "-c", 'model_reasoning_effort="high"', "-",
        ],
        id="codex-backend-profile-model-reasoning",
    ),
    pytest.param(
        "codex",
        {"backend_profile": "prof", "reasoning": "high"},
        "",
        ["codex", "exec", "--json", "-o", "<tmp>", "--yolo", "--profile", "prof", "-c", 'model_reasoning_effort="high"', "-"],
        id="codex-backend-profile-reasoning",
    ),
    pytest.param("codex", {}, "sess", ["codex", "exec", "--json", "-o", "<tmp>", "--yolo", "resume", "sess", "-"], id="codex-resume"),
    pytest.param("pi", {}, "", ["pi", "--mode", "json", "--approve"], id="pi-default"),
    pytest.param(
        "pi",
        {**POLICY, "args": ("--user-flag",)},
        "",
        ["pi", "--mode", "json", "--system-prompt", "sp", "--model", "m1", "--thinking", "high", "--user-flag", "--approve"],
        id="pi-approve-after-user-args",
    ),
    pytest.param("pi", {}, "sess", ["pi", "--mode", "json", "--session", "sess", "--approve"], id="pi-resume"),
    pytest.param(
        "agy",
        {},
        "",
        ["agy", "--output-format", "stream-json", "--log-file", "<tmp>", "--new-project", "--dangerously-skip-permissions", "--print", "PROMPT"],
        id="agy-default",
    ),
    pytest.param(
        "agy",
        {**POLICY, "args": ("--user-flag",)},
        "",
        ["agy", "--output-format", "stream-json", "--log-file", "<tmp>", "--new-project", "--model", "m1", "--dangerously-skip-permissions", "--user-flag", "--print", "PROMPT"],
        id="agy-policy-and-user-args",
    ),
    pytest.param(
        "agy",
        {},
        "sess",
        ["agy", "--output-format", "stream-json", "--log-file", "<tmp>", "--conversation", "sess", "--dangerously-skip-permissions", "--print", "PROMPT"],
        id="agy-resume",
    ),
]


@pytest.mark.parametrize(("backend", "fields", "session_id", "expected"), ARGV_CASES)
def test_backend_argv(monkeypatch, tmp_path, backend, fields, session_id, expected):
    target = TargetConfig(id=backend, backend=backend, **fields)
    outcome = run(monkeypatch, tmp_path, backend, STREAMS[backend], target=target, session_id=session_id)

    assert _mask(outcome.received["argv"], tmp_path) == expected
    assert outcome.result.outcome == "SUCCESS"


@pytest.mark.parametrize("backend", BACKENDS)
def test_backend_prompt_channel(monkeypatch, tmp_path, backend):
    outcome = run(monkeypatch, tmp_path, backend, STREAMS[backend])

    # agy takes the prompt as an argument; the others read it from stdin.
    assert outcome.received["stdin"] == ("" if backend == "agy" else "PROMPT")
    assert Path(outcome.received["cwd"]).resolve() == tmp_path.resolve()


# --- outcomes ---


def _assert_failure(outcome: Run, expected_outcome: str, error_code: str) -> None:
    assert outcome.result.outcome == expected_outcome
    assert outcome.result.error_code == error_code


@pytest.mark.parametrize("backend", BACKENDS)
def test_backend_success(monkeypatch, tmp_path, backend):
    outcome = run(monkeypatch, tmp_path, backend, STREAMS[backend])

    assert outcome.result == DriverResult(outcome="SUCCESS", session_id=SUCCESS[backend]["session_id"], text=SUCCESS[backend]["text"], error="", error_code="", model=None, tokens=SUCCESS[backend]["tokens"])


@pytest.mark.parametrize("backend", BACKENDS)
def test_backend_missing_cli(monkeypatch, tmp_path, backend):
    previous = shutil.which
    monkeypatch.setattr(shutil, "which", lambda name, *a, **k: None if name == backend else previous(name, *a, **k))

    outcome = run(monkeypatch, tmp_path, backend, stub=False)

    _assert_failure(outcome, "TARGET_FATAL", "missing_cli")
    assert outcome.result.error == f"'{backend}' was not found on PATH"
    assert outcome.pgids == []


@pytest.mark.parametrize("backend", BACKENDS)
def test_backend_bad_cwd(monkeypatch, tmp_path, backend):
    missing = tmp_path / "does-not-exist"

    outcome = run(monkeypatch, tmp_path, backend, STREAMS[backend], cwd=missing)

    _assert_failure(outcome, "REQUEST_FATAL", "bad_cwd")
    assert "is not a directory" in outcome.result.error
    assert not outcome.record.exists()


# Real auth output. The library classifies it as `auth` at any exit status, except agy at exit 0:
# there the output is the reply and the run succeeds without a warning.
AUTH_CASES = [
    pytest.param("claude", 0, "TARGET_FATAL", "auth", "Invalid API key · Please run /login\napi_error_status=401", id="claude-auth-exit-0"),
    pytest.param("claude", 1, "TARGET_FATAL", "auth", "Invalid API key · Please run /login\napi_error_status=401", id="claude-auth-exit-1"),
    pytest.param("codex", 0, "TARGET_FATAL", "auth", "ERROR: Not logged in. Run `codex login`", id="codex-auth-exit-0"),
    pytest.param("codex", 1, "TARGET_FATAL", "auth", "ERROR: Not logged in. Run `codex login`", id="codex-auth-exit-1"),
    pytest.param("pi", 0, "TARGET_FATAL", "auth", "Error: No API key found for anthropic. Use /login", id="pi-auth-exit-0"),
    pytest.param("pi", 1, "TARGET_FATAL", "auth", "Error: No API key found for anthropic. Use /login", id="pi-auth-exit-1"),
    pytest.param("agy", 0, "SUCCESS", "", "", id="agy-auth-exit-0"),
    pytest.param("agy", 1, "TARGET_FATAL", "auth", "Error: not logged in, authentication failed", id="agy-auth-exit-1"),
]


@pytest.mark.parametrize(("backend", "exit_code", "expected", "error_code", "error"), AUTH_CASES)
def test_backend_auth_failure(monkeypatch, tmp_path, backend, exit_code, expected, error_code, error):
    outcome = run(monkeypatch, tmp_path, backend, AUTH_OUTPUT[backend], exit_code=exit_code)

    _assert_failure(outcome, expected, error_code)
    assert outcome.result.error == error


NONZERO_CASES = [
    pytest.param("claude", "RETRYABLE", "execution_error", "command exited with status 3\nboom", id="claude-nonzero-exit"),
    pytest.param("codex", "RETRYABLE", "execution_error", "command exited with status 3\nboom", id="codex-nonzero-exit"),
    pytest.param("pi", "RETRYABLE", "execution_error", "command exited with status 3\nboom", id="pi-nonzero-exit"),
    pytest.param("agy", "RETRYABLE", "execution_error", "command exited with status 3", id="agy-nonzero-exit"),
]


@pytest.mark.parametrize(("backend", "expected", "error_code", "error"), NONZERO_CASES)
def test_backend_nonzero_exit(monkeypatch, tmp_path, backend, expected, error_code, error):
    outcome = run(monkeypatch, tmp_path, backend, ["boom"], exit_code=3)

    _assert_failure(outcome, expected, error_code)
    assert outcome.result.error == error


EMPTY_CASES = [
    pytest.param(backend, "RETRYABLE", "no_output", "the CLI produced no assistant text", id=f"{backend}-empty-output")
    for backend in BACKENDS
]


@pytest.mark.parametrize(("backend", "expected", "error_code", "error"), EMPTY_CASES)
def test_backend_empty_output(monkeypatch, tmp_path, backend, expected, error_code, error):
    outcome = run(monkeypatch, tmp_path, backend, [])

    _assert_failure(outcome, expected, error_code)
    assert outcome.result.error == error
    assert outcome.result.text == ""
    assert outcome.result.tokens == EMPTY_TOKENS


@pytest.mark.parametrize("backend", BACKENDS)
def test_backend_timeout(monkeypatch, tmp_path, backend):
    outcome = run(monkeypatch, tmp_path, backend, STREAMS[backend], sleep_s=60, timeout_s=TIMEOUT_S)

    _assert_failure(outcome, "RETRYABLE", "timeout")
    # The library names the launched file, so Windows adds the launcher extension.
    assert re.fullmatch(rf"{backend}(\.cmd)? subprocess timed out", outcome.result.error)
    # Output read before the deadline survives.
    assert outcome.result.session_id == SUCCESS[backend]["session_id"]
    assert outcome.result.text == SUCCESS[backend]["text"]


@pytest.mark.parametrize("backend", BACKENDS)
def test_backend_cancel(monkeypatch, tmp_path, backend):
    outcome = run(monkeypatch, tmp_path, backend, STREAMS[backend], sleep_s=60, cancel_after_events=len(EVENTS[backend]))

    assert outcome.result == DriverResult(
        outcome="CANCELLED",
        session_id=SUCCESS[backend]["session_id"],
        text=SUCCESS[backend]["text"],
        error="run cancelled",
        error_code="cancelled",
        model=None,
        tokens=SUCCESS[backend]["tokens"],
    )
    assert [e["kind"] for e in outcome.events] == [e["kind"] for e in EVENTS[backend]]
    assert len(outcome.pgids) == 1


# --- driver-level rejections ---


@pytest.mark.parametrize("backend", BACKENDS)
def test_backend_reserved_args_rejected(monkeypatch, tmp_path, backend):
    target = TargetConfig(id=backend, backend=backend, args=("--",))

    outcome = run(monkeypatch, tmp_path, backend, STREAMS[backend], target=target)

    _assert_failure(outcome, "TARGET_FATAL", "invalid_args")
    assert "reserved '--' token" in outcome.result.error
    assert not outcome.record.exists()


def test_codex_workspace_override_rejected(monkeypatch, tmp_path):
    target = TargetConfig(id="codex", backend="codex", args=("--cd", "/elsewhere"))

    outcome = run(monkeypatch, tmp_path, "codex", STREAMS["codex"], target=target)

    _assert_failure(outcome, "TARGET_FATAL", "invalid_args")
    assert "cannot override the workspace root" in outcome.result.error
    assert not outcome.record.exists()


def test_unsupported_backend_rejected(monkeypatch, tmp_path):
    target = TargetConfig(id="other", backend="other")

    outcome = run(monkeypatch, tmp_path, "other", target=target, stub=False)

    _assert_failure(outcome, "TARGET_FATAL", "invalid_args")
    assert outcome.result.error == "Unsupported backend: other"


# --- stream events, tokens, and process group ---


@pytest.mark.parametrize("backend", BACKENDS)
def test_backend_stream_events(monkeypatch, tmp_path, backend):
    outcome = run(monkeypatch, tmp_path, backend, STREAMS[backend])

    assert outcome.events == EVENTS[backend]
    assert all("parent_entity_id" not in event for event in outcome.events)
    # The last telemetry event carries the returned token counters.
    telemetry = [e["data"] for e in outcome.events if e["kind"] == "telemetry.updated"]
    assert (telemetry[-1] if telemetry else EMPTY_TOKENS) == outcome.result.tokens


@pytest.mark.parametrize("backend", BACKENDS)
def test_backend_records_process_group(monkeypatch, tmp_path, backend):
    outcome = run(monkeypatch, tmp_path, backend, STREAMS[backend])

    assert len(outcome.pgids) == 1
    assert outcome.pgids[0] > 0
