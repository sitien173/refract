from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from openmcp.models import ContextInstructionsResult, JobResult, JobView, ProjectView, SubmissionResult, TargetView
from openmcp.runtime import OrchestrationError, Runtime
from openmcp.server import context_init, context_instructions_resource, job_wait, mcp, profiles_resource, projects_resource, publish_job_resource, subscription_bus, targets_resource, task_guide, workflows_resource
from tests.orchestration_helpers import config, repository


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

    def fake_application(*, host: str) -> str:
        captured["application_host"] = host
        return "application"

    monkeypatch.setattr(server, "create_application", fake_application)

    def fake_run(application, *, host: str, port: int) -> None:
        captured["application"] = application
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr(uvicorn, "run", fake_run)
    cli.main(["serve"])

    assert captured == {
        "application": "application",
        "application_host": "127.0.0.2",
        "host": "127.0.0.2",
        "port": 9123,
    }


def test_serve_cli_transport_overrides_config(tmp_path, monkeypatch) -> None:
    from openmcp import cli, server
    import uvicorn

    home = tmp_path / "openmcp"
    home.mkdir()
    (home / "config.toml").write_text(_serve_config("127.0.0.2", 9123), encoding="utf-8")
    monkeypatch.setenv("OPENMCP_HOME", str(home))
    captured: dict[str, object] = {}

    def fake_application(*, host: str) -> str:
        captured["application_host"] = host
        return "application"

    monkeypatch.setattr(server, "create_application", fake_application)

    def fake_run(application, *, host: str, port: int) -> None:
        captured["application"] = application
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr(uvicorn, "run", fake_run)
    cli.main(["serve", "--host", "127.0.0.3", "--port", "9234"])

    assert captured == {
        "application": "application",
        "application_host": "127.0.0.3",
        "host": "127.0.0.3",
        "port": 9234,
    }


@pytest.mark.asyncio
async def test_mcp_exposes_direct_job_contract() -> None:
    tools = {tool.name: tool for tool in await mcp.list_tools()}
    assert {"doctor", "reload"}.isdisjoint(tools)
    assert "job_integrate" not in tools
    assert set(tools["job_submit"].input_schema["properties"]) == {"project_id", "workflow", "prompt", "context_key", "profile"}
    assert set(tools["context_init"].input_schema["properties"]) == {"project_id", "workflow", "instruction"}
    assert set(tools["task_guide"].input_schema["properties"]) == {"project_id"}
    assert set(tools["job_wait"].input_schema["properties"]) == {"job_id", "timeout_s"}
    assert tools["job_wait"].input_schema["properties"]["timeout_s"]["default"] == 30
    assert set(tools["job_retry"].input_schema["properties"]) == {"job_id"}
    assert {"stages", "parent_job_id", "branch", "integration_base", "artifacts", "base_commit"}.isdisjoint(JobView.model_fields)
    assert "commit" not in JobResult.model_fields
    assert {"resource_uri"} <= SubmissionResult.model_fields.keys()
    assert {"head_commit", "clean"}.isdisjoint(ProjectView.model_fields)
    capability_key = "capabil" + "ities"
    assert capability_key not in TargetView.model_fields


@pytest.mark.asyncio
async def test_task_guide_does_not_echo_a_task(tmp_path) -> None:
    class Database:
        @staticmethod
        def project(project_id: str):
            raise AssertionError("project lookup should not happen")

    (tmp_path / "task_guide.json").write_text('{"scope": "global"}', encoding="utf-8")
    runtime = SimpleNamespace(config=SimpleNamespace(home=tmp_path), database=Database())
    ctx = SimpleNamespace(request_context=SimpleNamespace(lifespan_context=runtime))

    assert (await task_guide(ctx)).model_dump() == {"guide": {"scope": "global"}}


@pytest.mark.asyncio
async def test_job_resource_updates_use_subscription_bus() -> None:
    events: list[object] = []
    unsubscribe = subscription_bus.subscribe(events.append)
    try:
        await publish_job_resource("openmcp://jobs/job-1")
    finally:
        unsubscribe()
    assert len(events) == 1
    assert events[0].uri == "openmcp://jobs/job-1"


@pytest.mark.asyncio
async def test_runtime_resources_use_v2_templates_and_context() -> None:
    templates = {template.uri_template for template in await mcp.list_resource_templates()}
    assert {"openmcp://projects{?scope}", "openmcp://targets{?scope}", "openmcp://profiles{?scope}"} <= templates
    assert await mcp.list_resources() == []

    class Database:
        @staticmethod
        def projects():
            return [{"id": "project-1"}]

    runtime = SimpleNamespace(
        database=Database(),
        targets=lambda: [{"id": "target-1"}],
        catalog=SimpleNamespace(default_profile="balanced", profiles={"balanced"}),
    )
    ctx = SimpleNamespace(request_context=SimpleNamespace(lifespan_context=runtime))
    assert json.loads(await projects_resource(ctx)) == [{"id": "project-1"}]
    assert json.loads(await targets_resource(ctx)) == [{"id": "target-1"}]
    assert json.loads(await profiles_resource(ctx)) == {"default": "balanced", "available": ["balanced"]}


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
    events: list[str] = []

    class Runtime:
        def __init__(self, received_config, *, notifier) -> None:
            assert received_config is config
            assert notifier is server.publish_job_resource
            events.append("runtime.create")

        async def start(self) -> None:
            events.append("runtime.start")

        async def close(self) -> None:
            events.append("runtime.close")

    monkeypatch.setattr(server, "Runtime", Runtime)
    monkeypatch.setattr(server, "configure_logging", lambda _: None)
    server._DAEMON_CONFIG = config

    application = server.create_application()
    async with application.router.lifespan_context(application):
        assert events == ["runtime.create", "runtime.start"]
        assert server._DAEMON_CONFIG is config
    assert events == ["runtime.create", "runtime.start", "runtime.close"]
    assert server._DAEMON_CONFIG is None


@pytest.mark.asyncio
async def test_application_lifespan_cleans_up_after_start_failure(monkeypatch) -> None:
    import openmcp.server as server

    config = SimpleNamespace(logging=object())
    events: list[str] = []

    class FailingRuntime:
        def __init__(self, received_config, *, notifier) -> None:
            assert received_config is config
            assert notifier is server.publish_job_resource

        async def start(self) -> None:
            events.append("runtime.start")
            raise RuntimeError("start failed")

        async def close(self) -> None:
            events.append("runtime.close")

    monkeypatch.setattr(server, "configure_logging", lambda _: None)
    monkeypatch.setattr(server, "Runtime", FailingRuntime)
    server._DAEMON_CONFIG = config

    application = server.create_application()
    with pytest.raises(RuntimeError, match="start failed"):
        async with application.router.lifespan_context(application):
            pass
    assert events == ["runtime.start", "runtime.close"]
    assert server._DAEMON_CONFIG is None


@pytest.mark.asyncio
async def test_application_lifespan_clears_state_when_runtime_close_fails(monkeypatch) -> None:
    import openmcp.server as server

    config = SimpleNamespace(logging=object())

    class FailingRuntime:
        def __init__(self, received_config, *, notifier) -> None:
            assert received_config is config
            assert notifier is server.publish_job_resource

        async def start(self) -> None:
            return None

        async def close(self) -> None:
            raise RuntimeError("close failed")

    monkeypatch.setattr(server, "configure_logging", lambda _: None)
    monkeypatch.setattr(server, "Runtime", FailingRuntime)
    server._DAEMON_CONFIG = config

    application = server.create_application()
    with pytest.raises(RuntimeError, match="close failed"):
        async with application.router.lifespan_context(application):
            pass
    assert server._DAEMON_CONFIG is None


@pytest.mark.asyncio
async def test_context_init_returns_instructions_model(tmp_path) -> None:
    root = repository(tmp_path)
    runtime = Runtime(config(tmp_path / "home"))
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        ctx = SimpleNamespace(request_context=SimpleNamespace(lifespan_context=runtime))
        result = await context_init(project.id, "implement", "follow the plan", ctx)
        assert isinstance(result, ContextInstructionsResult)
        assert result.project_id == project.id
        assert result.instructions == {"implement": "follow the plan"}
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_context_init_round_trips_through_resource(tmp_path) -> None:
    root = repository(tmp_path)
    runtime = Runtime(config(tmp_path / "home"))
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        ctx = SimpleNamespace(request_context=SimpleNamespace(lifespan_context=runtime))
        await context_init(project.id, "implement", "follow the plan", ctx)
        assert json.loads(await context_instructions_resource(project.id, ctx)) == {
            "project_id": project.id,
            "instructions": {"implement": "follow the plan"},
        }
        await context_init(project.id, "implement", "revised guidance", ctx)
        assert json.loads(await context_instructions_resource(project.id, ctx)) == {
            "project_id": project.id,
            "instructions": {"implement": "revised guidance"},
        }
        result = await context_init(project.id, "implement", "", ctx)
        assert result.instructions == {}
        assert json.loads(await context_instructions_resource(project.id, ctx)) == {
            "project_id": project.id,
            "instructions": {},
        }
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_context_init_stores_per_workflow_instructions(tmp_path) -> None:
    root = repository(tmp_path)
    runtime = Runtime(config(tmp_path / "home"))
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        ctx = SimpleNamespace(request_context=SimpleNamespace(lifespan_context=runtime))
        await context_init(project.id, "implement", "build it", ctx)
        await context_init(project.id, "review", "check it", ctx)
        assert json.loads(await context_instructions_resource(project.id, ctx)) == {
            "project_id": project.id,
            "instructions": {"implement": "build it", "review": "check it"},
        }
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_context_init_rejects_unknown_project_before_workflow(tmp_path) -> None:
    root = repository(tmp_path)
    runtime = Runtime(config(tmp_path / "home"))
    await runtime.start()
    try:
        runtime.register_project(str(root))
        ctx = SimpleNamespace(request_context=SimpleNamespace(lifespan_context=runtime))
        with pytest.raises(OrchestrationError, match="Unknown project"):
            await context_init("missing-project", "not-a-workflow", "ignored", ctx)
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_context_init_rejects_unknown_workflow(tmp_path) -> None:
    root = repository(tmp_path)
    runtime = Runtime(config(tmp_path / "home"))
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        ctx = SimpleNamespace(request_context=SimpleNamespace(lifespan_context=runtime))
        with pytest.raises(OrchestrationError, match="Unknown workflow"):
            await context_init(project.id, "not-a-workflow", "ignored", ctx)
        assert json.loads(await context_instructions_resource(project.id, ctx)) == {
            "project_id": project.id,
            "instructions": {},
        }
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_context_instructions_resource_rejects_unknown_project(tmp_path) -> None:
    runtime = Runtime(config(tmp_path / "home"))
    await runtime.start()
    try:
        ctx = SimpleNamespace(request_context=SimpleNamespace(lifespan_context=runtime))
        with pytest.raises(ValueError, match="Unknown project"):
            await context_instructions_resource("missing-project", ctx)
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_context_init_does_not_touch_job_execution(tmp_path) -> None:
    root = repository(tmp_path)
    runtime = Runtime(config(tmp_path / "home"))
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        ctx = SimpleNamespace(request_context=SimpleNamespace(lifespan_context=runtime))
        await context_init(project.id, "implement", "follow the plan", ctx)
        await context_init(project.id, "review", "check it", ctx)
        assert runtime.database.queued_jobs() == []
        assert runtime.database.jobs(project.id) == []
        assert runtime.scheduler.queued_jobs == 0
        assert runtime.scheduler.active_jobs == 0
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_context_init_survives_daemon_restart(tmp_path) -> None:
    root = repository(tmp_path)
    home = tmp_path / "home"
    first = Runtime(config(home))
    await first.start()
    try:
        project = first.register_project(str(root))
        ctx = SimpleNamespace(request_context=SimpleNamespace(lifespan_context=first))
        await context_init(project.id, "implement", "persistent guidance", ctx)
        project_id = project.id
    finally:
        await first.close()

    second = Runtime(config(home))
    await second.start()
    try:
        ctx = SimpleNamespace(request_context=SimpleNamespace(lifespan_context=second))
        assert json.loads(await context_instructions_resource(project_id, ctx)) == {
            "project_id": project_id,
            "instructions": {"implement": "persistent guidance"},
        }
    finally:
        await second.close()
