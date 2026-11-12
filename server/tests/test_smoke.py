import asyncio
import inspect
import json
from datetime import datetime
from urllib.parse import parse_qs, urlsplit
import subprocess
import sys
import threading
from dataclasses import fields
from pathlib import Path

import pytest

from refract import cli  # noqa: F401  # bind the real urlopen before conftest stubs it
from refract.backends import BackendResult
from refract.backends import BackendParams
from tests.claude_cli import stub_claude
from tests.cli_stub import execute_sync, fake_run_process, shell_fake_as_process
from refract.backends.agy import execute as agy_execute
from refract.backends.codex import execute as codex_execute


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

    assert locked_refract["version"] == project["project"]["version"]


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


@pytest.mark.parametrize(("http_status", "running", "exit_code"), [(200, True, 0), (406, True, 0), (None, False, 1)])
def test_status_probes_configured_daemon(monkeypatch, tmp_path, capsys, http_status, running, exit_code) -> None:
    from urllib.error import HTTPError, URLError

    from refract import cli

    home = tmp_path / "refract"
    home.mkdir()
    (home / "config.toml").write_text(
        """[daemon]
default_profile = "balanced"
port = 9911

[[targets]]
id = "primary"
backend = "codex"

[profiles.balanced]
implement = "primary"
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("REFRACT_HOME", str(home))
    seen: dict[str, object] = {}

    class Response:
        status = http_status

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def fake_urlopen(url, timeout=None):
        seen["url"], seen["timeout"] = url, timeout
        if http_status is None:
            raise URLError("refused")
        if http_status != 200:
            raise HTTPError(url, http_status, "unavailable", {}, None)
        return Response()

    monkeypatch.setattr(cli, "urlopen", fake_urlopen)

    with pytest.raises(SystemExit) as raised:
        cli.main(["status"])

    assert raised.value.code == exit_code
    assert seen["url"] == "http://127.0.0.1:9911/mcp"
    assert seen["timeout"] is not None
    assert json.loads(capsys.readouterr().out) == {
        "running": running, "url": "http://127.0.0.1:9911", "pid": None,
    }


@pytest.mark.parametrize(
    ("daemon_payload", "expected_pid"),
    [
        ({"token": "t", "host": "127.0.0.1", "port": 9911, "pid": 1234}, 1234),
        (None, None),
        ({"token": "t", "host": "127.0.0.1", "port": 9912, "pid": 1234}, None),
        ({"token": "t", "host": "127.0.0.1", "port": 9911, "pid": True}, None),
        ({"token": "t", "host": "127.0.0.1", "port": 9911, "pid": "1234"}, None),
    ],
    ids=["matching", "missing-file", "different-endpoint", "bool-pid", "string-pid"],
)
def test_status_reports_pid_only_for_matching_running_daemon(
    monkeypatch, tmp_path, capsys, daemon_payload, expected_pid
) -> None:
    from refract import cli

    home = tmp_path / "refract"
    home.mkdir()
    (home / "config.toml").write_text(
        '[daemon]\ndefault_profile = "balanced"\nport = 9911\n\n[[targets]]\nid = "primary"\nbackend = "codex"\n\n'
        '[profiles.balanced]\nimplement = "primary"\n', encoding="utf-8",
    )
    if daemon_payload is not None:
        (home / "daemon.json").write_text(json.dumps(daemon_payload), encoding="utf-8")
    monkeypatch.setenv("REFRACT_HOME", str(home))

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False

    monkeypatch.setattr(cli, "urlopen", lambda *_args, **_kwargs: Response())
    with pytest.raises(SystemExit) as raised:
        cli.main(["status"])

    assert raised.value.code == 0
    assert json.loads(capsys.readouterr().out) == {
        "running": True, "url": "http://127.0.0.1:9911", "pid": expected_pid,
    }


def test_status_pid_lookup_failure_does_not_change_running_result(monkeypatch, tmp_path, capsys) -> None:
    from refract import cli, daemon_control

    home = tmp_path / "refract"
    home.mkdir()
    (home / "config.toml").write_text(
        '[daemon]\ndefault_profile = "balanced"\n\n[[targets]]\nid = "primary"\nbackend = "codex"\n\n'
        '[profiles.balanced]\nimplement = "primary"\n', encoding="utf-8",
    )
    monkeypatch.setenv("REFRACT_HOME", str(home))

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False

    monkeypatch.setattr(cli, "urlopen", lambda *_args, **_kwargs: Response())
    monkeypatch.setattr(
        daemon_control, "read_daemon_file",
        lambda: (_ for _ in ()).throw(OSError("unavailable")),
    )
    with pytest.raises(SystemExit) as raised:
        cli.main(["status"])

    captured = json.loads(capsys.readouterr().out)
    assert raised.value.code == 0
    assert captured["running"] is True
    assert captured["pid"] is None


@pytest.mark.parametrize(
    ("case", "force", "exit_code", "message"),
    [
        ("idle", False, 0, "Stopped the Refract daemon."),
        ("busy", False, 1, "Refused: 2 running, 3 queued job(s)."),
        ("forced", True, 0, "Stopped the Refract daemon. Forced stop: 2 running, 3 queued job(s)."),
        ("missing", False, 0, "Refract daemon is not running."),
        ("stale", False, 0, "Refract daemon is not running."),
        ("manual", False, 1, "Cannot stop the Refract daemon automatically. Stop it manually."),
        ("http", False, 1, "Failed: the daemon rejected shutdown (HTTP 401)."),
        ("http-404", False, 1, "Failed: the daemon rejected shutdown (HTTP 404)."),
        ("http-503", False, 1, "Failed: the daemon rejected shutdown (HTTP 503)."),
        ("post-timeout", False, 1, "Failed: the shutdown request timed out."),
        ("unreachable", False, 1, "Failed: cannot reach the daemon."),
        ("unreadable", False, 1, "Failed: the daemon sent an unreadable shutdown reply."),
        ("wait-timeout", False, 1, "Failed: the daemon may still be stopping."),
        ("force-refused", True, 1, "Refused: 2 running, 3 queued job(s)."),
    ],
    ids=["idle", "busy-no-force", "busy-force", "not-running", "stale-daemon-file", "manual-stop", "http-failure", "http-404", "http-503", "request-timeout", "unreachable", "unreadable-reply", "stop-timeout", "old-daemon-force-refusal"],
)
def test_stop_cli_cases(monkeypatch, tmp_path, capsys, case, force, exit_code, message) -> None:
    from refract import daemon_control
    from refract.cli import main
    from refract.daemon_control import ShutdownFailure

    home = tmp_path / "refract"
    home.mkdir()
    (home / "config.toml").write_text(
        '[daemon]\ndefault_profile = "balanced"\n\n[[targets]]\nid = "primary"\n'
        'backend = "codex"\n\n[profiles.balanced]\nimplement = "primary"\n', encoding="utf-8",
    )
    monkeypatch.setenv("REFRACT_HOME", str(home))
    daemon = None if case in {"missing", "manual"} else ("token", "127.0.0.1", 9911, 123)
    monkeypatch.setattr(daemon_control, "read_daemon_file", lambda: daemon)
    monkeypatch.setattr(daemon_control, "configured_endpoint", lambda: ("127.0.0.1", 9911))
    monkeypatch.setattr(daemon_control, "port_open", lambda *_: case == "manual")
    calls = []

    def post(_token, _host, _port, timeout, *, force=False):
        calls.append((force, timeout))
        if case == "stale":
            return True
        if case in {"busy", "force-refused"}:
            return b'{"stopping": false, "running": 2, "queued": 3}'
        if case == "http":
            return ShutdownFailure("http", 401)
        if case == "http-404":
            return ShutdownFailure("http", 404)
        if case == "http-503":
            return ShutdownFailure("http", 503)
        if case == "post-timeout":
            return ShutdownFailure("timeout")
        if case == "unreachable":
            return ShutdownFailure("unreachable")
        return b'{"stopping": true, "running": 2, "queued": 3}'

    monkeypatch.setattr(daemon_control, "post_shutdown", post)
    if case == "unreadable":
        monkeypatch.setattr(daemon_control, "shutdown_reply", lambda _raw: None)
    wait_calls = []
    monkeypatch.setattr(
        daemon_control, "wait_for_stop",
        lambda *args: wait_calls.append(args) or case != "wait-timeout",
    )
    argv = ["stop"] + (["--force"] if force else [])
    with pytest.raises(SystemExit) as raised:
        main(argv)

    assert raised.value.code == exit_code
    assert capsys.readouterr().out.strip() == message
    assert calls == (
        [] if case in {"missing", "manual"}
        else [(force, daemon_control.SHUTDOWN_POST_TIMEOUT_S)]
    )
    assert bool(wait_calls) is (case in {"idle", "forced", "wait-timeout"})


@pytest.mark.parametrize(("force", "expected_wait_s"), [(False, 10.0), (True, 30.0)])
def test_stop_uses_force_specific_wait_timeout(monkeypatch, force, expected_wait_s) -> None:
    from refract import daemon_control
    from refract.cli import _stop_daemon

    monkeypatch.setattr(
        daemon_control, "read_daemon_file", lambda: ("token", "daemon-host", 8765, 123),
    )
    monkeypatch.setattr(
        daemon_control, "post_shutdown",
        lambda *_args, **_kwargs: b'{"stopping": true, "running": 1, "queued": 2}',
    )
    wait_args = []
    monkeypatch.setattr(
        daemon_control, "wait_for_stop", lambda *args: wait_args.append(args) or True,
    )

    assert _stop_daemon(force, lambda _message: None) is True
    expected_timeout = (
        daemon_control.FORCED_STOP_WAIT_S if force else daemon_control.STOP_WAIT_S
    )
    assert expected_timeout == expected_wait_s
    assert wait_args[0][2] == expected_timeout
    assert wait_args[0][3] == daemon_control.POLL_S


@pytest.mark.parametrize(
    ("case", "running_daemon", "force", "answers", "exit_code", "spawn_count", "message"),
    [
        ("start", False, False, True, 0, 1, "Started the Refract daemon."),
        ("start-timeout", False, False, False, 1, 1, "Failed: the Refract daemon did not start in time."),
        ("after-stop", True, False, True, 0, 1, "Started the Refract daemon."),
        ("forced", True, True, True, 0, 1, "Started the Refract daemon."),
        ("stale", True, False, True, 0, 1, "Started the Refract daemon."),
        ("refused", True, False, True, 1, 0, "Refused: 2 running, 3 queued job(s)."),
        ("stop-failed", True, False, True, 1, 0, "Failed: the daemon rejected shutdown (HTTP 503)."),
    ],
    ids=["no-daemon-running", "new-daemon-timeout", "stops-then-starts", "force", "stale-daemon-file", "stop-refused", "stop-failed"],
)
def test_restart_cli_cases(
    monkeypatch, tmp_path, capsys, case, running_daemon, force, answers, exit_code, spawn_count, message
) -> None:
    from refract import daemon_control
    from refract.cli import main

    home = tmp_path / "refract"
    home.mkdir()
    (home / "config.toml").write_text(
        '[daemon]\ndefault_profile = "balanced"\n\n[[targets]]\nid = "primary"\n'
        'backend = "codex"\n\n[profiles.balanced]\nimplement = "primary"\n', encoding="utf-8",
    )
    monkeypatch.setenv("REFRACT_HOME", str(home))
    monkeypatch.setattr(
        daemon_control, "read_daemon_file",
        lambda: ("token", "daemon-host", 8765, 123) if running_daemon else None,
    )
    monkeypatch.setattr(daemon_control, "configured_endpoint", lambda: ("127.0.0.1", 9911))
    monkeypatch.setattr(daemon_control, "port_open", lambda *_: False)
    post_calls = []
    post_args = []

    def post_shutdown(*args, **kwargs):
        post_calls.append(kwargs.get("force", False))
        post_args.append(args)
        if case == "stale":
            return True
        return (
            daemon_control.ShutdownFailure("http", 503) if case == "stop-failed"
            else b'{"stopping": false, "running": 2, "queued": 3}' if case == "refused"
            else b'{"stopping": true, "running": 0, "queued": 0}'
        )

    monkeypatch.setattr(daemon_control, "post_shutdown", post_shutdown)
    stop_wait_args = []
    monkeypatch.setattr(
        daemon_control, "wait_for_stop", lambda *args: stop_wait_args.append(args) or True,
    )
    spawned = []
    monkeypatch.setattr(daemon_control, "spawn_serve", lambda: spawned.append(True))
    start_wait_args = []
    monkeypatch.setattr(
        daemon_control, "wait_until_answers",
        lambda *args: start_wait_args.append(args) or answers,
    )

    with pytest.raises(SystemExit) as raised:
        main(["restart"] + (["--force"] if force else []))

    assert raised.value.code == exit_code
    assert post_calls == ([force] if running_daemon else [])
    assert post_args == (
        [("token", "daemon-host", 8765, daemon_control.SHUTDOWN_POST_TIMEOUT_S)]
        if running_daemon else []
    )
    assert stop_wait_args == (
        [(
            "daemon-host", 8765,
            daemon_control.FORCED_STOP_WAIT_S if force else daemon_control.STOP_WAIT_S,
            daemon_control.POLL_S,
        )]
        if running_daemon and case not in {"refused", "stop-failed", "stale"} else []
    )
    assert start_wait_args == (
        [("127.0.0.1", 9911, daemon_control.START_WAIT_S, daemon_control.POLL_S)]
        if spawn_count else []
    )
    assert len(spawned) == spawn_count
    assert capsys.readouterr().out.strip().splitlines()[-1] == message


@pytest.mark.parametrize("json_output", [True, False], ids=["json", "text"])
def test_stats_calls_api_and_prints_requested_output(monkeypatch, tmp_path, capsys, json_output) -> None:
    from refract import cli
    home = tmp_path / "refract"
    home.mkdir()
    (home / "config.toml").write_text(
        '[daemon]\ndefault_profile = "balanced"\n\n[[targets]]\nid = "primary"\nbackend = "codex"\n\n[profiles.balanced]\nimplement = "primary"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("REFRACT_HOME", str(home))
    payload = {"days": 7, "currency": "USD", "work_delegated": {"by_state": {"succeeded": 1},
        "worker_hours": 1.0, "success_rate": 1.0}, "failover_saves": {"skipped_targets": 1, "retries": 0, "retries_after_failure": 0,
            "unknown_skipped_targets": 0, "unknown_attempts": 0},
        "tokens": {"by_model": {"model": {}}}, "estimated_cost": {"total": 1.5}}
    raw_body = b'{ "days": 7, "currency": "USD" }\n'
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self): return raw_body if json_output else json.dumps(payload).encode()
    seen: dict[str, object] = {}

    def fake_urlopen(url, timeout=None):
        seen["url"] = url
        return Response()

    monkeypatch.setattr(cli, "urlopen", fake_urlopen)
    args = ["stats"] + (["--json"] if json_output else [])
    with pytest.raises(SystemExit) as raised:
        cli.main(args)
    captured = capsys.readouterr()
    assert raised.value.code == 0
    expected_offset = int(datetime.now().astimezone().utcoffset().total_seconds() // 60)
    assert parse_qs(urlsplit(seen["url"]).query) == {
        "days": ["7"], "tz_offset_minutes": [str(expected_offset)],
    }
    if json_output:
        assert captured.out.encode() == raw_body
    else:
        assert "Estimated cost" in captured.out


def test_stats_http_error_reports_status_and_api_error(monkeypatch, tmp_path, capsys) -> None:
    from io import BytesIO
    from urllib.error import HTTPError

    from refract import cli

    home = tmp_path / "refract"
    home.mkdir()
    (home / "config.toml").write_text(
        '[daemon]\ndefault_profile = "balanced"\n\n[[targets]]\nid = "primary"\nbackend = "codex"\n\n[profiles.balanced]\nimplement = "primary"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("REFRACT_HOME", str(home))
    body = b'{"error":"bad stats request"}'
    monkeypatch.setattr(
        cli, "urlopen",
        lambda url, timeout=None: (_ for _ in ()).throw(
            HTTPError(url, 400, "Bad Request", {}, BytesIO(body))
        ),
    )

    with pytest.raises(SystemExit) as raised:
        cli.main(["stats"])

    captured = capsys.readouterr()
    assert raised.value.code == 1
    assert "HTTP 400" in captured.err
    assert "bad stats request" in captured.err


def test_stats_malformed_response_exits_nonzero_without_traceback(monkeypatch, tmp_path, capsys) -> None:
    from refract import cli

    home = tmp_path / "refract"
    home.mkdir()
    (home / "config.toml").write_text(
        '[daemon]\ndefault_profile = "balanced"\n\n[[targets]]\nid = "primary"\nbackend = "codex"\n\n[profiles.balanced]\nimplement = "primary"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("REFRACT_HOME", str(home))

    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self): return b"{invalid json"

    monkeypatch.setattr(cli, "urlopen", lambda *args, **kwargs: Response())
    with pytest.raises(SystemExit) as raised:
        cli.main(["stats"])

    captured = capsys.readouterr()
    assert raised.value.code == 1
    assert "invalid JSON" in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize(
    "body",
    [
        b"{}", b"[]", b"null", b'{"work_delegated":{"by_state":1}}',
        b'{"work_delegated":{"by_state":{},"worker_hours":"x","success_rate":0},'
        b'"failover_saves":{},"tokens":{"by_model":{}},"estimated_cost":{"total":0},"currency":"USD"}',
    ],
    ids=["missing-keys", "list-payload", "null-payload", "wrong-field-type", "non-numeric-field"],
)
def test_stats_unexpected_payload_shape_exits_nonzero_without_traceback(monkeypatch, tmp_path, capsys, body) -> None:
    from refract import cli

    home = tmp_path / "refract"
    home.mkdir()
    (home / "config.toml").write_text(
        '[daemon]\ndefault_profile = "balanced"\n\n[[targets]]\nid = "primary"\nbackend = "codex"\n\n[profiles.balanced]\nimplement = "primary"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("REFRACT_HOME", str(home))

    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self): return body

    monkeypatch.setattr(cli, "urlopen", lambda *args, **kwargs: Response())
    with pytest.raises(SystemExit) as raised:
        cli.main(["stats"])

    captured = capsys.readouterr()
    assert raised.value.code == 1
    assert captured.out == ""
    assert captured.err.count("\n") == 1
    assert "unexpected shape" in captured.err


def test_stats_without_daemon_exits_nonzero(monkeypatch, tmp_path, capsys) -> None:
    from urllib.error import URLError
    from refract import cli
    home = tmp_path / "refract"
    home.mkdir()
    (home / "config.toml").write_text(
        '[daemon]\ndefault_profile = "balanced"\n\n[[targets]]\nid = "primary"\nbackend = "codex"\n\n[profiles.balanced]\nimplement = "primary"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("REFRACT_HOME", str(home))
    monkeypatch.setattr(cli, "urlopen", lambda *a, **k: (_ for _ in ()).throw(URLError("offline")))
    with pytest.raises(SystemExit) as raised:
        cli.main(["stats"])
    assert raised.value.code == 1
    assert "daemon" in capsys.readouterr().err.lower()


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
    monkeypatch.setattr(agy_backend, "run_process", shell_fake_as_process(fake_run_shell_command))

    out = await agy_backend.execute(BackendParams(PROMPT="x", cd=tmp_path))

    assert out.outcome == "OK"
    assert out.SESSION_ID == session_id
    assert out.agent_messages == "PONG"


@pytest.mark.asyncio
async def test_agy_uses_input_session_id_when_log_has_no_conversation_id(
    monkeypatch,
    tmp_path,
) -> None:
    from refract.backends import agy as agy_backend

    home = tmp_path / "agy-home"
    home.mkdir()
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
    monkeypatch.setattr(agy_backend, "run_process", shell_fake_as_process(fake_run_shell_command))

    out = await agy_backend.execute(
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
    monkeypatch.setattr(agy_backend, "run_process", shell_fake_as_process(fake_run_shell_command))

    out = await agy_backend.execute(
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
    monkeypatch.setattr(agy_backend, "run_process", shell_fake_as_process(fake_run_shell_command))

    out = await agy_backend.execute(BackendParams(PROMPT="x", cd=tmp_path, timeout_s=1))

    assert out.outcome == "FATAL"
    assert out.error_class == "timeout"


@pytest.mark.asyncio
async def test_bad_cd_agy_fatal() -> None:
    bad = Path("C:/definitely/not/real/path")
    out = await agy_execute(BackendParams(PROMPT="x", cd=bad))
    assert out.outcome == "FATAL"
    assert out.error_class == "bad_cd"


@pytest.mark.asyncio
async def test_bad_cd_codex_fatal() -> None:
    bad = Path("C:/definitely/not/real/path")
    out = await codex_execute(BackendParams(PROMPT="x", cd=bad))
    assert out.outcome == "FATAL"
    assert out.error_class == "bad_cd"


@pytest.mark.asyncio
async def test_codex_resume_without_exact_session_source_stores_no_session_id(monkeypatch, tmp_path) -> None:
    from refract.backends import codex as codex_backend

    def fake_run_shell_command(cmd, cwd=None, **kwargs):
        Path(cmd[cmd.index("-o") + 1]).write_text("PONG", encoding="utf-8")
        return iter(())

    monkeypatch.setattr("refract.backends.shutil.which", lambda name: f"C:/bin/{name}.exe")
    monkeypatch.setattr(codex_backend, "run_process", shell_fake_as_process(fake_run_shell_command))

    out = await codex_backend.execute(BackendParams(PROMPT="x", cd=tmp_path, SESSION_ID="resume-session-id"))

    assert out.outcome == "OK"
    assert out.SESSION_ID == ""
    assert out.agent_messages == "PONG"
    assert out.error_class == "warning"


def test_codex_thread_started_id_is_first_exact_source() -> None:
    from refract.backends import codex as codex_backend

    session_id = "b658ef34-d18c-4294-b329-0ae5dee0157b"

    assert codex_backend._resolve_session_id(session_id, "", "") == (session_id, "stdout-jsonl:thread.started")


@pytest.mark.asyncio
async def test_codex_nonzero_exit_is_fatal_despite_diagnostic_output(
    monkeypatch,
    tmp_path,
) -> None:
    from refract.backends import codex as codex_backend
    from tests.cli_stub import ShellCommandFailed

    def fake_run_shell_command(cmd, cwd=None, **kwargs):
        yield "error: unknown option"
        raise ShellCommandFailed(2)

    monkeypatch.setattr("refract.backends.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(codex_backend, "run_process", shell_fake_as_process(fake_run_shell_command))

    out = await codex_backend.execute(BackendParams(PROMPT="x", cd=tmp_path))

    assert out.outcome == "FATAL"
    assert out.error_class == "execution_error"


@pytest.mark.asyncio
async def test_claude_json_result_uses_last_result_and_transport_argv(monkeypatch, tmp_path) -> None:
    from refract.backends import claude as claude_backend

    record = tmp_path / "record.json"
    stub_claude(
        monkeypatch,
        tmp_path,
        [
            "Claude diagnostic: startup hook",
            json.dumps({"type": "assistant", "message": "ignore me"}),
            json.dumps({"type": "result", "subtype": "success", "session_id": "first-session", "result": "first"}),
            "not JSON diagnostic",
            json.dumps({"type": "result", "subtype": "success", "session_id": "final-session", "result": "PONG"}),
        ],
        record=record,
    )

    out = await claude_backend.execute(
        BackendParams(
            PROMPT="--prompt",
            cd=tmp_path,
            SESSION_ID="resume-session",
            args=("--tools", "Read"),
        )
    )

    captured = json.loads(record.read_text(encoding="utf-8"))
    assert captured["argv"] == [
        "claude", "--tools", "Read", "-p", "--permission-mode",
        "bypassPermissions", "--output-format", "json", "--resume",
        "resume-session",
    ]
    assert captured["stdin"] == "--prompt"
    assert Path(captured["cwd"]).resolve() == tmp_path.resolve()
    assert out.outcome == "OK"
    assert out.SESSION_ID == "final-session"
    assert out.agent_messages == "PONG"


@pytest.mark.asyncio
async def test_claude_new_session_argv_omits_resume(monkeypatch, tmp_path) -> None:
    from refract.backends import claude as claude_backend

    record = tmp_path / "record.json"
    stub_claude(
        monkeypatch,
        tmp_path,
        [json.dumps({"type": "result", "subtype": "success", "session_id": "new-session", "result": "PONG"})],
        record=record,
    )

    out = await claude_backend.execute(
        BackendParams(PROMPT="--prompt", cd=tmp_path, args=("--tools", "Read"))
    )

    captured = json.loads(record.read_text(encoding="utf-8"))
    assert captured["argv"] == [
        "claude", "--tools", "Read", "-p", "--permission-mode",
        "bypassPermissions", "--output-format", "json",
    ]
    assert captured["stdin"] == "--prompt"
    assert "--resume" not in captured["argv"]
    assert out.SESSION_ID == "new-session"


@pytest.mark.asyncio
async def test_claude_error_result_is_fatal(monkeypatch, tmp_path) -> None:
    from refract.backends import claude as claude_backend

    stub_claude(
        monkeypatch,
        tmp_path,
        [json.dumps({
            "type": "result",
            "subtype": "error_during_login",
            "is_error": True,
            "result": "login failed",
            "api_error_status": 401,
        })],
    )

    out = await claude_backend.execute(BackendParams(PROMPT="x", cd=tmp_path))

    assert out.outcome == "FATAL"
    assert out.error_class == "fatal_backend"
    assert "login failed" in out.error
    assert "401" in out.error


@pytest.mark.asyncio
async def test_claude_result_falls_back_to_input_session_id(monkeypatch, tmp_path) -> None:
    from refract.backends import claude as claude_backend

    stub_claude(monkeypatch, tmp_path, [json.dumps({"type": "result", "subtype": "success", "result": "PONG"})])

    out = await claude_backend.execute(
        BackendParams(PROMPT="x", cd=tmp_path, SESSION_ID="resume-session")
    )

    assert out.outcome == "OK"
    assert out.SESSION_ID == "resume-session"


@pytest.mark.asyncio
async def test_claude_nonzero_exit_is_fatal_despite_agent_output(monkeypatch, tmp_path) -> None:
    from refract.backends import claude as claude_backend

    stub_claude(
        monkeypatch,
        tmp_path,
        [json.dumps({"type": "result", "subtype": "success", "session_id": "session", "result": "partial"})],
        exit_code=2,
    )

    out = await claude_backend.execute(BackendParams(PROMPT="x", cd=tmp_path))

    assert out.outcome == "FATAL"
    assert out.error_class == "execution_error"
    assert out.agent_messages == "partial"


@pytest.mark.asyncio
async def test_claude_timeout_and_cancel_are_mapped(monkeypatch, tmp_path) -> None:
    from refract.backends import claude as claude_backend

    stub_claude(monkeypatch, tmp_path, ["partial"], sleep_s=30)
    timed_out = await claude_backend.execute(BackendParams(PROMPT="x", cd=tmp_path, timeout_s=1))
    assert timed_out.outcome == "FATAL"
    assert timed_out.error_class == "timeout"
    assert timed_out.error == "claude subprocess timed out after 1s"

    cancel = asyncio.Event()
    asyncio.get_running_loop().call_later(0.2, cancel.set)
    cancelled = await claude_backend.execute(BackendParams(PROMPT="x", cd=tmp_path), cancel=cancel)
    assert cancelled.outcome == "FATAL"
    assert cancelled.error_class == "cancelled"


@pytest.mark.asyncio
async def test_missing_claude_cli_is_fatal(monkeypatch, tmp_path) -> None:
    from refract.backends import claude as claude_backend

    monkeypatch.setattr("refract.backends.shutil.which", lambda name: None)

    out = await claude_backend.execute(BackendParams(PROMPT="x", cd=tmp_path))

    assert out.outcome == "FATAL"
    assert out.error_class == "missing_cli"


@pytest.mark.asyncio
async def test_bad_cd_claude_fatal() -> None:
    from refract.backends import claude as claude_backend

    out = await claude_backend.execute(
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
    from tests.cli_stub import ShellCommandFailed

    def fake_run_shell_command(cmd, cwd=None, **kwargs):
        yield json.dumps(
            {
                "type": "message_end",
                "message": {"role": "assistant", "content": "partial"},
            }
        )
        raise ShellCommandFailed(2)

    monkeypatch.setattr("refract.backends.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(pi_backend, "run_process", shell_fake_as_process(fake_run_shell_command))

    out = await pi_backend.execute(BackendParams(PROMPT="x", cd=tmp_path))

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
    monkeypatch.setattr(pi_backend, "run_process", shell_fake_as_process(fake_run_shell_command))

    out = await pi_backend.execute(BackendParams(PROMPT="x", cd=tmp_path))

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
        "run_process",
        fake_run_process(PI_CONTEXT_OVERFLOW_TRACE_FIXTURE),
    )

    out = await pi_backend.execute(BackendParams(PROMPT="x", cd=tmp_path))

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
        "run_process",
        fake_run_process(fixture),
    )

    out = await pi_backend.execute(BackendParams(PROMPT="x", cd=tmp_path))

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
            "run_process",
            fake_run_process(fixture),
        )

        out = await pi_backend.execute(BackendParams(PROMPT="x", cd=tmp_path))

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
            "run_process",
            fake_run_process(fixture),
        )

        out = await pi_backend.execute(BackendParams(PROMPT="x", cd=tmp_path))

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
        "run_process",
        fake_run_process(fixture),
    )

    out = await pi_backend.execute(BackendParams(PROMPT="x", cd=tmp_path))

    assert out.outcome == "OK"
    assert out.error_class == ""
    assert "context_length_exceeded" in out.agent_messages


@pytest.mark.asyncio
async def test_pi_cancellation_precedence_over_overflow(monkeypatch, tmp_path) -> None:
    from refract.backends import pi as pi_backend

    cancel = asyncio.Event()
    cancel.set()

    monkeypatch.setattr("refract.backends.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(
        pi_backend,
        "run_process",
        fake_run_process(PI_CONTEXT_OVERFLOW_TRACE_FIXTURE),
    )

    out = await pi_backend.execute(BackendParams(PROMPT="x", cd=tmp_path), cancel=cancel)

    assert out.outcome == "FATAL"
    assert out.error_class == "cancelled"


@pytest.mark.asyncio
async def test_pi_overflow_overrides_nonzero_exit_and_partial_output(
    monkeypatch,
    tmp_path,
) -> None:
    from refract.backends import pi as pi_backend
    from tests.cli_stub import ShellCommandFailed

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
    monkeypatch.setattr(pi_backend, "run_process", shell_fake_as_process(fake_run_shell_command))

    out = await pi_backend.execute(BackendParams(PROMPT="x", cd=tmp_path))

    assert out.outcome == "FATAL"
    assert out.error_class == "context_overflow"


@pytest.mark.asyncio
async def test_pi_stderr_overflow_detected(monkeypatch, tmp_path) -> None:
    from refract.backends import pi as pi_backend

    def fake_run_shell_command(cmd, cwd=None, **kwargs):
        yield json.dumps({"type": "session", "id": "pi-sess-1"})
        yield "Error from provider: context_length_exceeded in session buffer"

    monkeypatch.setattr("refract.backends.shutil.which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(pi_backend, "run_process", shell_fake_as_process(fake_run_shell_command))

    out = await pi_backend.execute(BackendParams(PROMPT="x", cd=tmp_path))

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
    from refract.backends._process import ProcessOutcome

    captured = {}
    session_id = "b658ef34-d18c-4294-b329-0ae5dee0157b"

    async def fake_run_process(argv, stdin, env, cwd, deadline, cancel, on_line):
        captured["cmd"] = argv
        captured["cwd"] = cwd
        captured["stdin"] = stdin
        await on_line("Reading additional input from stdin...")
        await on_line(json.dumps({"type": "thread.started", "thread_id": session_id}))
        await on_line(json.dumps(
            {
                "type": "item.completed",
                "item": {"id": "item_0", "type": "agent_message", "text": "PONG"},
            }
        ))
        await on_line(json.dumps({"type": "turn.completed"}))
        return ProcessOutcome()

    monkeypatch.setattr("refract.backends.shutil.which", lambda name: f"C:/bin/{name}.exe")
    monkeypatch.setattr(codex_backend, "run_process", fake_run_process)

    out = await codex_backend.execute(
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
    monkeypatch.setattr(pi_backend, "run_process", shell_fake_as_process(fake_run_shell_command))

    out = await pi_backend.execute(
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
        "existing-session",
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
    monkeypatch.setattr(pi_backend, "run_process", shell_fake_as_process(fake_run_shell_command))

    out = await pi_backend.execute(
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
    ]
    assert out.outcome == "OK"


@pytest.mark.asyncio
async def test_driver_passes_isolated_target_policy_to_pi(monkeypatch, tmp_path) -> None:
    import refract.drivers as drivers_module
    from refract.config import TargetConfig

    captured = {}

    async def fake_execute(params, *, cancel=None, on_event=None):
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

    async def fake_execute(params, *, cancel=None, on_event=None):
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

    async def fake_execute(params, *, cancel=None, on_event=None):
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

    async def fake_execute(params, *, cancel=None, on_event=None):
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

    async def fake_claude(params, *, cancel=None, on_event=None):
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

    async def fake_execute(params, *, cancel=None, on_event=None):
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

    async def fake_agy(params, *, cancel=None, on_event=None):
        captured["agy"] = params
        return BackendResult(outcome="OK", SESSION_ID="", agent_messages="", error="", error_class="")

    async def fake_codex(params, *, cancel=None, on_event=None):
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
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
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
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
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


def _telemetry_cli_home(monkeypatch, tmp_path) -> None:
    home = tmp_path / "refract"
    home.mkdir()
    (home / "config.toml").write_text(
        '[daemon]\ndefault_profile = "balanced"\n\n[[targets]]\nid = "primary"\nbackend = "codex"\n\n[profiles.balanced]\nimplement = "primary"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("REFRACT_HOME", str(home))


def _telemetry_cli_response(payload: dict):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self): return json.dumps(payload).encode()

    return Response()


def test_telemetry_prints_documented_fields_and_next_batch(monkeypatch, tmp_path, capsys) -> None:
    from refract import cli

    _telemetry_cli_home(monkeypatch, tmp_path)
    batch = {"schema": 1, "install_id": "id-1", "refract_version": "1.0.0", "sent_at": None,
             "events": [{"event": "job", "job_id": "one"}]}
    payload = {"enabled": True, "source": "config", "endpoint": "https://example.invalid/v1/events",
               "install_id": "id-1", "queued": 3, "last_send_at": "2026-11-10T00:00:00+00:00",
               "last_error": "HTTP 500", "next_batch": batch}
    seen: dict[str, object] = {}

    def fake_urlopen(url, timeout=None):
        seen["url"] = url
        return _telemetry_cli_response(payload)

    monkeypatch.setattr(cli, "urlopen", fake_urlopen)
    with pytest.raises(SystemExit) as raised:
        cli.main(["telemetry"])
    out = capsys.readouterr().out
    assert raised.value.code == 0
    assert urlsplit(seen["url"]).path == "/dashboard/api/telemetry"
    head, _, tail = out.partition("next_batch:\n")
    assert head.splitlines() == [
        "enabled: on", "source: config", "endpoint: https://example.invalid/v1/events",
        "install_id: id-1", "queued: 3", "last_send_at: 2026-11-10T00:00:00+00:00",
        "last_error: HTTP 500",
    ]
    assert json.loads(tail) == batch


def test_telemetry_prints_off_state_without_batch(monkeypatch, tmp_path, capsys) -> None:
    from refract import cli

    _telemetry_cli_home(monkeypatch, tmp_path)
    payload = {"enabled": False, "source": "default", "endpoint": "https://example.invalid/v1/events",
               "install_id": None, "queued": 0, "last_send_at": None, "last_error": None,
               "next_batch": None}
    monkeypatch.setattr(cli, "urlopen", lambda *a, **k: _telemetry_cli_response(payload))
    with pytest.raises(SystemExit) as raised:
        cli.main(["telemetry"])
    out = capsys.readouterr().out
    assert raised.value.code == 0
    assert out.splitlines()[0] == "enabled: off"
    assert "install_id: none" in out
    assert "last_send_at: never" in out
    assert "last_error: none" in out
    assert out.rstrip().endswith("next_batch: none")


def test_telemetry_without_daemon_exits_nonzero(monkeypatch, tmp_path, capsys) -> None:
    from urllib.error import URLError

    from refract import cli

    _telemetry_cli_home(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "urlopen", lambda *a, **k: (_ for _ in ()).throw(URLError("offline")))
    with pytest.raises(SystemExit) as raised:
        cli.main(["telemetry"])
    assert raised.value.code == 1
    assert "daemon" in capsys.readouterr().err.lower()


def test_telemetry_http_error_exits_nonzero(monkeypatch, tmp_path, capsys) -> None:
    from io import BytesIO
    from urllib.error import HTTPError

    from refract import cli

    _telemetry_cli_home(monkeypatch, tmp_path)
    body = b'{"error":"runtime not active"}'
    monkeypatch.setattr(
        cli, "urlopen",
        lambda url, timeout=None: (_ for _ in ()).throw(HTTPError(url, 503, "Unavailable", {}, BytesIO(body))),
    )
    with pytest.raises(SystemExit) as raised:
        cli.main(["telemetry"])
    captured = capsys.readouterr()
    assert raised.value.code == 1
    assert "HTTP 503" in captured.err
    assert "runtime not active" in captured.err


@pytest.mark.asyncio
async def test_telemetry_cli_next_batch_equals_sender_post_body_apart_from_sent_at(
    monkeypatch, tmp_path, capsys,
) -> None:
    from datetime import timezone
    from starlette.applications import Starlette

    from refract import cli
    from refract.config import DaemonConfig, TelemetryConfig
    from refract.dashboard import DashboardState, register_dashboard_routes
    from refract.product_telemetry import send_outbox_once
    from refract.runtime import Runtime
    from tests.test_dashboard_api import api_request

    _telemetry_cli_home(monkeypatch, tmp_path)
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    home = tmp_path / "daemon-home"
    runtime = Runtime(DaemonConfig(home=home, telemetry=TelemetryConfig(True)))
    try:
        runtime.database.enqueue_telemetry("job:one", json.dumps({"event": "job", "job_id": "one"}),
                                           datetime.now(timezone.utc).isoformat())
        app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime)))
        _code, route_body, _headers = await api_request(app, "/dashboard/api/telemetry", method="GET")
        monkeypatch.setattr(cli, "urlopen", lambda *a, **k: _telemetry_cli_response(route_body))
        with pytest.raises(SystemExit) as raised:
            cli.main(["telemetry"])
        assert raised.value.code == 0
        printed = json.loads(capsys.readouterr().out.partition("next_batch:\n")[2])
        posted: list[dict] = []

        class Response:
            status = 200

        def opener(request, timeout=None):
            posted.append(json.loads(request.data))
            return Response()

        await send_outbox_once(runtime.database, runtime._telemetry_config_check, home, opener)
        assert [{k: v for k, v in body.items() if k != "sent_at"} for body in posted] == [
            {k: v for k, v in printed.items() if k != "sent_at"},
        ]
    finally:
        runtime.database.close()
