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


def test_codex_session_file_fallback_without_prompt_match(monkeypatch, tmp_path) -> None:
    from openmcp.backends.codex import _extract_session_id_from_latest_session

    session_id = "019e532a-2d92-7281-8bd1-0110af0a34aa"
    sessions_dir = tmp_path / "codex-home" / "sessions" / "2026" / "05" / "23"
    sessions_dir.mkdir(parents=True)
    session_file = sessions_dir / f"rollout-2026-05-23T11-48-53-{session_id}.jsonl"
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
                json.dumps({"type": "event_msg", "payload": {"message": "different prompt"}}),
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))

    assert _extract_session_id_from_latest_session(tmp_path, "prompt that is not in file", time.time() - 1) == session_id


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


def test_agy_history_jsonl_extraction(monkeypatch, tmp_path) -> None:
    from openmcp.backends import agy as agy_backend
    
    session_id = "f8a70c35-1816-4b97-87b9-ce387e798c37"
    dot_gemini = tmp_path / ".gemini" / "antigravity-cli"
    dot_gemini.mkdir(parents=True)
    history_file = dot_gemini / "history.jsonl"
    
    # Write mock history content
    history_file.write_text(
        json.dumps({
            "display": "Read the current README.md and write a plan",
            "timestamp": int(time.time() * 1000),
            "workspace": str(tmp_path),
            "conversationId": session_id
        }) + "\n",
        encoding="utf-8"
    )
    
    # Monkeypatch the home path inside agy.py
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    
    extracted = agy_backend._extract_session_id_from_history(tmp_path, "Read the current")
    assert extracted == session_id
    
    # Try with unmatched prompt snippet
    extracted_unmatched = agy_backend._extract_session_id_from_history(tmp_path, "unmatched snippet")
    assert extracted_unmatched == ""
    
    # Try with another workspace
    other_workspace = tmp_path / "other"
    extracted_other = agy_backend._extract_session_id_from_history(other_workspace)
    assert extracted_other == ""


def test_agy_pb_signature_extraction(monkeypatch, tmp_path) -> None:
    from openmcp.backends import agy as agy_backend
    
    session_id = "d597e994-7312-49ec-9317-ce9ae59b38bc"
    pb_file = tmp_path / f"{session_id}.pb"
    
    # Write mock protobuf content containing the workspace path in bytes
    workspace_bytes = str(tmp_path.resolve()).encode("utf-8")
    pb_file.write_bytes(b"\x0a\x2fsome-header-bytes\x12\x10" + workspace_bytes + b"\x1a\x08metadata")
    
    monkeypatch.setattr(agy_backend, "_CONVERSATIONS_PATH", tmp_path)
    
    # Verify signature extraction matches workspace path
    extracted = agy_backend._extract_session_id_from_pb_signature(tmp_path)
    assert extracted == session_id
    
    # Verify unmatched workspace path returns empty
    other_workspace = Path("F:/other/workspace")
    extracted_unmatched = agy_backend._extract_session_id_from_pb_signature(other_workspace)
    assert extracted_unmatched == ""


def test_agy_strips_windows_terminal_title_escape() -> None:
    from openmcp.backends.agy import _strip_ansi

    assert _strip_ansi("\x1b]0;Administrator:  C:\\WINDOWS\\system32\\cmd.exe \x1b\\PONG") == "PONG"
    assert _strip_ansi("\x1b]0;Administrator:  C:\\WINDOWS\\system32\\cmd.exe \x1b\\") == ""


@pytest.mark.asyncio
async def test_agy_falls_back_to_configured_model_when_model_override_has_no_output(monkeypatch, tmp_path) -> None:
    from openmcp.backends import agy as agy_backend

    calls = []
    session_id = "b658ef34-d18c-4294-b329-0ae5dee0157b"
    outputs = iter(
        [
            "",
            "PONG",
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
    monkeypatch.setattr(agy_backend, "_extract_session_id_from_history", lambda workspace_path, prompt_snippet="": session_id)
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
        "reasoning",
        "max_retries",
        "retry_base_ms",
    ]


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
async def test_codex_uses_input_session_id_when_no_extraction_sources_match(monkeypatch, tmp_path) -> None:
    from openmcp.backends import codex as codex_backend

    def fake_run_shell_command(cmd, cwd=None):
        yield "PONG"

    monkeypatch.setattr(codex_backend.shutil, "which", lambda name: f"C:/bin/{name}.exe")
    monkeypatch.setattr(codex_backend, "run_shell_command", fake_run_shell_command)
    monkeypatch.setattr(codex_backend, "_extract_session_id_from_latest_session", lambda cwd, prompt, started_at: "")

    out = await codex_backend.execute(CodexParams(PROMPT="x", cd=tmp_path, SESSION_ID="resume-session-id"))

    assert out.outcome == "OK"
    assert out.SESSION_ID == "resume-session-id"
    assert out.agent_messages == "PONG"
    assert out.error_class == ""


@pytest.mark.asyncio
async def test_codex_does_not_inject_session_metadata_line(monkeypatch, tmp_path) -> None:
    from openmcp.backends import codex as codex_backend

    captured = {}
    session_id = "b658ef34-d18c-4294-b329-0ae5dee0157b"

    def fake_run_shell_command(cmd, cwd=None):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        yield "Reading additional input from stdin..."
        yield json.dumps({"type": "thread.started", "thread_id": session_id})
        yield json.dumps(
            {
                "type": "item.completed",
                "item": {"id": "item_0", "type": "agent_message", "text": "PONG"},
            }
        )
        yield json.dumps({"type": "turn.completed"})

    monkeypatch.setattr(codex_backend.shutil, "which", lambda name: f"C:/bin/{name}.exe")
    monkeypatch.setattr(codex_backend, "run_shell_command", fake_run_shell_command)
    monkeypatch.setattr(codex_backend, "_extract_session_id_from_latest_session", lambda cwd, prompt, started_at: "")

    out = await codex_backend.execute(CodexParams(PROMPT="x", cd=tmp_path))

    assert "--json" in captured["cmd"]
    assert captured["cmd"][-1] == "x"
    assert out.outcome == "OK"
    assert out.SESSION_ID == session_id
    assert out.agent_messages == "PONG"


@pytest.mark.asyncio
async def test_codex_disables_plugin_for_delegated_run(monkeypatch, tmp_path) -> None:
    from openmcp.backends import codex as codex_backend

    captured = {}

    def fake_run_shell_command(cmd, cwd=None):
        captured["cmd"] = cmd
        yield "PONG"

    monkeypatch.setattr(codex_backend.shutil, "which", lambda name: f"C:/bin/{name}.exe")
    monkeypatch.setattr(codex_backend, "run_shell_command", fake_run_shell_command)
    monkeypatch.setattr(codex_backend, "_extract_session_id_from_latest_session", lambda cwd, prompt, started_at: "")

    out = await codex_backend.execute(CodexParams(PROMPT="x", cd=tmp_path))

    override_index = captured["cmd"].index('plugins."superpowers-ccg@superpowers-ccg-marketplace".enabled=false')
    assert captured["cmd"][override_index - 1] == "-c"
    assert out.outcome == "OK"

@pytest.mark.asyncio
async def test_bad_cd_gemini_fatal() -> None:
    bad = Path("C:/definitely/not/real/path")
    out = await gemini_execute(GeminiParams(PROMPT="x", cd=bad))
    assert out.outcome == "FATAL"
    assert out.error_class == "bad_cd"


@pytest.mark.asyncio
async def test_gemini_uses_stream_json_output(monkeypatch, tmp_path) -> None:
    from openmcp.backends import gemini as gemini_backend

    captured = {}
    session_id = "sess-marker"

    def fake_run_shell_command(cmd, cwd=None):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        yield "banner text"
        yield json.dumps({"type": "init", "session_id": session_id})
        yield json.dumps({"type": "message", "role": "assistant", "content": "PONG"})
        yield json.dumps({"type": "result", "status": "success"})

    monkeypatch.setattr(gemini_backend.shutil, "which", lambda name: f"C:/bin/{name}.exe")
    monkeypatch.setattr(gemini_backend, "run_shell_command", fake_run_shell_command)

    out = await gemini_backend.execute(GeminiParams(PROMPT="x", cd=tmp_path))

    assert "-o" not in captured["cmd"]
    assert "--output-format" in captured["cmd"]
    assert "stream-json" in captured["cmd"]
    assert captured["cmd"][2] == "x"
    assert out.outcome == "OK"
    assert out.SESSION_ID == session_id
    assert out.agent_messages == "PONG"
    assert out.error == ""


@pytest.mark.asyncio
async def test_gemini_stream_output_without_session_id_is_retryable(monkeypatch, tmp_path) -> None:
    from openmcp.backends import gemini as gemini_backend

    def fake_run_shell_command(cmd, cwd=None):
        yield json.dumps({"type": "message", "role": "assistant", "content": "PONG"})
        yield json.dumps({"type": "result", "status": "success"})

    monkeypatch.setattr(gemini_backend.shutil, "which", lambda name: f"C:/bin/{name}.exe")
    monkeypatch.setattr(gemini_backend, "run_shell_command", fake_run_shell_command)

    out = await gemini_backend.execute(GeminiParams(PROMPT="x", cd=tmp_path))

    assert out.outcome == "RETRYABLE"
    assert out.SESSION_ID == ""
    assert out.agent_messages == "PONG"
    assert out.error == "missing SESSION_ID"
    assert out.error_class == "missing_session_id"


@pytest.mark.asyncio
async def test_response_shape_success(monkeypatch) -> None:
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
    assert set(out.keys()) == {"success", "SESSION_ID", "agent_messages", "error"}
    assert out == {"success": True, "SESSION_ID": "sess-x", "agent_messages": "lots of text", "error": ""}


@pytest.mark.asyncio
async def test_response_shape_failure(monkeypatch) -> None:
    import openmcp.server as srv

    async def fake(execute_fn, params, *, max_retries, retry_base_ms):
        return {"success": False, "error": "boom", "attempts": 1}

    monkeypatch.setattr(srv, "run_with_retry", fake)
    out = await srv.run(backend="codex", PROMPT="x", cd=Path("."))
    assert set(out.keys()) == {"success", "SESSION_ID", "agent_messages", "error"}
    assert out == {"success": False, "SESSION_ID": "", "agent_messages": "", "error": "boom"}


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
    assert captured["model"] == ""


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
    assert captured["model"] == ""


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
async def test_explicit_profile_suppresses_codex_model_override(monkeypatch) -> None:
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
    assert captured["model"] == ""
    assert captured["profile"] == "custom-profile"


@pytest.mark.asyncio
async def test_env_priority_user_then_openmcp_dotenv_then_plugin(monkeypatch, tmp_path) -> None:
    import openmcp.server as srv

    captured = {}

    async def fake(execute_fn, params, *, max_retries, retry_base_ms):
        captured["model"] = params.model
        captured["profile"] = params.profile
        return {"success": True, "SESSION_ID": "", "error": ""}

    config = {
        "mcpServers": {
            "openmcp": {
                "env": {
                    "OPENMCP_CODEX_MODEL_DEFAULT": "plugin-model",
                    "OPENMCP_CODEX_PROFILE_DEFAULT": "plugin-profile",
                }
            }
        }
    }
    (tmp_path / "mcp_config.json").write_text(json.dumps(config), encoding="utf-8")

    fake_home = tmp_path / "home"
    (fake_home / ".openmcp").mkdir(parents=True)
    (fake_home / ".openmcp" / ".env").write_text(
        "OPENMCP_CODEX_MODEL_DEFAULT=dotenv-model\nOPENMCP_CODEX_PROFILE_DEFAULT=dotenv-profile\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(srv.Path, "home", lambda: fake_home)
    monkeypatch.setenv("OPENMCP_CODEX_MODEL_DEFAULT", "user-model")
    monkeypatch.delenv("OPENMCP_CODEX_PROFILE_DEFAULT", raising=False)
    monkeypatch.setattr(srv, "run_with_retry", fake)

    await srv.run(backend="codex", PROMPT="x", cd=Path("."))

    assert captured["model"] == "user-model"
    assert captured["profile"] == "dotenv-profile"


@pytest.mark.asyncio
async def test_env_falls_back_to_plugin_env_when_higher_priorities_missing(monkeypatch, tmp_path) -> None:
    import openmcp.server as srv

    captured = {}

    async def fake(execute_fn, params, *, max_retries, retry_base_ms):
        captured["model"] = params.model
        return {"success": True, "SESSION_ID": "", "error": ""}

    config = {
        "mcpServers": {
            "openmcp": {
                "env": {
                    "OPENMCP_AGY_MODEL_DEFAULT": "plugin-agy-model",
                }
            }
        }
    }
    (tmp_path / "mcp_config.json").write_text(json.dumps(config), encoding="utf-8")

    fake_home = tmp_path / "home"
    fake_home.mkdir(parents=True)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(srv.Path, "home", lambda: fake_home)
    monkeypatch.delenv("OPENMCP_AGY_MODEL_DEFAULT", raising=False)
    monkeypatch.setattr(srv, "run_with_retry", fake)

    await srv.run(backend="agy", PROMPT="x", cd=Path("."))

    assert captured["model"] == ""


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
