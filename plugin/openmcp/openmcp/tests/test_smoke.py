import asyncio
import inspect
import json
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from openmcp.backends import BackendResult
from openmcp.backends.agy import AgyParams, execute as agy_execute
from openmcp.backends.codex import CodexParams, execute as codex_execute
from openmcp.retry import run_with_retry


def test_imports() -> None:
    import openmcp.server  # noqa: F401
    import openmcp.retry  # noqa: F401
    import openmcp.cli  # noqa: F401
    import openmcp.backends.agy  # noqa: F401
    import openmcp.backends.codex  # noqa: F401


def test_codex_session_file_fallback(monkeypatch, tmp_path) -> None:
    from openmcp.backends.codex import _extract_session_id_from_latest_session

    session_id = "019e532a-2d92-7281-8bd1-0110af0a34aa"
    sessions_dir = tmp_path / "codex-home" / "sessions" / "2026" / "05" / "23"
    sessions_dir.mkdir(parents=True)
    session_file = sessions_dir / f"rollout-2026-05-23T11-48-53-{session_id}.jsonl"
    prompt = "Reply with exactly the word PONG and nothing else."
    session_file.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "session_meta",
                        "payload": {
                            "id": session_id,
                            "cwd": str(tmp_path),
                            "originator": "codex_exec",
                        },
                    }
                ),
                json.dumps({"type": "event_msg", "payload": {"message": prompt}}),
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))

    assert _extract_session_id_from_latest_session(tmp_path, prompt, time.time() - 1) == session_id


def test_codex_profile_exists_from_config(monkeypatch, tmp_path) -> None:
    from openmcp.backends.codex import _profile_exists

    codex_home = tmp_path / "codex-home"
    codex_home.mkdir(parents=True)
    (codex_home / "config.toml").write_text(
        "[profiles]\n"
        "[profiles.mcp_execution]\n"
        "model = \"gpt-5\"\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    assert _profile_exists("mcp_execution") is True
    assert _profile_exists("missing") is False


def test_tool_signature() -> None:
    from openmcp.server import run

    sig = inspect.signature(run)
    params = list(sig.parameters.keys())
    assert params == [
        "backend",
        "PROMPT",
        "cd",
        "SESSION_ID",
        "model",
        "profile",
        "max_retries",
        "retry_base_ms",
        "debug",
    ]
    assert sig.parameters["debug"].default is False


@pytest.mark.asyncio
async def test_retry_forwards_session_id() -> None:
    @dataclass
    class StubParams:
        SESSION_ID: str = ""

    calls: list[str] = []

    async def execute_fn(params: StubParams) -> BackendResult:
        calls.append(params.SESSION_ID)
        if len(calls) == 1:
            return BackendResult(
                outcome="RETRYABLE",
                SESSION_ID="sess-1",
                agent_messages="",
                error="transient",
                error_class="retryable_backend",
            )
        return BackendResult(
            outcome="OK",
            SESSION_ID="sess-2",
            agent_messages="done",
            error="",
            error_class="",
        )

    out = await run_with_retry(execute_fn, StubParams(), max_retries=2, retry_base_ms=1)
    assert out["attempts"] == 2
    assert out["success"] is True
    assert out["SESSION_ID"] == "sess-2"
    assert calls == ["", "sess-1"]


@pytest.mark.asyncio
async def test_fatal_returns_immediately() -> None:
    @dataclass
    class StubParams:
        SESSION_ID: str = ""

    async def execute_fn(_: StubParams) -> BackendResult:
        return BackendResult(
            outcome="FATAL",
            SESSION_ID="",
            agent_messages="",
            error="fatal",
            error_class="fatal_backend",
        )

    out = await run_with_retry(execute_fn, StubParams(), max_retries=3, retry_base_ms=1)
    assert out["attempts"] == 1
    assert out["success"] is False


@pytest.mark.asyncio
async def test_bad_cd_agy_fatal() -> None:
    bad = Path("C:/definitely/not/real/path")
    out = await agy_execute(AgyParams(PROMPT="x", cd=bad))
    assert out.outcome == "FATAL"
    assert out.error_class == "bad_cd"


@pytest.mark.asyncio
async def test_bad_cd_codex_fatal() -> None:
    bad = Path("C:/definitely/not/real/path")
    out = await codex_execute(CodexParams(PROMPT="x", cd=bad))
    assert out.outcome == "FATAL"
    assert out.error_class == "bad_cd"


@pytest.mark.asyncio
async def test_non_debug_shape_success(monkeypatch) -> None:
    import openmcp.server as srv

    async def fake(execute_fn, params, *, max_retries, retry_base_ms):
        return {
            "success": True,
            "SESSION_ID": "sess-x",
            "agent_messages": "lots of text",
            "attempts": 1,
        }

    monkeypatch.setattr(srv, "run_with_retry", fake)
    out = await srv.run(backend="agy", PROMPT="x", cd=Path("."))
    assert set(out.keys()) == {"success", "SESSION_ID", "error"}
    assert out == {"success": True, "SESSION_ID": "sess-x", "error": ""}


@pytest.mark.asyncio
async def test_non_debug_shape_failure(monkeypatch) -> None:
    import openmcp.server as srv

    async def fake(execute_fn, params, *, max_retries, retry_base_ms):
        return {"success": False, "error": "boom", "attempts": 1}

    monkeypatch.setattr(srv, "run_with_retry", fake)
    out = await srv.run(backend="codex", PROMPT="x", cd=Path("."))
    assert set(out.keys()) == {"success", "SESSION_ID", "error"}
    assert out == {"success": False, "SESSION_ID": "", "error": "boom"}


@pytest.mark.asyncio
async def test_debug_shape_passthrough(monkeypatch) -> None:
    import openmcp.server as srv

    full = {
        "success": True,
        "SESSION_ID": "sess-x",
        "agent_messages": "hi",
        "attempts": 2,
    }

    async def fake(execute_fn, params, *, max_retries, retry_base_ms):
        return full

    monkeypatch.setattr(srv, "run_with_retry", fake)
    out = await srv.run(backend="agy", PROMPT="x", cd=Path("."), debug=True)
    assert out == full


@pytest.mark.asyncio
async def test_env_defaults_applied_for_agy_model(monkeypatch) -> None:
    import openmcp.server as srv

    captured = {}

    async def fake(execute_fn, params, *, max_retries, retry_base_ms):
        captured["model"] = params.model
        return {"success": True, "SESSION_ID": "", "error": ""}

    monkeypatch.setenv("OPENMCP_AGY_MODEL_DEFAULT", "gemini-3.5-flash")
    monkeypatch.setattr(srv, "run_with_retry", fake)
    await srv.run(backend="agy", PROMPT="x", cd=Path("."))
    assert captured["model"] == "gemini-3.5-flash"


@pytest.mark.asyncio
async def test_env_defaults_applied_for_codex_model_and_profile(monkeypatch) -> None:
    import openmcp.server as srv

    captured = {}

    async def fake(execute_fn, params, *, max_retries, retry_base_ms):
        captured["model"] = params.model
        captured["profile"] = params.profile
        return {"success": True, "SESSION_ID": "", "error": ""}

    monkeypatch.setenv("OPENMCP_CODEX_MODEL_DEFAULT", "gpt-5")
    monkeypatch.setenv("OPENMCP_CODEX_PROFILE_DEFAULT", "mcp_execution")
    monkeypatch.setattr(srv, "run_with_retry", fake)
    await srv.run(backend="codex", PROMPT="x", cd=Path("."))
    assert captured["model"] == "gpt-5"
    assert captured["profile"] == "mcp_execution"


@pytest.mark.asyncio
async def test_explicit_model_and_profile_override_env_defaults(monkeypatch) -> None:
    import openmcp.server as srv

    captured = {}

    async def fake(execute_fn, params, *, max_retries, retry_base_ms):
        captured["model"] = params.model
        captured["profile"] = params.profile
        return {"success": True, "SESSION_ID": "", "error": ""}

    monkeypatch.setenv("OPENMCP_CODEX_MODEL_DEFAULT", "gpt-5")
    monkeypatch.setenv("OPENMCP_CODEX_PROFILE_DEFAULT", "mcp_execution")
    monkeypatch.setattr(srv, "run_with_retry", fake)
    await srv.run(
        backend="codex",
        PROMPT="x",
        cd=Path("."),
        model="gpt-5-mini",
        profile="custom-profile",
    )
    assert captured["model"] == "gpt-5-mini"
    assert captured["profile"] == "custom-profile"
