import asyncio
import importlib
import sys
import types
from types import SimpleNamespace
from pathlib import Path

import pytest


def _load_compression_module(monkeypatch, client_cls=None, *, import_missing: bool = False):
    sys.modules.pop("openmcp.compression", None)
    sys.modules.pop("thetokencompany", None)
    if client_cls is not None:
        fake_module = types.ModuleType("thetokencompany")
        fake_module.AsyncTheTokenCompany = client_cls
        sys.modules["thetokencompany"] = fake_module
    original_import = __import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if import_missing and name == "thetokencompany":
            raise ImportError("missing optional dependency")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", fake_import)
    return importlib.import_module("openmcp.compression")


class _FakeClient:
    calls = []
    outputs = []
    error = None

    def __init__(self, *, api_key):
        self.api_key = api_key

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def compress(self, text, *, model, aggressiveness):
        type(self).calls.append(
            {
                "api_key": self.api_key,
                "text": text,
                "model": model,
                "aggressiveness": aggressiveness,
            }
        )
        if type(self).error is not None:
            raise type(self).error
        output = type(self).outputs.pop(0)
        return SimpleNamespace(output=output)


def _erp_text() -> str:
    return (
        "# EXTERNAL RESPONSE\n"
        "## META\n"
        "- Phase 2 / codex / SessionID N/A / Started 2026-06-15 / Finished 2026-06-15 / Plan dir docs/plans/x\n"
        "## SUMMARY\n"
        "Original summary prose.\n"
        "## FILES MODIFIED\n"
        "| Action | Path | Change |\n"
        "| Modify | src/openmcp/server.py | Hook compression |\n"
        "## COMMITS\n"
        "- phase-2.task-1: deadbee  phase-2.task-1: add compression tests\n"
        "## NOTES\n"
        "- First note prose.\n"
        "- Second note prose.\n"
        "## SPEC COMPLIANCE\n"
        "- Meets Spec? YES  - covered by tests.\n"
        "## CLARIFICATIONS NEEDED\n"
        "None\n"
        "## NEXT\n"
        "TASK_COMPLETE\n"
        "Phase 2 completed. Journal: docs/plans/x/phase-02/journal.md.\n"
    )


@pytest.mark.asyncio
async def test_compress_response_only_rewrites_summary_and_notes_in_erp(monkeypatch) -> None:
    _FakeClient.calls = []
    _FakeClient.outputs = ["COMPRESSED SUMMARY", "COMPRESSED NOTES"]
    _FakeClient.error = None
    compression = _load_compression_module(monkeypatch, _FakeClient)
    original = _erp_text()
    env = {
        "OPENMCP_COMPRESS_RESPONSE": "true",
        "OPENMCP_TTC_API_KEY": "secret",
    }

    out = await compression.compress_response(original, env)

    assert "COMPRESSED SUMMARY" in out
    assert "COMPRESSED NOTES" in out
    assert "Original summary prose." not in out
    assert "- First note prose." not in out
    assert "## META\n- Phase 2 / codex / SessionID N/A / Started 2026-06-15 / Finished 2026-06-15 / Plan dir docs/plans/x\n" in out
    assert "## FILES MODIFIED\n| Action | Path | Change |\n| Modify | src/openmcp/server.py | Hook compression |\n" in out
    assert "## COMMITS\n- phase-2.task-1: deadbee  phase-2.task-1: add compression tests\n" in out
    assert "## SPEC COMPLIANCE\n- Meets Spec? YES  - covered by tests.\n" in out
    assert out.endswith("Phase 2 completed. Journal: docs/plans/x/phase-02/journal.md.\n")
    assert [call["text"] for call in _FakeClient.calls] == [
        "Original summary prose.\n",
        "- First note prose.\n- Second note prose.\n",
    ]


@pytest.mark.asyncio
async def test_compress_response_without_erp_compresses_whole_text_once(monkeypatch) -> None:
    _FakeClient.calls = []
    _FakeClient.outputs = ["COMPRESSED BODY"]
    _FakeClient.error = None
    compression = _load_compression_module(monkeypatch, _FakeClient)
    env = {
        "OPENMCP_COMPRESS_RESPONSE": "1",
        "OPENMCP_TTC_API_KEY": "secret",
        "OPENMCP_TTC_MODEL": "bear-2",
        "OPENMCP_TTC_AGGRESSIVENESS": "0.7",
    }

    out = await compression.compress_response("plain response", env)

    assert out == "COMPRESSED BODY"
    assert _FakeClient.calls == [
        {
            "api_key": "secret",
            "text": "plain response",
            "model": "bear-2",
            "aggressiveness": 0.7,
        }
    ]


@pytest.mark.asyncio
async def test_compress_response_disabled_missing_key_and_empty_text_are_noops(monkeypatch) -> None:
    _FakeClient.calls = []
    _FakeClient.outputs = ["unused"]
    _FakeClient.error = None
    compression = _load_compression_module(monkeypatch, _FakeClient)

    assert await compression.compress_response("body", {}) == "body"
    assert await compression.compress_response(
        "body",
        {"OPENMCP_COMPRESS_RESPONSE": "true"},
    ) == "body"
    assert await compression.compress_response(
        "",
        {"OPENMCP_COMPRESS_RESPONSE": "true", "OPENMCP_TTC_API_KEY": "secret"},
    ) == ""
    assert _FakeClient.calls == []


@pytest.mark.asyncio
async def test_compress_response_is_noop_when_dependency_missing(monkeypatch) -> None:
    compression = _load_compression_module(monkeypatch, import_missing=True)
    env = {
        "OPENMCP_COMPRESS_RESPONSE": "yes",
        "OPENMCP_TTC_API_KEY": "secret",
    }

    out = await compression.compress_response("body", env)

    assert out == "body"


@pytest.mark.asyncio
async def test_compress_response_returns_original_when_client_raises(monkeypatch) -> None:
    _FakeClient.calls = []
    _FakeClient.outputs = []
    _FakeClient.error = RuntimeError("boom")
    compression = _load_compression_module(monkeypatch, _FakeClient)
    env = {
        "OPENMCP_COMPRESS_RESPONSE": "on",
        "OPENMCP_TTC_API_KEY": "secret",
    }
    original = "plain response"

    out = await compression.compress_response(original, env)

    assert out == original
    assert _FakeClient.calls[0]["text"] == original


@pytest.mark.asyncio
async def test_compress_response_returns_original_on_timeout(monkeypatch) -> None:
    _FakeClient.calls = []
    _FakeClient.outputs = ["never used"]
    _FakeClient.error = None
    compression = _load_compression_module(monkeypatch, _FakeClient)
    env = {
        "OPENMCP_COMPRESS_RESPONSE": "true",
        "OPENMCP_TTC_API_KEY": "secret",
        "OPENMCP_TTC_TIMEOUT_S": "3",
    }

    async def fake_wait_for(awaitable, timeout):
        awaitable.close()
        raise TimeoutError

    monkeypatch.setattr(compression.asyncio, "wait_for", fake_wait_for)

    out = await compression.compress_response("plain response", env)

    assert out == "plain response"
    assert _FakeClient.calls == []


@pytest.mark.asyncio
async def test_compress_response_leaves_malformed_erp_unchanged(monkeypatch) -> None:
    _FakeClient.calls = []
    _FakeClient.outputs = ["unused"]
    _FakeClient.error = None
    compression = _load_compression_module(monkeypatch, _FakeClient)
    env = {
        "OPENMCP_COMPRESS_RESPONSE": "true",
        "OPENMCP_TTC_API_KEY": "secret",
    }
    original = "# EXTERNAL RESPONSE\n## SUMMARY"

    out = await compression.compress_response(original, env)

    assert out == original
    assert _FakeClient.calls == []


@pytest.mark.asyncio
async def test_run_passes_agent_messages_through_compress_response(monkeypatch) -> None:
    import openmcp.server as srv

    captured = {}

    async def fake_run_with_retry(execute_fn, params, *, max_retries, retry_base_ms):
        captured["prompt"] = params.PROMPT
        return {
            "success": True,
            "SESSION_ID": "sess-x",
            "agent_messages": "original body",
            "attempts": 1,
        }

    async def fake_compress_response(text, env):
        captured["text"] = text
        captured["env"] = env
        return "compressed body"

    monkeypatch.setattr(srv, "run_with_retry", fake_run_with_retry)
    monkeypatch.setattr(srv, "compress_response", fake_compress_response)
    monkeypatch.setenv("OPENMCP_COMPRESS_RESPONSE", "true")
    monkeypatch.setenv("OPENMCP_TTC_API_KEY", "secret")

    out = await srv.run(backend="agy", PROMPT="prompt text", cd=Path("."))

    assert out == {
        "success": True,
        "SESSION_ID": "sess-x",
        "agent_messages": "compressed body",
        "error": "",
    }
    assert captured["text"] == "original body"
    assert captured["prompt"] == "prompt text"
    assert captured["env"]["OPENMCP_COMPRESS_RESPONSE"] == "true"
    assert captured["env"]["OPENMCP_TTC_API_KEY"] == "secret"


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

    monkeypatch.delenv("OPENMCP_COMPRESS_RESPONSE", raising=False)
    monkeypatch.delenv("OPENMCP_TTC_API_KEY", raising=False)
    monkeypatch.setattr(srv, "run_with_retry", fake_run_with_retry)

    out = await srv.run(backend="codex", PROMPT="x", cd=Path("."))

    assert out == {
        "success": True,
        "SESSION_ID": "sess-x",
        "agent_messages": "lots of text",
        "error": "",
    }
