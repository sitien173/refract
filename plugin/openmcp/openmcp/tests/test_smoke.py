import asyncio
import contextlib
import inspect
import json
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from openmcp.backends import BackendResult
from openmcp.backends.agy import AgyParams, execute as agy_execute
from openmcp.backends.codex import CodexParams, execute as codex_execute
from openmcp.backends.gemini import GeminiParams, execute as gemini_execute
from openmcp.retry import run_with_retry


def test_imports() -> None:
    import openmcp.server  # noqa: F401
    import openmcp.retry  # noqa: F401
    import openmcp.cli  # noqa: F401
    import openmcp.backends.agy  # noqa: F401
    import openmcp.backends.codex  # noqa: F401
    import openmcp.backends.gemini  # noqa: F401


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


def test_agy_extract_session_id_patterns() -> None:
    from openmcp.backends.agy import _extract_session_id

    session_id = "b658ef34-d18c-4294-b329-0ae5dee0157b"

    assert _extract_session_id(f"--conversation {session_id}") == session_id
    assert _extract_session_id(f"conversationId: {session_id}") == session_id
    assert _extract_session_id(f"session_id = {session_id}") == session_id
    assert _extract_session_id(f"threadId {session_id}") == session_id


def test_agy_recent_conversation_file_fallback(monkeypatch, tmp_path) -> None:
    from openmcp.backends import agy as agy_backend

    session_id = "b658ef34-d18c-4294-b329-0ae5dee0157b"
    conversation_file = tmp_path / f"{session_id}.pb"
    conversation_file.write_bytes(b"conversation")
    monkeypatch.setattr(agy_backend, "_CONVERSATIONS_PATH", tmp_path)

    assert agy_backend._extract_session_id_from_recent_conversation_file(time.time() - 1) == session_id
    assert agy_backend._extract_session_id_from_recent_conversation_file(time.time() + 120) == ""


def test_agy_strips_windows_terminal_title_escape() -> None:
    from openmcp.backends.agy import _strip_ansi

    assert _strip_ansi("\x1b]0;Administrator:  C:\\WINDOWS\\system32\\cmd.exe \x1b\\PONG") == "PONG"
    assert _strip_ansi("\x1b]0;Administrator:  C:\\WINDOWS\\system32\\cmd.exe \x1b\\") == ""


@pytest.mark.asyncio
async def test_agy_falls_back_to_configured_model_when_model_override_has_no_output(monkeypatch, tmp_path) -> None:
    from openmcp.backends import agy as agy_backend
    from openmcp.session_marker import SESSION_MARKER

    calls = []
    session_id = "b658ef34-d18c-4294-b329-0ae5dee0157b"
    outputs = iter(
        [
            "",
            f"PONG\n[{SESSION_MARKER}]: {session_id}",
        ]
    )

    def fake_pty(cmd, cwd=None):
        calls.append(cmd)
        return next(outputs)

    @contextlib.contextmanager
    def noop_context(*args, **kwargs):
        yield

    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps({"model": "Claude Opus 4.6 (Thinking)"}), encoding="utf-8")

    monkeypatch.setattr(agy_backend, "_SETTINGS_PATH", settings_path)
    monkeypatch.setattr(agy_backend, "_temporary_disabled_plugin", noop_context)
    monkeypatch.setattr(agy_backend, "run_shell_command_pty", fake_pty)
    monkeypatch.setattr(agy_backend, "_extract_session_id_from_recent_conversation_file", lambda started_at: "")
    monkeypatch.setattr(agy_backend, "_extract_session_id_from_latest_log", lambda: "")
    monkeypatch.setattr(agy_backend.shutil, "which", lambda name: f"C:/bin/{name}.exe")

    out = await agy_backend.execute(AgyParams(PROMPT="x", cd=tmp_path, model="gemini-3.5-flash"))

    assert out.outcome == "OK"
    assert out.SESSION_ID == session_id
    assert out.agent_messages == "PONG"
    assert len(calls) == 2
    assert calls[0][0:2] == ["agy", "--print"]
    assert calls[1][0:2] == ["agy", "--print"]


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
async def test_bad_cd_gemini_fatal() -> None:
    bad = Path("C:/definitely/not/real/path")
    out = await gemini_execute(GeminiParams(PROMPT="x", cd=bad))
    assert out.outcome == "FATAL"
    assert out.error_class == "bad_cd"


@pytest.mark.asyncio
async def test_gemini_uses_plain_output_without_stream_json(monkeypatch, tmp_path) -> None:
    from openmcp.backends import gemini as gemini_backend
    from openmcp.session_marker import SESSION_MARKER

    captured = {}

    def fake_run_shell_command(cmd, cwd=None):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        yield "PONG"
        yield f"[{SESSION_MARKER}]: sess-marker"

    monkeypatch.setattr(gemini_backend.shutil, "which", lambda name: f"C:/bin/{name}.exe")
    monkeypatch.setattr(gemini_backend, "run_shell_command", fake_run_shell_command)

    out = await gemini_backend.execute(GeminiParams(PROMPT="x", cd=tmp_path))

    assert "-o" not in captured["cmd"]
    assert "stream-json" not in captured["cmd"]
    assert SESSION_MARKER in captured["cmd"][2]
    assert out.outcome == "OK"
    assert out.SESSION_ID == "sess-marker"
    assert out.agent_messages == "PONG"
    assert "json decode error" not in out.error.lower()


@pytest.mark.asyncio
async def test_gemini_plain_output_without_session_id_is_warning(monkeypatch, tmp_path) -> None:
    from openmcp.backends import gemini as gemini_backend

    def fake_run_shell_command(cmd, cwd=None):
        yield "PONG"

    monkeypatch.setattr(gemini_backend.shutil, "which", lambda name: f"C:/bin/{name}.exe")
    monkeypatch.setattr(gemini_backend, "run_shell_command", fake_run_shell_command)

    out = await gemini_backend.execute(GeminiParams(PROMPT="x", cd=tmp_path))

    assert out.outcome == "OK"
    assert out.SESSION_ID == ""
    assert out.agent_messages == "PONG"
    assert out.error == "warning: no SESSION_ID"
    assert out.error_class == "warning"


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
async def test_env_defaults_applied_for_gemini_model(monkeypatch) -> None:
    import openmcp.server as srv

    captured = {}

    async def fake(execute_fn, params, *, max_retries, retry_base_ms):
        captured["execute_fn"] = execute_fn
        captured["model"] = params.model
        return {"success": True, "SESSION_ID": "", "error": ""}

    monkeypatch.setenv("OPENMCP_GEMINI_MODEL_DEFAULT", "gemini-2.5-pro")
    monkeypatch.setattr(srv, "run_with_retry", fake)
    await srv.run(backend="gemini", PROMPT="x", cd=Path("."))
    assert captured["execute_fn"] is srv.gemini_execute
    assert captured["model"] == "gemini-2.5-pro"


@pytest.mark.asyncio
async def test_gemini_can_route_to_agy_with_env(monkeypatch) -> None:
    import openmcp.server as srv

    captured = {}

    async def fake(execute_fn, params, *, max_retries, retry_base_ms):
        captured["execute_fn"] = execute_fn
        captured["params_type"] = type(params)
        captured["model"] = params.model
        return {"success": True, "SESSION_ID": "", "error": ""}

    monkeypatch.setenv("OPENMCP_GEMINI_ROUTE_TO_AGY", "true")
    monkeypatch.setenv("OPENMCP_AGY_MODEL_DEFAULT", "gemini-3.5-flash")
    monkeypatch.setenv("OPENMCP_GEMINI_MODEL_DEFAULT", "gemini-2.5-pro")
    monkeypatch.setattr(srv, "run_with_retry", fake)

    await srv.run(backend="gemini", PROMPT="x", cd=Path("."))

    assert captured["execute_fn"] is srv.agy_execute
    assert captured["params_type"] is AgyParams
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


def test_agy_plugin_temporarily_disabled_and_restored(monkeypatch) -> None:
    from openmcp.backends import agy as agy_backend

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return None

    monkeypatch.setattr(agy_backend.subprocess, "run", fake_run)

    with agy_backend._temporary_disabled_plugin("superpowers-ccg"):
        pass

    assert calls == [
        ["agy", "plugin", "disable", "superpowers-ccg"],
        ["agy", "plugin", "enable", "superpowers-ccg"],
    ]


def test_agy_plugin_restored_when_execution_fails(monkeypatch) -> None:
    from openmcp.backends import agy as agy_backend

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return None

    monkeypatch.setattr(agy_backend.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError):
        with agy_backend._temporary_disabled_plugin("superpowers-ccg"):
            raise RuntimeError("boom")

    assert calls == [
        ["agy", "plugin", "disable", "superpowers-ccg"],
        ["agy", "plugin", "enable", "superpowers-ccg"],
    ]


def test_agy_patch_model_maps_gemini_id_to_display_name(monkeypatch, tmp_path) -> None:
    from openmcp.backends import agy as agy_backend

    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps({"model": "Gemini 3.5 Flash (Low)", "other": "keep"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(agy_backend, "_SETTINGS_PATH", settings_path)

    with agy_backend._patch_model("gemini-3.5-flash"):
        patched = json.loads(settings_path.read_text(encoding="utf-8"))
        assert patched["model"] == "Gemini 3.5 Flash (Medium)"
        assert patched["other"] == "keep"

    restored = json.loads(settings_path.read_text(encoding="utf-8"))
    assert restored["model"] == "Gemini 3.5 Flash (Low)"
    assert restored["other"] == "keep"


def test_agy_patch_model_accepts_supported_display_name(monkeypatch, tmp_path) -> None:
    from openmcp.backends import agy as agy_backend

    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps({"model": "Gemini 3.5 Flash (Low)"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(agy_backend, "_SETTINGS_PATH", settings_path)

    with agy_backend._patch_model("Gemini 3.1 Pro (High)"):
        patched = json.loads(settings_path.read_text(encoding="utf-8"))
        assert patched["model"] == "Gemini 3.1 Pro (High)"

    restored = json.loads(settings_path.read_text(encoding="utf-8"))
    assert restored["model"] == "Gemini 3.5 Flash (Low)"
