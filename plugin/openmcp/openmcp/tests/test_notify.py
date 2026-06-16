import asyncio
import importlib
import sys
import types
from pathlib import Path

import pytest

from openmcp.backends import BackendResult


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

    await notify_mod.emit_start(backend="codex", session_id="sess-1", model="gpt-5")

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
                },
                "desktop": True,
                "webhook": False,
                "sound": False,
            },
        )
    ]


@pytest.mark.asyncio
async def test_emit_finish_and_error_use_expected_statuses(monkeypatch) -> None:
    calls = []

    def fake_notify(message, **kwargs):
        calls.append((message, kwargs))

    notify_mod = _load_notify_module(monkeypatch, fake_notify)
    monkeypatch.setenv("OPENMCP_NOTIFY_ENABLED", "yes")

    await notify_mod.emit_finish(backend="gemini", session_id="sess-2", model="gemini-2.5-pro")
    await notify_mod.emit_error(
        backend="gemini",
        session_id="sess-2",
        model="gemini-2.5-pro",
        error="fatal backend failure",
    )

    assert [call[1]["status"] for call in calls] == [
        "task_complete",
        "task_error",
    ]
    assert calls[0][0] == "Worker completed"
    assert calls[1][0] == "Worker failed: fatal backend failure"


@pytest.mark.asyncio
async def test_emit_is_disabled_by_default(monkeypatch) -> None:
    calls = []

    def fake_notify(message, **kwargs):
        calls.append((message, kwargs))

    notify_mod = _load_notify_module(monkeypatch, fake_notify)

    await notify_mod.emit_finish(backend="agy", session_id="", model="")

    assert calls == []


@pytest.mark.asyncio
async def test_emit_swallows_notify_errors(monkeypatch) -> None:
    def fake_notify(message, **kwargs):
        raise RuntimeError("boom")

    notify_mod = _load_notify_module(monkeypatch, fake_notify)
    monkeypatch.setenv("OPENMCP_NOTIFY_ENABLED", "on")

    await notify_mod.emit_error(backend="codex", session_id="sess-3", model="gpt-5", error="boom")


@pytest.mark.asyncio
async def test_emit_is_noop_when_dependency_missing(monkeypatch) -> None:
    notify_mod = _load_notify_module(monkeypatch, import_missing=True)
    monkeypatch.setenv("OPENMCP_NOTIFY_ENABLED", "1")

    await notify_mod.emit_start(backend="agy", session_id="", model="")


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

    await notify_mod.emit_finish(backend="codex", session_id="sess-4", model="gpt-5")

    assert len(to_thread_calls) == 1
    assert to_thread_calls[0][0] is fake_notify
    assert calls[0][0] == "Worker completed"


@pytest.mark.asyncio
async def test_run_emits_start_and_finish_on_success(monkeypatch) -> None:
    import openmcp.server as srv

    events = []

    async def fake_codex_execute(params):
        return BackendResult(
            outcome="OK",
            SESSION_ID="sess-ok",
            agent_messages="done",
            error="",
            error_class="",
        )

    async def fake_emit_start(**kwargs):
        events.append(("start", kwargs))

    async def fake_emit_finish(**kwargs):
        events.append(("finish", kwargs))

    async def fake_emit_error(**kwargs):
        events.append(("error", kwargs))

    monkeypatch.setattr(srv, "codex_execute", fake_codex_execute)
    monkeypatch.setattr(srv, "emit_start", fake_emit_start)
    monkeypatch.setattr(srv, "emit_finish", fake_emit_finish)
    monkeypatch.setattr(srv, "emit_error", fake_emit_error)
    monkeypatch.setenv("OPENMCP_CODEX_MODEL_DEFAULT", "")

    out = await srv.run(backend="codex", PROMPT="x", cd=Path("."))

    assert out == {"success": True, "SESSION_ID": "sess-ok", "agent_messages": "done", "error": ""}
    assert events == [
        ("start", {"backend": "codex", "session_id": "", "model": ""}),
        ("finish", {"backend": "codex", "session_id": "sess-ok", "model": ""}),
    ]


@pytest.mark.asyncio
async def test_run_emits_error_on_failure(monkeypatch) -> None:
    import openmcp.server as srv

    events = []

    async def fake_gemini_execute(params):
        return BackendResult(
            outcome="FATAL",
            SESSION_ID="sess-fail",
            agent_messages="partial",
            error="fatal",
            error_class="fatal_backend",
        )

    async def fake_emit_start(**kwargs):
        events.append(("start", kwargs))

    async def fake_emit_finish(**kwargs):
        events.append(("finish", kwargs))

    async def fake_emit_error(**kwargs):
        events.append(("error", kwargs))

    monkeypatch.setattr(srv, "gemini_execute", fake_gemini_execute)
    monkeypatch.setattr(srv, "emit_start", fake_emit_start)
    monkeypatch.setattr(srv, "emit_finish", fake_emit_finish)
    monkeypatch.setattr(srv, "emit_error", fake_emit_error)
    monkeypatch.setenv("OPENMCP_GEMINI_ROUTE_TO_AGY", "false")
    monkeypatch.setenv("OPENMCP_GEMINI_MODEL_DEFAULT", "")

    out = await srv.run(backend="gemini", PROMPT="x", cd=Path("."))

    assert out == {"success": False, "SESSION_ID": "sess-fail", "agent_messages": "partial", "error": "fatal"}
    assert events == [
        ("start", {"backend": "gemini", "session_id": "", "model": ""}),
        ("error", {"backend": "gemini", "session_id": "sess-fail", "model": "", "error": "fatal"}),
    ]


@pytest.mark.asyncio
async def test_run_defaults_disabled_keeps_response_payload_unchanged(monkeypatch) -> None:
    import openmcp.server as srv

    async def fake_agy_execute(params):
        return BackendResult(
            outcome="OK",
            SESSION_ID="sess-x",
            agent_messages="lots of text",
            error="",
            error_class="",
        )

    monkeypatch.delenv("OPENMCP_NOTIFY_ENABLED", raising=False)
    monkeypatch.setattr(srv, "agy_execute", fake_agy_execute)

    out = await srv.run(backend="agy", PROMPT="x", cd=Path("."))

    assert out == {"success": True, "SESSION_ID": "sess-x", "agent_messages": "lots of text", "error": ""}
