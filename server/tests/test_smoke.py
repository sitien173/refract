import asyncio
import inspect
import json
import threading
import time
from dataclasses import fields
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


def test_backend_params_are_transport_only() -> None:
    expected = {"PROMPT", "cd", "SESSION_ID", "args", "timeout_s", "cancel_event"}
    assert {field.name for field in fields(AgyParams)} == expected
    assert {field.name for field in fields(CodexParams)} == expected
    assert {field.name for field in fields(PiParams)} == expected


def test_doctor_validates_legacy_profile_alias(monkeypatch, tmp_path, capsys) -> None:
    from openmcp.cli import main

    home = tmp_path / "openmcp"
    home.mkdir()
    (home / "config.toml").write_text(
        """[routing_profiles.balanced]
default = "forge"
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENMCP_HOME", str(home))

    with pytest.raises(SystemExit) as raised:
        main(["doctor"])

    assert raised.value.code == 1
    assert "does not map built-in workflows" in capsys.readouterr().err


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
    captured = {}

    def fake_run_shell_command(cmd, cwd=None, **kwargs):
        captured["cmd"] = cmd
        log_path = Path(cmd[cmd.index("--log-file") + 1])
        log_path.write_text(
            f"I0702 21:32:01.000000 1 server.go:1] noisy diagnostic line\n"
            f"I0702 21:32:04.716348 1 server.go:807] Created conversation {session_id}\n",
            encoding="utf-8",
        )
        yield "pong from agy"

    monkeypatch.setattr(agy_backend.shutil, "which", lambda name: f"C:/bin/{name}.exe")
    monkeypatch.setattr(agy_backend, "run_shell_command", fake_run_shell_command)

    out = await agy_backend.execute(
        AgyParams(PROMPT="x", cd=tmp_path, args=("--mode", "plan", "--sandbox"))
    )

    assert captured["cmd"][1:5] == [
        "--dangerously-skip-permissions", "--mode", "plan", "--sandbox",
    ]
    assert "--add-dir" not in captured["cmd"]
    assert captured["cmd"][-2:] == ["--print", "x"]
    assert out.outcome == "OK"
    assert out.SESSION_ID == session_id
    assert out.agent_messages == "pong from agy"


def test_tool_signature() -> None:
    from openmcp.server import run

    sig = inspect.signature(run)
    params = list(sig.parameters.keys())
    assert params == ["backend", "PROMPT", "cd", "SESSION_ID", "timeout_s"]


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

    out = await codex_backend.execute(
        CodexParams(
            PROMPT="x",
            cd=tmp_path,
            args=("--ephemeral", "--color", "never"),
        )
    )

    extra_start = captured["cmd"].index("--ephemeral")
    assert captured["cmd"][extra_start:extra_start + 3] == [
        "--ephemeral", "--color", "never",
    ]
    assert "--json" in captured["cmd"]
    assert "--yolo" in captured["cmd"]
    assert "--skip-git-repo-check" not in captured["cmd"]
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
            args=(
                "--provider", "openai", "--offline", "--model", "openai/gpt-5",
                "--thinking", "high", "--approve",
            ),
        )
    )

    assert captured["cmd"] == [
        "pi", "--provider", "openai", "--offline", "--model", "openai/gpt-5",
        "--thinking", "high", "--approve", "--mode", "json", "--session",
        "existing-session", "x",
    ]
    assert Path(captured["cwd"]) == tmp_path.absolute()
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
            args=(
                "--no-approve",
                "--no-context-files",
                "--no-extensions",
                "--no-skills",
                "--no-prompt-templates",
                "--system-prompt",
                "sentinel instructions",
                "--tools",
                "read,grep,find,ls",
            ),
        )
    )

    assert captured["cmd"] == [
        "pi",
        "--no-approve",
        "--no-context-files",
        "--no-extensions",
        "--no-skills",
        "--no-prompt-templates",
        "--system-prompt",
        "sentinel instructions",
        "--tools",
        "read,grep,find,ls",
        "--mode",
        "json",
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
            reasoning="xhigh",
            system_prompt="sentinel",
            isolated=True,
            read_only=True,
            args=("--verbose",),
        ),
        prompt="review",
        cwd=tmp_path,
        session_id="",
        timeout_s=60,
        cancel_event=threading.Event(),
    )

    params = captured["params"]
    assert params.args == (
        "--verbose",
        "--no-approve",
        "--no-context-files",
        "--no-extensions",
        "--no-skills",
        "--no-prompt-templates",
        "--system-prompt",
        "sentinel",
        "--tools",
        "read,grep,find,ls",
        "--model",
        "gpt-5.6-sol",
        "--thinking",
        "xhigh",
    )


@pytest.mark.asyncio
async def test_driver_enforces_approval_after_normal_pi_target_args(monkeypatch, tmp_path) -> None:
    import openmcp.drivers as drivers_module
    from openmcp.config import TargetConfig

    captured = {}

    async def fake_execute(params):
        captured["args"] = params.args
        return BackendResult(outcome="OK", SESSION_ID="", agent_messages="", error="", error_class="")

    monkeypatch.setattr(drivers_module, "pi_execute", fake_execute)
    await drivers_module.DriverRegistry().execute(
        target=TargetConfig(
            id="normal",
            backend="pi",
            args=("--no-approve", "--verbose"),
        ),
        prompt="review",
        cwd=tmp_path,
        session_id="",
        timeout_s=0,
        cancel_event=threading.Event(),
    )

    assert captured["args"] == ("--no-approve", "--verbose", "--approve")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target",
    [
        pytest.param(
            {"id": "unsafe-terminator", "backend": "agy", "args": ("--",)},
            id="end-of-options",
        ),
        pytest.param(
            {"id": "unsafe-workspace", "backend": "codex", "args": ("-CD:/other",)},
            id="codex-workspace",
        ),
    ],
)
async def test_driver_rejects_programmatic_reserved_target_args(tmp_path, target) -> None:
    from openmcp.config import TargetConfig
    from openmcp.drivers import DriverRegistry

    result = await DriverRegistry().execute(
        target=TargetConfig(**target),
        prompt="review",
        cwd=tmp_path,
        session_id="",
        timeout_s=0,
        cancel_event=threading.Event(),
    )

    assert result.outcome == "TARGET_FATAL"
    assert result.error_code == "invalid_args"


@pytest.mark.asyncio
async def test_driver_rejects_unsafe_programmatic_isolated_pi_target(tmp_path) -> None:
    from openmcp.config import TargetConfig
    from openmcp.drivers import DriverRegistry

    result = await DriverRegistry().execute(
        target=TargetConfig(
            id="unsafe",
            backend="pi",
            isolated=True,
            args=("--extension=unsafe.ts",),
        ),
        prompt="review",
        cwd=tmp_path,
        session_id="",
        timeout_s=0,
        cancel_event=threading.Event(),
    )

    assert result.outcome == "TARGET_FATAL"
    assert result.error_code == "invalid_args"


@pytest.mark.asyncio
async def test_server_dispatches_pi_without_implicit_model(monkeypatch, tmp_path) -> None:
    import openmcp.server as srv

    captured = {}

    async def fake(params):
        captured["params"] = params
        return BackendResult(outcome="OK", SESSION_ID="pi-session", agent_messages="PONG", error="", error_class="")

    monkeypatch.setattr(srv, "pi_execute", fake)
    out = await srv.run(backend="pi", PROMPT="x", cd=str(tmp_path))

    assert captured["params"].args == ("--approve",)
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
async def test_driver_compiles_agy_and_codex_target_configuration(monkeypatch, tmp_path) -> None:
    import openmcp.drivers as drivers_module
    from openmcp.config import TargetConfig

    captured = {}

    async def fake_agy(params):
        captured["agy"] = params
        return BackendResult(outcome="OK", SESSION_ID="", agent_messages="", error="", error_class="")

    async def fake_codex(params):
        captured["codex"] = params
        return BackendResult(outcome="OK", SESSION_ID="", agent_messages="", error="", error_class="")

    monkeypatch.setattr(drivers_module, "agy_execute", fake_agy)
    monkeypatch.setattr(drivers_module, "codex_execute", fake_codex)
    registry = drivers_module.DriverRegistry()
    common = {
        "prompt": "x",
        "cwd": tmp_path,
        "session_id": "",
        "timeout_s": 0,
        "cancel_event": threading.Event(),
    }
    await registry.execute(
        target=TargetConfig(
            id="agy",
            backend="agy",
            model="Gemini 3.5 Flash (High)",
            args=("--sandbox",),
        ),
        **common,
    )
    await registry.execute(
        target=TargetConfig(
            id="codex",
            backend="codex",
            model="gpt-5-mini",
            backend_profile="custom-profile",
            reasoning="high",
            args=("--color", "never"),
        ),
        **common,
    )

    assert captured["agy"].args == (
        "--sandbox", "--model", "Gemini 3.5 Flash (High)",
    )
    assert captured["codex"].args == (
        "--color", "never",
        "--profile", "custom-profile",
        "--model", "gpt-5-mini",
        "-c", 'model="gpt-5-mini"',
        "-c", "model_reasoning_effort=high",
    )


@pytest.mark.asyncio
async def test_direct_run_ignores_legacy_environment_and_plugin_config(
    monkeypatch, tmp_path
) -> None:
    import openmcp.server as srv

    captured = {}

    async def fake(params):
        captured["args"] = params.args
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
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENMCP_CODEX_MODEL_DEFAULT", "environment-model")
    monkeypatch.setenv("OPENMCP_CODEX_PROFILE_DEFAULT", "environment-profile")
    monkeypatch.setattr(srv, "codex_execute", fake)

    await srv.run(backend="codex", PROMPT="x", cd=Path("."))

    assert captured == {"args": ()}
