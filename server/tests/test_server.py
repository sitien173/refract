from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager, suppress
import subprocess
import sys
import uuid
from types import SimpleNamespace

import pytest

from refract.config import load_config
from refract.models import JobSummary, JobView, SubmissionResult
from refract.runtime import OrchestrationError, Runtime
from refract.scheduler import _Dispatch
from refract.server import RefractError, answer, mcp, wait
from tests.orchestration_helpers import git, register_project


def _serve_config(host: str = "127.0.0.1", port: int = 8765) -> str:
    return f"""[daemon]
host = "{host}"
port = {port}
default_profile = "balanced"

[[targets]]
id = "primary"
backend = "codex"

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
other = "primary"
"""


@asynccontextmanager
async def _connected_client(tmp_path, monkeypatch):
    from mcp.client.session import ClientSession
    from mcp.shared.memory import create_client_server_memory_streams
    from refract import server

    home = tmp_path / "refract-home"
    home.mkdir()
    config_path = home / "config.toml"
    config_path.write_text(_serve_config(), encoding="utf-8")
    monkeypatch.setenv("REFRACT_HOME", str(home))
    monkeypatch.setattr(server, "configure_logging", lambda _settings: None)
    from refract.dashboard import DashboardState
    state = DashboardState()
    instance = server.create_mcp(server.load_config(config_path), state=state)
    lowlevel = instance._lowlevel_server
    async with create_client_server_memory_streams() as (client_streams, server_streams):
        server_task = asyncio.create_task(
            lowlevel.run(*server_streams, lowlevel.create_initialization_options())
        )
        try:
            async with ClientSession(*client_streams) as client:
                await client.initialize()
                yield client, state.runtime
        finally:
            server_task.cancel()
            with suppress(asyncio.CancelledError):
                await server_task


@pytest.mark.asyncio
async def test_tool_surface_lists_exact_v3_contract() -> None:
    expected = {
        "submit": {"path", "workflow", "prompt", "profile", "session", "fresh"},
        "wait": {"job_id", "timeout_s"},
        "answer": {"job_id", "answer"},
        "cancel": {"job_id"},
        "retry": {"job_id", "target"},
        "list": {"path"},
        "card_create": {"path", "title", "body", "job_ids"},
        "card_move": {"card_id", "state", "job_ids", "note"},
        "card_list": {"path"},
    }
    tools = {tool.name: tool for tool in await mcp.list_tools()}

    assert {name: set(tool.input_schema["properties"]) for name, tool in tools.items()} == expected
    assert await mcp.list_resources() == []
    assert await mcp.list_resource_templates() == []
    assert mcp.title == "Refract job queue"
    assert mcp.instructions
    assert len(mcp.instructions) <= 2048
    assert all(name in mcp.instructions for name in expected)
    for tool in tools.values():
        assert tool.title
        assert tool.description
        assert len(tool.description) <= 2048
        assert "refract://" not in tool.description
        assert tool.output_schema is None


def test_targets_unavailable_error_schema_carries_retry_delay_only_for_that_code() -> None:
    from refract.server import RefractError, _valid_refract_error

    payload = RefractError("targets_unavailable", "open", "wait", 8).to_payload()
    assert payload["retry_after_s"] == 8
    assert _valid_refract_error(payload) == payload
    assert _valid_refract_error({**payload, "retry_after_s": True}) is None
    assert _valid_refract_error({"code": "invalid_request", "message": "x", "next_action": "x", "retry_after_s": 8}) is None


def test_server_import_does_not_load_daemon_config(tmp_path) -> None:
    env = os.environ.copy()
    env["REFRACT_HOME"] = str(tmp_path / "missing-home")
    completed = subprocess.run(
        [sys.executable, "-c", "import refract.server"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_serve_uses_configured_transport(tmp_path, monkeypatch) -> None:
    from refract import cli, server
    import uvicorn

    home = tmp_path / "refract"
    home.mkdir()
    (home / "config.toml").write_text(_serve_config("127.0.0.2", 9123), encoding="utf-8")
    monkeypatch.setenv("REFRACT_HOME", str(home))
    captured: dict[str, object] = {}

    application = SimpleNamespace(state=SimpleNamespace(refract_dashboard=SimpleNamespace()))

    def fake_application(config, *, host: str, port: int, logging_overrides) -> SimpleNamespace:
        captured["application_host"] = host
        captured["application_port"] = port
        return application

    monkeypatch.setattr(server, "create_application", fake_application)

    def fake_run(self) -> None:
        self.started = True
        captured["application"] = self.config.app
        captured["host"] = self.config.host
        captured["port"] = self.config.port

    monkeypatch.setattr(uvicorn.Server, "run", fake_run)
    cli.main(["serve"])

    assert captured == {
        "application": application,
        "application_host": "127.0.0.2",
        "application_port": 9123,
        "host": "127.0.0.2",
        "port": 9123,
    }


def test_serve_cli_transport_overrides_config(tmp_path, monkeypatch) -> None:
    from refract import cli, server
    import uvicorn

    home = tmp_path / "refract"
    home.mkdir()
    (home / "config.toml").write_text(_serve_config("127.0.0.2", 9123), encoding="utf-8")
    monkeypatch.setenv("REFRACT_HOME", str(home))
    captured: dict[str, object] = {}

    application = SimpleNamespace(state=SimpleNamespace(refract_dashboard=SimpleNamespace()))

    def fake_application(config, *, host: str, port: int, logging_overrides) -> SimpleNamespace:
        captured["application_host"] = host
        captured["application_port"] = port
        return application

    monkeypatch.setattr(server, "create_application", fake_application)

    def fake_run(self) -> None:
        self.started = True
        captured["application"] = self.config.app
        captured["host"] = self.config.host
        captured["port"] = self.config.port

    monkeypatch.setattr(uvicorn.Server, "run", fake_run)
    cli.main(["serve", "--host", "127.0.0.3", "--port", "9234"])

    assert captured == {
        "application": application,
        "application_host": "127.0.0.3",
        "application_port": 9234,
        "host": "127.0.0.3",
        "port": 9234,
    }


def test_serve_refuses_non_loopback_host_without_opt_in(tmp_path, monkeypatch, capsys) -> None:
    from refract import cli, server
    import uvicorn

    home = tmp_path / "refract"
    home.mkdir()
    (home / "config.toml").write_text(_serve_config("0.0.0.0", 9123), encoding="utf-8")
    monkeypatch.setenv("REFRACT_HOME", str(home))
    launched: list[str] = []
    application = SimpleNamespace(state=SimpleNamespace(refract_dashboard=SimpleNamespace()))
    monkeypatch.setattr(server, "create_application", lambda config, *, host, port, logging_overrides: application)
    def fake_run(self) -> None:
        self.started = True
        launched.append(self.config.host)

    monkeypatch.setattr(uvicorn.Server, "run", fake_run)

    with pytest.raises(SystemExit) as refused:
        cli.main(["serve"])
    assert refused.value.code == 2
    assert "--allow-remote" in capsys.readouterr().err
    assert launched == []

    cli.main(["serve", "--allow-remote"])
    cli.main(["serve", "--host", "::1"])
    cli.main(["serve", "--host", "localhost"])
    assert launched == ["0.0.0.0", "::1", "localhost"]


@pytest.mark.asyncio
async def test_tool_schema_limits_and_annotations_are_v3() -> None:
    tools = {tool.name: tool for tool in await mcp.list_tools()}
    assert set(tools) == {
        "submit", "wait", "answer", "cancel", "retry", "list", "card_create", "card_move", "card_list",
    }
    from refract.workflows import BUILTIN_WORKFLOWS

    assert tools["submit"].input_schema["properties"]["workflow"]["enum"] == list(BUILTIN_WORKFLOWS)
    assert tools["wait"].input_schema["properties"]["timeout_s"]["minimum"] == 0
    assert tools["wait"].input_schema["properties"]["timeout_s"]["maximum"] == 3600
    assert tools["submit"].input_schema["properties"]["fresh"]["default"] is False
    assert tools["answer"].input_schema["properties"]["answer"]["maxLength"] == 8192
    assert tools["cancel"].annotations is not None
    assert tools["cancel"].annotations.idempotent_hint is True
    assert tools["wait"].annotations.read_only_hint is True
    assert tools["submit"].annotations.destructive_hint is True
    assert tools["retry"].annotations.idempotent_hint is False
    expected_annotations = {
        "submit": (False, True, False, True),
        "wait": (True, False, True, False),
        "answer": (False, False, False, False),
        "cancel": (False, True, True, False),
        "retry": (False, True, False, True),
        "list": (True, False, True, False),
        "card_create": (False, False, False, False),
        "card_move": (False, True, True, False),
        "card_list": (True, False, True, False),
    }
    for name, expected_hints in expected_annotations.items():
        annotations = tools[name].annotations
        assert annotations is not None
        actual_hints = (
            annotations.read_only_hint, annotations.destructive_hint,
            annotations.idempotent_hint, annotations.open_world_hint,
        )
        assert actual_hints == expected_hints
        assert annotations.title == tools[name].title
        assert all(prop.get("description") for prop in tools[name].input_schema["properties"].values())
    assert set(JobSummary.model_fields) == {
        "id", "project", "workflow", "profile", "target", "session", "state", "retry_of", "created_at", "updated_at",
    }
    assert "resource_uri" not in SubmissionResult.model_fields


@pytest.mark.asyncio
async def test_inprocess_client_receives_compact_json_errors(tmp_path, monkeypatch) -> None:
    async with _connected_client(tmp_path, monkeypatch) as (client, _runtime):
        malformed = await client.call_tool(
            "wait", {"job_id": "job", "timeout_s": -1}
        )
        assert malformed.is_error
        malformed_payload = json.loads(malformed.content[0].text)
        assert set(malformed_payload) == {"code", "message", "next_action"}
        assert malformed_payload["code"] == "invalid_request"
        assert malformed_payload["next_action"]

        unknown = await client.call_tool(
            "wait", {"job_id": "missing-job", "timeout_s": 0}
        )
        assert unknown.is_error
        unknown_payload = json.loads(unknown.content[0].text)
        assert unknown_payload["code"] == "unknown_job"
        assert unknown_payload["next_action"]


@pytest.mark.asyncio
async def test_inprocess_client_sanitizes_unexpected_tool_exception(tmp_path, monkeypatch) -> None:
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        root = tmp_path / "internal-error-project"
        root.mkdir()
        git(root, "init", "-q")
        secret = "provider-secret-that-must-not-escape"

        def fail_listing(_project_id: str):
            raise RuntimeError(secret)

        runtime.database.job_overview = fail_listing
        response = await client.call_tool("list", {"path": str(root)})

        assert response.is_error
        payload = json.loads(response.content[0].text)
        assert payload["code"] == "internal_error"
        assert payload["next_action"]
        assert "Request ID:" in payload["message"]
        assert payload["message"].split("Request ID:", 1)[1].strip().rstrip(".")
        assert secret not in response.content[0].text
        assert "Traceback" not in response.content[0].text


@pytest.mark.asyncio
async def test_list_guidance_overflow_returns_actionable_error(tmp_path, monkeypatch) -> None:
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        root = tmp_path / "guide-project"
        root.mkdir()
        git(root, "init", "-q")
        (runtime.config.home / "task_guide.json").write_text(
            json.dumps({"guidance": "g" * 12000}), encoding="utf-8"
        )
        result = await client.call_tool("list", {"path": str(root)})

        assert result.is_error
        payload = json.loads(result.content[0].text)
        assert payload["code"] == "response_too_large"
        assert payload["next_action"]
        wire = json.dumps(result.model_dump(by_alias=True, mode="json", exclude_none=True), separators=(",", ":"))
        assert len(wire.encode("utf-8")) < 9000


@pytest.mark.asyncio
async def test_mcp_client_completes_v3_cycle_in_three_calls(tmp_path, monkeypatch) -> None:
    from tests.orchestration_helpers import FakeDrivers, repository

    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        root = repository(tmp_path)
        guide_path = runtime.config.home / "task_guide.json"
        guide_path.write_text(json.dumps({"guidance": []}), encoding="utf-8")
        runtime.drivers = FakeDrivers()

        listed = await client.call_tool("list", {"path": str(root)})
        assert json.loads(listed.content[0].text)["profiles"]["default"] == "balanced"
        submitted = await client.call_tool(
            "submit",
            {"path": str(root), "workflow": "consult", "prompt": "inspect"},
        )
        job_id = json.loads(submitted.content[0].text)["job"]["id"]
        waited = await client.call_tool("wait", {"job_id": job_id, "timeout_s": 5})
        result = json.loads(waited.content[0].text)
        assert result["job"]["state"] == "succeeded"
        assert result["result"]["text"] == "response from primary"


@pytest.mark.asyncio
async def test_actual_client_rejects_sdk_coercions_before_dispatch(tmp_path, monkeypatch) -> None:
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        root = tmp_path / "coercion-project"
        root.mkdir()
        git(root, "init", "-q")
        project = register_project(runtime, str(root))
        before = runtime.database.jobs(project.id)
        invalid_calls = [
            ("wait", {"job_id": "missing", "timeout_s": True}),
            ("wait", {"job_id": "missing", "timeout_s": "0"}),
            ("submit", {"path": str(root), "workflow": "implement", "prompt": "must not queue", "fresh": 1}),
            ("submit", {"path": str(root), "workflow": "implement", "prompt": "must not queue", "fresh": "false"}),
        ]
        for name, arguments in invalid_calls:
            response = await client.call_tool(name, arguments)
            payload = json.loads(response.content[0].text)
            assert response.is_error
            assert payload["code"] == "invalid_request"
            assert "schema" in payload["next_action"].lower()
        assert runtime.database.jobs(project.id) == before


@pytest.mark.asyncio
async def test_expected_runtime_error_families_are_compact_json(tmp_path, monkeypatch) -> None:
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        root = tmp_path / "errors-project"
        root.mkdir()
        git(root, "init", "-q")
        project = register_project(runtime, str(root))

        forbidden = {"target_id", "backend", "model", "resource_uri", "config_revision"}

        def assert_private(value):
            if isinstance(value, dict):
                assert forbidden.isdisjoint(key.casefold() for key in value)
                for item in value.values():
                    assert_private(item)
            elif isinstance(value, list):
                for item in value:
                    assert_private(item)

        async def check(name, arguments, code):
            response = await client.call_tool(name, arguments)
            assert response.is_error
            payload = json.loads(response.content[0].text)
            assert set(payload) == {"code", "message", "next_action"}
            assert payload["code"] == code
            assert payload["next_action"]
            assert_private(payload)
            assert len(response.content) == 1
            assert response.content[0].type == "text"
            wire = json.dumps(response.model_dump(by_alias=True, mode="json", exclude_none=True), separators=(",", ":"))
            assert len(wire) < 30000
            assert len(wire.encode("utf-8")) < 9000
            return payload

        await check("list", {"path": str(root / "missing")}, "invalid_path")
        await check("wait", {"job_id": "missing-job", "timeout_s": 0}, "unknown_job")
        await check("cancel", {"job_id": "missing-job"}, "unknown_job")
        await check("submit", {"path": str(root), "workflow": "implement", "prompt": "x", "profile": "missing-profile"}, "unknown_profile")

        runtime.database.create_job(
            job_id="failed-parent", project_id=project.id, workflow="review", profile="balanced",
            prompt="parent", execution_plan_json="{}", session="parent",
        )
        runtime.database.finish_job("failed-parent", "failed")
        await check("retry", {"job_id": "missing-job"}, "unknown_job")

        runtime.database.create_job(
            job_id="queued-invalid-retry", project_id=project.id, workflow="review", profile="balanced",
            prompt="queued", execution_plan_json="{}", session="queued",
        )
        await check("retry", {"job_id": "queued-invalid-retry"}, "invalid_state")
        (runtime.config.home / "task_guide.json").write_text("{invalid", encoding="utf-8")
        await check("list", {"path": str(root)}, "config_invalid")
        (runtime.config.home / "task_guide.json").write_text(json.dumps({"guidance": "g" * 12000}), encoding="utf-8")
        await check("list", {"path": str(root)}, "response_too_large")

        runtime._closing = True
        await check("submit", {"path": str(root), "workflow": "implement", "prompt": "stopping"}, "daemon_stopping")
        runtime._closing = False


@pytest.mark.asyncio
async def test_mcp_submit_all_open_returns_retry_delay(tmp_path, monkeypatch) -> None:
    from refract.planning import target_execution_key

    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        root = tmp_path / "submit-all-open"
        root.mkdir()
        git(root, "init", "-q")
        project = register_project(runtime, str(root))
        target = runtime.catalog.targets[0]
        runtime.database._connection.execute(
            "INSERT OR REPLACE INTO target_health(target_id, consecutive_failures, circuit_open_until, cooldown_s, probe_job_id) VALUES (?, 1, '2999-01-01T00:00:00+00:00', 60, '')",
            (target_execution_key(target),),
        )
        runtime.database._connection.commit()
        response = await client.call_tool("submit", {"path": str(root), "workflow": "consult", "prompt": "blocked"})
        assert response.is_error
        payload = json.loads(response.content[0].text)
        assert payload["code"] == "targets_unavailable"
        assert type(payload["retry_after_s"]) is int
        assert runtime.database.jobs(project.id) == []


@pytest.mark.asyncio
async def test_all_tool_success_payloads_are_private_and_single_text_content(tmp_path, monkeypatch) -> None:
    from tests.orchestration_helpers import FakeDrivers

    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        root = tmp_path / "privacy-project"
        root.mkdir()
        git(root, "init", "-q")
        project = register_project(runtime, str(root))
        responses = []
        (runtime.config.home / "task_guide.json").write_text(json.dumps({"guidance": []}), encoding="utf-8")
        responses.append(await client.call_tool("list", {"path": str(root)}))
        runtime.drivers = FakeDrivers()
        submitted = await client.call_tool("submit", {"path": str(root), "workflow": "consult", "prompt": "inspect"})
        responses.append(submitted)
        submitted_id = json.loads(submitted.content[0].text)["job"]["id"]
        responses.append(await client.call_tool("wait", {"job_id": submitted_id, "timeout_s": 5}))
        responses.append(await client.call_tool("list", {"path": str(root)}))
        runtime.database.create_job(
            job_id="privacy-cancel", project_id=project.id, workflow="review", profile="balanced",
            prompt="cancel", execution_plan_json="{}", session="cancel",
        )
        responses.append(await client.call_tool("cancel", {"job_id": "privacy-cancel"}))
        runtime.database.create_job(
            job_id="privacy-retry", project_id=project.id, workflow="review", profile="balanced",
            prompt="retry", execution_plan_json="{}", session="retry",
        )
        runtime.database.finish_job("privacy-retry", "failed")
        responses.append(await client.call_tool("retry", {"job_id": "privacy-retry"}))

        forbidden = {"access_mode", "target_id", "backend", "resource_uri", "config_revision"}
        def visit(value):
            if isinstance(value, dict):
                assert forbidden.isdisjoint(key.casefold() for key in value)
                for item in value.values():
                    visit(item)
            elif isinstance(value, list):
                for item in value:
                    visit(item)
        for response in responses:
            assert not response.is_error
            assert len(response.content) == 1
            assert response.content[0].type == "text"
            wire = response.model_dump(by_alias=True, mode="json", exclude_none=True)
            assert "structuredContent" not in wire
            visit(json.loads(response.content[0].text))


@pytest.mark.asyncio
async def test_submit_retry_cancel_overflow_reports_applied_root_ids(tmp_path, monkeypatch) -> None:
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        root = tmp_path / "mutation-overflow"
        root.mkdir()
        git(root, "init", "-q")
        project = register_project(runtime, str(root))

        submitted = await client.call_tool("submit", {
            "path": str(root), "workflow": "implement", "prompt": "submit",
            "session": "s" * 10000,
        })
        assert submitted.is_error
        submit_error = json.loads(submitted.content[0].text)
        submitted_id = submit_error["message"].split("ID: ", 1)[1].rstrip(".")
        assert submit_error["code"] == "response_too_large"
        assert "applied" in submit_error["message"]
        assert runtime.database.job(submitted_id) is not None

        runtime.database.create_job(
            job_id="retry-overflow", project_id=project.id, workflow="review", profile="balanced",
            prompt="retry", execution_plan_json="{}", session="r" * 10000,
        )
        runtime.database.finish_job("retry-overflow", "failed")
        retried = await client.call_tool("retry", {"job_id": "retry-overflow"})
        assert retried.is_error
        retry_error = json.loads(retried.content[0].text)
        retried_id = retry_error["message"].split("ID: ", 1)[1].rstrip(".")
        assert retry_error["code"] == "response_too_large"
        assert "applied" in retry_error["message"]
        assert runtime.database.job(retried_id).retry_of == "retry-overflow"
        assert runtime.database.job("retry-overflow").state == "failed"

        runtime.database.create_job(
            job_id="cancel-overflow", project_id=project.id, workflow="review", profile="balanced",
            prompt="cancel", execution_plan_json="{}", session="c" * 10000,
        )
        cancelled = await client.call_tool("cancel", {"job_id": "cancel-overflow"})
        assert cancelled.is_error
        cancel_error = json.loads(cancelled.content[0].text)
        assert cancel_error["code"] == "response_too_large"
        assert "cancel-overflow" in cancel_error["message"]
        assert "applied" in cancel_error["message"]
        assert runtime.database.job("cancel-overflow").state == "cancelled"




@pytest.mark.asyncio
async def test_failed_driver_diagnostic_is_private_but_remains_in_operator_record(tmp_path, monkeypatch) -> None:
    from refract.drivers import DriverResult

    marker = "provider-secret-model-backend-detail-" + "private-diagnostic-" * 700

    class PrivateFailureDrivers:
        @staticmethod
        async def supports_structured_streaming(_target, cancel_event=None):
            return True

        @staticmethod
        def available(_target):
            return True

        async def execute(self, **_kwargs):
            return DriverResult("TARGET_FATAL", "", "", marker, "backend_failure")

    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        root = tmp_path / "private-failure-project"
        root.mkdir()
        git(root, "init", "-q")
        runtime.drivers = PrivateFailureDrivers()
        submitted = await client.call_tool("submit", {
            "path": str(root), "workflow": "implement", "prompt": "fail safely",
        })
        job_id = json.loads(submitted.content[0].text)["job"]["id"]
        response = await client.call_tool("wait", {"job_id": job_id, "timeout_s": 10})
        assert not response.is_error
        payload = json.loads(response.content[0].text)
        assert payload["result"]["failure_kind"] == "target_fatal"
        assert marker not in response.content[0].text
        assert "provider-secret-model-backend-detail" not in response.content[0].text
        envelope = json.dumps(response.model_dump(by_alias=True, mode="json", exclude_none=True), separators=(",", ":"))
        assert len(envelope) < 30000
        assert len(envelope.encode("utf-8")) < 9000
        stored = runtime.database.job(job_id)
        assert stored is not None
        assert stored.result.error == marker




def _job_view(state: str) -> JobView:
    return JobView(
        id="job-1",
        project_id="project-1",
        workflow="implement",
        profile="balanced",
        state=state,
        session="implement",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )


def _stub_project(_project_id: str) -> None:
    return None


def _stub_result_path(job_id: str) -> str:
    return f"{job_id}.md"


_STUB_ASK_REGISTRY = SimpleNamespace(get_pending=lambda _job_id: None)


def test_wait_constants() -> None:
    from refract import server

    assert server._MCP_WAIT_TIMEOUT_S == 3600
    assert server._MCP_HEARTBEAT_INTERVAL_S == 30


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout_s", [0, 5, 30, 3600])
async def test_wait_uses_timeout_and_returns_result_shape(timeout_s: int) -> None:
    initial = _job_view("running")
    latest = _job_view("succeeded")
    waits: list[tuple[str, int]] = []
    state = {"job": initial}

    class Database:
        def job(self, job_id: str) -> JobView:
            assert job_id == initial.id
            return state["job"]

        project = staticmethod(_stub_project)
        result_path = staticmethod(_stub_result_path)

    class Runtime:
        database = Database()
        ask_registry = _STUB_ASK_REGISTRY

        def live_routing(self, job: JobView):
            return job.result.metadata

        async def wait(self, job_id: str, timeout_s: int) -> JobView:
            waits.append((job_id, timeout_s))
            state["job"] = latest
            return latest

    progress_messages: list[str] = []

    async def report_progress(*, progress: float, total: float | None, message: str) -> None:
        progress_messages.append(message)

    ctx = SimpleNamespace(
        request_context=SimpleNamespace(lifespan_context=Runtime()),
        report_progress=report_progress,
    )
    result = json.loads(await wait(initial.id, ctx, timeout_s=timeout_s))

    assert waits == ([] if timeout_s == 0 else [(initial.id, timeout_s)])
    assert result["job"]["state"] == ("running" if timeout_s == 0 else "succeeded")
    assert result["result"]["text"] == ""
    assert result["result"]["truncated"] is False
    assert result["result"]["pending_question"] is None
    assert json.loads(progress_messages[0]) == {"state": "running"}


@pytest.mark.asyncio
async def test_wait_heartbeat_loop_reports_progress_until_terminal(monkeypatch) -> None:
    from refract import server

    monkeypatch.setattr(server, "_MCP_HEARTBEAT_INTERVAL_S", 0.005)
    current_job = _job_view("running")
    done_event = asyncio.Event()
    progress_reports: list[tuple[float, float | None, str]] = []

    class Database:
        def job(self, job_id: str) -> JobView:
            assert job_id == current_job.id
            return current_job

        project = staticmethod(_stub_project)
        result_path = staticmethod(_stub_result_path)

    class Runtime:
        database = Database()
        ask_registry = _STUB_ASK_REGISTRY

        def live_routing(self, job: JobView):
            return job.result.metadata

        async def wait(self, job_id: str, timeout_s: int) -> JobView:
            await done_event.wait()
            return current_job

    async def report_progress(*, progress: float, total: float | None, message: str) -> None:
        progress_reports.append((progress, total, message))
        if len(progress_reports) == 3:
            current_job.state = "succeeded"
            done_event.set()

    ctx = SimpleNamespace(
        request_context=SimpleNamespace(lifespan_context=Runtime()),
        report_progress=report_progress,
    )

    result = json.loads(await wait(current_job.id, ctx, timeout_s=3600))
    assert result["job"]["state"] == "succeeded"
    assert [report[:2] for report in progress_reports] == [
        (0.0, None),
        (1.0, None),
        (2.0, None),
    ]
    assert all(json.loads(message) == {"state": "running"} for _, _, message in progress_reports)


@pytest.mark.asyncio
async def test_wait_rejects_negative_timeout_before_job_lookup(tmp_path, monkeypatch) -> None:
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        def unexpected_lookup(job_id):
            raise AssertionError("job lookup should not happen")

        monkeypatch.setattr(runtime.database, "job", unexpected_lookup)
        result = await client.call_tool("wait", {"job_id": "job-1", "timeout_s": -1})
        assert result.is_error
        assert json.loads(result.content[0].text)["code"] == "invalid_request"


@pytest.mark.asyncio
async def test_wait_non_terminal_timeout(monkeypatch) -> None:
    from refract import server

    monkeypatch.setattr(server, "_MCP_HEARTBEAT_INTERVAL_S", 0.005)
    current_job = _job_view("running")
    progress_messages: list[str] = []
    timeout_event = asyncio.Event()

    class Database:
        def job(self, job_id: str) -> JobView:
            assert job_id == current_job.id
            return current_job

        project = staticmethod(_stub_project)
        result_path = staticmethod(_stub_result_path)

    class Runtime:
        database = Database()
        ask_registry = _STUB_ASK_REGISTRY

        def live_routing(self, job: JobView):
            return job.result.metadata

        async def wait(self, job_id: str, timeout_s: int) -> JobView:
            await timeout_event.wait()
            return current_job

    async def report_progress(*, progress: float, total: float, message: str) -> None:
        progress_messages.append(message)
        if len(progress_messages) == 3:
            timeout_event.set()

    ctx = SimpleNamespace(
        request_context=SimpleNamespace(lifespan_context=Runtime()),
        report_progress=report_progress,
    )

    result = json.loads(await wait(current_job.id, ctx, timeout_s=10))
    assert result["job"]["state"] == "running"
    assert result["result"]["text"] == ""
    assert len(progress_messages) == 3


@pytest.mark.asyncio
async def test_wait_cancellation_cleanup() -> None:
    current_job = _job_view("running")
    wait_started = asyncio.Event()
    wait_cancelled = asyncio.Event()

    class Database:
        def job(self, job_id: str) -> JobView:
            assert job_id == current_job.id
            return current_job

        project = staticmethod(_stub_project)
        result_path = staticmethod(_stub_result_path)

    class Runtime:
        database = Database()
        ask_registry = _STUB_ASK_REGISTRY

        def live_routing(self, job: JobView):
            return job.result.metadata

        async def wait(self, job_id: str, timeout_s: int) -> JobView:
            wait_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                wait_cancelled.set()
                raise

    ctx = SimpleNamespace(
        request_context=SimpleNamespace(lifespan_context=Runtime()),
        report_progress=lambda **kwargs: asyncio.sleep(0),
    )

    task = asyncio.create_task(wait(current_job.id, ctx, timeout_s=3600))
    await wait_started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert wait_cancelled.is_set()


@pytest.mark.asyncio
async def test_wait_propagates_cancellation_during_child_cleanup(monkeypatch) -> None:
    from refract import server

    monkeypatch.setattr(server, "_MCP_HEARTBEAT_INTERVAL_S", 0.005)
    current_job = _job_view("running")
    cleanup_started = asyncio.Event()

    class Database:
        def job(self, job_id: str) -> JobView:
            return current_job

        project = staticmethod(_stub_project)
        result_path = staticmethod(_stub_result_path)

    class Runtime:
        database = Database()
        ask_registry = _STUB_ASK_REGISTRY

        def live_routing(self, job: JobView):
            return job.result.metadata

        async def wait(self, job_id: str, timeout_s: int) -> JobView:
            current_job.state = "succeeded"
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cleanup_started.set()
                await asyncio.Event().wait()
                raise

    ctx = SimpleNamespace(
        request_context=SimpleNamespace(lifespan_context=Runtime()),
        report_progress=lambda **kwargs: asyncio.sleep(0),
    )
    task = asyncio.create_task(wait(current_job.id, ctx, timeout_s=3600))
    try:
        await asyncio.wait_for(cleanup_started.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_wait_response_truncates_long_text_and_keeps_result_path() -> None:
    from refract import server
    from refract.models import JobResult

    terminal = _job_view("succeeded").model_copy(update={"result": JobResult(text="x" * 200_000)})

    class Database:
        project = staticmethod(_stub_project)
        result_path = staticmethod(_stub_result_path)

    class Runtime:
        database = Database()
        ask_registry = _STUB_ASK_REGISTRY

    payload = json.loads(await server._wait_response(Runtime(), terminal))
    assert payload["result"]["truncated"] is True
    assert 0 < len(payload["result"]["text"]) < 200_000
    assert payload["result"]["result_path"] == "job-1.md"


@pytest.mark.asyncio
async def test_wait_returns_terminal_job_without_waiting() -> None:
    terminal = _job_view("failed")
    waits: list[str] = []
    progress_messages: list[str] = []

    class Database:
        @staticmethod
        def job(job_id: str) -> JobView:
            return terminal

        project = staticmethod(_stub_project)
        result_path = staticmethod(_stub_result_path)

    class Runtime:
        database = Database()
        ask_registry = _STUB_ASK_REGISTRY

        def live_routing(self, job: JobView):
            return job.result.metadata

        def _next_target(self, _job: JobView) -> None:
            return None

        async def wait(self, job_id: str, timeout_s: int) -> JobView:
            waits.append(job_id)
            return terminal

    async def report_progress(*, progress: float, total: float, message: str) -> None:
        progress_messages.append(message)

    ctx = SimpleNamespace(
        request_context=SimpleNamespace(lifespan_context=Runtime()),
        report_progress=report_progress,
    )

    result = json.loads(await wait(terminal.id, ctx))
    assert result["job"]["state"] == "failed"
    assert waits == []
    assert json.loads(progress_messages[0]) == {"state": "failed"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("wire_meta", "expected_present"),
    [
        ({"progressToken": "secret-token-123"}, True),
        ({"progressToken": ""}, True),
        ({"progressToken": 0}, True),
        ({"progressToken": 12}, True),
        ({"progressToken": True}, False),
        ({"progressToken": False}, False),
        ({"progressToken": 1.5}, False),
        ({"progress_token": "secret-token-456"}, False),
        ({}, False),
        (None, False),
    ],
)
async def test_wait_logs_progress_token_presence(caplog, wire_meta, expected_present) -> None:
    import logging
    from mcp.server.runner import _extract_meta

    terminal = _job_view("succeeded")

    class Database:
        @staticmethod
        def job(job_id: str) -> JobView:
            return terminal

        project = staticmethod(_stub_project)
        result_path = staticmethod(_stub_result_path)

    class Runtime:
        database = Database()
        ask_registry = _STUB_ASK_REGISTRY

        def live_routing(self, job: JobView):
            return job.result.metadata

    params = {"_meta": wire_meta} if wire_meta is not None else {}
    sdk_meta = _extract_meta(params)
    if wire_meta and "progressToken" in wire_meta:
        if type(wire_meta["progressToken"]) is bool:
            assert sdk_meta == {"progress_token": int(wire_meta["progressToken"])}
        elif type(wire_meta["progressToken"]) is float:
            assert sdk_meta is None
        else:
            assert sdk_meta == {"progress_token": wire_meta["progressToken"]}
    if wire_meta and "progress_token" in wire_meta:
        assert sdk_meta == {"progress_token": wire_meta["progress_token"]}
    ctx = SimpleNamespace(
        request_context=SimpleNamespace(
            lifespan_context=Runtime(),
            meta=sdk_meta,
            params=params,
        ),
        report_progress=lambda **kwargs: asyncio.sleep(0),
    )

    with caplog.at_level(logging.INFO, logger="refract.server"):
        result = json.loads(await wait(terminal.id, ctx))

    assert result["job"]["state"] == "succeeded"
    records = [
        record
        for record in caplog.records
        if getattr(record, "operation", "") == "wait"
    ]
    assert len(records) >= 2  # started and finished
    for record in records:
        assert getattr(record, "progress_token_present", None) is expected_present
        # Verify the secret token value is NEVER logged anywhere
        assert "secret-token-123" not in record.getMessage()
        assert "secret-token-123" not in str(record.__dict__)
        assert "secret-token-456" not in record.getMessage()
        assert "secret-token-456" not in str(record.__dict__)


@pytest.mark.asyncio
async def test_application_lifespan_shares_runtime_across_sessions(monkeypatch) -> None:
    import refract.server as server

    config = SimpleNamespace(logging=object())
    events: list[str] = []

    class Runtime:
        def __init__(self, received_config) -> None:
            assert received_config is config
            events.append("runtime.create")

        async def start(self) -> None:
            events.append("runtime.start")

        async def close(self) -> None:
            events.append("runtime.close")

    monkeypatch.setattr(server, "Runtime", Runtime)
    monkeypatch.setattr(server, "configure_logging", lambda _: None)
    application = server.create_application(config)
    async with application.router.lifespan_context(application):
        assert events == ["runtime.create", "runtime.start"]
        assert application.state.runtime is application.state.refract_dashboard.runtime
    assert events == ["runtime.create", "runtime.start", "runtime.close"]
    assert application.state.refract_dashboard.runtime is None
    assert application.state.runtime is None


@pytest.mark.asyncio
async def test_application_lifespan_cleans_up_after_start_failure(monkeypatch) -> None:
    import refract.server as server

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

    monkeypatch.setattr(server, "configure_logging", lambda _: None)
    monkeypatch.setattr(server, "Runtime", FailingRuntime)
    application = server.create_application(config)
    with pytest.raises(RuntimeError, match="start failed"):
        async with application.router.lifespan_context(application):
            pass
    assert events == ["runtime.start", "runtime.close"]
    assert application.state.refract_dashboard.runtime is None
    assert application.state.runtime is None


@pytest.mark.asyncio
async def test_application_lifespan_clears_state_when_runtime_close_fails(monkeypatch) -> None:
    import refract.server as server

    config = SimpleNamespace(logging=object())

    class FailingRuntime:
        def __init__(self, received_config) -> None:
            assert received_config is config

        async def start(self) -> None:
            return None

        async def close(self) -> None:
            raise RuntimeError("close failed")

    monkeypatch.setattr(server, "configure_logging", lambda _: None)
    monkeypatch.setattr(server, "Runtime", FailingRuntime)
    application = server.create_application(config)
    with pytest.raises(RuntimeError, match="close failed"):
        async with application.router.lifespan_context(application):
            pass
    assert application.state.refract_dashboard.runtime is None
    assert application.state.runtime is None


@pytest.mark.asyncio
async def test_runtime_wait_and_wait_tool_wake_early_with_pending_question(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    config_path = home / "config.toml"
    config_path.write_text(_serve_config(), encoding="utf-8")
    runtime = Runtime(load_config(config_path))
    try:
        project = register_project(runtime, str(tmp_path))
        runtime.database.create_job(
            job_id="job-q-1",
            project_id=project.id,
            workflow="consult",
            profile="balanced",
            prompt="Do work",
            execution_plan_json="{}",
            session="c1",
        )
        with runtime.database._connection:
            runtime.database._connection.execute("UPDATE jobs SET state='running' WHERE id='job-q-1'")
        runtime.scheduler._current["job-q-1"] = _Dispatch(job_id="job-q-1")
        token = runtime.ask_registry.issue_token("job-q-1")

        # 1. Test Runtime.wait wakes early when question is asked
        async def _ask_later():
            await asyncio.sleep(0.05)
            return await runtime.ask_registry.ask(token, "Need input on schema", timeout_s=5.0)

        task = asyncio.create_task(_ask_later())

        start = asyncio.get_running_loop().time()
        job = await runtime.wait("job-q-1", timeout_s=10)
        elapsed = asyncio.get_running_loop().time() - start

        assert elapsed < 3.0
        assert job.state == "running"
        assert runtime.ask_registry.has_pending("job-q-1")

        # 2. Test wait returns pending_question
        ctx = SimpleNamespace(
            request_context=SimpleNamespace(lifespan_context=runtime),
            report_progress=lambda **kwargs: asyncio.sleep(0),
        )
        res_str = await wait("job-q-1", ctx, timeout_s=10)
        res = json.loads(res_str)
        assert res["job"]["state"] == "running"
        assert "pending_question" in res["result"]
        pq = res["result"]["pending_question"]
        assert pq["text"] == "Need input on schema"
        assert pq["question_id"].startswith("q_")

        # 3. Test answer delivers answer
        ans_str = await answer("job-q-1", "Use v2 schema", ctx)
        ans = json.loads(ans_str)
        assert ans["job"]["id"] == "job-q-1"
        assert not runtime.ask_registry.has_pending("job-q-1")

        # HTTP ask receives answer
        asked_result = await task
        assert asked_result == "Use v2 schema"
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_answer_errors(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    config_path = home / "config.toml"
    config_path.write_text(_serve_config(), encoding="utf-8")
    runtime = Runtime(load_config(config_path))
    try:
        project = register_project(runtime, str(tmp_path))
        runtime.database.create_job(
            job_id="job-running",
            project_id=project.id,
            workflow="consult",
            profile="balanced",
            prompt="Do work",
            execution_plan_json="{}",
            session="c1",
        )
        runtime.database.create_job(
            job_id="job-succeeded",
            project_id=project.id,
            workflow="consult",
            profile="balanced",
            prompt="Do work",
            execution_plan_json="{}",
            session="c1",
        )
        with runtime.database._connection:
            runtime.database._connection.execute("UPDATE jobs SET state='running' WHERE id='job-running'")
            runtime.database._connection.execute("UPDATE jobs SET state='succeeded' WHERE id='job-succeeded'")

        ctx = SimpleNamespace(
            request_context=SimpleNamespace(lifespan_context=runtime),
            report_progress=lambda **kwargs: asyncio.sleep(0),
        )

        # 1. Unknown job -> unknown_job error
        with pytest.raises(RefractError) as exc_info:
            await answer("job-nonexistent", "ans", ctx)
        assert exc_info.value.code == "unknown_job"

        # 2. Terminal job -> invalid_state error
        with pytest.raises(RefractError) as exc_info:
            await answer("job-succeeded", "ans", ctx)
        assert exc_info.value.code == "invalid_state"

        # 3. Running job with no question pending -> invalid_state error
        with pytest.raises(RefractError) as exc_info:
            await answer("job-running", "ans", ctx)
        assert exc_info.value.code == "invalid_state"
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_wait_nonterminal_without_question(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    config_path = home / "config.toml"
    config_path.write_text(_serve_config(), encoding="utf-8")
    runtime = Runtime(load_config(config_path))
    try:
        project = register_project(runtime, str(tmp_path))
        runtime.database.create_job(
            job_id="job-running-no-q",
            project_id=project.id,
            workflow="consult",
            profile="balanced",
            prompt="Do work",
            execution_plan_json="{}",
            session="c1",
        )
        with runtime.database._connection:
            runtime.database._connection.execute("UPDATE jobs SET state='running' WHERE id='job-running-no-q'")

        ctx = SimpleNamespace(
            request_context=SimpleNamespace(lifespan_context=runtime),
            report_progress=lambda **kwargs: asyncio.sleep(0),
        )

        res_str = await wait("job-running-no-q", ctx, timeout_s=0)
        res = json.loads(res_str)
        assert res["job"]["state"] == "running"
        assert res["result"]["text"] == ""
        assert res["result"]["truncated"] is False
        assert res["result"]["pending_question"] is None
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_connected_client_answer_and_wait(tmp_path, monkeypatch) -> None:
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        project = register_project(runtime, str(tmp_path))
        runtime.database.create_job(
            job_id="job-client-test",
            project_id=project.id,
            workflow="consult",
            profile="balanced",
            prompt="Do work",
            execution_plan_json="{}",
            session="c1",
        )
        with runtime.database._connection:
            runtime.database._connection.execute("UPDATE jobs SET state='running' WHERE id='job-client-test'")
        runtime.scheduler._current["job-client-test"] = _Dispatch(job_id="job-client-test")
        token = runtime.ask_registry.issue_token("job-client-test")

        async def _ask_later():
            await asyncio.sleep(0.05)
            return await runtime.ask_registry.ask(token, "Question via client", timeout_s=5.0)

        task = asyncio.create_task(_ask_later())

        # wait wakes early
        wait_res = await client.call_tool("wait", {"job_id": "job-client-test", "timeout_s": 10})
        assert not wait_res.is_error
        wait_data = json.loads(wait_res.content[0].text)
        assert wait_data["job"]["state"] == "running"
        assert wait_data["result"]["pending_question"]["text"] == "Question via client"

        # answer delivers
        ans_res = await client.call_tool("answer", {"job_id": "job-client-test", "answer": "Answer via client"})
        assert not ans_res.is_error
        ans_data = json.loads(ans_res.content[0].text)
        assert ans_data["job"]["id"] == "job-client-test"

        asked_result = await task
        assert asked_result == "Answer via client"


@pytest.mark.asyncio
async def test_answer_bounds_and_unicode_acceptance(tmp_path, monkeypatch) -> None:
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        project = register_project(runtime, str(tmp_path))
        runtime.database.create_job(
            job_id="job-bounds-test",
            project_id=project.id,
            workflow="consult",
            profile="balanced",
            prompt="Do work",
            execution_plan_json="{}",
            session="c1",
        )
        with runtime.database._connection:
            runtime.database._connection.execute("UPDATE jobs SET state='running' WHERE id='job-bounds-test'")
        runtime.scheduler._current["job-bounds-test"] = _Dispatch(job_id="job-bounds-test")
        token = runtime.ask_registry.issue_token("job-bounds-test")

        ask_task = asyncio.create_task(runtime.ask_registry.ask(token, "Question?", timeout_s=10.0))
        await asyncio.sleep(0.02)
        assert runtime.ask_registry.has_pending("job-bounds-test")

        # 1. Direct Runtime.job_answer rejects answer > 8192 chars with invalid_request
        oversized = "x" * 8193
        with pytest.raises(OrchestrationError) as exc_info:
            await runtime.job_answer("job-bounds-test", oversized)
        assert exc_info.value.code == "invalid_request"
        # Preserves pending question on rejection
        assert runtime.ask_registry.has_pending("job-bounds-test")

        # 2. MCP client rejection for answer > 8192 chars
        mcp_res = await client.call_tool("answer", {"job_id": "job-bounds-test", "answer": oversized})
        assert mcp_res.is_error
        err_payload = json.loads(mcp_res.content[0].text)
        assert err_payload["code"] == "invalid_request"
        # Preserves pending question on rejection
        assert runtime.ask_registry.has_pending("job-bounds-test")

        # 3. Accepted Unicode boundary answer delivered exactly
        unicode_answer = "Accepted: 🚀 Café ñ 日本語 " + ("A" * 100)
        await runtime.job_answer("job-bounds-test", unicode_answer)
        assert not runtime.ask_registry.has_pending("job-bounds-test")
        delivered = await ask_task
        assert delivered == unicode_answer


@pytest.mark.asyncio
async def test_wait_oversized_pending_question_raises_response_too_large(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    config_path = home / "config.toml"
    config_path.write_text(_serve_config(), encoding="utf-8")
    runtime = Runtime(load_config(config_path))
    try:
        project = register_project(runtime, str(tmp_path))
        runtime.database.create_job(
            job_id="job-oversized-q",
            project_id=project.id,
            workflow="consult",
            profile="balanced",
            prompt="Do work",
            execution_plan_json="{}",
            session="c1",
        )
        with runtime.database._connection:
            runtime.database._connection.execute("UPDATE jobs SET state='running' WHERE id='job-oversized-q'")
        runtime.scheduler._current["job-oversized-q"] = _Dispatch(job_id="job-oversized-q")
        token = runtime.ask_registry.issue_token("job-oversized-q")

        # Pending question that exceeds envelope char limit
        huge_text = "q" * 35000
        asyncio.create_task(runtime.ask_registry.ask(token, huge_text, timeout_s=5.0))
        await asyncio.sleep(0.02)

        ctx = SimpleNamespace(
            request_context=SimpleNamespace(lifespan_context=runtime),
            report_progress=lambda **kwargs: asyncio.sleep(0),
        )
        with pytest.raises(RefractError) as exc_info:
            await wait("job-oversized-q", ctx, timeout_s=0)
        assert exc_info.value.code == "response_too_large"
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_real_asgi_ask_and_mcp_wait_answer_integration(tmp_path, monkeypatch) -> None:
    from starlette.applications import Starlette
    from refract.dashboard import register_dashboard_routes

    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        from refract import server
        state = [obj for obj in gc.get_objects() if type(obj).__name__ == "DashboardState" and getattr(obj, "runtime", None) is runtime][0] if "gc" in globals() else None
        # Build ASGI app with real dashboard routes pointing to the same runtime
        from refract.dashboard import DashboardState
        dash_state = DashboardState()
        dash_state.runtime = runtime
        app = Starlette(routes=register_dashboard_routes(dash_state))

        project = register_project(runtime, str(tmp_path))
        runtime.database.create_job(
            job_id="job-asgi-1",
            project_id=project.id,
            workflow="consult",
            profile="balanced",
            prompt="Do work",
            execution_plan_json="{}",
            session="c1",
        )
        with runtime.database._connection:
            runtime.database._connection.execute("UPDATE jobs SET state='running' WHERE id='job-asgi-1'")
        runtime.scheduler._current["job-asgi-1"] = _Dispatch(job_id="job-asgi-1")
        token = runtime.ask_registry.issue_token("job-asgi-1")

        # 1. Send genuine ASGI POST /ask request in background
        sent = []
        body_bytes = json.dumps({"token": token, "question": "Need ASGI confirmation?"}).encode("utf-8")
        received = False

        async def receive():
            nonlocal received
            if received:
                return {"type": "http.disconnect"}
            received = True
            return {"type": "http.request", "body": body_bytes, "more_body": False}

        async def send(msg):
            sent.append(msg)

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "path": "/ask",
            "raw_path": b"/ask",
            "query_string": b"",
            "headers": [(b"host", b"127.0.0.1:8765")],
            "client": ("127.0.0.1", 1234),
            "server": ("127.0.0.1", 8765),
            "scheme": "http",
            "root_path": "",
            "app": app,
        }
        asgi_task = asyncio.create_task(app(scope, receive, send))

        # 2. Call wait via MCP -> wakes early with pending_question
        wait_res = await client.call_tool("wait", {"job_id": "job-asgi-1", "timeout_s": 15})
        assert not wait_res.is_error
        wait_data = json.loads(wait_res.content[0].text)
        assert wait_data["job"]["state"] == "running"
        assert wait_data["result"]["pending_question"]["text"] == "Need ASGI confirmation?"

        # 3. Call answer via MCP -> delivers answer
        ans_res = await client.call_tool("answer", {"job_id": "job-asgi-1", "answer": "Confirmed via MCP"})
        assert not ans_res.is_error
        ans_data = json.loads(ans_res.content[0].text)
        assert ans_data["job"]["id"] == "job-asgi-1"

        # 4. Verify ASGI POST /ask response status 200 and exact JSON answer
        await asgi_task
        status = next(m["status"] for m in sent if m["type"] == "http.response.start")
        body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
        assert status == 200
        assert json.loads(body.decode("utf-8")) == {"answer": "Confirmed via MCP"}


@pytest.mark.asyncio
async def test_runtime_wait_scheduler_exception_and_task_cleanup(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    config_path = home / "config.toml"
    config_path.write_text(_serve_config(), encoding="utf-8")
    runtime = Runtime(load_config(config_path))
    try:
        project = register_project(runtime, str(tmp_path))
        runtime.database.create_job(
            job_id="job-err-1",
            project_id=project.id,
            workflow="consult",
            profile="balanced",
            prompt="Do work",
            execution_plan_json="{}",
            session="c1",
        )
        with runtime.database._connection:
            runtime.database._connection.execute("UPDATE jobs SET state='running' WHERE id='job-err-1'")

        async def _failing_scheduler_wait(job_id, timeout_s):
            await asyncio.sleep(0.01)
            raise RuntimeError("scheduler simulated failure")

        runtime.scheduler.wait = _failing_scheduler_wait

        with pytest.raises(RuntimeError, match="scheduler simulated failure"):
            await runtime.wait("job-err-1", timeout_s=5)

        # Question waiter must be cleaned up
        assert not runtime.ask_registry._question_waiters.get("job-err-1")
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_runtime_wait_indefinite_on_timeout_zero_until_question(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    config_path = home / "config.toml"
    config_path.write_text(_serve_config(), encoding="utf-8")
    runtime = Runtime(load_config(config_path))
    try:
        project = register_project(runtime, str(tmp_path))
        runtime.database.create_job(
            job_id="job-t0-1",
            project_id=project.id,
            workflow="consult",
            profile="balanced",
            prompt="Do work",
            execution_plan_json="{}",
            session="c1",
        )
        with runtime.database._connection:
            runtime.database._connection.execute("UPDATE jobs SET state='running' WHERE id='job-t0-1'")
        runtime.scheduler._current["job-t0-1"] = _Dispatch(job_id="job-t0-1")
        token = runtime.ask_registry.issue_token("job-t0-1")

        # Runtime.wait with timeout_s=0 must NOT return immediately while running
        wait_task = asyncio.create_task(runtime.wait("job-t0-1", timeout_s=0))
        await asyncio.sleep(0.05)
        assert not wait_task.done()

        # Asking a question wakes it
        ask_task = asyncio.create_task(runtime.ask_registry.ask(token, "Question at t=0", timeout_s=5.0))
        job = await asyncio.wait_for(wait_task, timeout=2.0)
        assert job.state == "running"
        assert runtime.ask_registry.has_pending("job-t0-1")

        # Cleanup
        runtime.ask_registry.deliver_answer("job-t0-1", "done")
        await ask_task
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_question_waiter_cleanup_on_timeout_and_cancellation(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    config_path = home / "config.toml"
    config_path.write_text(_serve_config(), encoding="utf-8")
    runtime = Runtime(load_config(config_path))
    try:
        # 1. Cleanup on timeout
        res = await runtime.ask_registry.wait_question("job-waiter-1", timeout_s=0.02)
        assert res is None
        assert "job-waiter-1" not in runtime.ask_registry._question_waiters

        # 2. Cleanup on cancellation
        task = asyncio.create_task(runtime.ask_registry.wait_question("job-waiter-2", timeout_s=10.0))
        await asyncio.sleep(0.01)
        assert "job-waiter-2" in runtime.ask_registry._question_waiters
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        assert "job-waiter-2" not in runtime.ask_registry._question_waiters
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_list_recovery_string_names_config_toml(tmp_path, monkeypatch) -> None:
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        root = tmp_path / "proj"
        root.mkdir()
        git(root, "init", "-q")
        (runtime.config.home / "task_guide.json").write_text("{invalid", encoding="utf-8")
        response = await client.call_tool("list", {"path": str(root)})
        assert response.is_error
        payload = json.loads(response.content[0].text)
        assert payload["code"] == "config_invalid"
        assert payload["next_action"] == "Fix the project guidance or configuration in .refract/config.toml."



_ARRAY_SCHEMA = {
    "properties": {
        "path": {"type": "string"},
        "job_ids": {"type": "array", "maxItems": 16, "items": {"type": "string", "minLength": 1, "maxLength": 64}},
    },
}


def test_raw_argument_error_checks_array_fields() -> None:
    from refract.server import _raw_argument_error

    assert not _raw_argument_error(_ARRAY_SCHEMA, {"path": "p", "job_ids": ["a", "b"]})
    assert not _raw_argument_error(_ARRAY_SCHEMA, {"path": "p", "job_ids": []})
    assert not _raw_argument_error(_ARRAY_SCHEMA, {"path": "p", "job_ids": ["a"] * 16})
    assert not _raw_argument_error(_ARRAY_SCHEMA, {"path": "p", "job_ids": ["a" * 64]})
    assert _raw_argument_error(_ARRAY_SCHEMA, {"path": "p", "job_ids": "abc"})
    assert _raw_argument_error(_ARRAY_SCHEMA, {"path": "p", "job_ids": ["a", 1]})
    assert _raw_argument_error(_ARRAY_SCHEMA, {"path": "p", "job_ids": [""]})
    assert _raw_argument_error(_ARRAY_SCHEMA, {"path": "p", "job_ids": ["a" * 65]})
    assert _raw_argument_error(_ARRAY_SCHEMA, {"path": "p", "job_ids": ["a"] * 17})
    assert _raw_argument_error(_ARRAY_SCHEMA, {"path": 1, "job_ids": []})


def _project(tmp_path, name: str = "card-project"):
    root = tmp_path / name
    root.mkdir()
    git(root, "init", "-q")
    return root


def _linkable_job(runtime, path, job_id: str) -> str:
    project = register_project(runtime, str(path))
    runtime.database.create_job(
        job_id=job_id, project_id=project.id, workflow="implement", profile="default",
        prompt="p", execution_plan_json="{}", session="s",
    )
    return job_id


async def _card_call(client, name: str, arguments: dict) -> tuple[bool, dict]:
    response = await client.call_tool(name, arguments)
    return response.is_error, json.loads(response.content[0].text)


CARD_KEYS = {"id", "project", "title", "state", "job_ids", "created_at", "updated_at"}


@pytest.mark.asyncio
async def test_card_create_move_list_round_trip(tmp_path, monkeypatch) -> None:
    root = _project(tmp_path)
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        _linkable_job(runtime, root, "job-1")
        error, created = await _card_call(client, "card_create", {"path": str(root), "title": "Ship", "body": "secret body", "job_ids": ["job-1"]})
        assert not error
        assert set(created) == {"card"}
        card = created["card"]
        assert set(card) == CARD_KEYS
        assert card["state"] == "todo"
        assert card["job_ids"] == ["job-1"]
        assert card["project"] == root.resolve().as_posix()
        assert uuid.UUID(card["id"]).version == 4
        assert "secret body" not in json.dumps(created)

        error, moved = await _card_call(client, "card_move", {"card_id": card["id"], "state": "in_progress", "note": "go"})
        assert not error
        assert set(moved) == {"card", "moved"}
        assert moved["moved"] is True
        assert set(moved["card"]) == CARD_KEYS
        assert moved["card"]["state"] == "in_progress"

        error, same = await _card_call(client, "card_move", {"card_id": card["id"], "state": "in_progress"})
        assert not error
        assert same["moved"] is False

        error, listed = await _card_call(client, "card_list", {"path": str(root)})
        assert not error
        assert set(listed) == {"cards", "truncated", "omitted"}
        assert listed["truncated"] is False
        assert listed["omitted"] == 0
        assert listed["cards"] == [{
            "id": card["id"], "title": "Ship", "state": "in_progress", "job_ids": ["job-1"],
            "updated_at": same["card"]["updated_at"],
        }]


@pytest.mark.asyncio
async def test_card_tool_error_codes(tmp_path, monkeypatch) -> None:
    root = _project(tmp_path)
    plain = tmp_path / "plain"
    plain.mkdir()
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        _, created = await _card_call(client, "card_create", {"path": str(root), "title": "t"})
        card_id = created["card"]["id"]

        cases = [
            ("card_create", {"path": str(plain), "title": "t"}, "invalid_path"),
            ("card_list", {"path": str(plain)}, "invalid_path"),
            ("card_create", {"path": str(root), "title": "t", "job_ids": ["missing"]}, "unknown_job"),
            ("card_create", {"path": str(root), "title": "   "}, "invalid_request"),
            ("card_create", {"path": str(root), "title": "x" * 201}, "invalid_request"),
            ("card_create", {"path": str(root), "title": "t", "body": "b" * 4001}, "invalid_request"),
            ("card_create", {"path": str(root), "title": "t", "job_ids": ["a"] * 17}, "invalid_request"),
            ("card_create", {"path": str(root), "title": "t", "job_ids": [""]}, "invalid_request"),
            ("card_create", {"path": str(root), "title": "t", "job_ids": ["j" * 65]}, "invalid_request"),
            ("card_create", {"path": str(root), "title": "t", "job_ids": "job-1"}, "invalid_request"),
            ("card_move", {"card_id": "nope", "state": "done"}, "unknown_card"),
            ("card_move", {"card_id": card_id, "state": "bogus"}, "invalid_state"),
            ("card_move", {"card_id": card_id, "state": "done"}, "invalid_state"),
            ("card_move", {"card_id": card_id, "state": "in_progress", "job_ids": ["missing"]}, "unknown_job"),
            ("card_move", {"card_id": card_id, "state": "in_progress", "note": "n" * 1001}, "invalid_request"),
            ("card_move", {"card_id": card_id, "state": "in_progress", "job_ids": ["a"] * 17}, "invalid_request"),
        ]
        for name, arguments, code in cases:
            error, payload = await _card_call(client, name, arguments)
            assert error, (name, arguments)
            assert payload["code"] == code, (name, arguments, payload)
            assert payload["next_action"]

        _, bad = await _card_call(client, "card_move", {"card_id": card_id, "state": "done"})
        assert "todo" in bad["message"]
        _, unknown = await _card_call(client, "card_move", {"card_id": "nope", "state": "done"})
        assert "card_list" in unknown["next_action"]


@pytest.mark.asyncio
async def test_card_list_is_scoped_to_the_resolved_project(tmp_path, monkeypatch) -> None:
    first, second = _project(tmp_path, "one"), _project(tmp_path, "two")
    async with _connected_client(tmp_path, monkeypatch) as (client, _runtime):
        await _card_call(client, "card_create", {"path": str(first), "title": "first"})
        await _card_call(client, "card_create", {"path": str(second), "title": "second"})
        _, listed = await _card_call(client, "card_list", {"path": str(first)})
        assert [card["title"] for card in listed["cards"]] == ["first"]


@pytest.mark.asyncio
async def test_card_list_returns_largest_fitting_prefix(tmp_path, monkeypatch) -> None:
    from refract import server

    root = _project(tmp_path)
    async with _connected_client(tmp_path, monkeypatch) as (client, _runtime):
        for number in range(8):
            await _card_call(client, "card_create", {"path": str(root), "title": f"card {number} " + "x" * 100})
        _, full = await _card_call(client, "card_list", {"path": str(root)})
        assert len(full["cards"]) == 8
        assert full["truncated"] is False
        assert full["omitted"] == 0

        monkeypatch.setattr(server, "_MAX_RESPONSE_BYTES", 1500)
        error, partial = await _card_call(client, "card_list", {"path": str(root)})
        assert not error
        kept = partial["cards"]
        assert 0 < len(kept) < 8
        assert kept == full["cards"][: len(kept)]
        assert partial["truncated"] is True
        assert partial["omitted"] == 8 - len(kept)
        assert server._fits_response(server._json(partial))
        assert not server._fits_response(
            server._json({"cards": full["cards"][: len(kept) + 1], "truncated": True, "omitted": 8 - len(kept) - 1})
        )


@pytest.mark.asyncio
async def test_oversized_card_create_and_move_report_the_applied_card(tmp_path, monkeypatch) -> None:
    from refract import server

    root = _project(tmp_path)
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        monkeypatch.setattr(server, "_fits_response", lambda text, *, is_error=False: is_error or not text.startswith('{"card"'))
        error, created = await _card_call(client, "card_create", {"path": str(root), "title": "big"})
        assert error
        assert created["code"] == "response_too_large"
        card_id = runtime.database.list_cards(project_id=None, limit=None)["cards"][0]["id"]
        assert card_id in created["message"]
        assert "Card creation was applied" in created["message"]
        assert "card_list" in created["next_action"]

        error, moved = await _card_call(client, "card_move", {"card_id": card_id, "state": "in_progress"})
        assert error
        assert moved["code"] == "response_too_large"
        assert card_id in moved["message"]
        assert "Card move was applied" in moved["message"]
        assert runtime.database.card_detail(card_id)["card"]["state"] == "in_progress"


def test_instructions_name_card_tools_within_limit() -> None:
    from refract.server import _INSTRUCTIONS

    assert len(_INSTRUCTIONS) <= 2048
    assert all(name in _INSTRUCTIONS for name in ("card_create", "card_move", "card_list"))


def test_unknown_tool_hint_does_not_state_a_count() -> None:
    from refract.server import _normalize_tool_error

    wire = {"content": [{"type": "text", "text": "Error executing tool nope: Unknown tool: nope"}], "isError": True}
    payload = json.loads(_normalize_tool_error(wire, "nope", "").content[0].text)
    assert payload["code"] == "invalid_request"
    assert payload["next_action"] == "Use one of the tools returned by tools/list."


class _ProgressRuntime:
    """Runtime double whose wait() blocks until released; database.job() replays scripted views."""

    def __init__(self, views: list[JobView | None], wait_error: Exception | None = None) -> None:
        self.views = views
        self.wait_error = wait_error
        self.release = asyncio.Event()
        self.database = SimpleNamespace(job=self._job)

    def _job(self, job_id: str) -> JobView | None:
        assert job_id == "job-1"
        return self.views.pop(0)

    async def wait(self, job_id: str, timeout_s: int) -> JobView:
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            if self.wait_error is not None:
                raise self.wait_error
            raise
        return _job_view("succeeded")


def _progress_context(reports: list[tuple[float, float | None, str]], runtime: _ProgressRuntime | None = None):
    async def report_progress(*, progress: float, total: float | None, message: str) -> None:
        reports.append((progress, total, message))
        if runtime is not None and len(reports) == 2:
            runtime.release.set()

    return SimpleNamespace(report_progress=report_progress)


@pytest.mark.asyncio
async def test_wait_with_progress_reports_each_heartbeat_with_incrementing_progress(monkeypatch) -> None:
    from refract import server

    monkeypatch.setattr(server, "_MCP_HEARTBEAT_INTERVAL_S", 0.005)
    runtime = _ProgressRuntime([_job_view("running")] * 2)
    reports: list[tuple[float, float | None, str]] = []
    await server._wait_with_progress(runtime, _progress_context(reports, runtime), "job-1", 5)
    assert reports == [(1.0, None, '{"state":"running"}'), (2.0, None, '{"state":"running"}')]


@pytest.mark.asyncio
async def test_wait_with_progress_stops_without_report_when_job_is_terminal(monkeypatch) -> None:
    from refract import server

    monkeypatch.setattr(server, "_MCP_HEARTBEAT_INTERVAL_S", 0.005)
    runtime = _ProgressRuntime([_job_view("succeeded")])
    reports: list[tuple[float, float | None, str]] = []
    await server._wait_with_progress(runtime, _progress_context(reports), "job-1", 5)
    assert reports == []


@pytest.mark.asyncio
async def test_wait_with_progress_unknown_job_raises_and_cancels_wait(monkeypatch) -> None:
    from refract import server

    monkeypatch.setattr(server, "_MCP_HEARTBEAT_INTERVAL_S", 0.005)
    runtime = _ProgressRuntime([None])
    context = _progress_context([])
    with pytest.raises(OrchestrationError, match="Job does not exist.") as raised:
        await server._wait_with_progress(runtime, context, "job-1", 5)
    assert (raised.value.code, raised.value.next_action) == ("unknown_job", "Call list with the project path and use a listed job ID.")


@pytest.mark.asyncio
async def test_wait_with_progress_logs_wait_cleanup_failure(monkeypatch, caplog) -> None:
    from refract import server

    monkeypatch.setattr(server, "_MCP_HEARTBEAT_INTERVAL_S", 0.005)
    runtime = _ProgressRuntime([None], wait_error=RuntimeError("cleanup broke"))
    context = _progress_context([])
    with caplog.at_level("WARNING"), pytest.raises(OrchestrationError, match="Job does not exist.") as raised:
        await server._wait_with_progress(runtime, context, "job-1", 5)
    assert raised.value.code == "unknown_job"
    record = next(r for r in caplog.records if r.getMessage() == "Job wait cleanup failed")
    assert (record.event, record.job_id) == ("job.wait_cleanup_failed", "job-1")


@pytest.mark.asyncio
async def test_wait_with_progress_nonpositive_heartbeat_uses_thirty_seconds(monkeypatch) -> None:
    from refract import server

    monkeypatch.setattr(server, "_MCP_HEARTBEAT_INTERVAL_S", 0)
    timeouts: list[float] = []
    real_wait_for = asyncio.wait_for

    async def recording_wait_for(awaitable, timeout):
        timeouts.append(timeout)
        return await real_wait_for(awaitable, timeout=0.001)

    monkeypatch.setattr(server.asyncio, "wait_for", recording_wait_for)
    runtime = _ProgressRuntime([_job_view("succeeded")])
    await server._wait_with_progress(runtime, _progress_context([]), "job-1", 5)
    assert timeouts == [30.0]


_V2026_VERSION = "2026-07-28"


def _v2026_post(client, method: str, params: dict | None = None, *, name: str | None = None, progress_token: str | None = None):
    meta = {
        "io.modelcontextprotocol/protocolVersion": _V2026_VERSION,
        "io.modelcontextprotocol/clientCapabilities": {},
        "io.modelcontextprotocol/clientInfo": {"name": "refract-test", "version": "0"},
    }
    if progress_token is not None:
        meta["progressToken"] = progress_token
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": _V2026_VERSION,
        "Mcp-Method": method,
    }
    if name is not None:
        headers["Mcp-Name"] = name
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": {**(params or {}), "_meta": meta}}
    return client.post("/mcp", json=body, headers=headers)


def _v2026_messages(response) -> list[dict]:
    if response.headers["content-type"].startswith("text/event-stream"):
        return [
            json.loads(line.removeprefix("data:").strip())
            for line in response.text.splitlines()
            if line.startswith("data:") and line.removeprefix("data:").strip()
        ]
    return [response.json()]


def _v2026_call(client, tool: str, arguments: dict, *, progress_token: str | None = None) -> list[dict]:
    response = _v2026_post(
        client, "tools/call", {"name": tool, "arguments": arguments}, name=tool, progress_token=progress_token
    )
    assert response.status_code == 200, response.text
    return _v2026_messages(response)


@pytest.fixture
def v2026_http(tmp_path, monkeypatch):
    from starlette.testclient import TestClient

    from refract import server
    from tests.orchestration_helpers import config as make_config

    monkeypatch.setattr(server, "configure_logging", lambda _settings: None)
    application = server.create_application(make_config(tmp_path / "home"), host="127.0.0.1", port=9322)
    with TestClient(application, base_url="http://127.0.0.1:9322") as client:
        yield client, application.state.runtime


def test_v2026_http_discover_lists_protocol_version(v2026_http) -> None:
    client, _runtime = v2026_http
    response = _v2026_post(client, "server/discover")
    assert response.status_code == 200, response.text
    assert _V2026_VERSION in _v2026_messages(response)[-1]["result"]["supportedVersions"]


def test_v2026_http_tools_list_returns_the_nine_tools(v2026_http) -> None:
    client, _runtime = v2026_http
    response = _v2026_post(client, "tools/list")
    assert response.status_code == 200, response.text
    tools = _v2026_messages(response)[-1]["result"]["tools"]
    assert {tool["name"] for tool in tools} == {
        "submit", "wait", "answer", "cancel", "retry", "list", "card_create", "card_move", "card_list",
    }
    assert len(tools) == 9


def test_v2026_http_submit_wait_progress_and_cancel(v2026_http, tmp_path, monkeypatch) -> None:
    from refract import server
    from tests.orchestration_helpers import BlockingDrivers, repository

    client, runtime = v2026_http
    monkeypatch.setattr(server, "_MCP_HEARTBEAT_INTERVAL_S", 0.005)
    runtime.drivers = BlockingDrivers()
    root = repository(tmp_path)

    submitted = _v2026_call(client, "submit", {"path": str(root), "workflow": "consult", "prompt": "inspect"})[-1]
    job_id = json.loads(submitted["result"]["content"][0]["text"])["job"]["id"]

    messages = _v2026_call(client, "wait", {"job_id": job_id, "timeout_s": 1}, progress_token="p1")
    progress = [m for m in messages if m.get("method") == "notifications/progress"]
    assert progress, messages
    assert all(m["params"]["progressToken"] == "p1" for m in progress)
    assert messages.index(progress[0]) < len(messages) - 1
    assert "result" in messages[-1]
    assert json.loads(messages[-1]["result"]["content"][0]["text"])["job"]["state"] == "running"

    cancelled = _v2026_call(client, "cancel", {"job_id": job_id})[-1]
    assert not cancelled["result"].get("isError")


def test_v2026_http_refract_error_matches_2025_payload(v2026_http) -> None:
    client, _runtime = v2026_http
    message = _v2026_call(client, "wait", {"job_id": "missing-job", "timeout_s": 0})[-1]
    assert message["result"]["isError"] is True
    payload = json.loads(message["result"]["content"][0]["text"])
    assert set(payload) == {"code", "message", "next_action"}
    assert payload["code"] == "unknown_job"
    assert payload["next_action"]


def test_create_application_never_expires_idle_2025_sessions(tmp_path, monkeypatch) -> None:
    from refract import server
    from tests.orchestration_helpers import config as make_config

    monkeypatch.setattr(server, "configure_logging", lambda _settings: None)
    application = server.create_application(make_config(tmp_path / "home"), host="127.0.0.1", port=9323)
    assert application.state.mcp.session_manager.session_idle_timeout is None


def _true_flags(value, path: str = "") -> list[str]:
    if isinstance(value, dict):
        return [found for key, item in value.items() for found in _true_flags(item, f"{path}.{key}")]
    return [path] if value is True and path.rsplit(".", 1)[-1] in {"listChanged", "subscribe"} else []


def test_v2026_http_discover_advertises_no_list_changed_or_subscribe(v2026_http) -> None:
    client, _runtime = v2026_http
    response = _v2026_post(client, "server/discover")
    assert response.status_code == 200, response.text
    capabilities = _v2026_messages(response)[-1]["result"]["capabilities"]
    assert _true_flags(capabilities) == []


def test_v2026_http_subscriptions_listen_is_refused(v2026_http) -> None:
    client, _runtime = v2026_http
    response = _v2026_post(client, "subscriptions/listen", {"notifications": {"toolsListChanged": True}})
    message = _v2026_messages(response)[-1]
    assert "error" in message, message


def test_v2026_http_tools_list_carries_cache_hint(v2026_http) -> None:
    client, _runtime = v2026_http
    result = _v2026_messages(_v2026_post(client, "tools/list"))[-1]["result"]
    assert result["ttlMs"] == 300000
    assert result["cacheScope"] == "private"


def test_2025_http_session_round_trip(v2026_http) -> None:
    client, _runtime = v2026_http
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    initialize = {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "legacy", "version": "0"}},
    }
    response = client.post("/mcp", json=initialize, headers=headers)
    assert response.status_code == 200, response.text
    session_id = response.headers["Mcp-Session-Id"]
    assert _v2026_messages(response)[-1]["result"]["protocolVersion"] == "2025-06-18"

    session_headers = {**headers, "Mcp-Session-Id": session_id, "MCP-Protocol-Version": "2025-06-18"}
    ack = client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=session_headers)
    assert ack.status_code == 202, ack.text

    listed = client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, headers=session_headers)
    assert listed.status_code == 200, listed.text
    assert len(_v2026_messages(listed)[-1]["result"]["tools"]) == 9
