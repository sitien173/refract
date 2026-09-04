from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from openmcp.planning import execution_plan_data, resolve_execution_plan
from openmcp.runtime import Runtime
from openmcp.server import create_application
from tests.orchestration_helpers import config


async def request(app, path, *, method="GET", headers=(), body=b"", client_host="127.0.0.1"):
    sent = []
    request_body = body
    received = False

    async def receive():
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": request_body, "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [(key.lower().encode(), value.encode()) for key, value in headers],
        "client": (client_host, 1234),
        "server": ("127.0.0.1", 8765),
        "scheme": "http",
        "root_path": "",
        "app": None,
    }
    await app(scope, receive, send)
    start = next(message for message in sent if message["type"] == "http.response.start")
    chunks = [message.get("body", b"") for message in sent if message["type"] == "http.response.body"]
    return start["status"], dict(start["headers"]), b"".join(chunks)


@pytest.fixture
def active_runtime(tmp_path):
    runtime = Runtime(config(tmp_path / "home"))
    runtime.register_project(str(tmp_path), "project")
    from openmcp import server
    server._DASHBOARD_STATE.runtime = runtime
    server._DASHBOARD_STATE.csrf_token = "test-token"
    try:
        yield runtime
    finally:
        server._DASHBOARD_STATE.runtime = None
        server._DASHBOARD_STATE.csrf_token = ""
        runtime.database.close()


@pytest.mark.asyncio
async def test_dashboard_reads_fail_closed_without_runtime() -> None:
    from openmcp import server
    server._DASHBOARD_STATE.runtime = None
    app = create_application()

    status, _, body = await request(app, "/dashboard/api/overview")

    assert status == 503
    assert json.loads(body)["error"] == "OpenMCP runtime is not active"


@pytest.mark.asyncio
async def test_dashboard_bootstrap_is_loopback_only_and_not_cached(active_runtime) -> None:
    app = create_application()

    status, headers, body = await request(
        app,
        "/dashboard/api/bootstrap",
        headers=(("Host", "127.0.0.1"),),
    )
    remote, _, _ = await request(
        app,
        "/dashboard/api/bootstrap",
        headers=(("Host", "127.0.0.1"),),
        client_host="192.0.2.1",
    )

    assert status == 200
    assert headers[b"cache-control"] == b"no-store"
    assert json.loads(body)["csrf_token"] == "test-token"
    assert remote == 403


@pytest.mark.asyncio
async def test_dashboard_overview_separates_daemon_and_configuration(active_runtime) -> None:
    app = create_application()

    status, _, body = await request(app, "/dashboard/api/overview")

    payload = json.loads(body)
    assert status == 200
    assert set(payload) >= {"daemon", "configuration"}
    assert "status" in payload["daemon"]
    assert "valid" in payload["configuration"]


@pytest.mark.asyncio
async def test_dashboard_project_includes_resolved_configuration(active_runtime) -> None:
    app = create_application()

    status, _, body = await request(app, "/dashboard/api/projects/project")

    payload = json.loads(body)
    assert status == 200
    assert payload["configuration"]["global_default_profile"] == "balanced"
    profile = payload["configuration"]["profiles"][0]
    assert profile["effective"]["consult"]["targets"] == ["primary"]
    assert profile["sources"]["consult"] == "global"


@pytest.mark.asyncio
async def test_dashboard_project_source_attribution_shows_project_override(active_runtime, tmp_path) -> None:
    project_root = tmp_path / "project-config"
    project_root.mkdir()
    project = active_runtime.register_project(str(project_root), "project-config")
    (project_root / ".openmcp").mkdir()
    (project_root / ".openmcp" / "config.toml").write_text(
        '[profiles.balanced]\nconsult = "primary"\n', encoding="utf-8"
    )
    app = create_application()

    status, _, body = await request(
        app, f"/dashboard/api/projects/{project.id}/profiles"
    )

    payload = json.loads(body)
    profile = next(item for item in payload["profiles"] if item["id"] == "balanced")
    assert status == 200
    assert profile["sources"]["consult"] == "project"
    assert profile["effective"]["consult"]["targets"] == ["primary"]


@pytest.mark.asyncio
async def test_dashboard_identical_project_override_reports_project_source(active_runtime, tmp_path) -> None:
    project_root = tmp_path / "identical-project"
    project_root.mkdir()
    project = active_runtime.register_project(str(project_root), "identical-project")
    (project_root / ".openmcp").mkdir()
    (project_root / ".openmcp" / "config.toml").write_text(
        """[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
other = "primary"
""",
        encoding="utf-8",
    )
    app = create_application()

    status, _, body = await request(app, f"/dashboard/api/projects/{project.id}/profiles")

    profile = next(item for item in json.loads(body)["profiles"] if item["id"] == "balanced")
    assert status == 200
    assert profile["sources"]["consult"] == "project"


@pytest.mark.asyncio
async def test_dashboard_project_self_extension_reports_global_inheritance(active_runtime, tmp_path) -> None:
    project_root = tmp_path / "self-project"
    project_root.mkdir()
    project = active_runtime.register_project(str(project_root), "self-project")
    (project_root / ".openmcp").mkdir()
    (project_root / ".openmcp" / "config.toml").write_text(
        '[profiles.balanced]\nextends = "balanced"\nconsult = "primary"\n',
        encoding="utf-8",
    )
    app = create_application()

    status, _, body = await request(app, f"/dashboard/api/projects/{project.id}/profiles")

    profile = next(item for item in json.loads(body)["profiles"] if item["id"] == "balanced")
    assert status == 200
    assert profile["parent"] == {"value": "balanced", "source": "project"}
    assert profile["sources"]["implement"] == "global"
    assert profile["sources"]["consult"] == "project"


@pytest.mark.asyncio
async def test_dashboard_job_detail_redacts_execution_plan(active_runtime) -> None:
    runtime = active_runtime
    project = runtime.database.project("project")
    plan = resolve_execution_plan("consult", runtime.catalog, "balanced", "secret instruction")
    runtime.database.create_job(
        job_id="job",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="secret job prompt",
        execution_plan_json=json.dumps(execution_plan_data(plan)),
        context_key="consult",
    )
    app = create_application()

    status, _, body = await request(app, "/dashboard/api/jobs/job")

    payload = json.loads(body)
    assert status == 200
    assert "prompt" not in payload
    assert "execution_plan" in payload
    serialized = json.dumps(payload)
    assert "secret instruction" not in serialized
    assert "system_prompt" not in serialized
    assert "backend_profile" not in serialized
    assert '"args"' not in serialized
    assert payload["execution_plan"]["selection"]["targets"] == ["primary"]


@pytest.mark.asyncio
async def test_context_mutation_requires_loopback_csrf_and_origin(active_runtime) -> None:
    app = create_application()
    path = "/dashboard/api/projects/project/context-instructions/consult"
    body = json.dumps({"instruction": "follow the plan", "expected_current": ""}).encode()

    remote, _, _ = await request(app, path, method="PUT", body=body, client_host="192.0.2.1", headers=(("Host", "192.0.2.1"),))
    missing_csrf, _, _ = await request(app, path, method="PUT", body=body, headers=(("Host", "127.0.0.1"), ("Origin", "http://127.0.0.1")))
    wrong_origin, _, _ = await request(app, path, method="PUT", body=body, headers=(("Host", "127.0.0.1"), ("Origin", "http://evil.example"), ("X-OpenMCP-CSRF", "test-token")))
    valid, _, valid_body = await request(app, path, method="PUT", body=body, headers=(("Host", "127.0.0.1"), ("Origin", "http://127.0.0.1"), ("X-OpenMCP-CSRF", "test-token")))

    assert remote == missing_csrf == wrong_origin == 403
    assert valid == 200
    assert json.loads(valid_body)["instruction"] == "follow the plan"


@pytest.mark.asyncio
async def test_delete_context_instruction_requires_expected_current(active_runtime) -> None:
    app = create_application()
    path = "/dashboard/api/projects/project/context-instructions/consult"
    headers = (("Host", "127.0.0.1"), ("Origin", "http://127.0.0.1"), ("X-OpenMCP-CSRF", "test-token"))
    await request(
        app,
        path,
        method="PUT",
        headers=headers,
        body=json.dumps({"instruction": "existing", "expected_current": ""}).encode(),
    )

    missing, _, _ = await request(app, path, method="DELETE", headers=headers, body=b"{}")
    stale, _, _ = await request(
        app,
        path,
        method="DELETE",
        headers=headers,
        body=json.dumps({"expected_current": "stale"}).encode(),
    )
    deleted, _, deleted_body = await request(
        app,
        path,
        method="DELETE",
        headers=headers,
        body=json.dumps({"expected_current": "existing"}).encode(),
    )

    assert missing == 400
    assert stale == 409
    assert deleted == 200
    assert json.loads(deleted_body)["instruction"] == ""


@pytest.mark.asyncio
async def test_context_mutation_returns_conflict_with_current_value(active_runtime) -> None:
    app = create_application()
    path = "/dashboard/api/projects/project/context-instructions/consult"
    headers = (("Host", "127.0.0.1"), ("Origin", "http://127.0.0.1"), ("X-OpenMCP-CSRF", "test-token"))
    body = json.dumps({"instruction": "new", "expected_current": "stale"}).encode()

    status, _, response_body = await request(app, path, method="PUT", body=body, headers=headers)

    assert status == 409
    assert json.loads(response_body)["current"] == ""
