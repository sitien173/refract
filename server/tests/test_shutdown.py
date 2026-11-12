from __future__ import annotations

import asyncio
import json
import os
import signal
import sqlite3
import stat
import threading
import time
from contextlib import closing
from types import SimpleNamespace

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from refract.dashboard import DashboardState, register_dashboard_routes
from refract.runtime import OrchestrationError, Runtime
from refract.workers import run_sync
from tests.cli_stub import stub_cli
from tests.orchestration_helpers import config as make_config, repository, register_project


def _runtime(tmp_path) -> tuple[Runtime, str]:
    runtime = Runtime(make_config(tmp_path / "home"))
    project = register_project(runtime, str(repository(tmp_path)))
    return runtime, project.id


def _finish(runtime: Runtime, job_id: str) -> None:
    runtime.database.finish_job(job_id, "failed", target="primary")
    runtime.scheduler.complete(job_id)


def _race_create_job(runtime: Runtime) -> list[dict]:
    """Fire ``shutdown_if_idle`` from another thread while ``create_job`` runs.

    Without a shared critical section the latch completes inside the window and
    the job is admitted after it. With one, the latch blocks until the job row
    exists and reports busy.
    """
    results: list[dict] = []
    threads: list[threading.Thread] = []
    original = runtime.database.create_job

    def create_job(**kwargs):
        thread = threading.Thread(target=lambda: results.append(runtime.shutdown_if_idle()))
        thread.start()
        threads.append(thread)
        thread.join(timeout=0.3)
        return original(**kwargs)

    runtime.database.create_job = create_job  # type: ignore[method-assign]
    runtime._race_threads = threads  # type: ignore[attr-defined]
    return results


def _assert_latch_consistent(runtime: Runtime, admitted: list[str], latch: dict) -> None:
    queued = {job_id for job_id, _ in runtime.database.queued_jobs()}
    if latch["stopping"]:
        assert not admitted, f"jobs {admitted} admitted although the daemon latched"
        assert not queued
    else:
        assert latch["queued"] + latch["running"] >= 1
    assert runtime.database.interrupt_active_jobs() == []


@pytest.mark.asyncio
async def test_submit_racing_shutdown_is_never_admitted_after_latch(tmp_path) -> None:
    runtime, project_id = _runtime(tmp_path)
    results = _race_create_job(runtime)
    admitted: list[str] = []
    try:
        try:
            admitted.append((await runtime.submit(project_id, "consult", "hello")).job_id)
        except OrchestrationError as error:
            assert error.code == "daemon_stopping"
        for thread in runtime._race_threads:  # type: ignore[attr-defined]
            thread.join(timeout=5)
        assert len(results) == 1
        _assert_latch_consistent(runtime, admitted, results[0])
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_retry_racing_shutdown_is_never_admitted_after_latch(tmp_path) -> None:
    runtime, project_id = _runtime(tmp_path)
    try:
        source = await runtime.submit(project_id, "consult", "hello")
        _finish(runtime, source.job_id)
        results = _race_create_job(runtime)
        admitted: list[str] = []
        try:
            admitted.append((await runtime.retry(source.job_id, target="primary")).job_id)
        except OrchestrationError as error:
            assert error.code == "daemon_stopping"
        for thread in runtime._race_threads:  # type: ignore[attr-defined]
            thread.join(timeout=5)
        assert len(results) == 1
        _assert_latch_consistent(runtime, admitted, results[0])
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_concurrent_submit_retry_and_shutdown_never_interrupt_a_job(tmp_path) -> None:
    for round_index in range(8):
        runtime, project_id = _runtime(tmp_path / f"round-{round_index}")
        try:
            source = await runtime.submit(project_id, "consult", "seed")
            _finish(runtime, source.job_id)
            # The seed job is terminal, so the daemon is idle until a racer is admitted.
            outcomes = await asyncio.gather(
                runtime.submit(project_id, "consult", "one"),
                runtime.retry(source.job_id, target="primary"),
                runtime.submit(project_id, "consult", "two"),
                run_sync(runtime.shutdown_if_idle),
                return_exceptions=True,
            )
            latch = outcomes[3]
            assert isinstance(latch, dict)
            admitted = []
            for outcome in outcomes[:3]:
                if isinstance(outcome, BaseException):
                    assert isinstance(outcome, OrchestrationError)
                    assert outcome.code == "daemon_stopping"
                else:
                    admitted.append(outcome.job_id)
            _assert_latch_consistent(runtime, admitted, latch)
            states = {job.state for job in runtime.database.jobs(project_id)}
            assert "interrupted" not in states
        finally:
            await runtime.close()


@pytest.mark.asyncio
async def test_shutdown_if_idle_counts_queued_and_running_and_latches_when_idle(tmp_path) -> None:
    runtime, project_id = _runtime(tmp_path)
    try:
        queued = await runtime.submit(project_id, "consult", "queued")
        busy = runtime.shutdown_if_idle()
        assert busy["stopping"] is False
        assert busy["queued"] >= 1
        assert busy["running"] == 0
        runtime.database.start_job(queued.job_id)
        busy = runtime.shutdown_if_idle()
        assert busy["stopping"] is False
        assert busy["running"] >= 1
        # A refused latch leaves admission open.
        again = await runtime.submit(project_id, "consult", "still open")
        runtime.database.finish_job(queued.job_id, "failed", target="primary")
        runtime.database.finish_job(again.job_id, "failed", target="primary")
        runtime.scheduler._pending.clear()
        runtime.scheduler._active.clear()
        assert runtime.shutdown_if_idle() == {"stopping": True, "running": 0, "queued": 0}
        with pytest.raises(OrchestrationError) as raised:
            await runtime.submit(project_id, "consult", "too late")
        assert raised.value.code == "daemon_stopping"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_forced_shutdown_reports_real_counts_and_latches_admission(tmp_path) -> None:
    runtime, project_id = _runtime(tmp_path)
    try:
        running = await runtime.submit(project_id, "consult", "running")
        runtime.database.start_job(running.job_id)
        await runtime.submit(project_id, "consult", "queued")
        latch = runtime.shutdown_if_idle(force=True)
        assert latch["stopping"] is True
        assert latch["running"] >= 1
        assert latch["queued"] >= 1
        with pytest.raises(OrchestrationError) as raised:
            await runtime.submit(project_id, "consult", "too late")
        assert raised.value.code == "daemon_stopping"
    finally:
        await runtime.close()


def _application(tmp_path, port: int = 9321):
    from refract.server import create_application

    settings = make_config(tmp_path / "home")
    return create_application(settings, host="127.0.0.1", port=port), settings.home


@pytest.mark.asyncio
async def test_daemon_json_is_private_complete_and_removed_on_exit(tmp_path, monkeypatch, caplog) -> None:
    import refract.server as server_module

    application, home = _application(tmp_path)
    path = home / "daemon.json"
    replaced: list[tuple[int, int]] = []
    real_replace = os.replace

    def checking_replace(source, destination):
        info = os.stat(source)
        replaced.append((stat.S_IMODE(info.st_mode), info.st_size))
        return real_replace(source, destination)

    monkeypatch.setattr(os, "replace", checking_replace)
    async with application.router.lifespan_context(application):
        assert os.name == "nt" or stat.S_IMODE(path.stat().st_mode) == 0o600  # file modes are POSIX-only
        data = json.loads(path.read_text(encoding="utf-8"))
        assert set(data) == {"token", "host", "port", "version", "pid"}
        assert data["pid"] == os.getpid()
        assert len(data["token"]) == 64
        assert int(data["token"], 16) >= 0
        assert (data["host"], data["port"]) == ("127.0.0.1", 9321)
        assert data["version"] == server_module.package_version("refract")
        assert application.state.refract_dashboard.shutdown_token == data["token"]
        token = data["token"]
    assert len(replaced) == 1
    assert replaced[0][1] > 0
    assert os.name == "nt" or replaced[0][0] == 0o600  # file modes are POSIX-only
    assert not path.exists()
    assert not list(home.glob(".daemon*"))
    assert token not in caplog.text


@pytest.mark.asyncio
async def test_daemon_json_with_foreign_token_is_left_in_place(tmp_path) -> None:
    application, home = _application(tmp_path)
    path = home / "daemon.json"
    async with application.router.lifespan_context(application):
        path.write_text(json.dumps({"token": "foreign"}), encoding="utf-8")
    assert json.loads(path.read_text(encoding="utf-8")) == {"token": "foreign"}


class _StubRuntime:
    def __init__(self, result: dict) -> None:
        self.result = result
        self.calls = 0
        self.forced: list[bool] = []

    def shutdown_if_idle(self, *, force: bool = False) -> dict:
        self.calls += 1
        self.forced.append(force)
        return {**self.result, "stopping": True} if force else self.result


def _shutdown_client(result: dict, token: str = "secret-token", client_host: str = "127.0.0.1"):
    exits: list[bool] = []
    runtime = _StubRuntime(result)
    state = DashboardState(runtime=runtime, shutdown_token=token, request_exit=lambda: exits.append(True))
    app = Starlette(routes=register_dashboard_routes(state))
    client = TestClient(app, base_url="http://127.0.0.1:8765", client=(client_host, 1234))
    return client, runtime, exits


_SHUTDOWN = "/dashboard/api/shutdown"
_IDLE = {"stopping": True, "running": 0, "queued": 0}
_BUSY = {"stopping": False, "running": 1, "queued": 2}


def test_shutdown_rejects_non_loopback_client() -> None:
    client, runtime, exits = _shutdown_client(_IDLE, client_host="203.0.113.9")
    response = client.post(_SHUTDOWN, headers={"Authorization": "Bearer secret-token"})
    assert response.status_code == 403
    assert (runtime.calls, exits) == (0, [])


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": "secret-token"}])
def test_shutdown_rejects_missing_or_wrong_token(headers) -> None:
    client, runtime, exits = _shutdown_client(_IDLE)
    response = client.post(_SHUTDOWN, headers=headers)
    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"
    assert "secret-token" not in response.text
    assert (runtime.calls, exits) == (0, [])


def test_shutdown_rejects_every_request_when_no_token_is_configured() -> None:
    client, runtime, exits = _shutdown_client(_IDLE, token="")
    for headers in ({}, {"Authorization": "Bearer "}):
        response = client.post(_SHUTDOWN, headers=headers)
        assert response.status_code == 401
        assert response.json()["code"] == "unauthorized"
    assert (runtime.calls, exits) == (0, [])


def test_shutdown_busy_reports_counts_and_keeps_running() -> None:
    client, runtime, exits = _shutdown_client(_BUSY)
    response = client.post(_SHUTDOWN, headers={"Authorization": "Bearer secret-token"})
    assert response.status_code == 200
    assert response.json() == {"stopping": False, "running": 1, "queued": 2}
    assert (runtime.calls, exits) == (1, [])


def test_shutdown_idle_reports_stopping_then_requests_exit() -> None:
    client, runtime, exits = _shutdown_client(_IDLE)
    response = client.post(_SHUTDOWN, headers={"Authorization": "Bearer secret-token"})
    assert response.status_code == 200
    assert response.json() == {"stopping": True, "running": 0, "queued": 0}
    assert (runtime.calls, exits) == (1, [True])


_AUTH = {"Authorization": "Bearer secret-token"}


def test_shutdown_force_true_stops_a_busy_runtime_and_requests_exit_once() -> None:
    client, runtime, exits = _shutdown_client(_BUSY)
    response = client.post(_SHUTDOWN, headers=_AUTH, json={"force": True})
    assert response.status_code == 200
    assert response.json() == {"stopping": True, "running": 1, "queued": 2}
    assert (runtime.calls, runtime.forced, exits) == (1, [True], [True])


@pytest.mark.parametrize("content", [b"", b"{}", b'{"force": false}'])
def test_shutdown_without_force_behaves_as_before(content) -> None:
    client, runtime, exits = _shutdown_client(_BUSY)
    response = client.post(_SHUTDOWN, headers=_AUTH, content=content)
    assert response.status_code == 200
    assert response.json() == _BUSY
    assert (runtime.forced, exits) == ([False], [])
    client, runtime, exits = _shutdown_client(_IDLE)
    response = client.post(_SHUTDOWN, headers=_AUTH, content=content)
    assert response.json() == _IDLE
    assert (runtime.forced, exits) == ([False], [True])


@pytest.mark.parametrize("content", [b"{", b"[]", b'"force"', b'{"force": 1}', b'{"force": "true"}', b'{"force": null}'])
def test_shutdown_rejects_invalid_body_without_latching(content) -> None:
    client, runtime, exits = _shutdown_client(_BUSY)
    response = client.post(_SHUTDOWN, headers=_AUTH, content=content)
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_request"
    assert response.json()["unchanged"] == "The daemon was not stopped."
    assert (runtime.calls, exits) == (0, [])


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}])
def test_shutdown_force_without_valid_token_is_unauthorized_even_with_bad_body(headers) -> None:
    client, runtime, exits = _shutdown_client(_BUSY)
    for content in (b'{"force": true}', b"{"):
        response = client.post(_SHUTDOWN, headers=headers, content=content)
        assert response.status_code == 401
    assert (runtime.calls, exits) == (0, [])


def test_serve_idle_shutdown_request_sets_server_exit_flag(tmp_path, monkeypatch) -> None:
    import uvicorn

    from refract import cli, server
    from tests.test_server import _serve_config

    home = tmp_path / "refract"
    home.mkdir()
    (home / "config.toml").write_text(_serve_config("127.0.0.2", 9123), encoding="utf-8")
    monkeypatch.setenv("REFRACT_HOME", str(home))
    captured: dict[str, object] = {}

    def fake_application(config, *, host: str, logging_overrides, port: int | None = None):
        captured["application_args"] = (host, port)
        state = DashboardState(runtime=_StubRuntime(_IDLE), shutdown_token="secret-token")
        application = Starlette(routes=register_dashboard_routes(state))
        application.state.refract_dashboard = state
        return application

    def fake_serve(self) -> None:
        captured["host_port"] = (self.config.host, self.config.port)
        self.started = True
        captured["flag_before"] = self.should_exit
        client = TestClient(self.config.app, base_url="http://127.0.0.1:8765", client=("127.0.0.1", 1234))
        captured["status"] = client.post(_SHUTDOWN, headers={"Authorization": "Bearer secret-token"}).status_code
        captured["flag_after"] = self.should_exit

    monkeypatch.setattr(server, "create_application", fake_application)
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: captured.setdefault("legacy_run", True))
    monkeypatch.setattr(uvicorn.Server, "run", fake_serve)
    cli.main(["serve"])

    assert "legacy_run" not in captured
    assert captured["application_args"] == ("127.0.0.2", 9123)
    assert captured["host_port"] == ("127.0.0.2", 9123)
    assert (captured["flag_before"], captured["status"], captured["flag_after"]) == (False, 200, True)


def _serve_with_stubbed_run(tmp_path, monkeypatch, fake_serve):
    import uvicorn

    from refract import cli, server
    from tests.test_server import _serve_config

    home = tmp_path / "refract"
    home.mkdir()
    (home / "config.toml").write_text(_serve_config("127.0.0.2", 9123), encoding="utf-8")
    monkeypatch.setenv("REFRACT_HOME", str(home))
    state = DashboardState()
    application = Starlette()
    application.state.refract_dashboard = state
    monkeypatch.setattr(server, "create_application", lambda config, *, host, port=None, logging_overrides=None: application)
    monkeypatch.setattr(uvicorn.Server, "run", fake_serve)
    cli.main(["serve"])


def test_serve_exits_with_startup_failure_code_when_server_never_started(tmp_path, monkeypatch) -> None:
    with pytest.raises(SystemExit) as raised:
        _serve_with_stubbed_run(tmp_path, monkeypatch, lambda self: None)
    assert raised.value.code == 3


def test_serve_returns_normally_after_a_started_server_stops(tmp_path, monkeypatch) -> None:
    def fake_serve(self) -> None:
        self.started = True

    _serve_with_stubbed_run(tmp_path, monkeypatch, fake_serve)


def test_serve_bounds_graceful_shutdown(tmp_path, monkeypatch) -> None:
    seen: list[object] = []

    def fake_serve(self) -> None:
        self.started = True
        seen.append(self.config.timeout_graceful_shutdown)

    _serve_with_stubbed_run(tmp_path, monkeypatch, fake_serve)
    assert seen == [5]


def test_shutdown_without_exit_hook_returns_503_and_leaves_admission_open() -> None:
    runtime = _StubRuntime(_IDLE)
    state = DashboardState(runtime=runtime, shutdown_token="secret-token")
    client = TestClient(Starlette(routes=register_dashboard_routes(state)), base_url="http://127.0.0.1:8765", client=("127.0.0.1", 1234))
    response = client.post(_SHUTDOWN, headers={"Authorization": "Bearer secret-token"})
    assert response.status_code == 503
    assert response.json()["code"] == "shutdown_unavailable"
    assert runtime.calls == 0
    assert client.post(_SHUTDOWN, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.post(_SHUTDOWN).status_code == 401
    assert runtime.calls == 0


@pytest.mark.asyncio
async def test_active_job_counts_reports_queued_and_running(tmp_path) -> None:
    runtime, project_id = _runtime(tmp_path)
    try:
        assert runtime.database.active_job_counts() == {"queued": 0, "running": 0}
        first = await runtime.submit(project_id, "consult", "one")
        await runtime.submit(project_id, "consult", "two")
        assert runtime.database.active_job_counts() == {"queued": 2, "running": 0}
        runtime.database.start_job(first.job_id)
        assert runtime.database.active_job_counts() == {"queued": 1, "running": 1}
        runtime.database.finish_job(first.job_id, "failed", target="primary")
        assert runtime.database.active_job_counts() == {"queued": 1, "running": 0}
    finally:
        await runtime.close()


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _stored_state(runtime: Runtime, job_id: str) -> str:
    with closing(sqlite3.connect(runtime.config.database_path)) as probe:
        return probe.execute("SELECT state FROM jobs WHERE id=?", (job_id,)).fetchone()[0]


@pytest.mark.asyncio
@pytest.mark.skipif(os.name == "nt", reason="the worker liveness probe uses POSIX signals")
async def test_forced_shutdown_interrupts_a_running_job_and_ends_its_worker(tmp_path, monkeypatch) -> None:
    pid_file = tmp_path / "worker.pid"
    stub_cli(monkeypatch, tmp_path, "codex", ["{}"], sleep_s=30, pid_file=pid_file)
    runtime, project_id = _runtime(tmp_path)
    await runtime.start()
    worker_pid = 0
    try:
        submitted = await runtime.submit(project_id, "consult", "long")
        # The fake CLI also runs for short probes that overwrite the file, so wait for a live PID.
        for _ in range(200):
            text = pid_file.read_text(encoding="utf-8") if pid_file.exists() else ""
            if text and _pid_alive(int(text)):
                worker_pid = int(text)
                break
            await asyncio.sleep(0.05)
        assert worker_pid
        assert runtime.database.job_record(submitted.job_id)["state"] == "running"
        assert runtime.shutdown_if_idle(force=True) == {"stopping": True, "running": 1, "queued": 0}
        started = time.monotonic()
        await runtime.close()
        assert time.monotonic() - started < 5
        assert _stored_state(runtime, submitted.job_id) == "interrupted"
        assert not _pid_alive(worker_pid)
        restarted = Runtime(runtime.config)
        await restarted.start()
        try:
            assert restarted.database.job_record(submitted.job_id)["state"] == "interrupted"
            assert not _pid_alive(worker_pid)
        finally:
            await restarted.close()
    finally:
        if worker_pid and _pid_alive(worker_pid):
            os.kill(worker_pid, signal.SIGKILL)
