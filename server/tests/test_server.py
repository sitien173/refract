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
from refract.models import JobResult, JobSummary, JobView, SubmissionResult
from refract.result_metadata import JobResultMetadata
from refract.runtime import OrchestrationError, Runtime
from refract.scheduler import _Dispatch
from refract.server import RefractError, job_answer, job_wait, mcp
from tests.orchestration_helpers import register_project


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
async def test_v2_tool_surface_lists_exact_contract() -> None:
    expected = {
        "project_resolve": {"path", "alias"},
        "task_guide": {"project_id"},
        "job_submit": {"project_id", "workflow", "prompt", "profile", "context_key", "fresh_session", "next_target"},
        "job_wait": {"job_id", "timeout_s", "result_offset"},
        "job_list": {"project_id"},
        "job_cancel": {"job_id"},
        "job_retry": {"job_id"},
        "job_answer": {"job_id", "answer"},
        "job_report_error": {"job_id", "category", "expected", "observed", "report_key"},
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

    payload = RefractError("targets_unavailable", "open", "wait", True, 8).to_payload()
    assert payload["retry_after_s"] == 8
    assert _valid_refract_error(payload) == payload
    assert _valid_refract_error({**payload, "retry_after_s": True}) is None
    assert _valid_refract_error({"code": "invalid_request", "message": "x", "next_action": "x", "retryable": False, "retry_after_s": 8}) is None


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
async def test_v2_tool_schema_limits_annotations_and_no_legacy_tools() -> None:
    tools = {tool.name: tool for tool in await mcp.list_tools()}
    assert set(tools) == {
        "project_resolve", "task_guide", "job_submit", "job_wait",
        "job_list", "job_cancel", "job_retry", "job_answer", "job_report_error",
    }
    from refract.workflows import BUILTIN_WORKFLOWS

    assert tools["job_submit"].input_schema["properties"]["workflow"]["enum"] == list(BUILTIN_WORKFLOWS)
    assert tools["job_wait"].input_schema["properties"]["timeout_s"]["minimum"] == 0
    assert tools["job_wait"].input_schema["properties"]["timeout_s"]["maximum"] == 3600
    assert tools["job_wait"].input_schema["properties"]["result_offset"]["minimum"] == 0
    assert tools["job_submit"].input_schema["properties"]["fresh_session"]["default"] is False
    assert tools["job_report_error"].input_schema["properties"]["category"]["enum"] == ["protocol", "output"]
    assert tools["job_report_error"].input_schema["properties"]["expected"]["maxLength"] == 2048
    assert tools["job_report_error"].input_schema["properties"]["observed"]["maxLength"] == 2048
    assert tools["job_report_error"].input_schema["properties"]["report_key"]["maxLength"] == 128
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
        "job_answer": (False, False, False, False),
        "job_report_error": (False, False, True, False),
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
        "id", "project_id", "workflow", "profile", "state", "context_key",
        "attempts", "created_at", "updated_at",
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
async def test_job_submit_rejects_depends_on_and_summary_has_reduced_fields(tmp_path, monkeypatch) -> None:
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        root = tmp_path / "reduced-summary-project"
        root.mkdir()
        project = register_project(runtime, str(root), "reduced-summary")
        rejected = await client.call_tool(
            "job_submit",
            {"project_id": project.id, "workflow": "consult", "prompt": "x", "depends_on": []},
        )
        assert rejected.is_error
        assert json.loads(rejected.content[0].text)["code"] == "invalid_request"

        submitted = await client.call_tool(
            "job_submit", {"project_id": project.id, "workflow": "consult", "prompt": "x"}
        )
        assert not submitted.is_error
        summary_fields = {
            "id", "project_id", "workflow", "profile", "state", "context_key",
            "attempts", "created_at", "updated_at",
        }
        submitted_summary = json.loads(submitted.content[0].text)["job"]
        assert set(submitted_summary) == summary_fields
        cancelled = await client.call_tool("job_cancel", {"job_id": submitted_summary["id"]})
        assert not cancelled.is_error
        cancelled_payload = json.loads(cancelled.content[0].text)
        assert set(cancelled_payload) == {"job"}
        assert set(cancelled_payload["job"]) == summary_fields


@pytest.mark.asyncio
async def test_inprocess_client_sanitizes_unexpected_tool_exception(tmp_path, monkeypatch) -> None:
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        root = tmp_path / "internal-error-project"
        root.mkdir()
        project = register_project(runtime, str(root))
        secret = "provider-secret-that-must-not-escape"

        def fail_listing(_project_id: str):
            raise RuntimeError(secret)

        runtime.database.job_listing = fail_listing
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
        project = register_project(runtime, str(project_root), "pages")
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
        project = register_project(runtime, str(root), "guide")
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
        project = register_project(runtime, str(root), "coercion")
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
    from refract.server import RefractError, _page_terminal_result

    job = _job_view("succeeded")
    job.result = JobResult(text="😀😀")
    job.context_key = "x" * 9000
    summary = JobSummary(
        id=job.id, project_id=job.project_id, workflow=job.workflow, profile=job.profile,
        state=job.state, context_key=job.context_key,
        attempts=0,
        created_at=job.created_at, updated_at=job.updated_at,
    ).model_dump(mode="json")
    empty_page = json.dumps(
        {"job": summary, "result": {"text": "", "error": "", "next_offset": 0, "metadata": {}}},
        ensure_ascii=False, separators=(",", ":"),
    )
    from refract.server import _fits_response
    assert not _fits_response(empty_page)
    with pytest.raises(RefractError) as raised:
        _page_terminal_result(job, summary, 0)
    assert raised.value.code == "response_too_large"


@pytest.mark.asyncio
async def test_expected_runtime_error_families_are_compact_json(tmp_path, monkeypatch) -> None:
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        root = tmp_path / "errors-project"
        root.mkdir()
        project = register_project(runtime, str(root), "errors")

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

        runtime.database.create_job(
            job_id="failed-parent", project_id=project.id, workflow="review", profile="balanced",
            prompt="parent", execution_plan_json="{}", context_key="parent",
        )
        runtime.database.finish_job("failed-parent", "failed")
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
async def test_mcp_job_submit_all_open_returns_retry_delay(tmp_path, monkeypatch) -> None:
    from refract.planning import target_execution_key

    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        root = tmp_path / "submit-all-open"
        root.mkdir()
        project = register_project(runtime, str(root), "submit-all-open")
        target = runtime.catalog.targets[0]
        runtime.database._connection.execute(
            "INSERT OR REPLACE INTO target_health(target_id, consecutive_failures, circuit_open_until, cooldown_s, probe_job_id) VALUES (?, 1, '2999-01-01T00:00:00+00:00', 60, '')",
            (target_execution_key(target),),
        )
        runtime.database._connection.commit()
        response = await client.call_tool("job_submit", {"project_id": project.id, "workflow": "consult", "prompt": "blocked"})
        assert response.is_error
        payload = json.loads(response.content[0].text)
        assert payload["code"] == "targets_unavailable"
        assert payload["retryable"] is True and type(payload["retry_after_s"]) is int
        assert runtime.database.jobs(project.id) == []


@pytest.mark.asyncio
async def test_multipage_terminal_wait_has_metadata_and_stays_private_and_bounded(tmp_path, monkeypatch) -> None:
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        root = tmp_path / "multipage-terminal"
        root.mkdir()
        project = register_project(runtime, str(root), "multipage-terminal")
        runtime.database.create_job(job_id="multi-terminal", project_id=project.id, workflow="consult", profile="balanced", prompt="x", execution_plan_json="{}", context_key="multi")
        runtime.database.finish_job("multi-terminal", "succeeded", text="z" * 40_000)
        offset = 0
        pages = 0
        forbidden = {"target_id", "backend"}
        while True:
            response = await client.call_tool("job_wait", {"job_id": "multi-terminal", "timeout_s": 0, "result_offset": offset})
            assert not response.is_error
            wire = response.model_dump(by_alias=True, mode="json", exclude_none=True)
            serialized = json.dumps(wire, ensure_ascii=False, separators=(",", ":"))
            assert len(serialized.encode("utf-8")) < 9000
            payload = json.loads(response.content[0].text)
            assert set(payload["result"]["metadata"]) == {"execution", "failure", "retry", "telemetry"}
            def inspect_private(value):
                if isinstance(value, dict):
                    assert forbidden.isdisjoint(key.casefold() for key in value)
                    for item in value.values(): inspect_private(item)
                elif isinstance(value, list):
                    for item in value: inspect_private(item)
            inspect_private(payload)
            pages += 1
            next_offset = payload["result"]["next_offset"]
            if next_offset is None: break
            offset = next_offset
        assert pages > 1


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

        forbidden = {"access_mode", "target_id", "backend", "model", "resource_uri", "config_revision"}
        def visit(value, in_metadata: bool = False):
            if isinstance(value, dict):
                current_forbidden = forbidden - {"model"} if in_metadata else forbidden
                assert current_forbidden.isdisjoint(key.casefold() for key in value)
                for k, item in value.items():
                    visit(item, in_metadata=(in_metadata or k == "metadata"))
            elif isinstance(value, list):
                for item in value:
                    visit(item, in_metadata=in_metadata)
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
        project = register_project(runtime, str(root), "overflow")

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
        project = register_project(runtime, str(root), "private-failure")
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
async def test_public_terminal_error_preserves_execution_task_cancellation(tmp_path, monkeypatch) -> None:
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        root = tmp_path / "cancel-error"
        root.mkdir()
        project = register_project(runtime, str(root), "cancel-error")
        runtime.database.create_job(
            job_id="cancel-cause", project_id=project.id, workflow="review", profile="balanced",
            prompt="cancelled", execution_plan_json="{}", context_key="cancel-cause",
        )
        runtime.database.finish_job("cancel-cause", "cancelled", error="execution task cancelled")

        response = await client.call_tool("job_wait", {"job_id": "cancel-cause", "timeout_s": 0})

        assert json.loads(response.content[0].text)["result"]["error"] == "execution task cancelled"


@pytest.mark.asyncio
async def test_empty_and_eof_result_metadata_overflow_is_bounded(tmp_path, monkeypatch) -> None:
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        root = tmp_path / "empty-eof-overflow"
        root.mkdir()
        project = register_project(runtime, str(root), "empty-eof-overflow")
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
        assert json.loads(empty_ok.content[0].text)["result"] == {"text": "", "error": "", "next_offset": None, "metadata": JobResultMetadata().model_dump(mode="json")}

        runtime.database.create_job(
            job_id="eof-fitting", project_id=project.id, workflow="review", profile="balanced",
            prompt="eof", execution_plan_json="{}", context_key="short-eof",
        )
        runtime.database.finish_job("eof-fitting", "succeeded", text="done")
        eof_ok = await client.call_tool("job_wait", {"job_id": "eof-fitting", "timeout_s": 0, "result_offset": 4})
        assert not eof_ok.is_error
        assert json.loads(eof_ok.content[0].text)["result"] == {"text": "", "error": "", "next_offset": None, "metadata": JobResultMetadata().model_dump(mode="json")}


@pytest.mark.parametrize(("result_text", "offset"), [("", 0), ("done", 4)])
def test_empty_or_eof_page_fit_loop_has_finite_sentinel(monkeypatch, result_text, offset) -> None:
    from refract import server

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
    with pytest.raises(server.RefractError) as raised:
        server._page_terminal_result(job, {"id": job.id}, offset)
    assert raised.value.code == "response_too_large"


def test_public_data_filters_unvalidated_metadata_and_preserves_canonical_execution_model() -> None:
    from refract.server import _public_data
    from refract.result_metadata import JobResultMetadata, ExecutionMetadata

    arbitrary = {"metadata": {"backend": "synthetic-private-backend", "execution": {"model": "unvalidated-private-model"}}}
    filtered = _public_data(arbitrary)
    assert filtered == {"metadata": {"execution": {}}}
    canonical = JobResultMetadata(execution=ExecutionMetadata(model="allowed-model"))
    public = _public_data({"metadata": canonical})
    assert public["metadata"]["execution"]["model"] == "allowed-model"
    assert set(public["metadata"]) == {"execution", "failure", "retry", "telemetry"}
    assert public["metadata"]["failure"] is None
    assert public["metadata"]["telemetry"]["completeness"] == "unavailable"


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


def test_terminal_page_rejects_malformed_canonical_metadata_and_keeps_unavailable_shape() -> None:
    from refract.server import _page_terminal_result

    job = _job_view("succeeded")
    with pytest.raises(ValueError):
        _page_terminal_result(job, {"id": job.id}, 0, metadata={"execution": {}, "retry": {"legacy": True}})
    payload = json.loads(_page_terminal_result(job, {"id": job.id}, 0))
    metadata = payload["result"]["metadata"]
    assert set(metadata) == {"execution", "failure", "retry", "telemetry"}
    assert metadata["failure"] is None
    assert metadata["telemetry"]["completeness"] == "unavailable"
    assert metadata["telemetry"]["total_input_tokens"] == {"value": None, "source": None, "quality": "unavailable", "observed_at": None}


def _stub_job_record(_job_id: str) -> dict[str, str]:
    return {}


def test_job_wait_constants() -> None:
    from refract import server

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

    class Runtime:
        database = Database()

        def live_result_metadata(self, job: JobView):
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
    result = json.loads(await job_wait(initial.id, ctx, timeout_s=timeout_s))

    assert waits == ([] if timeout_s == 0 else [(initial.id, timeout_s)])
    assert result["job"]["state"] == ("running" if timeout_s == 0 else "succeeded")
    assert result["result"] == ({"text": "", "error": "", "next_offset": None} if timeout_s == 0 else {"text": "", "error": "", "next_offset": None, "metadata": JobResultMetadata().model_dump(mode="json")})
    assert json.loads(progress_messages[0]) == {"state": "running"}


@pytest.mark.asyncio
async def test_job_wait_heartbeat_loop_reports_progress_until_terminal(monkeypatch) -> None:
    from refract import server

    monkeypatch.setattr(server, "_MCP_HEARTBEAT_INTERVAL_S", 0.005)
    current_job = _job_view("running")
    done_event = asyncio.Event()
    progress_reports: list[tuple[float, float | None, str]] = []

    class Database:
        def job(self, job_id: str) -> JobView:
            assert job_id == current_job.id
            return current_job

        job_record = staticmethod(_stub_job_record)

    class Runtime:
        database = Database()

        def live_result_metadata(self, job: JobView):
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

    result = json.loads(await job_wait(current_job.id, ctx, timeout_s=3600))
    assert result["job"]["state"] == "succeeded"
    assert [report[:2] for report in progress_reports] == [
        (0.0, None),
        (1.0, None),
        (2.0, None),
    ]
    assert all(json.loads(message) == {"state": "running"} for _, _, message in progress_reports)


@pytest.mark.asyncio
async def test_job_wait_rejects_negative_timeout_before_job_lookup(tmp_path, monkeypatch) -> None:
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        def unexpected_lookup(job_id):
            raise AssertionError("job lookup should not happen")

        monkeypatch.setattr(runtime.database, "job", unexpected_lookup)
        result = await client.call_tool("job_wait", {"job_id": "job-1", "timeout_s": -1})
        assert result.is_error
        assert json.loads(result.content[0].text)["code"] == "invalid_request"


@pytest.mark.asyncio
async def test_job_wait_non_terminal_timeout(monkeypatch) -> None:
    from refract import server

    monkeypatch.setattr(server, "_MCP_HEARTBEAT_INTERVAL_S", 0.005)
    current_job = _job_view("running")
    progress_messages: list[str] = []
    timeout_event = asyncio.Event()

    class Database:
        def job(self, job_id: str) -> JobView:
            assert job_id == current_job.id
            return current_job

        job_record = staticmethod(_stub_job_record)

    class Runtime:
        database = Database()

        def live_result_metadata(self, job: JobView):
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

    class Runtime:
        database = Database()

        def live_result_metadata(self, job: JobView):
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

    task = asyncio.create_task(job_wait(current_job.id, ctx, timeout_s=3600))
    await wait_started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert wait_cancelled.is_set()


@pytest.mark.asyncio
async def test_job_wait_propagates_cancellation_during_child_cleanup(monkeypatch) -> None:
    from refract import server

    monkeypatch.setattr(server, "_MCP_HEARTBEAT_INTERVAL_S", 0.005)
    current_job = _job_view("running")
    cleanup_started = asyncio.Event()

    class Database:
        def job(self, job_id: str) -> JobView:
            return current_job

        job_record = staticmethod(_stub_job_record)

    class Runtime:
        database = Database()

        def live_result_metadata(self, job: JobView):
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
    task = asyncio.create_task(job_wait(current_job.id, ctx, timeout_s=3600))
    try:
        await asyncio.wait_for(cleanup_started.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


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

    class Runtime:
        database = Database()

        def live_result_metadata(self, job: JobView):
            return job.result.metadata

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
async def test_job_wait_logs_progress_token_presence(caplog, wire_meta, expected_present) -> None:
    import logging
    from mcp.server.runner import _extract_meta

    terminal = _job_view("succeeded")

    class Database:
        @staticmethod
        def job(job_id: str) -> JobView:
            return terminal

        job_record = staticmethod(_stub_job_record)

    class Runtime:
        database = Database()

        def live_result_metadata(self, job: JobView):
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
async def test_runtime_wait_and_job_wait_wake_early_with_pending_question(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    config_path = home / "config.toml"
    config_path.write_text(_serve_config(), encoding="utf-8")
    runtime = Runtime(load_config(config_path))
    try:
        project = register_project(runtime, str(tmp_path), "test-proj")
        runtime.database.create_job(
            job_id="job-q-1",
            project_id=project.id,
            workflow="consult",
            profile="balanced",
            prompt="Do work",
            execution_plan_json="{}",
            context_key="c1",
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

        # 2. Test job_wait returns pending_question
        ctx = SimpleNamespace(
            request_context=SimpleNamespace(lifespan_context=runtime),
            report_progress=lambda **kwargs: asyncio.sleep(0),
        )
        res_str = await job_wait("job-q-1", ctx, timeout_s=10)
        res = json.loads(res_str)
        assert res["job"]["state"] == "running"
        assert "pending_question" in res["result"]
        pq = res["result"]["pending_question"]
        assert pq["text"] == "Need input on schema"
        assert pq["question_id"].startswith("q_")
        assert res["next_action"] == "Call job_answer to answer the pending question."

        # 3. Test job_answer delivers answer
        ans_str = await job_answer("job-q-1", "Use v2 schema", ctx)
        ans = json.loads(ans_str)
        assert ans["job"]["id"] == "job-q-1"
        assert not runtime.ask_registry.has_pending("job-q-1")

        # HTTP ask receives answer
        asked_result = await task
        assert asked_result == "Use v2 schema"
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_job_answer_errors(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    config_path = home / "config.toml"
    config_path.write_text(_serve_config(), encoding="utf-8")
    runtime = Runtime(load_config(config_path))
    try:
        project = register_project(runtime, str(tmp_path), "test-proj")
        runtime.database.create_job(
            job_id="job-running",
            project_id=project.id,
            workflow="consult",
            profile="balanced",
            prompt="Do work",
            execution_plan_json="{}",
            context_key="c1",
        )
        runtime.database.create_job(
            job_id="job-succeeded",
            project_id=project.id,
            workflow="consult",
            profile="balanced",
            prompt="Do work",
            execution_plan_json="{}",
            context_key="c1",
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
            await job_answer("job-nonexistent", "ans", ctx)
        assert exc_info.value.code == "unknown_job"

        # 2. Terminal job -> invalid_state error
        with pytest.raises(RefractError) as exc_info:
            await job_answer("job-succeeded", "ans", ctx)
        assert exc_info.value.code == "invalid_state"

        # 3. Running job with no question pending -> invalid_state error
        with pytest.raises(RefractError) as exc_info:
            await job_answer("job-running", "ans", ctx)
        assert exc_info.value.code == "invalid_state"
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_job_wait_nonterminal_without_question(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    config_path = home / "config.toml"
    config_path.write_text(_serve_config(), encoding="utf-8")
    runtime = Runtime(load_config(config_path))
    try:
        project = register_project(runtime, str(tmp_path), "test-proj")
        runtime.database.create_job(
            job_id="job-running-no-q",
            project_id=project.id,
            workflow="consult",
            profile="balanced",
            prompt="Do work",
            execution_plan_json="{}",
            context_key="c1",
        )
        with runtime.database._connection:
            runtime.database._connection.execute("UPDATE jobs SET state='running' WHERE id='job-running-no-q'")

        ctx = SimpleNamespace(
            request_context=SimpleNamespace(lifespan_context=runtime),
            report_progress=lambda **kwargs: asyncio.sleep(0),
        )

        res_str = await job_wait("job-running-no-q", ctx, timeout_s=0)
        res = json.loads(res_str)
        assert res["job"]["state"] == "running"
        assert res["result"] == {"text": "", "error": "", "next_offset": None}
        assert "pending_question" not in res["result"]
        assert res["next_action"] == "Call job_wait again with the same job_id."
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_connected_client_job_answer_and_wait(tmp_path, monkeypatch) -> None:
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        project = register_project(runtime, str(tmp_path), "test-proj")
        runtime.database.create_job(
            job_id="job-client-test",
            project_id=project.id,
            workflow="consult",
            profile="balanced",
            prompt="Do work",
            execution_plan_json="{}",
            context_key="c1",
        )
        with runtime.database._connection:
            runtime.database._connection.execute("UPDATE jobs SET state='running' WHERE id='job-client-test'")
        runtime.scheduler._current["job-client-test"] = _Dispatch(job_id="job-client-test", project_id=project.id)
        token = runtime.ask_registry.issue_token("job-client-test")

        async def _ask_later():
            await asyncio.sleep(0.05)
            return await runtime.ask_registry.ask(token, "Question via client", timeout_s=5.0)

        task = asyncio.create_task(_ask_later())

        # job_wait wakes early
        wait_res = await client.call_tool("job_wait", {"job_id": "job-client-test", "timeout_s": 10})
        assert not wait_res.is_error
        wait_data = json.loads(wait_res.content[0].text)
        assert wait_data["job"]["state"] == "running"
        assert wait_data["result"]["pending_question"]["text"] == "Question via client"

        # job_answer delivers
        ans_res = await client.call_tool("job_answer", {"job_id": "job-client-test", "answer": "Answer via client"})
        assert not ans_res.is_error
        ans_data = json.loads(ans_res.content[0].text)
        assert ans_data["job"]["id"] == "job-client-test"

        asked_result = await task
        assert asked_result == "Answer via client"


@pytest.mark.asyncio
async def test_job_answer_bounds_and_unicode_acceptance(tmp_path, monkeypatch) -> None:
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        project = register_project(runtime, str(tmp_path), "test-proj")
        runtime.database.create_job(
            job_id="job-bounds-test",
            project_id=project.id,
            workflow="consult",
            profile="balanced",
            prompt="Do work",
            execution_plan_json="{}",
            context_key="c1",
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
        mcp_res = await client.call_tool("job_answer", {"job_id": "job-bounds-test", "answer": oversized})
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
async def test_job_wait_oversized_pending_question_raises_response_too_large(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    config_path = home / "config.toml"
    config_path.write_text(_serve_config(), encoding="utf-8")
    runtime = Runtime(load_config(config_path))
    try:
        project = register_project(runtime, str(tmp_path), "test-proj")
        runtime.database.create_job(
            job_id="job-oversized-q",
            project_id=project.id,
            workflow="consult",
            profile="balanced",
            prompt="Do work",
            execution_plan_json="{}",
            context_key="c1",
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
            await job_wait("job-oversized-q", ctx, timeout_s=0)
        assert exc_info.value.code == "response_too_large"
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_real_asgi_ask_and_mcp_job_wait_job_answer_integration(tmp_path, monkeypatch) -> None:
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

        project = register_project(runtime, str(tmp_path), "test-proj")
        runtime.database.create_job(
            job_id="job-asgi-1",
            project_id=project.id,
            workflow="consult",
            profile="balanced",
            prompt="Do work",
            execution_plan_json="{}",
            context_key="c1",
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

        # 2. Call job_wait via MCP -> wakes early with pending_question
        wait_res = await client.call_tool("job_wait", {"job_id": "job-asgi-1", "timeout_s": 15})
        assert not wait_res.is_error
        wait_data = json.loads(wait_res.content[0].text)
        assert wait_data["job"]["state"] == "running"
        assert wait_data["result"]["pending_question"]["text"] == "Need ASGI confirmation?"

        # 3. Call job_answer via MCP -> delivers answer
        ans_res = await client.call_tool("job_answer", {"job_id": "job-asgi-1", "answer": "Confirmed via MCP"})
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
        project = register_project(runtime, str(tmp_path), "test-proj")
        runtime.database.create_job(
            job_id="job-err-1",
            project_id=project.id,
            workflow="consult",
            profile="balanced",
            prompt="Do work",
            execution_plan_json="{}",
            context_key="c1",
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
        project = register_project(runtime, str(tmp_path), "test-proj")
        runtime.database.create_job(
            job_id="job-t0-1",
            project_id=project.id,
            workflow="consult",
            profile="balanced",
            prompt="Do work",
            execution_plan_json="{}",
            context_key="c1",
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
async def test_job_wait_running_returns_persisted_synthetic_telemetry(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    config_path = home / "config.toml"
    config_path.write_text(_serve_config(), encoding="utf-8")
    runtime = Runtime(load_config(config_path))
    try:
        project = register_project(runtime, str(tmp_path), "test-proj")
        runtime.database.create_job(
            job_id="job-running-tel",
            project_id=project.id,
            workflow="consult",
            profile="balanced",
            prompt="Do work",
            execution_plan_json="{}",
            context_key="c1",
        )
        with runtime.database._connection:
            runtime.database._connection.execute("UPDATE jobs SET state='running' WHERE id='job-running-tel'")

        synthetic_telemetry = {
            "version": 1,
            "completeness": "complete",
            "context_used_tokens": {"value": 1500, "source": "provider", "quality": "reported"},
            "context_window_size": {"value": 8000, "source": "provider", "quality": "reported"},
            "total_input_tokens": {"value": 300, "source": "provider", "quality": "reported"},
            "total_output_tokens": {"value": 100, "source": "provider", "quality": "reported"},
        }
        runtime.database.merge_job_telemetry("job-running-tel", synthetic_telemetry)

        ctx = SimpleNamespace(
            request_context=SimpleNamespace(lifespan_context=runtime),
            report_progress=lambda **kwargs: asyncio.sleep(0),
        )

        res_str = await job_wait("job-running-tel", ctx, timeout_s=0)
        res = json.loads(res_str)
        assert res["job"]["state"] == "running"
        assert "metadata" in res["result"]
        tel = res["result"]["metadata"]["telemetry"]
        assert tel["context_used_tokens"]["value"] == 1500
        assert tel["total_input_tokens"]["value"] == 300
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_job_wait_paginated_retains_identical_telemetry(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    config_path = home / "config.toml"
    config_path.write_text(_serve_config(), encoding="utf-8")
    runtime = Runtime(load_config(config_path))
    try:
        project = register_project(runtime, str(tmp_path), "test-proj")
        long_text = "word " * 15000  # large enough to paginate across multiple pages
        runtime.database.create_job(
            job_id="job-paged-tel",
            project_id=project.id,
            workflow="consult",
            profile="balanced",
            prompt="Do work",
            execution_plan_json="{}",
            context_key="c1",
        )
        synthetic_telemetry = {
            "completeness": "complete",
            "context_used_tokens": {"value": 2500, "source": "provider", "quality": "reported", "observed_at": "2026-01-01T00:00:00Z"},
            "total_input_tokens": {"value": 600, "source": "provider", "quality": "reported", "observed_at": "2026-01-01T00:00:00Z"},
        }
        runtime.database.finish_job(
            "job-paged-tel",
            "succeeded",
            text=long_text,
            metadata={"telemetry": synthetic_telemetry},
        )

        ctx = SimpleNamespace(
            request_context=SimpleNamespace(lifespan_context=runtime),
            report_progress=lambda **kwargs: asyncio.sleep(0),
        )

        page1_str = await job_wait("job-paged-tel", ctx, timeout_s=0, result_offset=0)
        page1 = json.loads(page1_str)
        next_offset = page1["result"]["next_offset"]
        assert next_offset is not None
        assert page1["result"]["metadata"]["telemetry"]["context_used_tokens"]["value"] == 2500

        page2_str = await job_wait("job-paged-tel", ctx, timeout_s=0, result_offset=next_offset)
        page2 = json.loads(page2_str)
        assert page2["result"]["metadata"]["telemetry"]["context_used_tokens"]["value"] == 2500
        assert page1["result"]["metadata"]["telemetry"] == page2["result"]["metadata"]["telemetry"]
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_job_report_error_mcp_validation_and_acknowledgement(tmp_path, monkeypatch) -> None:
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        project = register_project(runtime, str(tmp_path), "test-proj")
        runtime.database.create_job(
            job_id="job-rep-1",
            project_id=project.id,
            workflow="consult",
            profile="balanced",
            prompt="Hello",
            execution_plan_json="{}",
            context_key="k1",
        )

        # Missing required parameter -> invalid_request
        bad_args = await client.call_tool(
            "job_report_error",
            {"job_id": "job-rep-1", "category": "protocol"},
        )
        assert bad_args.is_error
        bad_payload = json.loads(bad_args.content[0].text)
        assert bad_payload["code"] == "invalid_request"

        # Extra parameter -> invalid_request
        extra_args = await client.call_tool(
            "job_report_error",
            {
                "job_id": "job-rep-1",
                "category": "protocol",
                "expected": "exp",
                "observed": "obs",
                "report_key": "k-1",
                "extra": "forbidden",
            },
        )
        assert extra_args.is_error
        extra_payload = json.loads(extra_args.content[0].text)
        assert extra_payload["code"] == "invalid_request"

        # Valid call returns compact acknowledgement without summaries
        res = await client.call_tool(
            "job_report_error",
            {
                "job_id": "job-rep-1",
                "category": "protocol",
                "expected": "Expected behavior Bearer secret-123",
                "observed": "Observed behavior sk-456",
                "report_key": "k-1",
            },
        )
        assert not res.is_error
        data = json.loads(res.content[0].text)
        assert data["duplicate"] is False
        assert set(data) == {"report", "duplicate"}
        assert set(data["report"]) == {"id", "job_id", "category", "created_at"}
        assert "expected" not in data["report"]
        assert "observed" not in data["report"]
        assert "secret-123" not in res.content[0].text
        assert "sk-456" not in res.content[0].text

        # Duplicate delivery
        dup_res = await client.call_tool(
            "job_report_error",
            {
                "job_id": "job-rep-1",
                "category": "protocol",
                "expected": "Expected behavior Bearer secret-123",
                "observed": "Observed behavior sk-456",
                "report_key": "k-1",
            },
        )
        assert not dup_res.is_error
        dup_data = json.loads(dup_res.content[0].text)
        assert dup_data["duplicate"] is True
        assert dup_data["report"]["id"] == data["report"]["id"]

        # Unknown job
        unk_res = await client.call_tool(
            "job_report_error",
            {
                "job_id": "job-missing",
                "category": "protocol",
                "expected": "exp",
                "observed": "obs",
                "report_key": "k-2",
            },
        )
        assert unk_res.is_error
        unk_payload = json.loads(unk_res.content[0].text)
        assert unk_payload["code"] == "unknown_job"


@pytest.mark.asyncio
async def test_job_report_error_logging_behavior(tmp_path, monkeypatch, caplog) -> None:
    import logging

    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        project = register_project(runtime, str(tmp_path), "test-proj")
        runtime.database.create_job(
            job_id="job-log-1",
            project_id=project.id,
            workflow="consult",
            profile="balanced",
            prompt="Hello",
            execution_plan_json="{}",
            context_key="k1",
        )

        with caplog.at_level(logging.INFO, logger="refract.server"):
            res1 = await client.call_tool(
                "job_report_error",
                {
                    "job_id": "job-log-1",
                    "category": "protocol",
                    "expected": "Expected behavior",
                    "observed": "Observed behavior",
                    "report_key": "log-key-1",
                },
            )
            assert not res1.is_error

            records = [
                r
                for r in caplog.records
                if getattr(r, "event", "") == "job.error_reported"
            ]
            assert len(records) == 1
            rec = records[0]
            assert rec.report_id
            assert rec.job_id == "job-log-1"
            assert rec.project_id == project.id
            assert rec.category == "protocol"
            assert "Expected behavior" not in rec.getMessage()
            assert "Expected behavior" not in str(rec.__dict__)
            assert "Observed behavior" not in rec.getMessage()
            assert "Observed behavior" not in str(rec.__dict__)
            assert "log-key-1" not in rec.getMessage()
            assert "log-key-1" not in str(rec.__dict__)

            # Second call (duplicate delivery): no second job.error_reported log!
            res2 = await client.call_tool(
                "job_report_error",
                {
                    "job_id": "job-log-1",
                    "category": "protocol",
                    "expected": "Expected behavior",
                    "observed": "Observed behavior",
                    "report_key": "log-key-1",
                },
            )
            assert not res2.is_error
            records2 = [
                r
                for r in caplog.records
                if getattr(r, "event", "") == "job.error_reported"
            ]
            assert len(records2) == 1
