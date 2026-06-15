import asyncio
import importlib
import sys
import types
from dataclasses import dataclass
from pathlib import Path

import pytest

from openmcp.backends import BackendResult
from openmcp.retry import run_with_retry


def _load_notify_module(monkeypatch, notify_impl=None, *, import_missing: bool = False):
    sys.modules.pop("openmcp.notify", None)
    sys.modules.pop("notify_system", None)
    if notify_impl is not None:
        fake_module = types.ModuleType("notify_system")
        fake_module.notify = notify_impl
        sys.modules["notify_system"] = fake_module
    original_import = __import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if import_missing and name == "notify_system":
            raise ImportError("missing optional dependency")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", fake_import)
    return importlib.import_module("openmcp.notify")


@pytest.mark.asyncio
async def test_emit_start_notifies_with_expected_payload(monkeypatch) -> None:
    calls = []

    def fake_notify(message, **kwargs):
        calls.append((message, kwargs))

    notify_mod = _load_notify_module(monkeypatch, fake_notify)

    monkeypatch.setenv("OPENMCP_NOTIFY_ENABLED", "true")
    monkeypatch.setenv("OPENMCP_NOTIFY_TITLE", "openmcp worker")

    await notify_mod.emit_start(backend="codex", session_id="sess-1", model="gpt-5", attempts=1)

    assert calls == [
        (
            "Worker started",
            {
                "status": "task_started",
                "title": "openmcp worker",
                "context": {
                    "backend": "codex",
                    "session_id": "sess-1",
                    "model": "gpt-5",
                    "attempts": 1,
                },
                "desktop": True,
                "webhook": False,
                "sound": False,
            },
        )
    ]


@pytest.mark.asyncio
async def test_emit_attempt_finish_and_error_use_expected_statuses(monkeypatch) -> None:
    calls = []

    def fake_notify(message, **kwargs):
        calls.append((message, kwargs))

    notify_mod = _load_notify_module(monkeypatch, fake_notify)
    monkeypatch.setenv("OPENMCP_NOTIFY_ENABLED", "yes")

    await notify_mod.emit_attempt_failed(
        backend="gemini",
        session_id="sess-2",
        model="gemini-2.5-pro",
        attempts=2,
        error="rate limit",
    )
    await notify_mod.emit_finish(backend="gemini", session_id="sess-2", model="gemini-2.5-pro", attempts=3)
    await notify_mod.emit_error(
        backend="gemini",
        session_id="sess-2",
        model="gemini-2.5-pro",
        attempts=3,
        error="fatal backend failure",
    )

    assert [call[1]["status"] for call in calls] == [
        "task_retry",
        "task_complete",
        "task_error",
    ]
    assert calls[0][0] == "Attempt 2 failed: rate limit"
    assert calls[1][0] == "Worker completed"
    assert calls[2][0] == "Worker failed: fatal backend failure"


@pytest.mark.asyncio
async def test_emit_is_disabled_by_default(monkeypatch) -> None:
    calls = []

    def fake_notify(message, **kwargs):
        calls.append((message, kwargs))

    notify_mod = _load_notify_module(monkeypatch, fake_notify)

    await notify_mod.emit_finish(backend="agy", session_id="", model="", attempts=1)

    assert calls == []


@pytest.mark.asyncio
async def test_emit_swallows_notify_errors(monkeypatch) -> None:
    def fake_notify(message, **kwargs):
        raise RuntimeError("boom")

    notify_mod = _load_notify_module(monkeypatch, fake_notify)
    monkeypatch.setenv("OPENMCP_NOTIFY_ENABLED", "on")

    await notify_mod.emit_error(backend="codex", session_id="sess-3", model="gpt-5", attempts=1, error="boom")


@pytest.mark.asyncio
async def test_emit_is_noop_when_dependency_missing(monkeypatch) -> None:
    notify_mod = _load_notify_module(monkeypatch, import_missing=True)
    monkeypatch.setenv("OPENMCP_NOTIFY_ENABLED", "1")

    await notify_mod.emit_start(backend="agy", session_id="", model="", attempts=1)


@pytest.mark.asyncio
async def test_emit_dispatches_notify_via_asyncio_to_thread(monkeypatch) -> None:
    calls = []
    to_thread_calls = []

    def fake_notify(message, **kwargs):
        calls.append((message, kwargs))

    notify_mod = _load_notify_module(monkeypatch, fake_notify)
    monkeypatch.setenv("OPENMCP_NOTIFY_ENABLED", "true")

    async def fake_to_thread(fn, *args, **kwargs):
        to_thread_calls.append((fn, args, kwargs))
        return fn(*args, **kwargs)

    monkeypatch.setattr(notify_mod.asyncio, "to_thread", fake_to_thread)

    await notify_mod.emit_finish(backend="codex", session_id="sess-4", model="gpt-5", attempts=2)

    assert len(to_thread_calls) == 1
    assert to_thread_calls[0][0] is fake_notify
    assert calls[0][0] == "Worker completed"


@pytest.mark.asyncio
async def test_run_emits_start_and_finish_on_success(monkeypatch) -> None:
    import openmcp.server as srv

    events = []

    async def fake_run_with_retry(execute_fn, params, *, max_retries, retry_base_ms):
        return {
            "success": True,
            "SESSION_ID": "sess-ok",
            "agent_messages": "done",
            "attempts": 2,
        }

    async def fake_emit_start(**kwargs):
        events.append(("start", kwargs))

    async def fake_emit_finish(**kwargs):
        events.append(("finish", kwargs))

    async def fake_emit_error(**kwargs):
        events.append(("error", kwargs))

    monkeypatch.setattr(srv, "run_with_retry", fake_run_with_retry)
    monkeypatch.setattr(srv, "emit_start", fake_emit_start)
    monkeypatch.setattr(srv, "emit_finish", fake_emit_finish)
    monkeypatch.setattr(srv, "emit_error", fake_emit_error)
    monkeypatch.setenv("OPENMCP_CODEX_MODEL_DEFAULT", "")

    out = await srv.run(backend="codex", PROMPT="x", cd=Path("."))

    assert out == {"success": True, "SESSION_ID": "sess-ok", "agent_messages": "done", "error": ""}
    assert events == [
        ("start", {"backend": "codex", "session_id": "", "model": "", "attempts": 1}),
        ("finish", {"backend": "codex", "session_id": "sess-ok", "model": "", "attempts": 2}),
    ]


@pytest.mark.asyncio
async def test_run_with_retry_emits_attempt_failed_for_retryable_attempt(monkeypatch) -> None:
    import openmcp.retry as retry_mod

    @dataclass
    class StubParams:
        SESSION_ID: str = ""
        model: str = "gpt-5"

    events = []

    async def fake_emit_attempt_failed(**kwargs):
        events.append(kwargs)

    async def fake_sleep(_seconds):
        return None

    calls = 0

    async def execute_fn(params: StubParams) -> BackendResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            return BackendResult(
                outcome="RETRYABLE",
                SESSION_ID="sess-retry",
                agent_messages="",
                error="transient",
                error_class="retryable_backend",
            )
        return BackendResult(
            outcome="OK",
            SESSION_ID="sess-ok",
            agent_messages="done",
            error="",
            error_class="",
        )

    monkeypatch.setattr(retry_mod, "emit_attempt_failed", fake_emit_attempt_failed)
    monkeypatch.setattr(retry_mod.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(retry_mod.random, "uniform", lambda _low, _high: 1.0)

    out = await run_with_retry(execute_fn, StubParams(), max_retries=2, retry_base_ms=1)

    assert out["success"] is True
    assert out["attempts"] == 2
    assert events == [
        {
            "backend": "test_notify",
            "session_id": "sess-retry",
            "model": "gpt-5",
            "attempts": 1,
            "error": "transient",
        }
    ]


@pytest.mark.asyncio
async def test_run_emits_error_on_final_failure(monkeypatch) -> None:
    import openmcp.server as srv

    events = []

    async def fake_run_with_retry(execute_fn, params, *, max_retries, retry_base_ms):
        return {
            "success": False,
            "SESSION_ID": "sess-fail",
            "agent_messages": "partial",
            "error": "fatal",
            "attempts": 3,
        }

    async def fake_emit_start(**kwargs):
        events.append(("start", kwargs))

    async def fake_emit_finish(**kwargs):
        events.append(("finish", kwargs))

    async def fake_emit_error(**kwargs):
        events.append(("error", kwargs))

    monkeypatch.setattr(srv, "run_with_retry", fake_run_with_retry)
    monkeypatch.setattr(srv, "emit_start", fake_emit_start)
    monkeypatch.setattr(srv, "emit_finish", fake_emit_finish)
    monkeypatch.setattr(srv, "emit_error", fake_emit_error)
    monkeypatch.setenv("OPENMCP_GEMINI_ROUTE_TO_AGY", "false")
    monkeypatch.setenv("OPENMCP_GEMINI_MODEL_DEFAULT", "")

    out = await srv.run(backend="gemini", PROMPT="x", cd=Path("."))

    assert out == {"success": False, "SESSION_ID": "sess-fail", "agent_messages": "partial", "error": "fatal"}
    assert events == [
        ("start", {"backend": "gemini", "session_id": "", "model": "", "attempts": 1}),
        ("error", {"backend": "gemini", "session_id": "sess-fail", "model": "", "attempts": 3, "error": "fatal"}),
    ]


@pytest.mark.asyncio
async def test_run_defaults_disabled_keeps_response_payload_unchanged(monkeypatch) -> None:
    import openmcp.server as srv

    async def fake_run_with_retry(execute_fn, params, *, max_retries, retry_base_ms):
        return {
            "success": True,
            "SESSION_ID": "sess-x",
            "agent_messages": "lots of text",
            "attempts": 1,
        }

    monkeypatch.delenv("OPENMCP_NOTIFY_ENABLED", raising=False)
    monkeypatch.setattr(srv, "run_with_retry", fake_run_with_retry)

    out = await srv.run(backend="agy", PROMPT="x", cd=Path("."))

    assert out == {"success": True, "SESSION_ID": "sess-x", "agent_messages": "lots of text", "error": ""}
