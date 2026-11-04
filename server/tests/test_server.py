from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager, suppress
import subprocess
import sys
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
    }
    tools = {tool.name: tool for tool in await mcp.list_tools()}

    assert {name: set(tool.input_schema["properties"]) for name, tool in tools.items()} == expected
    assert await mcp.list_resources() == []
    assert await mcp.list_resource_templates() == []
    assert mcp.title == "Refract job queue"
    assert mcp.instructions and len(mcp.instructions) <= 2048
    assert all(name in mcp.instructions for name in expected)
    for tool in tools.values():
        assert tool.title
        assert tool.description and len(tool.description) <= 2048
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

    def fake_application(config, *, host: str, logging_overrides) -> str:
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
    from refract import cli, server
    import uvicorn

    home = tmp_path / "refract"
    home.mkdir()
    (home / "config.toml").write_text(_serve_config("127.0.0.2", 9123), encoding="utf-8")
    monkeypatch.setenv("REFRACT_HOME", str(home))
    captured: dict[str, object] = {}

    def fake_application(config, *, host: str, logging_overrides) -> str:
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


def test_serve_refuses_non_loopback_host_without_opt_in(tmp_path, monkeypatch, capsys) -> None:
    from refract import cli, server
    import uvicorn

    home = tmp_path / "refract"
    home.mkdir()
    (home / "config.toml").write_text(_serve_config("0.0.0.0", 9123), encoding="utf-8")
    monkeypatch.setenv("REFRACT_HOME", str(home))
    launched: list[str] = []
    monkeypatch.setattr(server, "create_application", lambda config, *, host, logging_overrides: "application")
    monkeypatch.setattr(uvicorn, "run", lambda application, *, host, port: launched.append(host))

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
    assert set(tools) == {"submit", "wait", "answer", "cancel", "retry", "list"}
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
            assert len(response.content) == 1 and response.content[0].type == "text"
            wire = json.dumps(response.model_dump(by_alias=True, mode="json", exclude_none=True), separators=(",", ":"))
            assert len(wire) < 30000 and len(wire.encode("utf-8")) < 9000
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
            assert len(response.content) == 1 and response.content[0].type == "text"
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
        assert submit_error["code"] == "response_too_large" and "applied" in submit_error["message"]
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
        assert retry_error["code"] == "response_too_large" and "applied" in retry_error["message"]
        assert runtime.database.job(retried_id).retry_of == "retry-overflow"
        assert runtime.database.job("retry-overflow").state == "failed"

        runtime.database.create_job(
            job_id="cancel-overflow", project_id=project.id, workflow="review", profile="balanced",
            prompt="cancel", execution_plan_json="{}", session="c" * 10000,
        )
        cancelled = await client.call_tool("cancel", {"job_id": "cancel-overflow"})
        assert cancelled.is_error
        cancel_error = json.loads(cancelled.content[0].text)
        assert cancel_error["code"] == "response_too_large" and "cancel-overflow" in cancel_error["message"]
        assert "applied" in cancel_error["message"]
        assert runtime.database.job("cancel-overflow").state == "cancelled"




@pytest.mark.asyncio
async def test_failed_driver_diagnostic_is_private_but_remains_in_operator_record(tmp_path, monkeypatch) -> None:
    from refract.drivers import DriverResult

    marker = "provider-secret-model-backend-detail-" + "private-diagnostic-" * 700

    class PrivateFailureDrivers:
        @staticmethod
        def supports_structured_streaming(_target):
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
        assert len(envelope) < 30000 and len(envelope.encode("utf-8")) < 9000
        stored = runtime.database.job(job_id)
        assert stored is not None and stored.result.error == marker




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
    assert result["result"]["text"] == "" and result["result"]["truncated"] is False
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
        runtime.scheduler._current["job-q-1"] = _Dispatch(job_id="job-q-1", project_id=project.id)
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
        assert res["result"]["text"] == "" and res["result"]["truncated"] is False
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
        runtime.scheduler._current["job-client-test"] = _Dispatch(job_id="job-client-test", project_id=project.id)
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
        runtime.scheduler._current["job-bounds-test"] = _Dispatch(job_id="job-bounds-test", project_id=project.id)
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
        runtime.scheduler._current["job-oversized-q"] = _Dispatch(job_id="job-oversized-q", project_id=project.id)
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
        runtime.scheduler._current["job-asgi-1"] = _Dispatch(job_id="job-asgi-1", project_id=project.id)
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
        runtime.scheduler._current["job-t0-1"] = _Dispatch(job_id="job-t0-1", project_id=project.id)
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

