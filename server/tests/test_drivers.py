
import asyncio
import threading
from pathlib import Path

import pytest
from coding_agent_cli import Capabilities, Diagnostic, Outcome, Result, Usage, events

from refract import drivers
from refract.config import TargetConfig
from refract.drivers import (
    DriverRegistry,
    DriverResult,
    _event_dict,
    _normalize,
    _target_args,
)
from tests.orchestration_helpers import Raised, outcome, plain

TOKEN_KEYS = ("context_used", "context_window", "input", "output", "cache_read", "cache_write")


def test_normalize_preserves_usage_as_tokens() -> None:
    result = _normalize(Result(
        outcome=Outcome.SUCCESS,
        session_id="session",
        text="done",
        usage=Usage(input=17, context_window=200),
    ))

    assert result == DriverResult(
        "SUCCESS", "session", "done", "", "", None, dict.fromkeys(TOKEN_KEYS) | {"input": 17, "context_window": 200},
    )


def test_driver_result_tokens_default_to_all_unknown() -> None:
    result = DriverResult("SUCCESS", "", "", "", "")

    assert result.tokens == dict.fromkeys(TOKEN_KEYS)


def _failed(outcome: Outcome, code: str) -> Result:
    return Result(outcome=outcome, error=Diagnostic(code=code, message=f"{code} message"))


_OUTCOME_CASES = [
    (Outcome.CANCELLED, "cancelled", "CANCELLED"),
    (Outcome.REQUEST_FATAL, "bad_cwd", "REQUEST_FATAL"),
    (Outcome.REQUEST_FATAL, "invalid_prompt", "REQUEST_FATAL"),
    (Outcome.REQUEST_FATAL, "invalid_args", "TARGET_FATAL"),
    (Outcome.REQUEST_FATAL, "unsupported_option", "TARGET_FATAL"),
    (Outcome.REQUEST_FATAL, "invalid_model", "TARGET_FATAL"),
    (Outcome.REQUEST_FATAL, "context_overflow", "RETRYABLE"),
    (Outcome.AGENT_FATAL, "missing_cli", "TARGET_FATAL"),
    (Outcome.AGENT_FATAL, "spawn_failed", "TARGET_FATAL"),
    (Outcome.AGENT_FATAL, "auth", "TARGET_FATAL"),
    (Outcome.AGENT_FATAL, "anything_else", "TARGET_FATAL"),
    (Outcome.RETRYABLE, "timeout", "RETRYABLE"),
    (Outcome.RETRYABLE, "no_output", "RETRYABLE"),
    (Outcome.RETRYABLE, "anything_else", "RETRYABLE"),
]


@pytest.mark.parametrize(("library_outcome", "code", "expected"), _OUTCOME_CASES)
def test_normalize_outcome_table(library_outcome, code, expected) -> None:
    result = _normalize(_failed(library_outcome, code))

    assert (result.outcome, result.error_code, result.error) == (expected, code, f"{code} message")


def test_normalize_success_has_no_error_fields() -> None:
    result = _normalize(Result(outcome=Outcome.SUCCESS, text="ok", session_id=None))

    assert (result.outcome, result.error_code, result.error, result.session_id) == ("SUCCESS", "", "", "")


def test_normalize_success_ignores_warnings() -> None:
    result = _normalize(Result(outcome=Outcome.SUCCESS, warnings=(Diagnostic(code="warning", message="w"),)))

    assert (result.outcome, result.error_code, result.error) == ("SUCCESS", "", "")


@pytest.mark.parametrize("removed", ["no_agent_messages", "fatal_backend", "bad_cd", "request_fatal"])
def test_removed_codes_are_not_produced_by_the_mapping(removed) -> None:
    assert removed not in {code for _, code, _ in _OUTCOME_CASES}


def test_normalize_failure_without_diagnostic_still_fails() -> None:
    result = _normalize(Result(outcome=Outcome.AGENT_FATAL))

    assert (result.outcome, result.error_code, result.error) == ("TARGET_FATAL", "", "")


_EVENT_CASES = [
    (events.TextDelta(text="hi", entity_id="msg-1"), {"kind": "assistant.text.delta", "entity_id": "msg-1", "data": {"text": "hi"}}),
    (events.TextDelta(text="hi"), {"kind": "assistant.text.delta", "data": {"text": "hi"}}),
    (events.MessageStarted(entity_id="msg-1"), {"kind": "assistant.message.started", "entity_id": "msg-1", "data": {}}),
    (events.MessageCompleted(entity_id="msg-1"), {"kind": "assistant.message.completed", "entity_id": "msg-1", "data": {}}),
    (
        events.ToolStarted(tool="Read", activity="tool_call", input={"p": 1}, entity_id="tool-1"),
        {"kind": "tool.started", "entity_id": "tool-1", "data": {"tool": "Read", "activity": "tool_call", "input": {"p": 1}}},
    ),
    (events.ToolCompleted(status="error", entity_id="tool-1"), {"kind": "tool.completed", "entity_id": "tool-1", "data": {"status": "error"}}),
    (
        events.UsageUpdated(usage=Usage(input=3, output=4)),
        {"kind": "telemetry.updated", "data": dict.fromkeys(TOKEN_KEYS) | {"input": 3, "output": 4}},
    ),
    (events.SessionIdentified(session_id="s"), None),
    (events.RunCompleted(result=Result(outcome=Outcome.SUCCESS)), None),
    (object(), None),
]


@pytest.mark.parametrize(("event", "expected"), _EVENT_CASES)
def test_event_dict_matches_stored_schema(event, expected) -> None:
    assert _event_dict(event) == expected


def _capabilities(streaming):
    async def check(req, **kwargs):
        check.calls += 1
        return Capabilities(available=True, executable=Path("/bin/x"), structured_streaming=streaming)

    check.calls = 0
    return check


def test_structured_streaming_none_reads_false_and_is_not_cached(monkeypatch) -> None:
    check = _capabilities(None)
    monkeypatch.setattr(drivers.shutil, "which", lambda *a, **k: "/bin/x")
    monkeypatch.setattr(drivers.coding_agent_cli, "check", check)
    registry = DriverRegistry()

    first = asyncio.run(registry.supports_structured_streaming(_target("claude")))
    second = asyncio.run(registry.supports_structured_streaming(_target("claude")))

    assert (first, second, check.calls) == (False, False, 2)


@pytest.mark.parametrize("supported", [True, False])
def test_structured_streaming_bool_is_cached_per_executable(monkeypatch, supported) -> None:
    check = _capabilities(supported)
    monkeypatch.setattr(drivers.shutil, "which", lambda *a, **k: "/bin/x")
    monkeypatch.setattr(drivers.coding_agent_cli, "check", check)
    registry = DriverRegistry()

    first = asyncio.run(registry.supports_structured_streaming(_target("claude")))
    second = asyncio.run(registry.supports_structured_streaming(_target("claude")))

    assert (first, second, check.calls) == (supported, supported, 1)


def test_structured_streaming_false_when_cli_missing(monkeypatch) -> None:
    check = _capabilities(True)
    monkeypatch.setattr(drivers.shutil, "which", lambda *a, **k: None)
    monkeypatch.setattr(drivers.coding_agent_cli, "check", check)

    assert asyncio.run(DriverRegistry().supports_structured_streaming(_target("claude"))) is False
    assert check.calls == 0


def test_structured_streaming_caller_cancellation_cancels_and_awaits_probe(monkeypatch) -> None:
    started = asyncio.Event()
    probe_cancelled = False
    probe_finished = False

    async def check(req, **kwargs):
        nonlocal probe_cancelled, probe_finished
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            probe_cancelled = True
            await asyncio.sleep(0)
            raise
        finally:
            probe_finished = True

    monkeypatch.setattr(drivers.shutil, "which", lambda *a, **k: "/bin/x")
    monkeypatch.setattr(drivers.coding_agent_cli, "check", check)

    async def scenario() -> tuple[bool, bool, bool]:
        caller = asyncio.create_task(DriverRegistry().supports_structured_streaming(_target("claude")))
        await started.wait()
        caller.cancel()
        with pytest.raises(asyncio.CancelledError):
            await caller
        return caller.cancelled(), probe_cancelled, probe_finished

    assert asyncio.run(scenario()) == (True, True, True)


def _target(backend: str, **settings) -> TargetConfig:
    return TargetConfig("t", backend, **settings)


# Refract-owned argv: permission flags and the codex profile come from the adapter. Model, reasoning,
# and system prompt travel as Request fields, so they never appear here, except for a codex profile,
# which carries model and reasoning in args because the library rejects `-c` beside Request.reasoning.
_TARGET_ARGS_CASES = {
    'agy_plain': (
        _target('agy'),
        ('--dangerously-skip-permissions',),
    ),
    'agy_ignores_policy_fields': (
        _target('agy', model='m', reasoning='r', system_prompt='s', backend_profile='bp', args=('--x',)),
        ('--dangerously-skip-permissions', '--x'),
    ),
    'codex_plain': (
        _target('codex'),
        ('--yolo',),
    ),
    'codex_profile': (
        _target('codex', backend_profile='bp'),
        ('--yolo', '--profile', 'bp'),
    ),
    'codex_model_follows_target_args': (
        _target('codex', model='m'),
        ('--yolo', '--model', 'm'),
    ),
    'codex_profile_model': (
        _target('codex', model='m', backend_profile='bp'),
        ('--yolo', '--profile', 'bp', '--model', 'm', '-c', 'model="m"'),
    ),
    'codex_profile_model_escaped': (
        _target('codex', model='a\\b"c', backend_profile='bp'),
        ('--yolo', '--profile', 'bp', '--model', 'a\\b"c', '-c', 'model="a\\\\b\\"c"'),
    ),
    'codex_reasoning_follows_target_args': (
        _target('codex', reasoning='high'),
        ('--yolo', '-c', 'model_reasoning_effort="high"'),
    ),
    'codex_all': (
        _target('codex', model='m', reasoning='r', system_prompt='s', backend_profile='bp', args=('--x', 'y')),
        ('--yolo', '--x', 'y', '--profile', 'bp', '--model', 'm', '-c', 'model="m"',
         '-c', 'model_reasoning_effort="r"'),
    ),
    'codex_profile_model_reasoning': (
        _target('codex', model='m', reasoning='high', backend_profile='bp'),
        ('--yolo', '--profile', 'bp', '--model', 'm', '-c', 'model="m"',
         '-c', 'model_reasoning_effort="high"'),
    ),
    'codex_profile_reasoning_without_model': (
        _target('codex', reasoning='high', backend_profile='bp'),
        ('--yolo', '--profile', 'bp', '-c', 'model_reasoning_effort="high"'),
    ),
    'pi_plain': (
        _target('pi'),
        ('--approve',),
    ),
    'pi_user_args_then_approve': (
        _target('pi', args=('--x',)),
        ('--x', '--approve'),
    ),
    'pi_all': (
        _target('pi', model='m', reasoning='r', system_prompt='s', backend_profile='bp', args=('--x',)),
        ('--x', '--approve'),
    ),
    'claude_plain': (
        _target('claude'),
        ('--permission-mode', 'bypassPermissions'),
    ),
    'claude_all': (
        _target('claude', model='m', reasoning='r', system_prompt='s', backend_profile='bp', args=('--x',)),
        ('--permission-mode', 'bypassPermissions', '--x'),
    ),
    'unknown_backend_passthrough': (
        _target('other', model='m', reasoning='r', args=('--x',)),
        ('--x',),
    ),
    'user_args_keep_order': (
        _target('claude', model='m', args=('--model', 'user')),
        ('--permission-mode', 'bypassPermissions', '--model', 'user'),
    ),
    'reject_dashdash': (
        _target('codex', args=('--',)),
        Raised(ValueError, "Target 't' args cannot contain the reserved '--' token"),
    ),
    'reject_nul': (
        _target('claude', args=('a\x00',)),
        Raised(ValueError, "Target 't' args cannot contain NUL bytes"),
    ),
    'reject_codex_cd': (
        _target('codex', args=('--cd=/x',)),
        Raised(ValueError, "Codex target 't' args cannot override the workspace root"),
    ),
    'reject_codex_short_c': (
        _target('codex', args=('-Cx',)),
        Raised(ValueError, "Codex target 't' args cannot override the workspace root"),
    ),
    'pi_skill_allowed': (
        _target('pi', args=('--skill=x',)),
        ('--skill=x', '--approve'),
    ),
    'reject_codex_cd_agy_ok': (
        _target('agy', args=('--cd', 'x')),
        ('--dangerously-skip-permissions', '--cd', 'x'),
    ),
}


@pytest.mark.parametrize("case", list(_TARGET_ARGS_CASES))
def test_target_args_characterization(case) -> None:
    target, expected = _TARGET_ARGS_CASES[case]
    assert outcome(lambda: _target_args(target)) == plain(expected)


def test_target_args_does_not_leak_env_into_argv() -> None:
    target = _target("claude", model="m", env={"SECRET": "value"})
    assert "value" not in _target_args(target)
    assert "SECRET" not in _target_args(target)



def _captured_request(monkeypatch, target: TargetConfig, **call) -> object:
    seen = []

    async def fake_run(request, **kwargs):
        seen.append(request)
        return Result(outcome=Outcome.SUCCESS)

    monkeypatch.setattr(drivers.coding_agent_cli, "run", fake_run)
    asyncio.run(DriverRegistry().execute(
        target=target, prompt="p", cwd=Path("."), session_id=call.get("session_id", ""),
        timeout_s=call.get("timeout_s", 0), cancel_event=threading.Event(),
    ))
    return seen[0]


def test_request_maps_unset_target_fields_to_none(monkeypatch) -> None:
    request = _captured_request(monkeypatch, _target("claude"))

    assert (request.model, request.reasoning, request.system_prompt) == (None, None, None)
    assert (request.session_id, request.timeout_s) == (None, None)


def test_request_carries_target_policy_and_call_values(monkeypatch) -> None:
    request = _captured_request(
        monkeypatch, _target("claude", model="m", reasoning="r", system_prompt="s"), session_id="sess", timeout_s=9,
    )

    assert (request.driver, request.model, request.reasoning, request.system_prompt) == ("claude", "m", "r", "s")
    assert (request.session_id, request.timeout_s) == ("sess", 9)


# Fields the previous drivers ignored; the library would reject them as unsupported_option.
_DROPPED_FIELDS = [
    ("codex", "system_prompt"),
    ("agy", "reasoning"),
    ("agy", "system_prompt"),
]


@pytest.mark.parametrize(("backend", "field"), _DROPPED_FIELDS)
def test_request_drops_fields_the_backend_ignored_before(monkeypatch, backend, field) -> None:
    request = _captured_request(monkeypatch, _target(backend, model="m", reasoning="r", system_prompt="s"))

    assert getattr(request, field) is None
    assert request.model == (None if backend == "codex" else "m")


@pytest.mark.parametrize(("backend", "field"), [
    ("claude", "reasoning"), ("claude", "system_prompt"), ("pi", "reasoning"), ("pi", "system_prompt"),
])
def test_request_keeps_fields_the_backend_supports(monkeypatch, backend, field) -> None:
    request = _captured_request(monkeypatch, _target(backend, reasoning="r", system_prompt="s"))

    assert getattr(request, field) == {"reasoning": "r", "system_prompt": "s"}[field]


@pytest.mark.parametrize(
    "settings",
    [
        {"backend_profile": "bp", "model": "m", "reasoning": "high"},
        {"backend_profile": "bp", "reasoning": "high"},
        {"reasoning": "high", "args": ["-c", "web_search=live"]},
    ],
    ids=["profile-model-reasoning", "profile-reasoning", "reasoning-with-config-args"],
)
def test_codex_target_is_not_rejected_for_reasoning(tmp_path, settings) -> None:
    target = _target("codex", **settings)

    result = asyncio.run(DriverRegistry().execute(
        target=target, prompt="p", cwd=tmp_path / "missing", session_id="", timeout_s=0,
        cancel_event=threading.Event(),
    ))

    assert result.error_code == "bad_cwd"


def test_codex_profile_target_moves_model_and_reasoning_out_of_the_request(monkeypatch) -> None:
    request = _captured_request(monkeypatch, _target("codex", backend_profile="bp", model="m", reasoning="high"))

    assert (request.model, request.reasoning) == (None, None)


def test_codex_target_fields_follow_target_args(monkeypatch) -> None:
    request = _captured_request(monkeypatch, _target("codex", model="m", reasoning="high", args=["-c", "web_search=live"]))

    assert (request.model, request.reasoning) == (None, None)
    assert request.args == ("--yolo", "-c", "web_search=live", "--model", "m", "-c", 'model_reasoning_effort="high"')
