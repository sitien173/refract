from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Self
from urllib.error import HTTPError, URLError

import pytest

from refract import daemon_control
from refract.daemon_control import ShutdownFailure


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("REFRACT_HOME", str(tmp_path))
    return tmp_path


def write_daemon(home: Path, payload: Any) -> None:
    (home / "daemon.json").write_text(payload if isinstance(payload, str) else json.dumps(payload))


@pytest.mark.parametrize("port", [1, 8765, 65535])
def test_read_daemon_file_valid(home: Path, port: int) -> None:
    write_daemon(home, {"token": "t", "host": "127.0.0.1", "port": port, "pid": 123})
    assert daemon_control.read_daemon_file() == ("t", "127.0.0.1", port, 123)


@pytest.mark.parametrize("pid", [None, "123", True, 1.5])
def test_read_daemon_file_invalid_pid_becomes_none(home: Path, pid: Any) -> None:
    write_daemon(home, {"token": "t", "host": "127.0.0.1", "port": 8765, "pid": pid})
    assert daemon_control.read_daemon_file() == ("t", "127.0.0.1", 8765, None)


def test_read_daemon_file_missing(home: Path) -> None:
    assert daemon_control.read_daemon_file() is None


def test_read_daemon_file_missing_pid(home: Path) -> None:
    write_daemon(home, {"token": "t", "host": "127.0.0.1", "port": 8765})
    assert daemon_control.read_daemon_file() == ("t", "127.0.0.1", 8765, None)


@pytest.mark.parametrize(
    "payload",
    [
        "{not json",
        [],
        "null",
        {"host": "127.0.0.1", "port": 1},
        {"token": "", "host": "127.0.0.1", "port": 1},
        {"token": "t", "port": 1},
        {"token": "t", "host": "127.0.0.1"},
        {"token": "t", "host": "127.0.0.1", "port": True},
        {"token": "t", "host": "127.0.0.1", "port": 0},
        {"token": "t", "host": "127.0.0.1", "port": 65536},
        {"token": "t", "host": "127.0.0.1", "port": "80"},
    ],
)
def test_read_daemon_file_rejects_invalid(home: Path, payload: Any) -> None:
    write_daemon(home, payload)
    assert daemon_control.read_daemon_file() is None


def fake_open(monkeypatch: pytest.MonkeyPatch, *, raises: Exception | None = None, reply: bytes = b"") -> list[Any]:
    seen: list[Any] = []

    class Response:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self, size: int) -> bytes:
            return reply[:size]

    def fake(request: Any, timeout: float) -> Response:
        seen.append((request, timeout))
        if raises is not None:
            raise raises
        return Response()

    monkeypatch.setattr(daemon_control, "open_direct", fake)
    return seen


def test_post_shutdown_returns_reply_and_sends_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = fake_open(monkeypatch, reply=b'{"stopping": true}')
    assert daemon_control.post_shutdown("tok", "::1", 9, 3.0) == b'{"stopping": true}'
    [(request, timeout)] = seen
    assert request.full_url == "http://[::1]:9/dashboard/api/shutdown"
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "Bearer tok"
    assert request.data == b""
    assert request.get_header("Content-type") is None
    assert timeout == 3.0


def test_post_shutdown_force_sends_json_body(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = fake_open(monkeypatch)
    daemon_control.post_shutdown("tok", "127.0.0.1", 9, 3.0, force=True)
    [(request, _timeout)] = seen
    assert request.data == b'{"force": true}'
    assert request.get_header("Content-type") == "application/json"


def test_post_shutdown_connection_refused_returns_true(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_open(monkeypatch, raises=URLError(ConnectionRefusedError()))
    assert daemon_control.post_shutdown("t", "127.0.0.1", 1, 1.0) is True


@pytest.mark.parametrize("code", [401, 404, 503])
def test_post_shutdown_reports_http_error(monkeypatch: pytest.MonkeyPatch, code: int) -> None:
    fake_open(monkeypatch, raises=HTTPError("u", code, "m", None, None))  # type: ignore[arg-type]
    assert daemon_control.post_shutdown("t", "127.0.0.1", 1, 1.0) == ShutdownFailure("http", code)


def test_post_shutdown_reports_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_open(monkeypatch, raises=URLError(TimeoutError()))
    assert daemon_control.post_shutdown("t", "127.0.0.1", 1, 1.0) == ShutdownFailure("timeout")


def test_post_shutdown_reports_other_os_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_open(monkeypatch, raises=OSError("boom"))
    assert daemon_control.post_shutdown("t", "127.0.0.1", 1, 1.0) == ShutdownFailure("unreachable")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (b'{"stopping": true, "running": 0, "queued": 0}', (True, 0, 0)),
        (b'{"stopping": false, "running": 2, "queued": 3}', (False, 2, 3)),
        (b"not json", None),
        (b"[]", None),
        (b'{"running": 0, "queued": 0}', None),
        (b'{"stopping": 1, "running": 0, "queued": 0}', None),
        (b'{"stopping": true, "running": -1, "queued": 0}', None),
        (b'{"stopping": true, "running": true, "queued": 0}', None),
        (b'{"stopping": true, "running": 0}', None),
    ],
)
def test_shutdown_reply(raw: bytes, expected: tuple[bool, int, int] | None) -> None:
    assert daemon_control.shutdown_reply(raw) == expected


def test_wait_for_stop_succeeds_when_file_gone_and_port_closed(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(daemon_control, "port_open", lambda _h, _p: False)
    assert daemon_control.wait_for_stop("127.0.0.1", 1, 1.0, 0.01) is True


def test_wait_for_stop_waits_for_the_file_to_clear(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_daemon(home, {})
    monkeypatch.setattr(daemon_control, "port_open", lambda _h, _p: False)
    monkeypatch.setattr(daemon_control.time, "sleep", lambda _s: (home / "daemon.json").unlink(missing_ok=True))
    assert daemon_control.wait_for_stop("127.0.0.1", 1, 5.0, 0.01) is True


def test_wait_for_stop_times_out(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(daemon_control, "port_open", lambda _h, _p: True)
    assert daemon_control.wait_for_stop("127.0.0.1", 1, 0.05, 0.01) is False


def test_wait_until_answers() -> None:
    answers = iter([False, False, True])
    assert daemon_control.wait_until_answers("h", 1, 5.0, 0.01, lambda _h, _p: next(answers)) is True
    assert daemon_control.wait_until_answers("h", 1, 0.05, 0.01, lambda _h, _p: False) is False


def test_wait_until_answers_uses_current_default(monkeypatch: pytest.MonkeyPatch) -> None:
    answers = iter([False, True])
    monkeypatch.setattr(daemon_control, "daemon_answers", lambda _h, _p: next(answers))
    assert daemon_control.wait_until_answers("h", 1, 1.0, 0.01) is True


def test_daemon_answers_treats_http_error_as_running(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        daemon_control, "open_direct",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(HTTPError("u", 404, "missing", {}, None)),
    )
    assert daemon_control.daemon_answers("example", 12) is True


def test_daemon_answers_returns_false_when_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        daemon_control, "open_direct",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("offline")),
    )
    assert daemon_control.daemon_answers("example", 12) is False


def test_spawn_serve_starts_detached_process(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = []
    monkeypatch.setattr(daemon_control.shutil, "which", lambda _name: "/bin/refract")
    monkeypatch.setattr(daemon_control.subprocess, "Popen", lambda *args, **kwargs: seen.append((args, kwargs)))
    daemon_control.spawn_serve()
    assert seen[0][0] == (["/bin/refract", "serve"],)
    assert seen[0][1]["start_new_session"] is True
    assert seen[0][1]["stdin"] is daemon_control.subprocess.DEVNULL


def test_configured_endpoint_reads_valid_config(home: Path) -> None:
    (home / "config.toml").write_text('[daemon]\nhost = "::1"\nport = 1234\n', encoding="utf-8")
    assert daemon_control.configured_endpoint() == ("::1", 1234)


@pytest.mark.parametrize(("host", "port", "expected"), [("localhost", 80, "localhost:80"), ("::1", 80, "[::1]:80")])
def test_netloc_formats_host_and_port(host: str, port: int, expected: str) -> None:
    assert daemon_control.netloc(host, port) == expected


@pytest.mark.parametrize(("value", "expected"), [(0, 0), (3, 3), (-1, None), (True, None), ("2", None)])
def test_count_accepts_nonnegative_integers_only(value: Any, expected: int | None) -> None:
    assert daemon_control.count(value) == expected
