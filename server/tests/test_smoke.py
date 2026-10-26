import inspect
import json
import subprocess
import sys
import threading
import time
from dataclasses import fields
from pathlib import Path

import pytest

from refract.backends import BackendResult
from refract.backends import BackendParams
from refract.backends.agy import execute as agy_execute
from refract.backends.codex import execute as codex_execute


def test_shell_stream_reports_nonzero_exit_after_output() -> None:
    from refract.backends._shell import ShellCommandFailed, stream_shell_command_lines

    executable_name = Path(sys.executable).name
    command = [sys.executable, "-c", "print('unknown option'); raise SystemExit(2)"]
    stream = stream_shell_command_lines(
        command,
        executable_name=executable_name,
        line_transform=str.strip,
        terminate_wait_s=1,
        check_returncode=True,
    )

    assert next(stream) == "unknown option"
    with pytest.raises(ShellCommandFailed, match="status 2"):
        next(stream)


_CHATTY_CHILD = "import time\nwhile True:\n    print('tick', flush=True)\n    time.sleep(0.05)"


def test_shell_stream_cancels_while_child_keeps_printing() -> None:
    from refract.backends._shell import ShellCommandCancelled, stream_shell_command_lines

    cancel = threading.Event()
    stream = stream_shell_command_lines(
        [sys.executable, "-c", _CHATTY_CHILD],
        executable_name=Path(sys.executable).name,
        line_transform=str.strip,
        terminate_wait_s=1,
        cancel_event=cancel,
    )

    assert next(stream) == "tick"
    cancel.set()
    started = time.monotonic()
    with pytest.raises(ShellCommandCancelled):
        for _ in stream:
            pass
    assert time.monotonic() - started < 3


def test_shell_stream_times_out_while_child_keeps_printing() -> None:
    from refract.backends._shell import stream_shell_command_lines

    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        for _ in stream_shell_command_lines(
            [sys.executable, "-c", _CHATTY_CHILD],
            executable_name=Path(sys.executable).name,
            timeout_s=1,
            line_transform=str.strip,
            terminate_wait_s=1,
        ):
            pass
    assert time.monotonic() - started < 4


def test_shell_stream_writes_stdin_text_to_child() -> None:
    from refract.backends._shell import stream_shell_command_lines

    lines = list(stream_shell_command_lines(
        [sys.executable, "-c", "import sys; print(sys.stdin.read().upper())"],
        executable_name=Path(sys.executable).name,
        line_transform=str.strip,
        terminate_wait_s=1,
        check_returncode=True,
        stdin_text="prompt via stdin",
    ))

    assert lines == ["PROMPT VIA STDIN"]


def test_v1_server_facades_and_resource_uri_model_are_removed() -> None:
    import importlib.util

    import refract.models as models
    import refract.server as server

    assert not hasattr(server, "run")
    assert not hasattr(server, "project_register")
    assert not hasattr(server, "status")
    assert not hasattr(server, "subscription_bus")
    assert not hasattr(server, "publish_job_resource")
    assert not hasattr(models, "job_resource_uri")
    assert not hasattr(models, "JOB_RESOURCE_URI_TEMPLATE")
    assert "resource_uri" not in models.SubmissionResult.model_fields
    assert importlib.util.find_spec("refract.backend_runner") is None


def test_refract_version_is_1_and_lock_matches_without_dependency_changes() -> None:
    import tomllib

    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    locked_refract = next(package for package in lock["package"] if package["name"] == "refract")

    assert project["project"]["version"] == "2.0.0"
    assert locked_refract["version"] == "2.0.0"


def test_imports() -> None:
    import refract.server  # noqa: F401
    import refract.cli  # noqa: F401
    import refract.backends.agy  # noqa: F401
    import refract.backends.claude  # noqa: F401
    import refract.backends.codex  # noqa: F401
    import refract.backends.pi  # noqa: F401


def test_backend_params_are_transport_only() -> None:
    expected = {"PROMPT", "cd", "SESSION_ID", "args", "timeout_s", "cancel_event", "emitter", "env"}
    params = BackendParams(PROMPT="x", cd=Path("."), env={"REFRACT_ASK_TOKEN": "secret"})
    assert "secret" not in repr(params)
    assert params.env == {"REFRACT_ASK_TOKEN": "secret"}
    assert {field.name for field in fields(BackendParams)} == expected


@pytest.mark.parametrize(
    ("home_writable", "executable", "exit_code"),
    [(True, "/usr/bin/codex", 0), (True, None, 1), (False, "/usr/bin/codex", 1)],
)
def test_doctor_checks_prerequisites_and_accepts_partial_profiles(
    monkeypatch, tmp_path, capsys, home_writable, executable, exit_code
) -> None:
    from refract.cli import main

    home = tmp_path / "refract"
    home.mkdir()
    (home / "config.toml").write_text(
        """[daemon]
default_profile = "balanced"

[[targets]]
id = "primary"
backend = "codex"

[profiles.balanced]
implement = "primary"
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("REFRACT_HOME", str(home))
    monkeypatch.setattr("refract.cli.os.access", lambda *_: home_writable)
    monkeypatch.setattr("refract.cli.shutil.which", lambda _: executable)

    with pytest.raises(SystemExit) as raised:
        main(["doctor"])
    captured = capsys.readouterr()
    assert raised.value.code == exit_code
    assert "does not map built-in workflows" not in captured.err
    assert "git" not in json.loads(captured.out)


def test_serve_reports_configuration_errors(monkeypatch, tmp_path, capsys) -> None:
    from refract.cli import main

    monkeypatch.setenv("REFRACT_HOME", str(tmp_path / "missing-home"))

    with pytest.raises(SystemExit) as raised:
        main(["serve"])

    error = capsys.readouterr().err
    assert raised.value.code == 1
    assert "Configuration error" in error
    assert "Missing config file" in error


def test_serve_reports_invalid_configuration(monkeypatch, tmp_path, capsys) -> None:
    from refract.cli import main

    home = tmp_path / "refract"
    home.mkdir()
    (home / "config.toml").write_text("[daemon]\ndefault_profile = 'balanced'\n", encoding="utf-8")
    monkeypatch.setenv("REFRACT_HOME", str(home))

    with pytest.raises(SystemExit) as raised:
        main(["serve"])

    error = capsys.readouterr().err
    assert raised.value.code == 1
    assert "Configuration error" in error
    assert "[targets]" in error


def test_codex_session_file_fallback(monkeypatch, tmp_path) -> None:
    from refract.backends.codex import _extract_session_id_from_latest_session

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
    from refract.backends.codex import _extract_session_id_from_latest_session

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
    from refract.backends import agy as agy_backend

    session_id = "b658ef34-d18c-4294-b329-0ae5dee0157b"

    def fake_run_shell_command(cmd, cwd=None, **kwargs):
        log_path = Path(cmd[cmd.index("--log-file") + 1])
        log_path.write_text(f"{prefix} conversation {session_id}", encoding="utf-8")
        yield "PONG"

    monkeypatch.setattr("refract.backends.shutil.which", lambda name: f"C:/bin/{name}.exe")
    monkeypatch.setattr(agy_backend, "run_shell_command", fake_run_shell_command)

    out = agy_backend.execute(BackendParams(PROMPT="x", cd=tmp_path))

    assert out.outcome == "OK"
    assert out.SESSION_ID == session_id
    assert out.agent_messages == "PONG"


@pytest.mark.asyncio
async def test_agy_uses_input_session_id_when_log_has_no_conversation_id(
    monkeypatch,
    tmp_path,
    tmp_path_factory,
) -> None:
    from refract.backends import agy as agy_backend

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

    captured = {}

    def fake_run_shell_command(cmd, cwd=None, **kwargs):
        captured["cmd"] = cmd
        log_path = Path(cmd[cmd.index("--log-file") + 1])
        log_path.write_text("PONG", encoding="utf-8")
        yield "PONG"

    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr("refract.backends.shutil.which", lambda name: f"C:/bin/{name}.exe")
    monkeypatch.setattr(agy_backend, "run_shell_command", fake_run_shell_command)

    out = agy_backend.execute(
        BackendParams(PROMPT="x", cd=tmp_path, SESSION_ID="resume-session-id")
    )

    assert out.outcome == "OK"
    assert out.SESSION_ID == "resume-session-id"
    assert out.agent_messages == "PONG"
    assert "--new-project" not in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("--conversation") + 1] == "resume-session-id"


@pytest.mark.asyncio
async def test_agy_prefers_stdout_reply_over_noisy_log_file(monkeypatch, tmp_path) -> None:
    from refract.backends import agy as agy_backend

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

    monkeypatch.setattr("refract.backends.shutil.which", lambda name: f"C:/bin/{name}.exe")
    monkeypatch.setattr(agy_backend, "run_shell_command", fake_run_shell_command)

    out = agy_backend.execute(
        BackendParams(PROMPT="x", cd=tmp_path, args=("--mode", "plan", "--sandbox"))
    )

    assert captured["cmd"][1:5] == [
        "--dangerously-skip-permissions", "--mode", "plan", "--sandbox",
    ]
    assert "--add-dir" not in captured["cmd"]
    assert captured["cmd"].count("--new-project") == 1
    assert "--conversation" not in captured["cmd"]
    assert captured["cmd"][-2:] == ["--print", "x"]
    assert out.outcome == "OK"
    assert out.SESSION_ID == session_id
    assert out.agent_messages == "pong from agy"


@pytest.mark.asyncio
async def test_agy_timeout_with_partial_output_is_fatal(monkeypatch, tmp_path) -> None:
    from refract.backends import agy as agy_backend

    def fake_run_shell_command(cmd, cwd=None, **kwargs):
        yield "partial reply"
        raise subprocess.TimeoutExpired(cmd=["agy"], timeout=1)

    monkeypatch.setattr("refract.backends.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(agy_backend, "run_shell_command", fake_run_shell_command)

    out = agy_backend.execute(BackendParams(PROMPT="x", cd=tmp_path, timeout_s=1))

    assert out.outcome == "FATAL"
    assert out.error_class == "timeout"


@pytest.mark.asyncio
async def test_bad_cd_agy_fatal() -> None:
    bad = Path("C:/definitely/not/real/path")
    out = agy_execute(BackendParams(PROMPT="x", cd=bad))
    assert out.outcome == "FATAL"
    assert out.error_class == "bad_cd"


@pytest.mark.asyncio
async def test_bad_cd_codex_fatal() -> None:
    bad = Path("C:/definitely/not/real/path")
    out = codex_execute(BackendParams(PROMPT="x", cd=bad))
    assert out.outcome == "FATAL"
    assert out.error_class == "bad_cd"


@pytest.mark.asyncio
async def test_codex_uses_input_session_id_when_no_extraction_sources_match(monkeypatch, tmp_path) -> None:
    from refract.backends import codex as codex_backend

    def fake_run_shell_command(cmd, cwd=None, **kwargs):
        yield "PONG"

    monkeypatch.setattr("refract.backends.shutil.which", lambda name: f"C:/bin/{name}.exe")
    monkeypatch.setattr(codex_backend, "run_shell_command", fake_run_shell_command)
    monkeypatch.setattr(codex_backend, "_extract_session_id_from_latest_session", lambda cwd, prompt, started_at: "")

    out = codex_backend.execute(BackendParams(PROMPT="x", cd=tmp_path, SESSION_ID="resume-session-id"))

    assert out.outcome == "OK"
    assert out.SESSION_ID == "resume-session-id"
    assert out.agent_messages == "PONG"
    assert out.error_class == ""


def test_codex_session_resolution_skips_filesystem_when_stdout_has_id(
    monkeypatch,
    tmp_path,
) -> None:
    from refract.backends import codex as codex_backend

    session_id = "b658ef34-d18c-4294-b329-0ae5dee0157b"

    def fail_scan(*args):
        raise AssertionError("session filesystem should not be scanned")

    monkeypatch.setattr(codex_backend, "_extract_session_id_from_latest_session", fail_scan)

    assert codex_backend._resolve_session_id(
        parsed_session_id=session_id,
        last_message="",
        stdout_text="",
        cwd=tmp_path,
        prompt="x",
        started_at=time.time(),
        fallback_session_id="",
    ) == (session_id, "stdout-jsonl:thread.started")


@pytest.mark.asyncio
async def test_codex_nonzero_exit_is_fatal_despite_diagnostic_output(
    monkeypatch,
    tmp_path,
) -> None:
    from refract.backends import codex as codex_backend
    from refract.backends._shell import ShellCommandFailed

    def fake_run_shell_command(cmd, cwd=None, **kwargs):
        yield "error: unknown option"
        raise ShellCommandFailed(2)

    monkeypatch.setattr("refract.backends.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(codex_backend, "run_shell_command", fake_run_shell_command)
    monkeypatch.setattr(
        codex_backend,
        "_extract_session_id_from_latest_session",
        lambda *args: "",
    )

    out = codex_backend.execute(BackendParams(PROMPT="x", cd=tmp_path))

    assert out.outcome == "FATAL"
    assert out.error_class == "execution_error"


@pytest.mark.asyncio
async def test_claude_json_result_uses_last_result_and_transport_argv(monkeypatch, tmp_path) -> None:
    from refract.backends import claude as claude_backend

    captured = {}
    first_session = "first-session"
    final_session = "final-session"

    def fake_run_shell_command(cmd, cwd=None, **kwargs):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        captured["stdin"] = kwargs.get("stdin_text")
        yield "Claude diagnostic: startup hook"
        yield json.dumps({"type": "assistant", "message": "ignore me"})
        yield json.dumps({"type": "result", "subtype": "success", "session_id": first_session, "result": "first"})
        yield "not JSON diagnostic"
        yield json.dumps({"type": "result", "subtype": "success", "session_id": final_session, "result": "PONG"})

    monkeypatch.setattr("refract.backends.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(claude_backend, "run_shell_command", fake_run_shell_command)

    out = claude_backend.execute(
        BackendParams(
            PROMPT="--prompt",
            cd=tmp_path,
            SESSION_ID="resume-session",
            args=("--tools", "Read"),
        )
    )

    assert captured["cmd"] == [
        "claude", "--tools", "Read", "-p", "--permission-mode",
        "bypassPermissions", "--output-format", "json", "--resume",
        "resume-session",
    ]
    assert captured["stdin"] == "--prompt"
    assert Path(captured["cwd"]) == tmp_path.absolute()
    assert out.outcome == "OK"
    assert out.SESSION_ID == final_session
    assert out.agent_messages == "PONG"


@pytest.mark.asyncio
async def test_claude_new_session_argv_omits_resume(monkeypatch, tmp_path) -> None:
    from refract.backends import claude as claude_backend

    captured = {}

    def fake_run_shell_command(cmd, cwd=None, **kwargs):
        captured["cmd"] = cmd
        captured["stdin"] = kwargs.get("stdin_text")
        yield json.dumps({"type": "result", "subtype": "success", "session_id": "new-session", "result": "PONG"})

    monkeypatch.setattr("refract.backends.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(claude_backend, "run_shell_command", fake_run_shell_command)

    out = claude_backend.execute(
        BackendParams(PROMPT="--prompt", cd=tmp_path, args=("--tools", "Read"))
    )

    assert captured["cmd"] == [
        "claude", "--tools", "Read", "-p", "--permission-mode",
        "bypassPermissions", "--output-format", "json",
    ]
    assert captured["stdin"] == "--prompt"
    assert "--resume" not in captured["cmd"]
    assert out.SESSION_ID == "new-session"


@pytest.mark.asyncio
async def test_claude_error_result_is_fatal(monkeypatch, tmp_path) -> None:
    from refract.backends import claude as claude_backend

    def fake_run_shell_command(cmd, cwd=None, **kwargs):
        yield json.dumps({
            "type": "result",
            "subtype": "error_during_login",
            "is_error": True,
            "result": "login failed",
            "api_error_status": 401,
        })

    monkeypatch.setattr("refract.backends.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(claude_backend, "run_shell_command", fake_run_shell_command)

    out = claude_backend.execute(BackendParams(PROMPT="x", cd=tmp_path))

    assert out.outcome == "FATAL"
    assert out.error_class == "fatal_backend"
    assert "login failed" in out.error
    assert "401" in out.error


@pytest.mark.asyncio
async def test_claude_result_falls_back_to_input_session_id(monkeypatch, tmp_path) -> None:
    from refract.backends import claude as claude_backend

    def fake_run_shell_command(cmd, cwd=None, **kwargs):
        yield json.dumps({"type": "result", "subtype": "success", "result": "PONG"})

    monkeypatch.setattr("refract.backends.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(claude_backend, "run_shell_command", fake_run_shell_command)

    out = claude_backend.execute(
        BackendParams(PROMPT="x", cd=tmp_path, SESSION_ID="resume-session")
    )

    assert out.outcome == "OK"
    assert out.SESSION_ID == "resume-session"


@pytest.mark.asyncio
async def test_claude_nonzero_exit_is_fatal_despite_agent_output(monkeypatch, tmp_path) -> None:
    from refract.backends import claude as claude_backend
    from refract.backends._shell import ShellCommandFailed

    def fake_run_shell_command(cmd, cwd=None, **kwargs):
        yield json.dumps({"type": "result", "subtype": "success", "session_id": "session", "result": "partial"})
        raise ShellCommandFailed(2)

    monkeypatch.setattr("refract.backends.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(claude_backend, "run_shell_command", fake_run_shell_command)

    out = claude_backend.execute(BackendParams(PROMPT="x", cd=tmp_path))

    assert out.outcome == "FATAL"
    assert out.error_class == "execution_error"
    assert out.agent_messages == "partial"


@pytest.mark.asyncio
async def test_claude_timeout_and_cancel_are_mapped(monkeypatch, tmp_path) -> None:
    from refract.backends import claude as claude_backend
    from refract.backends._shell import ShellCommandCancelled

    def timeout_run(cmd, cwd=None, **kwargs):
        yield "partial"
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=1)

    monkeypatch.setattr("refract.backends.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(claude_backend, "run_shell_command", timeout_run)
    timed_out = claude_backend.execute(BackendParams(PROMPT="x", cd=tmp_path, timeout_s=1))
    assert timed_out.outcome == "FATAL"
    assert timed_out.error_class == "timeout"

    def cancel_run(cmd, cwd=None, **kwargs):
        raise ShellCommandCancelled("cancelled")
        yield "unreachable"

    monkeypatch.setattr(claude_backend, "run_shell_command", cancel_run)
    cancelled = claude_backend.execute(BackendParams(PROMPT="x", cd=tmp_path))
    assert cancelled.outcome == "FATAL"
    assert cancelled.error_class == "cancelled"


@pytest.mark.asyncio
async def test_missing_claude_cli_is_fatal(monkeypatch, tmp_path) -> None:
    from refract.backends import claude as claude_backend

    monkeypatch.setattr("refract.backends.shutil.which", lambda name: None)

    out = claude_backend.execute(BackendParams(PROMPT="x", cd=tmp_path))

    assert out.outcome == "FATAL"
    assert out.error_class == "missing_cli"


@pytest.mark.asyncio
async def test_bad_cd_claude_fatal() -> None:
    from refract.backends import claude as claude_backend

    out = claude_backend.execute(
        BackendParams(PROMPT="x", cd=Path("C:/definitely/not/real/path"))
    )

    assert out.outcome == "FATAL"
    assert out.error_class == "bad_cd"


@pytest.mark.asyncio
async def test_pi_nonzero_exit_is_fatal_despite_agent_output(
    monkeypatch,
    tmp_path,
) -> None:
    from refract.backends import pi as pi_backend
    from refract.backends._shell import ShellCommandFailed

    def fake_run_shell_command(cmd, cwd=None, **kwargs):
        yield json.dumps(
            {
                "type": "message_end",
                "message": {"role": "assistant", "content": "partial"},
            }
        )
        raise ShellCommandFailed(2)

    monkeypatch.setattr("refract.backends.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(pi_backend, "run_shell_command", fake_run_shell_command)

    out = pi_backend.execute(BackendParams(PROMPT="x", cd=tmp_path))

    assert out.outcome == "FATAL"
    assert out.error_class == "execution_error"


@pytest.mark.asyncio
async def test_pi_server_error_auth_unavailable_is_fatal(monkeypatch, tmp_path) -> None:
    from refract.backends import pi as pi_backend

    def fake_run_shell_command(cmd, cwd=None, **kwargs):
        yield json.dumps(
            {
                "message": "auth_unavailable: no auth available (providers=openai-compatible-codex-chatgpt, model=chatgpt-web/high)",
                "type": "server_error",
                "code": "internal_server_error",
            }
        )

    monkeypatch.setattr("refract.backends.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(pi_backend, "run_shell_command", fake_run_shell_command)

    out = pi_backend.execute(BackendParams(PROMPT="x", cd=tmp_path))

    assert out.outcome == "FATAL"
    assert out.error_class == "fatal_backend"
    assert "auth_unavailable" in out.error


PI_CONTEXT_OVERFLOW_TRACE_FIXTURE = [
    json.dumps({"type": "session", "version": 3, "id": "pi-overflow-synthetic-session-1"}),
    json.dumps(
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [],
                "stopReason": "error",
                "errorMessage": '502: {"message":"No ChatGPT effort available to this account can carry a Bigger Context stage with <estimated_tokens> estimated tokens and <characters> characters.","type":"invalid_request_error","param":null,"code":"context_length_exceeded"}',
            },
        }
    ),
    json.dumps({"type": "agent_end", "messages": []}),
]


@pytest.mark.asyncio
async def test_pi_context_overflow_real_trace(monkeypatch, tmp_path) -> None:
    from refract.backends import pi as pi_backend

    monkeypatch.setattr("refract.backends.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(
        pi_backend,
        "run_shell_command",
        lambda *args, **kwargs: (line for line in PI_CONTEXT_OVERFLOW_TRACE_FIXTURE),
    )

    out = pi_backend.execute(BackendParams(PROMPT="x", cd=tmp_path))

    assert out.outcome == "FATAL"
    assert out.error_class == "context_overflow"
    assert "context_length_exceeded" in out.error


@pytest.mark.asyncio
async def test_pi_structured_assistant_error_with_partial_content_is_fatal(
    monkeypatch,
    tmp_path,
) -> None:
    from refract.backends import pi as pi_backend

    fixture = [
        json.dumps({"type": "session", "id": "pi-sess-1"}),
        json.dumps(
            {
                "type": "message_end",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "partial text before failure"}],
                    "stopReason": "error",
                    "errorMessage": "upstream stream disconnected",
                    "unknown_field": "ignore_me",
                },
                "arbitrary_top_field": 123,
            }
        ),
    ]

    monkeypatch.setattr("refract.backends.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(
        pi_backend,
        "run_shell_command",
        lambda *args, **kwargs: (line for line in fixture),
    )

    out = pi_backend.execute(BackendParams(PROMPT="x", cd=tmp_path))

    assert out.outcome == "FATAL"
    assert out.error_class == "execution_error"
    assert "upstream stream disconnected" in out.error


@pytest.mark.asyncio
async def test_pi_close_negative_overflow_cases_not_classified_as_overflow(
    monkeypatch,
    tmp_path,
) -> None:
    from refract.backends import pi as pi_backend

    cases = [
        "too long",
        "context error",
        "prompt too long",
        "maximum tokens exceeded",
    ]
    for msg in cases:
        fixture = [
            json.dumps({"type": "session", "id": "pi-sess-1"}),
            json.dumps(
                {
                    "type": "message_end",
                    "message": {
                        "role": "assistant",
                        "content": [],
                        "stopReason": "error",
                        "errorMessage": msg,
                    },
                }
            ),
        ]
        monkeypatch.setattr("refract.backends.shutil.which", lambda name: f"/bin/{name}")
        monkeypatch.setattr(
            pi_backend,
            "run_shell_command",
            lambda *args, **kwargs: (line for line in fixture),
        )

        out = pi_backend.execute(BackendParams(PROMPT="x", cd=tmp_path))

        assert out.outcome == "FATAL"
        assert out.error_class != "context_overflow"


def test_pi_is_context_overflow_boundary_and_case() -> None:
    from refract.backends.pi import _is_context_overflow

    assert _is_context_overflow('{"code":"context_length_exceeded"}') is True
    assert _is_context_overflow("error: context_length_exceeded") is True
    assert _is_context_overflow("prefix_context_length_exceeded_suffix") is False
    assert _is_context_overflow("notcontext_length_exceeded") is False
    assert _is_context_overflow("context_length_exceededly") is False
    assert _is_context_overflow("CONTEXT_LENGTH_EXCEEDED") is False
    assert _is_context_overflow("Context_Length_Exceeded") is False


@pytest.mark.asyncio
async def test_pi_boundary_and_case_negative_overflow_cases(
    monkeypatch,
    tmp_path,
) -> None:
    from refract.backends import pi as pi_backend

    cases = [
        "prefix_context_length_exceeded_suffix",
        "notcontext_length_exceeded",
        "context_length_exceededly",
        "CONTEXT_LENGTH_EXCEEDED",
        "Context_Length_Exceeded",
    ]
    for msg in cases:
        fixture = [
            json.dumps({"type": "session", "id": "pi-sess-1"}),
            json.dumps(
                {
                    "type": "message_end",
                    "message": {
                        "role": "assistant",
                        "content": [],
                        "stopReason": "error",
                        "errorMessage": msg,
                    },
                }
            ),
        ]
        monkeypatch.setattr("refract.backends.shutil.which", lambda name: f"/bin/{name}")
        monkeypatch.setattr(
            pi_backend,
            "run_shell_command",
            lambda *args, **kwargs: (line for line in fixture),
        )

        out = pi_backend.execute(BackendParams(PROMPT="x", cd=tmp_path))

        assert out.outcome == "FATAL"
        assert out.error_class != "context_overflow", f"False positive overflow for {msg}"


@pytest.mark.asyncio
async def test_pi_assistant_prose_containing_overflow_token_is_not_overflow(
    monkeypatch,
    tmp_path,
) -> None:
    from refract.backends import pi as pi_backend

    fixture = [
        json.dumps({"type": "session", "id": "pi-sess-1"}),
        json.dumps(
            {
                "type": "message_end",
                "message": {
                    "role": "assistant",
                    "content": "The error code context_length_exceeded indicates an oversized session.",
                    "stopReason": "stop",
                },
            }
        ),
    ]
    monkeypatch.setattr("refract.backends.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(
        pi_backend,
        "run_shell_command",
        lambda *args, **kwargs: (line for line in fixture),
    )

    out = pi_backend.execute(BackendParams(PROMPT="x", cd=tmp_path))

    assert out.outcome == "OK"
    assert out.error_class == ""
    assert "context_length_exceeded" in out.agent_messages


@pytest.mark.asyncio
async def test_pi_cancellation_precedence_over_overflow(monkeypatch, tmp_path) -> None:
    from refract.backends import pi as pi_backend

    cancel_evt = threading.Event()
    cancel_evt.set()

    monkeypatch.setattr("refract.backends.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(
        pi_backend,
        "run_shell_command",
        lambda *args, **kwargs: (line for line in PI_CONTEXT_OVERFLOW_TRACE_FIXTURE),
    )

    out = pi_backend.execute(BackendParams(PROMPT="x", cd=tmp_path, cancel_event=cancel_evt))

    assert out.outcome == "FATAL"
    assert out.error_class == "cancelled"


@pytest.mark.asyncio
async def test_pi_overflow_overrides_nonzero_exit_and_partial_output(
    monkeypatch,
    tmp_path,
) -> None:
    from refract.backends import pi as pi_backend
    from refract.backends._shell import ShellCommandFailed

    def fake_run_shell_command(cmd, cwd=None, **kwargs):
        yield json.dumps({"type": "session", "id": "pi-sess-1"})
        yield json.dumps(
            {
                "type": "message_end",
                "message": {
                    "role": "assistant",
                    "content": "partial output before crash",
                    "stopReason": "error",
                    "errorMessage": '{"code":"context_length_exceeded"}',
                },
            }
        )
        raise ShellCommandFailed(2)

    monkeypatch.setattr("refract.backends.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(pi_backend, "run_shell_command", fake_run_shell_command)

    out = pi_backend.execute(BackendParams(PROMPT="x", cd=tmp_path))

    assert out.outcome == "FATAL"
    assert out.error_class == "context_overflow"


@pytest.mark.asyncio
async def test_pi_stderr_overflow_detected(monkeypatch, tmp_path) -> None:
    from refract.backends import pi as pi_backend

    def fake_run_shell_command(cmd, cwd=None, **kwargs):
        yield json.dumps({"type": "session", "id": "pi-sess-1"})
        yield "Error from provider: context_length_exceeded in session buffer"

    monkeypatch.setattr("refract.backends.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(pi_backend, "run_shell_command", fake_run_shell_command)

    out = pi_backend.execute(BackendParams(PROMPT="x", cd=tmp_path))

    assert out.outcome == "FATAL"
    assert out.error_class == "context_overflow"


def test_pi_driver_normalizes_context_overflow_to_retryable() -> None:
    from refract.drivers import _normalize

    res = BackendResult(
        outcome="FATAL",
        SESSION_ID="sess-123",
        agent_messages="",
        error="context_length_exceeded",
        error_class="context_overflow",
    )
    norm = _normalize(res)
    assert norm.outcome == "RETRYABLE"
    assert norm.error_code == "context_overflow"
    assert norm.session_id == "sess-123"


@pytest.mark.asyncio
async def test_codex_does_not_inject_session_metadata_line(monkeypatch, tmp_path) -> None:
    from refract.backends import codex as codex_backend

    captured = {}
    session_id = "b658ef34-d18c-4294-b329-0ae5dee0157b"

    def fake_run_shell_command(cmd, cwd=None, **kwargs):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        captured["stdin"] = kwargs.get("stdin_text")
        yield "Reading additional input from stdin..."
        yield json.dumps({"type": "thread.started", "thread_id": session_id})
        yield json.dumps(
            {
                "type": "item.completed",
                "item": {"id": "item_0", "type": "agent_message", "text": "PONG"},
            }
        )
        yield json.dumps({"type": "turn.completed"})

    monkeypatch.setattr("refract.backends.shutil.which", lambda name: f"C:/bin/{name}.exe")
    monkeypatch.setattr(codex_backend, "run_shell_command", fake_run_shell_command)
    monkeypatch.setattr(codex_backend, "_extract_session_id_from_latest_session", lambda cwd, prompt, started_at: "")

    out = codex_backend.execute(
        BackendParams(
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
    assert captured["cmd"][-1] == "-"
    assert captured["stdin"] == "x"
    assert out.outcome == "OK"
    assert out.SESSION_ID == session_id
    assert out.agent_messages == "PONG"


@pytest.mark.asyncio
async def test_pi_json_mode_extracts_reply_session_and_cli_options(monkeypatch, tmp_path) -> None:
    from refract.backends import pi as pi_backend

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

    monkeypatch.setattr("refract.backends.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(pi_backend, "run_shell_command", fake_run_shell_command)

    out = pi_backend.execute(
        BackendParams(
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
    from refract.backends import pi as pi_backend

    captured = {}

    def fake_run_shell_command(cmd, **kwargs):
        captured["cmd"] = cmd
        yield json.dumps(
            {
                "type": "message_end",
                "message": {"role": "assistant", "content": "reviewed"},
            }
        )

    monkeypatch.setattr("refract.backends.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(pi_backend, "run_shell_command", fake_run_shell_command)

    out = pi_backend.execute(
        BackendParams(
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
    import refract.drivers as drivers_module
    from refract.config import TargetConfig

    captured = {}

    def fake_execute(params):
        captured["params"] = params
        return BackendResult(
            outcome="OK",
            SESSION_ID="session",
            agent_messages="reviewed",
            error="",
            error_class="",
        )

    monkeypatch.setattr(drivers_module.pi, "execute", fake_execute)
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
async def test_driver_compiles_claude_isolated_target_args(monkeypatch, tmp_path) -> None:
    import refract.drivers as drivers_module
    from refract.config import TargetConfig

    captured = {}

    def fake_execute(params):
        captured["params"] = params
        return BackendResult(outcome="OK", SESSION_ID="session", agent_messages="reviewed", error="", error_class="")

    monkeypatch.setattr(drivers_module.claude, "execute", fake_execute)
    await drivers_module.DriverRegistry().execute(
        target=TargetConfig(
            id="claude-isolated",
            backend="claude",
            isolated=True,
            system_prompt="sentinel instructions",
            read_only=True,
            model="claude-model",
            reasoning="high",
            args=("--verbose",),
        ),
        prompt="review",
        cwd=tmp_path,
        session_id="",
        timeout_s=60,
        cancel_event=threading.Event(),
    )

    assert captured["params"].args == (
        "--verbose",
        "--safe-mode",
        "--strict-mcp-config",
        "--system-prompt",
        "sentinel instructions",
        "--tools",
        "Read,Grep,Glob",
        "--model",
        "claude-model",
        "--effort",
        "high",
    )


@pytest.mark.asyncio
async def test_driver_compiles_claude_read_only_args(monkeypatch, tmp_path) -> None:
    import refract.drivers as drivers_module
    from refract.config import TargetConfig

    captured = {}

    def fake_execute(params):
        captured["args"] = params.args
        return BackendResult(outcome="OK", SESSION_ID="", agent_messages="reviewed", error="", error_class="")

    monkeypatch.setattr(drivers_module.claude, "execute", fake_execute)
    await drivers_module.DriverRegistry().execute(
        target=TargetConfig(id="claude-read-only", backend="claude", read_only=True),
        prompt="review",
        cwd=tmp_path,
        session_id="",
        timeout_s=0,
        cancel_event=threading.Event(),
    )

    assert captured["args"] == ("--tools", "Read,Grep,Glob")


@pytest.mark.asyncio
async def test_driver_compiles_claude_model_and_reasoning_args(monkeypatch, tmp_path) -> None:
    import refract.drivers as drivers_module
    from refract.config import TargetConfig

    captured = {}

    def fake_execute(params):
        captured["args"] = params.args
        return BackendResult(outcome="OK", SESSION_ID="", agent_messages="reviewed", error="", error_class="")

    monkeypatch.setattr(drivers_module.claude, "execute", fake_execute)
    await drivers_module.DriverRegistry().execute(
        target=TargetConfig(
            id="claude-policy",
            backend="claude",
            model="claude-model",
            reasoning="xhigh",
        ),
        prompt="review",
        cwd=tmp_path,
        session_id="",
        timeout_s=0,
        cancel_event=threading.Event(),
    )

    assert captured["args"] == ("--model", "claude-model", "--effort", "xhigh")


@pytest.mark.asyncio
async def test_driver_dispatches_claude_instead_of_pi(monkeypatch, tmp_path) -> None:
    import refract.drivers as drivers_module
    from refract.config import TargetConfig

    calls = []

    def fake_claude(params):
        calls.append("claude")
        return BackendResult(outcome="OK", SESSION_ID="session", agent_messages="reviewed", error="", error_class="")

    def fake_pi(params):
        calls.append("pi")
        return BackendResult(outcome="OK", SESSION_ID="pi", agent_messages="wrong", error="", error_class="")

    monkeypatch.setattr(drivers_module.claude, "execute", fake_claude)
    monkeypatch.setattr(drivers_module.pi, "execute", fake_pi)
    result = await drivers_module.DriverRegistry().execute(
        target=TargetConfig(id="claude", backend="claude"),
        prompt="review",
        cwd=tmp_path,
        session_id="",
        timeout_s=0,
        cancel_event=threading.Event(),
    )

    assert calls == ["claude"]
    assert result.outcome == "SUCCESS"
    assert result.session_id == "session"


@pytest.mark.asyncio
async def test_driver_rejects_unrecognized_backend_without_fallthrough(tmp_path) -> None:
    import refract.drivers as drivers_module
    from refract.config import TargetConfig

    result = await drivers_module.DriverRegistry().execute(
        target=TargetConfig(id="unknown", backend="unknown"),
        prompt="review",
        cwd=tmp_path,
        session_id="",
        timeout_s=0,
        cancel_event=threading.Event(),
    )

    assert result.outcome == "TARGET_FATAL"
    assert result.error_code == "invalid_args"


@pytest.mark.asyncio
async def test_driver_enforces_approval_after_normal_pi_target_args(monkeypatch, tmp_path) -> None:
    import refract.drivers as drivers_module
    from refract.config import TargetConfig

    captured = {}

    def fake_execute(params):
        captured["args"] = params.args
        return BackendResult(outcome="OK", SESSION_ID="", agent_messages="", error="", error_class="")

    monkeypatch.setattr(drivers_module.pi, "execute", fake_execute)
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
    from refract.config import TargetConfig
    from refract.drivers import DriverRegistry

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
    from refract.config import TargetConfig
    from refract.drivers import DriverRegistry

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
async def test_driver_compiles_agy_and_codex_target_configuration(monkeypatch, tmp_path) -> None:
    import refract.drivers as drivers_module
    from refract.config import TargetConfig

    captured = {}

    def fake_agy(params):
        captured["agy"] = params
        return BackendResult(outcome="OK", SESSION_ID="", agent_messages="", error="", error_class="")

    def fake_codex(params):
        captured["codex"] = params
        return BackendResult(outcome="OK", SESSION_ID="", agent_messages="", error="", error_class="")

    monkeypatch.setattr(drivers_module.agy, "execute", fake_agy)
    monkeypatch.setattr(drivers_module.codex, "execute", fake_codex)
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


def test_ask_missing_env(monkeypatch, capsys) -> None:
    from refract.cli import main

    monkeypatch.delenv("REFRACT_ASK_URL", raising=False)
    monkeypatch.delenv("REFRACT_ASK_TOKEN", raising=False)

    with pytest.raises(SystemExit) as exc_info:
        main(["ask", "Should we migrate?"])
    assert exc_info.value.code != 0
    captured = capsys.readouterr()
    assert "REFRACT_ASK_URL" in captured.err
    assert "REFRACT_ASK_TOKEN" in captured.err


def test_ask_unreachable_server(monkeypatch, capsys) -> None:
    from refract.cli import main

    monkeypatch.setenv("REFRACT_ASK_URL", "http://127.0.0.1:1/ask")
    monkeypatch.setenv("REFRACT_ASK_TOKEN", "fake-token")

    with pytest.raises(SystemExit) as exc_info:
        main(["ask", "Should we migrate?"])
    assert exc_info.value.code != 0
    captured = capsys.readouterr()
    assert "unreachable" in captured.err.lower() or "connection" in captured.err.lower() or "failed" in captured.err.lower()


def test_ask_http_rejection(monkeypatch, capsys) -> None:
    import http.server

    from refract.cli import main

    class RejectHandler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Forbidden"}).encode("utf-8"))

        def log_message(self, format, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), RejectHandler)
    server.timeout = 1
    port = server.server_port
    t = threading.Thread(target=server.handle_request, daemon=True)
    t.start()

    monkeypatch.setenv("REFRACT_ASK_URL", f"http://127.0.0.1:{port}/ask")
    monkeypatch.setenv("REFRACT_ASK_TOKEN", "bad-token")

    try:
        with pytest.raises(SystemExit) as exc_info:
            main(["ask", "Question?"])
        assert exc_info.value.code != 0
        captured = capsys.readouterr()
        assert "403" in captured.err
    finally:
        server.server_close()
        t.join(timeout=2)


def test_ask_successful_answer(monkeypatch, capsys) -> None:
    import http.server

    from refract.cli import main

    received_body = {}

    class AnswerHandler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            nonlocal received_body
            received_body = json.loads(self.rfile.read(length).decode("utf-8"))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"answer": "Use schema v15."}).encode("utf-8"))

        def log_message(self, format, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), AnswerHandler)
    server.timeout = 1
    port = server.server_port
    t = threading.Thread(target=server.handle_request, daemon=True)
    t.start()

    monkeypatch.setenv("REFRACT_ASK_URL", f"http://127.0.0.1:{port}/ask")
    monkeypatch.setenv("REFRACT_ASK_TOKEN", "valid-token-123")

    try:
        with pytest.raises(SystemExit) as exc_info:
            main(["ask", "What schema version?"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "Use schema v15."
        assert received_body == {"token": "valid-token-123", "question": "What schema version?"}
    finally:
        server.server_close()
        t.join(timeout=2)


def test_ask_timeout_prints_exact_no_answer_text(monkeypatch, capsys) -> None:
    import http.server

    from refract.ask import NO_ANSWER_TEXT
    from refract.cli import main

    class TimeoutHandler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"answer": NO_ANSWER_TEXT}).encode("utf-8"))

        def log_message(self, format, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), TimeoutHandler)
    server.timeout = 1
    port = server.server_port
    t = threading.Thread(target=server.handle_request, daemon=True)
    t.start()

    monkeypatch.setenv("REFRACT_ASK_URL", f"http://127.0.0.1:{port}/ask")
    monkeypatch.setenv("REFRACT_ASK_TOKEN", "valid-token")

    try:
        with pytest.raises(SystemExit) as exc_info:
            main(["ask", "Timeout question?"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == NO_ANSWER_TEXT
    finally:
        server.server_close()
        t.join(timeout=2)


def test_ask_token_secrecy(monkeypatch, capsys) -> None:
    import http.server

    from refract.cli import main

    secret_token = "secret-token-never-disclose-998877"

    class EchoErrorHandler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": f"Invalid token {secret_token}"}).encode("utf-8"))

        def log_message(self, format, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), EchoErrorHandler)
    server.timeout = 1
    port = server.server_port
    t = threading.Thread(target=server.handle_request, daemon=True)
    t.start()

    monkeypatch.setenv("REFRACT_ASK_URL", f"http://127.0.0.1:{port}/ask")
    monkeypatch.setenv("REFRACT_ASK_TOKEN", secret_token)

    try:
        with pytest.raises(SystemExit) as exc_info:
            main(["ask", "Question with secret?"])
        assert exc_info.value.code != 0
        captured = capsys.readouterr()
        assert secret_token not in captured.out
        assert secret_token not in captured.err
    finally:
        server.server_close()
        t.join(timeout=2)


def test_ask_does_not_require_daemon_config(monkeypatch, tmp_path, capsys) -> None:
    import http.server

    from refract.cli import main

    class OkHandler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"answer": "ok"}).encode("utf-8"))

        def log_message(self, format, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), OkHandler)
    server.timeout = 1
    port = server.server_port
    t = threading.Thread(target=server.handle_request, daemon=True)
    t.start()

    # Point REFRACT_HOME to non-existent directory without config.toml
    monkeypatch.setenv("REFRACT_HOME", str(tmp_path / "nonexistent-home"))
    monkeypatch.setenv("REFRACT_ASK_URL", f"http://127.0.0.1:{port}/ask")
    monkeypatch.setenv("REFRACT_ASK_TOKEN", "valid-token")

    try:
        with pytest.raises(SystemExit) as exc_info:
            main(["ask", "Question without config?"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == "ok"
    finally:
        server.server_close()
        t.join(timeout=2)
