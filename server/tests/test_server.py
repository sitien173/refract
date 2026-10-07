from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager, suppress
import subprocess
import sys
from types import SimpleNamespace

import pytest

from openmcp.models import JobResult, JobSummary, JobView, SubmissionResult
from openmcp.server import job_wait, mcp


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
    from openmcp import server

    home = tmp_path / "openmcp-home"
    home.mkdir()
    config_path = home / "config.toml"
    config_path.write_text(_serve_config(), encoding="utf-8")
    monkeypatch.setenv("OPENMCP_HOME", str(home))
    monkeypatch.setattr(server, "configure_logging", lambda _settings: None)
    monkeypatch.setattr(server, "_DAEMON_CONFIG", server.load_config(config_path))
    lowlevel = server.mcp._lowlevel_server
    async with create_client_server_memory_streams() as (client_streams, server_streams):
        server_task = asyncio.create_task(
            lowlevel.run(*server_streams, lowlevel.create_initialization_options())
        )
        try:
            async with ClientSession(*client_streams) as client:
                await client.initialize()
                yield client, server._ACTIVE_RUNTIME
        finally:
            server_task.cancel()
            with suppress(asyncio.CancelledError):
                await server_task


@pytest.mark.asyncio
async def test_v2_tool_surface_lists_exact_contract() -> None:
    expected = {
        "project_resolve": {"path", "alias"},
        "task_guide": {"project_id"},
        "job_submit": {"project_id", "workflow", "prompt", "profile", "context_key", "fresh_session", "depends_on"},
        "job_wait": {"job_id", "timeout_s", "result_offset"},
        "job_list": {"project_id"},
        "job_cancel": {"job_id"},
        "job_retry": {"job_id"},
    }
    tools = {tool.name: tool for tool in await mcp.list_tools()}

    assert {name: set(tool.input_schema["properties"]) for name, tool in tools.items()} == expected
    assert await mcp.list_resources() == []
    assert await mcp.list_resource_templates() == []
    assert mcp.title == "OpenMCP job queue"
    assert mcp.instructions and len(mcp.instructions) <= 2048
    assert all(name in mcp.instructions for name in expected)
    for tool in tools.values():
        assert tool.title
        assert tool.description and len(tool.description) <= 2048
        assert "openmcp://" not in tool.description
        assert tool.output_schema is None


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
async def test_v2_tool_schema_limits_annotations_and_no_legacy_tools() -> None:
    tools = {tool.name: tool for tool in await mcp.list_tools()}
    assert set(tools) == {
        "project_resolve", "task_guide", "job_submit", "job_wait",
        "job_list", "job_cancel", "job_retry",
    }
    assert tools["job_submit"].input_schema["properties"]["workflow"]["enum"] == [
        "consult", "implement", "review", "other"
    ]
    assert tools["job_wait"].input_schema["properties"]["timeout_s"]["minimum"] == 0
    assert tools["job_wait"].input_schema["properties"]["timeout_s"]["maximum"] == 3600
    assert tools["job_wait"].input_schema["properties"]["result_offset"]["minimum"] == 0
    assert tools["job_submit"].input_schema["properties"]["fresh_session"]["default"] is False
    assert tools["job_cancel"].annotations is not None
    assert tools["job_cancel"].annotations.idempotent_hint is True
    assert tools["project_resolve"].annotations.idempotent_hint is True
    assert tools["task_guide"].annotations.read_only_hint is True
    assert tools["job_wait"].annotations.read_only_hint is True
    assert tools["job_submit"].annotations.destructive_hint is True
    assert tools["job_retry"].annotations.idempotent_hint is False
    expected_annotations = {
        "project_resolve": (False, False, True, False),
        "task_guide": (True, False, True, False),
        "job_submit": (False, True, False, True),
        "job_wait": (True, False, True, False),
        "job_list": (True, False, True, False),
        "job_cancel": (False, True, True, False),
        "job_retry": (False, True, False, True),
    }
    for name, expected_hints in expected_annotations.items():
        annotations = tools[name].annotations
        assert annotations is not None
        assert (
            annotations.read_only_hint, annotations.destructive_hint,
            annotations.idempotent_hint, annotations.open_world_hint,
        ) == expected_hints
        assert annotations.title == tools[name].title
        assert all(prop.get("description") for prop in tools[name].input_schema["properties"].values())
    assert set(JobSummary.model_fields) == {
        "id", "project_id", "workflow", "profile", "state", "context_key",
        "attempts", "access_mode", "depends_on", "waiting_on", "waiting_reason",
        "created_at", "updated_at",
    }
    assert "resource_uri" not in SubmissionResult.model_fields


@pytest.mark.asyncio
async def test_inprocess_client_receives_compact_json_errors(tmp_path, monkeypatch) -> None:
    async with _connected_client(tmp_path, monkeypatch) as (client, _runtime):
        malformed = await client.call_tool(
            "job_wait", {"job_id": "job", "timeout_s": -1}
        )
        assert malformed.is_error
        malformed_payload = json.loads(malformed.content[0].text)
        assert set(malformed_payload) == {"code", "message", "next_action", "retryable"}
        assert malformed_payload["code"] == "invalid_request"
        assert malformed_payload["retryable"] is False
        assert malformed_payload["next_action"]

        unknown = await client.call_tool(
            "job_wait", {"job_id": "missing-job", "timeout_s": 0}
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
        project = runtime.register_project(str(root))
        secret = "provider-secret-that-must-not-escape"

        def fail_listing(_project_id: str):
            raise RuntimeError(secret)

        runtime.database.jobs = fail_listing
        response = await client.call_tool("job_list", {"project_id": project.id})

        assert response.is_error
        payload = json.loads(response.content[0].text)
        assert payload["code"] == "internal_error"
        assert payload["next_action"]
        assert "Request ID:" in payload["message"]
        assert payload["message"].split("Request ID:", 1)[1].strip().rstrip(".")
        assert secret not in response.content[0].text
        assert "Traceback" not in response.content[0].text


@pytest.mark.asyncio
async def test_job_wait_pages_complete_text_without_loss_and_bounds_wire_envelope(tmp_path, monkeypatch) -> None:
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        project_root = tmp_path / "page-project"
        project_root.mkdir()
        project = runtime.register_project(str(project_root), "pages")
        runtime.database.create_job(
            job_id="paged-job", project_id=project.id, workflow="review",
            profile="balanced", prompt="large output", execution_plan_json="{}",
            context_key="paging",
        )
        original_text = ('quote="slash=\\ carriage=\r\n emoji=🙂 star=✨\n') * 1800
        runtime.database.finish_job("paged-job", "succeeded", text=original_text)

        collected: list[str] = []
        offset = 0
        pages = 0
        while True:
            response = await client.call_tool(
                "job_wait",
                {"job_id": "paged-job", "timeout_s": 0, "result_offset": offset},
            )
            assert not response.is_error
            payload = json.loads(response.content[0].text)
            assert set(payload) == {"job", "result"}
            assert payload["job"]["id"] == "paged-job"
            page = payload["result"]
            collected.append(page["text"])
            pages += 1
            envelope = json.dumps(
                response.model_dump(by_alias=True, mode="json", exclude_none=True),
                ensure_ascii=False,
                separators=(",", ":"),
            )
            assert len(envelope) < 30000
            assert len(envelope.encode("utf-8")) < 9000
            next_offset = page["next_offset"]
            if next_offset is None:
                break
            assert next_offset == offset + len(page["text"])
            assert next_offset > offset
            offset = next_offset

        assert pages > 1
        assert "".join(collected) == original_text
        assert not (await client.call_tool(
            "job_wait", {"job_id": "paged-job", "timeout_s": 0, "result_offset": len(original_text) + 1}
        )).is_error


@pytest.mark.asyncio
async def test_unpageable_guidance_overflow_returns_actionable_error(tmp_path, monkeypatch) -> None:
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        root = tmp_path / "guide-project"
        root.mkdir()
        project = runtime.register_project(str(root), "guide")
        (runtime.config.home / "task_guide.json").write_text(
            json.dumps({"guidance": "g" * 12000}), encoding="utf-8"
        )
        result = await client.call_tool("task_guide", {"project_id": project.id})

        assert result.is_error
        payload = json.loads(result.content[0].text)
        assert payload["code"] == "response_too_large"
        assert payload["next_action"]
        wire = json.dumps(result.model_dump(by_alias=True, mode="json", exclude_none=True), separators=(",", ":"))
        assert len(wire.encode("utf-8")) < 9000


@pytest.mark.asyncio
async def test_project_resolve_reports_id_if_result_overflows_after_creation(tmp_path, monkeypatch) -> None:
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        project_root = tmp_path / "applied-project"
        project_root.mkdir()
        result = await client.call_tool(
            "project_resolve",
            {"path": str(project_root), "alias": "alias-" + "a" * 10000},
        )

        assert result.is_error
        payload = json.loads(result.content[0].text)
        assert payload["code"] == "response_too_large"
        assert payload["next_action"]
        assert "applied" in payload["message"].lower()
        project = runtime.database.project("alias-" + "a" * 10000)
        assert project is not None
        assert project.id in payload["message"] or project.id in payload["next_action"]


@pytest.mark.asyncio
async def test_mcp_client_completes_v2_cycle_in_four_calls(tmp_path, monkeypatch) -> None:
    from tests.orchestration_helpers import FakeDrivers, repository

    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        root = repository(tmp_path)
        guide_path = runtime.config.home / "task_guide.json"
        guide_path.write_text(json.dumps({"guidance": []}), encoding="utf-8")
        runtime.drivers = FakeDrivers()

        resolved = await client.call_tool("project_resolve", {"path": str(root)})
        project_id = json.loads(resolved.content[0].text)["project"]["id"]
        guide = await client.call_tool("task_guide", {"project_id": project_id})
        assert json.loads(guide.content[0].text)["profiles"]["default"] == "balanced"
        submitted = await client.call_tool(
            "job_submit",
            {"project_id": project_id, "workflow": "consult", "prompt": "inspect"},
        )
        job_id = json.loads(submitted.content[0].text)["job"]["id"]
        waited = await client.call_tool("job_wait", {"job_id": job_id, "timeout_s": 5})
        result = json.loads(waited.content[0].text)
        assert result["job"]["state"] == "succeeded"
        assert result["result"]["text"] == "response from primary"


@pytest.mark.asyncio
async def test_actual_client_rejects_sdk_coercions_before_dispatch(tmp_path, monkeypatch) -> None:
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        root = tmp_path / "coercion-project"
        root.mkdir()
        project = runtime.register_project(str(root), "coercion")
        before = runtime.database.jobs(project.id)
        invalid_calls = [
            ("job_wait", {"job_id": "missing", "timeout_s": True}),
            ("job_wait", {"job_id": "missing", "timeout_s": "0"}),
            ("job_wait", {"job_id": "missing", "timeout_s": 0, "result_offset": True}),
            ("job_submit", {"project_id": project.id, "workflow": "implement", "prompt": "must not queue", "fresh_session": 1}),
            ("job_submit", {"project_id": project.id, "workflow": "implement", "prompt": "must not queue", "fresh_session": "false"}),
        ]
        for name, arguments in invalid_calls:
            response = await client.call_tool(name, arguments)
            payload = json.loads(response.content[0].text)
            assert response.is_error
            assert payload["code"] == "invalid_request"
            assert payload["retryable"] is False
            assert "schema" in payload["next_action"].lower()
        assert runtime.database.jobs(project.id) == before


def test_terminal_page_with_tight_metadata_advances_or_errors() -> None:
    from openmcp.server import OpenMCPError, _page_terminal_result

    job = _job_view("succeeded")
    job.result = JobResult(text="😀😀")
    job.context_key = "x" * 8510
    summary = JobSummary(
        id=job.id, project_id=job.project_id, workflow=job.workflow, profile=job.profile,
        state=job.state, context_key=job.context_key, access_mode="exclusive",
        depends_on=[], waiting_on=[], waiting_reason="", attempts=0,
        created_at=job.created_at, updated_at=job.updated_at,
    ).model_dump(mode="json")
    empty_page = json.dumps(
        {"job": summary, "result": {"text": "", "error": "", "next_offset": 0}},
        ensure_ascii=False, separators=(",", ":"),
    )
    from openmcp.server import _fits_response
    assert _fits_response(empty_page)
    with pytest.raises(OpenMCPError) as raised:
        _page_terminal_result(job, summary, 0)
    assert raised.value.code == "response_too_large"


@pytest.mark.asyncio
async def test_expected_runtime_error_families_are_compact_json(tmp_path, monkeypatch) -> None:
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        root = tmp_path / "errors-project"
        root.mkdir()
        project = runtime.register_project(str(root), "errors")

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
            assert set(payload) == {"code", "message", "next_action", "retryable"}
            assert payload["code"] == code
            assert payload["next_action"]
            assert_private(payload)
            assert len(response.content) == 1 and response.content[0].type == "text"
            wire = json.dumps(response.model_dump(by_alias=True, mode="json", exclude_none=True), separators=(",", ":"))
            assert len(wire) < 30000 and len(wire.encode("utf-8")) < 9000
            return payload

        await check("project_resolve", {"path": str(root / "missing")}, "invalid_path")
        await check("task_guide", {"project_id": "unknown-project"}, "unknown_project")
        await check("job_list", {"project_id": "unknown-project"}, "unknown_project")
        await check("job_wait", {"job_id": "missing-job", "timeout_s": 0}, "unknown_job")
        await check("job_cancel", {"job_id": "missing-job"}, "unknown_job")
        other = tmp_path / "alias-collision"
        other.mkdir()
        await check("project_resolve", {"path": str(other), "alias": "errors"}, "alias_taken")
        await check("job_submit", {"project_id": project.id, "workflow": "implement", "prompt": "x", "profile": "missing-profile"}, "unknown_profile")
        await check("job_submit", {"project_id": project.id, "workflow": "implement", "prompt": "x", "depends_on": ["no-such-dependency"]}, "invalid_dependency")

        runtime.database.create_job(
            job_id="failed-parent", project_id=project.id, workflow="review", profile="balanced",
            prompt="parent", execution_plan_json="{}", context_key="parent",
        )
        runtime.database.finish_job("failed-parent", "failed")
        runtime.database.create_job_with_dependencies(
            job_id="cancelled-child", project_id=project.id, workflow="review", profile="balanced",
            prompt="child", execution_plan_json="{}", context_key="child", access_mode="exclusive",
            depends_on=["failed-parent"],
        )
        runtime.database.finish_job("cancelled-child", "cancelled")
        await check("job_retry", {"job_id": "cancelled-child"}, "dependency_failed")
        await check("job_retry", {"job_id": "missing-job"}, "unknown_job")

        runtime.database.create_job(
            job_id="queued-invalid-retry", project_id=project.id, workflow="review", profile="balanced",
            prompt="queued", execution_plan_json="{}", context_key="queued",
        )
        await check("job_retry", {"job_id": "queued-invalid-retry"}, "invalid_state")
        (runtime.config.home / "task_guide.json").write_text("{invalid", encoding="utf-8")
        await check("task_guide", {"project_id": project.id}, "config_invalid")
        (runtime.config.home / "task_guide.json").write_text(json.dumps({"guidance": "g" * 12000}), encoding="utf-8")
        await check("task_guide", {"project_id": project.id}, "response_too_large")

        runtime._closing = True
        await check("job_submit", {"project_id": project.id, "workflow": "implement", "prompt": "stopping"}, "daemon_stopping")
        runtime._closing = False


@pytest.mark.asyncio
async def test_all_tool_success_payloads_are_private_and_single_text_content(tmp_path, monkeypatch) -> None:
    from tests.orchestration_helpers import FakeDrivers

    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        root = tmp_path / "privacy-project"
        root.mkdir()
        responses = []
        resolved = await client.call_tool("project_resolve", {"path": str(root)})
        responses.append(resolved)
        project_id = json.loads(resolved.content[0].text)["project"]["id"]
        (runtime.config.home / "task_guide.json").write_text(json.dumps({"guidance": []}), encoding="utf-8")
        responses.append(await client.call_tool("task_guide", {"project_id": project_id}))
        runtime.drivers = FakeDrivers()
        submitted = await client.call_tool("job_submit", {"project_id": project_id, "workflow": "consult", "prompt": "inspect"})
        responses.append(submitted)
        submitted_id = json.loads(submitted.content[0].text)["job"]["id"]
        responses.append(await client.call_tool("job_wait", {"job_id": submitted_id, "timeout_s": 5}))
        responses.append(await client.call_tool("job_list", {"project_id": project_id}))
        runtime.database.create_job(
            job_id="privacy-cancel", project_id=project_id, workflow="review", profile="balanced",
            prompt="cancel", execution_plan_json="{}", context_key="cancel",
        )
        responses.append(await client.call_tool("job_cancel", {"job_id": "privacy-cancel"}))
        runtime.database.create_job(
            job_id="privacy-retry", project_id=project_id, workflow="review", profile="balanced",
            prompt="retry", execution_plan_json="{}", context_key="retry",
        )
        runtime.database.finish_job("privacy-retry", "failed")
        responses.append(await client.call_tool("job_retry", {"job_id": "privacy-retry"}))

        forbidden = {"target_id", "backend", "model", "resource_uri", "config_revision"}
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
        project = runtime.register_project(str(root), "overflow")

        submitted = await client.call_tool("job_submit", {
            "project_id": project.id, "workflow": "implement", "prompt": "submit",
            "context_key": "s" * 10000,
        })
        assert submitted.is_error
        submit_error = json.loads(submitted.content[0].text)
        submitted_id = submit_error["message"].split("ID: ", 1)[1].rstrip(".")
        assert submit_error["code"] == "response_too_large" and "applied" in submit_error["message"]
        assert runtime.database.job(submitted_id) is not None

        runtime.database.create_job(
            job_id="retry-overflow", project_id=project.id, workflow="review", profile="balanced",
            prompt="retry", execution_plan_json="{}", context_key="r" * 10000,
        )
        runtime.database.finish_job("retry-overflow", "failed")
        retried = await client.call_tool("job_retry", {"job_id": "retry-overflow"})
        assert retried.is_error
        retry_error = json.loads(retried.content[0].text)
        assert retry_error["code"] == "response_too_large" and "retry-overflow" in retry_error["message"]
        assert "applied" in retry_error["message"]
        assert runtime.database.job("retry-overflow") is not None

        runtime.database.create_job(
            job_id="cancel-overflow", project_id=project.id, workflow="review", profile="balanced",
            prompt="cancel", execution_plan_json="{}", context_key="c" * 10000,
        )
        cancelled = await client.call_tool("job_cancel", {"job_id": "cancel-overflow"})
        assert cancelled.is_error
        cancel_error = json.loads(cancelled.content[0].text)
        assert cancel_error["code"] == "response_too_large" and "cancel-overflow" in cancel_error["message"]
        assert "applied" in cancel_error["message"]
        assert runtime.database.job("cancel-overflow").state == "cancelled"


@pytest.mark.asyncio
async def test_job_cancel_reports_complete_cancelled_dependents(tmp_path, monkeypatch) -> None:
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        root = tmp_path / "cancel-dependencies"
        root.mkdir()
        project = runtime.register_project(str(root), "cancel-dependencies")
        runtime.database.create_job(
            job_id="cancel-parent", project_id=project.id, workflow="review", profile="balanced",
            prompt="parent", execution_plan_json="{}", context_key="parent",
        )
        runtime.database.create_job_with_dependencies(
            job_id="cancel-child", project_id=project.id, workflow="review", profile="balanced",
            prompt="child", execution_plan_json="{}", context_key="child", access_mode="exclusive",
            depends_on=["cancel-parent"],
        )
        listed = await client.call_tool("job_list", {"project_id": project.id})
        listed_jobs = {item["id"]: item for item in json.loads(listed.content[0].text)["active"]}
        assert listed_jobs["cancel-child"]["depends_on"] == ["cancel-parent"]
        assert listed_jobs["cancel-child"]["waiting_on"] == ["cancel-parent"]
        response = await client.call_tool("job_cancel", {"job_id": "cancel-parent"})
        assert not response.is_error
        result = json.loads(response.content[0].text)
        assert result["cancelled_dependents"] == ["cancel-child"]
        assert runtime.database.job("cancel-child").state == "cancelled"


@pytest.mark.asyncio
async def test_failed_driver_diagnostic_is_private_but_remains_in_operator_record(tmp_path, monkeypatch) -> None:
    from openmcp.drivers import DriverResult

    marker = "provider-secret-model-backend-detail-" + "private-diagnostic-" * 700

    class PrivateFailureDrivers:
        @staticmethod
        def available(_target):
            return True

        async def execute(self, **_kwargs):
            return DriverResult("TARGET_FATAL", "", "", marker, "backend_failure")

    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        root = tmp_path / "private-failure-project"
        root.mkdir()
        project = runtime.register_project(str(root), "private-failure")
        runtime.drivers = PrivateFailureDrivers()
        submitted = await client.call_tool("job_submit", {
            "project_id": project.id, "workflow": "implement", "prompt": "fail safely",
        })
        job_id = json.loads(submitted.content[0].text)["job"]["id"]
        response = await client.call_tool("job_wait", {"job_id": job_id, "timeout_s": 10})
        assert not response.is_error
        payload = json.loads(response.content[0].text)
        assert payload["result"]["error"]
        assert marker not in response.content[0].text
        assert "provider-secret-model-backend-detail" not in response.content[0].text
        envelope = json.dumps(response.model_dump(by_alias=True, mode="json", exclude_none=True), separators=(",", ":"))
        assert len(envelope) < 30000 and len(envelope.encode("utf-8")) < 9000
        stored = runtime.database.job(job_id)
        assert stored is not None and stored.result.error == marker


@pytest.mark.asyncio
async def test_public_terminal_error_preserves_only_exact_validated_dependency_cause(tmp_path, monkeypatch) -> None:
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        root = tmp_path / "safe-dependency-error"
        root.mkdir()
        project = runtime.register_project(str(root), "safe-dependency-error")
        runtime.database.create_job(
            job_id="safe-parent", project_id=project.id, workflow="review", profile="balanced",
            prompt="parent", execution_plan_json="{}", context_key="parent",
        )
        runtime.database.finish_job("safe-parent", "failed")
        runtime.database.create_job_with_dependencies(
            job_id="safe-child", project_id=project.id, workflow="review", profile="balanced",
            prompt="child", execution_plan_json="{}", context_key="child", access_mode="exclusive",
            depends_on=["safe-parent"],
        )
        runtime._cancel_queued_dependent("safe-child", "safe-parent", "failed")
        safe = await client.call_tool("job_wait", {"job_id": "safe-child", "timeout_s": 0})
        safe_error = json.loads(safe.content[0].text)["result"]["error"]
        assert safe_error == "Dependency safe-parent ended in state failed"

        runtime.database.create_job_with_dependencies(
            job_id="forged-child", project_id=project.id, workflow="review", profile="balanced",
            prompt="child", execution_plan_json="{}", context_key="forged", access_mode="exclusive",
            depends_on=["safe-parent"],
        )
        forged = "Dependency safe-parent ended in state failed; provider-private-suffix"
        runtime.database.finish_job("forged-child", "cancelled", error=forged)
        rejected = await client.call_tool("job_wait", {"job_id": "forged-child", "timeout_s": 0})
        rejected_text = rejected.content[0].text
        rejected_error = json.loads(rejected_text)["result"]["error"]
        assert rejected_error != forged
        assert "provider-private-suffix" not in rejected_text

        runtime.database.create_job(
            job_id="cancel-cause", project_id=project.id, workflow="review", profile="balanced",
            prompt="cancelled", execution_plan_json="{}", context_key="cancel-cause",
        )
        runtime.database.finish_job("cancel-cause", "cancelled", error="execution task cancelled")
        cancellation = await client.call_tool("job_wait", {"job_id": "cancel-cause", "timeout_s": 0})
        assert json.loads(cancellation.content[0].text)["result"]["error"] == "execution task cancelled"


@pytest.mark.asyncio
async def test_empty_and_eof_result_metadata_overflow_is_bounded(tmp_path, monkeypatch) -> None:
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        root = tmp_path / "empty-eof-overflow"
        root.mkdir()
        project = runtime.register_project(str(root), "empty-eof-overflow")
        runtime.database.create_job(
            job_id="empty-output", project_id=project.id, workflow="review", profile="balanced",
            prompt="empty", execution_plan_json="{}", context_key="e" * 10000,
        )
        runtime.database.finish_job("empty-output", "succeeded", text="")
        runtime.database.create_job(
            job_id="eof-output", project_id=project.id, workflow="review", profile="balanced",
            prompt="eof", execution_plan_json="{}", context_key="f" * 10000,
        )
        runtime.database.finish_job("eof-output", "succeeded", text="done")
        for job_id, offset in (("empty-output", 0), ("eof-output", 4)):
            response = await client.call_tool("job_wait", {
                "job_id": job_id, "timeout_s": 0, "result_offset": offset,
            })
            assert response.is_error
            assert json.loads(response.content[0].text)["code"] == "response_too_large"
            envelope = json.dumps(response.model_dump(by_alias=True, mode="json", exclude_none=True), separators=(",", ":"))
            assert len(envelope) < 30000 and len(envelope.encode("utf-8")) < 9000

        runtime.database.create_job(
            job_id="empty-fitting", project_id=project.id, workflow="review", profile="balanced",
            prompt="empty", execution_plan_json="{}", context_key="short",
        )
        runtime.database.finish_job("empty-fitting", "succeeded", text="")
        empty_ok = await client.call_tool("job_wait", {"job_id": "empty-fitting", "timeout_s": 0})
        assert not empty_ok.is_error
        assert json.loads(empty_ok.content[0].text)["result"] == {"text": "", "error": "", "next_offset": None}

        runtime.database.create_job(
            job_id="eof-fitting", project_id=project.id, workflow="review", profile="balanced",
            prompt="eof", execution_plan_json="{}", context_key="short-eof",
        )
        runtime.database.finish_job("eof-fitting", "succeeded", text="done")
        eof_ok = await client.call_tool("job_wait", {"job_id": "eof-fitting", "timeout_s": 0, "result_offset": 4})
        assert not eof_ok.is_error
        assert json.loads(eof_ok.content[0].text)["result"] == {"text": "", "error": "", "next_offset": None}


@pytest.mark.parametrize(("result_text", "offset"), [("", 0), ("done", 4)])
def test_empty_or_eof_page_fit_loop_has_finite_sentinel(monkeypatch, result_text, offset) -> None:
    from openmcp import server

    job = _job_view("succeeded")
    job.result = JobResult(text=result_text)
    calls = 0

    def bounded_never_fits(_text, *, is_error=False):
        nonlocal calls
        calls += 1
        if calls > 8:
            raise AssertionError("page fit loop failed to terminate")
        return False

    monkeypatch.setattr(server, "_fits_response", bounded_never_fits)
    with pytest.raises(server.OpenMCPError) as raised:
        server._page_terminal_result(job, {"id": job.id}, offset)
    assert raised.value.code == "response_too_large"


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


def _stub_job_record(_job_id: str) -> dict[str, str]:
    return {"access_mode": "exclusive"}


def _stub_job_dependencies(_job_id: str) -> list[str]:
    return []


def test_job_wait_constants() -> None:
    from openmcp import server

    assert server._MCP_WAIT_TIMEOUT_S == 3600
    assert server._MCP_HEARTBEAT_INTERVAL_S == 30


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout_s", [0, 5, 30, 3600])
async def test_job_wait_uses_timeout_and_returns_v2_page_shape(timeout_s: int) -> None:
    initial = _job_view("running")
    latest = _job_view("succeeded")
    waits: list[tuple[str, int]] = []
    state = {"job": initial}

    class Database:
        def job(self, job_id: str) -> JobView:
            assert job_id == initial.id
            return state["job"]

        job_record = staticmethod(_stub_job_record)
        dependencies_for_job = staticmethod(_stub_job_dependencies)

    class Runtime:
        database = Database()

        def waiting_metadata(self, job_id: str):
            return [], ""

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
    result = json.loads(await job_wait(initial.id, ctx, timeout_s=timeout_s))

    assert waits == ([] if timeout_s == 0 else [(initial.id, timeout_s)])
    assert result["job"]["state"] == ("running" if timeout_s == 0 else "succeeded")
    assert result["result"] == {"text": "", "error": "", "next_offset": None}
    assert json.loads(progress_messages[0]) == {"state": "running", "waiting_reason": ""}


@pytest.mark.asyncio
async def test_job_wait_heartbeat_loop_reports_progress_until_terminal(monkeypatch) -> None:
    from openmcp import server

    monkeypatch.setattr(server, "_MCP_HEARTBEAT_INTERVAL_S", 0.005)
    current_job = _job_view("running")
    done_event = asyncio.Event()
    progress_reports: list[tuple[float, float | None, str]] = []

    class Database:
        def job(self, job_id: str) -> JobView:
            assert job_id == current_job.id
            return current_job

        job_record = staticmethod(_stub_job_record)
        dependencies_for_job = staticmethod(_stub_job_dependencies)

    class Runtime:
        database = Database()

        def waiting_metadata(self, job_id: str):
            return [], ""

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

    result = json.loads(await job_wait(current_job.id, ctx, timeout_s=3600))
    assert result["job"]["state"] == "succeeded"
    assert [report[:2] for report in progress_reports] == [
        (0.0, None),
        (1.0, None),
        (2.0, None),
    ]
    assert all(json.loads(message) == {"state": "running", "waiting_reason": ""} for _, _, message in progress_reports)


@pytest.mark.asyncio
async def test_job_wait_rejects_negative_timeout_before_job_lookup() -> None:
    class Database:
        def job(self, job_id: str) -> JobView:
            raise AssertionError("job lookup should not happen")

    runtime = SimpleNamespace(database=Database())
    ctx = SimpleNamespace(request_context=SimpleNamespace(lifespan_context=runtime))

    with pytest.raises(Exception) as raised:
        await job_wait("job-1", ctx, timeout_s=-1)
    assert getattr(raised.value, "code", "") == "invalid_request"


@pytest.mark.asyncio
async def test_job_wait_non_terminal_timeout(monkeypatch) -> None:
    from openmcp import server

    monkeypatch.setattr(server, "_MCP_HEARTBEAT_INTERVAL_S", 0.005)
    current_job = _job_view("running")
    progress_messages: list[str] = []
    timeout_event = asyncio.Event()

    class Database:
        def job(self, job_id: str) -> JobView:
            assert job_id == current_job.id
            return current_job

        job_record = staticmethod(_stub_job_record)
        dependencies_for_job = staticmethod(_stub_job_dependencies)

    class Runtime:
        database = Database()

        def waiting_metadata(self, job_id: str):
            return [], ""

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

    result = json.loads(await job_wait(current_job.id, ctx, timeout_s=10))
    assert result["job"]["state"] == "running"
    assert result["result"]["text"] == ""
    assert result["next_action"] == "Call job_wait again with the same job_id."
    assert len(progress_messages) == 3


@pytest.mark.asyncio
async def test_job_wait_cancellation_cleanup() -> None:
    current_job = _job_view("running")
    wait_started = asyncio.Event()
    wait_cancelled = asyncio.Event()

    class Database:
        def job(self, job_id: str) -> JobView:
            assert job_id == current_job.id
            return current_job

        job_record = staticmethod(_stub_job_record)
        dependencies_for_job = staticmethod(_stub_job_dependencies)

    class Runtime:
        database = Database()

        def waiting_metadata(self, job_id: str):
            return [], ""

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

    task = asyncio.create_task(job_wait(current_job.id, ctx, timeout_s=3600))
    await wait_started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert wait_cancelled.is_set()


@pytest.mark.asyncio
async def test_job_wait_returns_terminal_job_without_waiting() -> None:
    terminal = _job_view("failed")
    waits: list[str] = []
    progress_messages: list[str] = []

    class Database:
        @staticmethod
        def job(job_id: str) -> JobView:
            return terminal

        job_record = staticmethod(_stub_job_record)
        dependencies_for_job = staticmethod(_stub_job_dependencies)

    class Runtime:
        database = Database()

        def waiting_metadata(self, job_id: str):
            return [], ""

        async def wait(self, job_id: str, timeout_s: int) -> JobView:
            waits.append(job_id)
            return terminal

    async def report_progress(*, progress: float, total: float, message: str) -> None:
        progress_messages.append(message)

    ctx = SimpleNamespace(
        request_context=SimpleNamespace(lifespan_context=Runtime()),
        report_progress=report_progress,
    )

    result = json.loads(await job_wait(terminal.id, ctx))
    assert result["job"]["state"] == "failed"
    assert waits == []
    assert json.loads(progress_messages[0]) == {"state": "failed", "waiting_reason": ""}


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
async def test_job_wait_logs_progress_token_presence(caplog, wire_meta, expected_present) -> None:
    import logging
    from mcp.server.runner import _extract_meta

    terminal = _job_view("succeeded")

    class Database:
        @staticmethod
        def job(job_id: str) -> JobView:
            return terminal

        job_record = staticmethod(_stub_job_record)
        dependencies_for_job = staticmethod(_stub_job_dependencies)

    class Runtime:
        database = Database()

        def waiting_metadata(self, job_id: str):
            return [], ""

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

    with caplog.at_level(logging.INFO, logger="openmcp.server"):
        result = json.loads(await job_wait(terminal.id, ctx))

    assert result["job"]["state"] == "succeeded"
    records = [
        record
        for record in caplog.records
        if getattr(record, "operation", "") == "job_wait"
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
    import openmcp.server as server

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
        def __init__(self, received_config) -> None:
            assert received_config is config

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
        def __init__(self, received_config) -> None:
            assert received_config is config

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
