from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from types import SimpleNamespace

from starlette.applications import Starlette

import pytest

from openmcp.models import JobResult, JobView, ProjectView, TargetView
from openmcp.server import job_wait, mcp, workflows_resource


def _serve_config(host: str = "127.0.0.1", port: int = 8765) -> str:
    return f"""[daemon]
host = "{host}"
port = {port}
default_profile = "balanced"

[[targets]]
id = "primary"
backend = "codex"
capabilities = ["code", "review", "consult"]

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
other = "primary"
"""


def test_workflows_resource_discovers_other(monkeypatch) -> None:
    class Database:
        @staticmethod
        def project(project_id):
            return object()

    runtime = SimpleNamespace(database=Database())
    ctx = SimpleNamespace(request_context=SimpleNamespace(lifespan_context=runtime))
    assert tuple(json.loads(asyncio.run(workflows_resource("project", ctx)))) == (
        "consult", "implement", "other", "review"
    )


def test_server_import_does_not_load_daemon_config(tmp_path) -> None:
    env = os.environ.copy()
    env["OPENMCP_HOME"] = str(tmp_path / "missing-home")
    completed = subprocess.run(
        [sys.executable, "-c", "import openmcp.server"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_serve_uses_configured_transport(tmp_path, monkeypatch) -> None:
    from openmcp import cli, server
    import uvicorn

    home = tmp_path / "openmcp"
    home.mkdir()
    (home / "config.toml").write_text(_serve_config("127.0.0.2", 9123), encoding="utf-8")
    monkeypatch.setenv("OPENMCP_HOME", str(home))
    captured: dict[str, object] = {}
    old_host = server.mcp.settings.host
    old_port = server.mcp.settings.port

    monkeypatch.setattr(server, "create_application", lambda: "application")

    def fake_run(application, *, host: str, port: int) -> None:
        captured["application"] = application
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr(uvicorn, "run", fake_run)
    try:
        cli.main(["serve"])
    finally:
        server.mcp.settings.host = old_host
        server.mcp.settings.port = old_port

    assert captured == {"application": "application", "host": "127.0.0.2", "port": 9123}


def test_serve_cli_transport_overrides_config(tmp_path, monkeypatch) -> None:
    from openmcp import cli, server
    import uvicorn

    home = tmp_path / "openmcp"
    home.mkdir()
    (home / "config.toml").write_text(_serve_config("127.0.0.2", 9123), encoding="utf-8")
    monkeypatch.setenv("OPENMCP_HOME", str(home))
    captured: dict[str, object] = {}
    old_host = server.mcp.settings.host
    old_port = server.mcp.settings.port

    monkeypatch.setattr(server, "create_application", lambda: "application")

    def fake_run(application, *, host: str, port: int) -> None:
        captured["application"] = application
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr(uvicorn, "run", fake_run)
    try:
        cli.main(["serve", "--host", "127.0.0.3", "--port", "9234"])
    finally:
        server.mcp.settings.host = old_host
        server.mcp.settings.port = old_port

    assert captured == {"application": "application", "host": "127.0.0.3", "port": 9234}


@pytest.mark.asyncio
async def test_mcp_exposes_direct_job_contract() -> None:
    tools = {tool.name: tool for tool in await mcp.list_tools()}
    assert {"doctor", "reload"}.isdisjoint(tools)
    assert "job_integrate" not in tools
    assert set(tools["job_submit"].inputSchema["properties"]) == {"project_id", "workflow", "prompt", "context_key", "profile"}
    assert set(tools["job_wait"].inputSchema["properties"]) == {"job_id", "timeout_s"}
    assert tools["job_wait"].inputSchema["properties"]["timeout_s"]["default"] == 30
    assert set(tools["job_retry"].inputSchema["properties"]) == {"job_id"}
    assert {"stages", "parent_job_id", "branch", "integration_base", "artifacts", "base_commit"}.isdisjoint(JobView.model_fields)
    assert "commit" not in JobResult.model_fields
    assert {"head_commit", "clean"}.isdisjoint(ProjectView.model_fields)
    capability_key = "capabil" + "ities"
    assert capability_key not in TargetView.model_fields


def _job_view(state: str) -> JobView:
    return JobView(
        id="job-1",
        project_id="project-1",
        workflow="implement",
        profile="balanced",
        state=state,
        context_key="implement",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("timeout_s", "expected_timeout_s"),
    [(None, 30), (0, 30), (5, 5), (30, 30), (45, 30)],
)
async def test_job_wait_bounds_public_timeout(timeout_s: int | None, expected_timeout_s: int) -> None:
    initial = _job_view("running")
    latest = _job_view("succeeded")
    waits: list[tuple[str, int]] = []
    database_reads = 0

    class Database:
        def job(self, job_id: str) -> JobView:
            nonlocal database_reads
            assert job_id == initial.id
            database_reads += 1
            return initial if database_reads == 1 else latest

    class Runtime:
        database = Database()

        async def wait(self, job_id: str, timeout_s: int) -> JobView:
            waits.append((job_id, timeout_s))
            return initial

    progress_messages: list[str] = []

    async def report_progress(*, progress: float, total: float, message: str) -> None:
        progress_messages.append(message)

    ctx = SimpleNamespace(
        request_context=SimpleNamespace(lifespan_context=Runtime()),
        report_progress=report_progress,
    )
    if timeout_s is None:
        result = await job_wait(initial.id, ctx)
    else:
        result = await job_wait(initial.id, ctx, timeout_s)

    assert waits == [(initial.id, expected_timeout_s)]
    assert result is latest
    assert progress_messages == ["running", "succeeded"]


@pytest.mark.asyncio
async def test_job_wait_rejects_negative_timeout_before_job_lookup() -> None:
    class Database:
        def job(self, job_id: str) -> JobView:
            raise AssertionError("job lookup should not happen")

    runtime = SimpleNamespace(database=Database())
    ctx = SimpleNamespace(request_context=SimpleNamespace(lifespan_context=runtime))

    with pytest.raises(ValueError, match="negative"):
        await job_wait("job-1", ctx, timeout_s=-1)


@pytest.mark.asyncio
async def test_job_wait_returns_terminal_job_without_waiting() -> None:
    terminal = _job_view("failed")
    waits: list[str] = []

    class Database:
        @staticmethod
        def job(job_id: str) -> JobView:
            return terminal

    class Runtime:
        database = Database()

        async def wait(self, job_id: str, timeout_s: int) -> JobView:
            waits.append(job_id)
            return terminal

    ctx = SimpleNamespace(
        request_context=SimpleNamespace(lifespan_context=Runtime()),
        report_progress=lambda **kwargs: asyncio.sleep(0),
    )

    assert await job_wait(terminal.id, ctx) is terminal
    assert waits == []


@pytest.mark.asyncio
async def test_application_lifespan_shares_runtime_across_sessions(monkeypatch) -> None:
    import openmcp.server as server

    config = SimpleNamespace(logging=object())
    events: list[object] = []

    class Runtime:
        def __init__(self, received_config) -> None:
            assert received_config is config
            events.append("runtime.create")
            self.database = SimpleNamespace(projects=lambda: [])

        async def start(self) -> None:
            events.append("runtime.start")

        async def close(self) -> None:
            events.append(("runtime.close", server._ACTIVE_RUNTIME))

    class SessionManager:
        @asynccontextmanager
        async def run(self):
            events.append("session.enter")
            try:
                yield
            finally:
                events.append("session.exit")

    session_manager = SessionManager()
    child = Starlette()
    monkeypatch.setattr(server.mcp, "streamable_http_app", lambda: child)
    monkeypatch.setattr(server.mcp, "_session_manager", session_manager)
    monkeypatch.setattr(server, "Runtime", Runtime)
    monkeypatch.setattr(server, "configure_logging", lambda _: None)
    server._DAEMON_CONFIG = config
    server._ACTIVE_RUNTIME = None

    try:
        application = server.create_application()
        async with application.router.lifespan_context(application):
            assert events == ["runtime.create", "runtime.start", "session.enter"]
            async with server._lifespan(server.mcp) as first_session:
                assert server._active_runtime() is first_session
            assert await server.projects_resource() == "[]"
            async with server._lifespan(server.mcp) as second_session:
                assert second_session is first_session
            assert events == ["runtime.create", "runtime.start", "session.enter"]
        assert events == [
            "runtime.create",
            "runtime.start",
            "session.enter",
            "session.exit",
            ("runtime.close", None),
        ]
        assert server._ACTIVE_RUNTIME is None
        assert server._DAEMON_CONFIG is None
    finally:
        server._ACTIVE_RUNTIME = None
        server._DAEMON_CONFIG = None


@pytest.mark.asyncio
async def test_application_lifespan_cleans_up_after_start_failure(monkeypatch) -> None:
    import openmcp.server as server

    config = SimpleNamespace(logging=object())
    events: list[str] = []

    class FailingRuntime:
        def __init__(self, received_config) -> None:
            assert received_config is config

        async def start(self) -> None:
            events.append("runtime.start")
            raise RuntimeError("start failed")

        async def close(self) -> None:
            events.append("runtime.close")

    monkeypatch.setattr(server.mcp, "streamable_http_app", lambda: Starlette())
    monkeypatch.setattr(server.mcp, "_session_manager", SimpleNamespace())
    monkeypatch.setattr(server, "configure_logging", lambda _: None)
    monkeypatch.setattr(server, "Runtime", FailingRuntime)
    server._DAEMON_CONFIG = config
    server._ACTIVE_RUNTIME = None

    try:
        application = server.create_application()
        with pytest.raises(RuntimeError, match="start failed"):
            async with application.router.lifespan_context(application):
                pass
        assert events == ["runtime.start", "runtime.close"]
        assert server._ACTIVE_RUNTIME is None
        assert server._DAEMON_CONFIG is None
    finally:
        server._ACTIVE_RUNTIME = None
        server._DAEMON_CONFIG = None


@pytest.mark.asyncio
async def test_application_lifespan_clears_state_when_runtime_close_fails(monkeypatch) -> None:
    import openmcp.server as server

    config = SimpleNamespace(logging=object())

    class FailingRuntime:
        def __init__(self, received_config) -> None:
            assert received_config is config

        async def start(self) -> None:
            return None

        async def close(self) -> None:
            raise RuntimeError("close failed")

    @asynccontextmanager
    async def session_manager_run():
        yield

    session_manager = SimpleNamespace(run=session_manager_run)
    monkeypatch.setattr(server.mcp, "streamable_http_app", lambda: Starlette())
    monkeypatch.setattr(server.mcp, "_session_manager", session_manager)
    monkeypatch.setattr(server, "configure_logging", lambda _: None)
    monkeypatch.setattr(server, "Runtime", FailingRuntime)
    server._DAEMON_CONFIG = config
    server._ACTIVE_RUNTIME = None

    try:
        application = server.create_application()
        with pytest.raises(RuntimeError, match="close failed"):
            async with application.router.lifespan_context(application):
                assert server._ACTIVE_RUNTIME is not None
        assert server._ACTIVE_RUNTIME is None
        assert server._DAEMON_CONFIG is None
    finally:
        server._ACTIVE_RUNTIME = None
        server._DAEMON_CONFIG = None
