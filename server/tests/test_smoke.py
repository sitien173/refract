import asyncio
import json
import os
import sys
import time
from datetime import datetime
from urllib.parse import parse_qs, urlsplit
import threading
from pathlib import Path

import pytest

from refract import cli as _cli  # noqa: F401  # bind the real urlopen before conftest stubs it
from tests.claude_cli import stub_claude


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

    
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    locked_refract = next(package for package in lock["package"] if package["name"] == "refract")

    assert locked_refract["version"] == project["project"]["version"]


def test_imports() -> None:
    import refract.server  # noqa: F401
    import refract.cli  # noqa: F401


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
        ("wait-timeout", False, 1, "Failed: the daemon may still be stopping."),
        ("force-refused", True, 1, "Refused: 2 running, 3 queued job(s)."),
    ],
    ids=["idle", "busy-no-force", "busy-force", "not-running", "stale-daemon-file", "manual-stop", "http-failure", "http-404", "http-503", "request-timeout", "unreachable", "stop-timeout", "old-daemon-force-refusal"],
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


def _process_gone(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        synchronize, query_limited = 0x00100000, 0x1000
        handle = kernel32.OpenProcess(synchronize | query_limited, 0, pid)
        if not handle:
            return True
        try:
            return kernel32.WaitForSingleObject(handle, 0) == 0
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


@pytest.mark.asyncio
async def test_driver_threading_cancel_reaches_worker_child(tmp_path, monkeypatch) -> None:
    from refract.config import TargetConfig
    from refract.drivers import DriverRegistry

    pid_file = tmp_path / "pid"
    stub_claude(monkeypatch, tmp_path, ["started"], sleep_s=30, pid_file=pid_file)
    cancel_event = threading.Event()

    def cancel_once_started() -> None:
        while not pid_file.exists():
            time.sleep(0.02)
        cancel_event.set()

    threading.Thread(target=cancel_once_started, daemon=True).start()
    result = await asyncio.wait_for(
        DriverRegistry().execute(
            target=TargetConfig(id="claude", backend="claude"),
            prompt="p",
            cwd=tmp_path,
            session_id="",
            timeout_s=0,
            cancel_event=cancel_event,
        ),
        timeout=10,
    )

    assert result.outcome == "CANCELLED"
    assert result.error_code == "cancelled"
    assert _process_gone(int(pid_file.read_text(encoding="utf-8")))


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
    assert "install_id: none" in out and "last_send_at: never" in out and "last_error: none" in out
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
    assert "HTTP 503" in captured.err and "runtime not active" in captured.err


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
