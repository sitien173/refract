import asyncio
import inspect
import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from openmcp.backends import BackendResult
from openmcp.backends.agy import AgyParams, execute as agy_execute
from openmcp.backends.codex import CodexParams, execute as codex_execute
from openmcp.backends.pi import PiParams, execute as pi_execute


def test_imports() -> None:
    import openmcp.server  # noqa: F401
    import openmcp.cli  # noqa: F401
    import openmcp.backends.agy  # noqa: F401
    import openmcp.backends.codex  # noqa: F401
    import openmcp.backends.pi  # noqa: F401


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


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", ["Created", "Streaming"])
async def test_agy_extracts_session_id_from_conversation_log(monkeypatch, tmp_path, prefix) -> None:
    from openmcp.backends import agy as agy_backend

    session_id = "b658ef34-d18c-4294-b329-0ae5dee0157b"

    def fake_run_shell_command(cmd, cwd=None, **kwargs):
        log_path = Path(cmd[cmd.index("--log-file") + 1])
        log_path.write_text(f"{prefix} conversation {session_id}\nPONG", encoding="utf-8")
        yield ""

    monkeypatch.setattr(agy_backend.shutil, "which", lambda name: f"C:/bin/{name}.exe")
    monkeypatch.setattr(agy_backend, "run_shell_command", fake_run_shell_command)

    out = await agy_backend.execute(AgyParams(PROMPT="x", cd=tmp_path))

    assert out.outcome == "OK"
    assert out.SESSION_ID == session_id
    assert out.agent_messages == f"{prefix} conversation {session_id}\nPONG"


@pytest.mark.asyncio
async def test_agy_uses_input_session_id_when_log_has_no_conversation_id(
    monkeypatch,
    tmp_path,
    tmp_path_factory,
) -> None:
    from openmcp.backends import agy as agy_backend

    home = tmp_path_factory.mktemp("agy-home")
    stale_id = "d597e994-7312-49ec-9317-ce9ae59b38bc"
    history_dir = home / ".gemini" / "antigravity-cli"
    history_dir.mkdir(parents=True)
    (history_dir / "history.jsonl").write_text(
        json.dumps(
            {
                "display": "x",
                "workspace": str(tmp_path),
                "conversationId": stale_id,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_run_shell_command(cmd, cwd=None, **kwargs):
        log_path = Path(cmd[cmd.index("--log-file") + 1])
        log_path.write_text("PONG", encoding="utf-8")
        yield ""

    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(agy_backend.shutil, "which", lambda name: f"C:/bin/{name}.exe")
    monkeypatch.setattr(agy_backend, "run_shell_command", fake_run_shell_command)

    out = await agy_backend.execute(
        AgyParams(PROMPT="x", cd=tmp_path, SESSION_ID="resume-session-id")
    )

    assert out.outcome == "OK"
    assert out.SESSION_ID == "resume-session-id"
    assert out.agent_messages == "PONG"


@pytest.mark.asyncio
async def test_agy_prefers_stdout_reply_over_noisy_log_file(monkeypatch, tmp_path) -> None:
    from openmcp.backends import agy as agy_backend

    session_id = "b658ef34-d18c-4294-b329-0ae5dee0157b"

    def fake_run_shell_command(cmd, cwd=None, **kwargs):
        log_path = Path(cmd[cmd.index("--log-file") + 1])
        log_path.write_text(
            f"I0702 21:32:01.000000 1 server.go:1] noisy diagnostic line\n"
            f"I0702 21:32:04.716348 1 server.go:807] Created conversation {session_id}\n",
            encoding="utf-8",
        )
        yield "pong from agy"

    monkeypatch.setattr(agy_backend.shutil, "which", lambda name: f"C:/bin/{name}.exe")
    monkeypatch.setattr(agy_backend, "run_shell_command", fake_run_shell_command)

    out = await agy_backend.execute(AgyParams(PROMPT="x", cd=tmp_path))

    assert out.outcome == "OK"
    assert out.SESSION_ID == session_id
    assert out.agent_messages == "pong from agy"


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
        "timeout_s",
    ]


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

    def fake_run_shell_command(cmd, cwd=None, **kwargs):
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

    def fake_run_shell_command(cmd, cwd=None, **kwargs):
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
async def test_pi_json_mode_extracts_reply_session_and_cli_options(monkeypatch, tmp_path) -> None:
    from openmcp.backends import pi as pi_backend

    captured = {}
    session_id = "b658ef34-d18c-4294-b329-0ae5dee0157b"

    def fake_run_shell_command(cmd, cwd=None, **kwargs):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        yield json.dumps({"type": "session", "version": 3, "id": session_id})
        yield json.dumps(
            {
                "type": "message_end",
                "message": {"role": "assistant", "content": [{"type": "text", "text": "PONG"}]},
            }
        )
        yield json.dumps({"type": "agent_end", "messages": []})

    monkeypatch.setattr(pi_backend.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(pi_backend, "run_shell_command", fake_run_shell_command)

    out = await pi_backend.execute(
        PiParams(
            PROMPT="x",
            cd=tmp_path,
            SESSION_ID="existing-session",
            model="openai/gpt-5",
            reasoning_effort="high",
        )
    )

    assert captured["cmd"] == [
        "pi", "--mode", "json", "--approve", "--session", "existing-session",
        "--model", "openai/gpt-5", "--thinking", "high", "x",
    ]
    assert captured["cwd"] == str(tmp_path.absolute())
    assert out.outcome == "OK"
    assert out.SESSION_ID == session_id
    assert out.agent_messages == "PONG"


@pytest.mark.asyncio
async def test_pi_isolated_mode_replaces_instructions_and_disables_writes(monkeypatch, tmp_path) -> None:
    from openmcp.backends import pi as pi_backend

    captured = {}

    def fake_run_shell_command(cmd, **kwargs):
        captured["cmd"] = cmd
        yield json.dumps(
            {
                "type": "message_end",
                "message": {"role": "assistant", "content": "reviewed"},
            }
        )

    monkeypatch.setattr(pi_backend.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(pi_backend, "run_shell_command", fake_run_shell_command)

    out = await pi_backend.execute(
        PiParams(
            PROMPT="review",
            cd=tmp_path,
            system_prompt="sentinel instructions",
            isolated=True,
            read_only=True,
        )
    )

    assert captured["cmd"] == [
        "pi",
        "--mode",
        "json",
        "--no-approve",
        "--no-context-files",
        "--no-extensions",
        "--no-skills",
        "--no-prompt-templates",
        "--system-prompt",
        "sentinel instructions",
        "--tools",
        "read,grep,find,ls",
        "review",
    ]
    assert out.outcome == "OK"


@pytest.mark.asyncio
async def test_driver_passes_isolated_target_policy_to_pi(monkeypatch, tmp_path) -> None:
    import openmcp.drivers as drivers_module
    from openmcp.config import TargetConfig

    captured = {}

    async def fake_execute(params):
        captured["params"] = params
        return BackendResult(
            outcome="OK",
            SESSION_ID="session",
            agent_messages="reviewed",
            error="",
            error_class="",
        )

    monkeypatch.setattr(drivers_module, "pi_execute", fake_execute)
    registry = drivers_module.DriverRegistry()
    await registry.execute(
        target=TargetConfig(
            id="sentinel-primary",
            backend="pi",
            model="gpt-5.6-sol",
            system_prompt="sentinel",
            isolated=True,
            read_only=True,
        ),
        prompt="review",
        cwd=tmp_path,
        session_id="",
        timeout_s=60,
        cancel_event=threading.Event(),
    )

    params = captured["params"]
    assert params.model == "gpt-5.6-sol"
    assert params.system_prompt == "sentinel"
    assert params.isolated
    assert params.read_only


@pytest.mark.asyncio
async def test_server_dispatches_pi_with_default_model(monkeypatch, tmp_path) -> None:
    import openmcp.server as srv

    captured = {}

    async def fake(params):
        captured["params"] = params
        return BackendResult(outcome="OK", SESSION_ID="pi-session", agent_messages="PONG", error="", error_class="")

    monkeypatch.setenv("OPENMCP_PI_MODEL_DEFAULT", "openai/gpt-5")
    monkeypatch.setattr(srv, "pi_execute", fake)
    out = await srv.run(backend="pi", PROMPT="x", cd=str(tmp_path), reasoning="high")

    assert captured["params"].model == "openai/gpt-5"
    assert captured["params"].reasoning_effort == "high"
    assert out == {"success": True, "SESSION_ID": "pi-session", "agent_messages": "PONG", "error": ""}


@pytest.mark.asyncio
async def test_response_shape_success(monkeypatch) -> None:
    import openmcp.server as srv

    async def fake(params):
        return BackendResult(
            outcome="OK",
            SESSION_ID="sess-x",
            agent_messages="lots of text",
            error="",
            error_class="",
        )

    monkeypatch.setattr(srv, "agy_execute", fake)
    out = await srv.run(backend="agy", PROMPT="x", cd=Path("."))
    assert set(out.keys()) == {"success", "SESSION_ID", "agent_messages", "error"}
    assert out == {"success": True, "SESSION_ID": "sess-x", "agent_messages": "lots of text", "error": ""}


@pytest.mark.asyncio
async def test_response_shape_failure(monkeypatch) -> None:
    import openmcp.server as srv

    async def fake(params):
        return BackendResult(
            outcome="FATAL",
            SESSION_ID="",
            agent_messages="",
            error="boom",
            error_class="fatal_backend",
        )

    monkeypatch.setattr(srv, "codex_execute", fake)
    out = await srv.run(backend="codex", PROMPT="x", cd=Path("."))
    assert set(out.keys()) == {"success", "SESSION_ID", "agent_messages", "error"}
    assert out == {"success": False, "SESSION_ID": "", "agent_messages": "", "error": "boom"}


@pytest.mark.asyncio
async def test_env_defaults_applied_for_agy_model(monkeypatch) -> None:
    import openmcp.server as srv

    captured = {}

    async def fake(params):
        captured["model"] = params.model
        return BackendResult(outcome="OK", SESSION_ID="", agent_messages="", error="", error_class="")

    monkeypatch.setenv("OPENMCP_AGY_MODEL_DEFAULT", "gemini-3.5-flash")
    monkeypatch.setattr(srv, "agy_execute", fake)
    await srv.run(backend="agy", PROMPT="x", cd=Path("."))
    assert captured["model"] == ""


@pytest.mark.asyncio
async def test_env_defaults_applied_for_codex_model_and_profile(monkeypatch) -> None:
    import openmcp.server as srv

    captured = {}

    async def fake(params):
        captured["model"] = params.model
        captured["profile"] = params.profile
        return BackendResult(outcome="OK", SESSION_ID="", agent_messages="", error="", error_class="")

    monkeypatch.setenv("OPENMCP_CODEX_MODEL_DEFAULT", "gpt-5")
    monkeypatch.setenv("OPENMCP_CODEX_PROFILE_DEFAULT", "mcp_execution")
    monkeypatch.setattr(srv, "codex_execute", fake)
    await srv.run(backend="codex", PROMPT="x", cd=Path("."))
    assert captured["model"] == "gpt-5"
    assert captured["profile"] == "mcp_execution"


@pytest.mark.asyncio
async def test_explicit_model_overrides_codex_profile_model(monkeypatch) -> None:
    import openmcp.server as srv

    captured = {}

    async def fake(params):
        captured["model"] = params.model
        captured["profile"] = params.profile
        return BackendResult(outcome="OK", SESSION_ID="", agent_messages="", error="", error_class="")

    monkeypatch.setenv("OPENMCP_CODEX_MODEL_DEFAULT", "gpt-5")
    monkeypatch.setenv("OPENMCP_CODEX_PROFILE_DEFAULT", "mcp_execution")
    monkeypatch.setattr(srv, "codex_execute", fake)
    await srv.run(
        backend="codex",
        PROMPT="x",
        cd=Path("."),
        model="gpt-5-mini",
        profile="custom-profile",
    )
    assert captured["model"] == "gpt-5-mini"
    assert captured["profile"] == "custom-profile"


@pytest.mark.asyncio
async def test_env_priority_user_then_openmcp_dotenv_then_plugin(monkeypatch, tmp_path) -> None:
    import openmcp.server as srv

    captured = {}

    async def fake(params):
        captured["model"] = params.model
        captured["profile"] = params.profile
        return BackendResult(outcome="OK", SESSION_ID="", agent_messages="", error="", error_class="")

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
    monkeypatch.setattr(srv, "codex_execute", fake)

    await srv.run(backend="codex", PROMPT="x", cd=Path("."))

    assert captured["model"] == "user-model"
    assert captured["profile"] == "dotenv-profile"


@pytest.mark.asyncio
async def test_env_falls_back_to_plugin_env_when_higher_priorities_missing(monkeypatch, tmp_path) -> None:
    import openmcp.server as srv

    captured = {}

    async def fake(params):
        captured["model"] = params.model
        return BackendResult(outcome="OK", SESSION_ID="", agent_messages="", error="", error_class="")

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
    monkeypatch.setattr(srv, "agy_execute", fake)

    await srv.run(backend="agy", PROMPT="x", cd=Path("."))

    assert captured["model"] == ""


@pytest.mark.asyncio
async def test_agy_passes_model_per_invocation(monkeypatch, tmp_path) -> None:
    from openmcp.backends import agy as agy_backend

    captured: dict[str, list[str]] = {}

    def fake_run_shell_command(cmd, **kwargs):
        captured["cmd"] = cmd
        yield "PONG"

    monkeypatch.setattr(agy_backend.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(agy_backend, "run_shell_command", fake_run_shell_command)

    result = await agy_backend.execute(
        AgyParams(PROMPT="x", cd=tmp_path, model="gemini-3.5-flash")
    )

    assert result.outcome == "OK"
    assert captured["cmd"][captured["cmd"].index("--model") + 1] == (
        "Gemini 3.5 Flash (Medium)"
    )
