from __future__ import annotations

import httpx
import pytest
import pytest_asyncio

import openmcp.server
from openmcp.runtime import Runtime
from openmcp.server import mcp
from tests.orchestration_helpers import config, repository


@pytest_asyncio.fixture
async def active_runtime(tmp_path, monkeypatch):
    cfg = config(tmp_path)
    runtime = Runtime(cfg)
    await runtime.start()
    monkeypatch.setattr(openmcp.server, "_ACTIVE_RUNTIME", runtime)
    try:
        yield runtime
    finally:
        await runtime.close()


@pytest_asyncio.fixture
async def async_client(active_runtime):
    mcp._session_manager = None
    app = mcp.streamable_http_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765") as client:
        yield client


@pytest.mark.asyncio
async def test_dashboard_api_status(async_client: httpx.AsyncClient) -> None:
    res = await async_client.get("/dashboard/api/status")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "workers" in data


@pytest.mark.asyncio
async def test_dashboard_api_projects(async_client: httpx.AsyncClient, active_runtime: Runtime, tmp_path) -> None:
    repo = repository(tmp_path)
    project = active_runtime.register_project(str(repo))

    res = await async_client.get("/dashboard/api/projects")
    assert res.status_code == 200
    projects = res.json()
    assert isinstance(projects, list)
    assert len(projects) == 1
    assert projects[0]["id"] == project.id


@pytest.mark.asyncio
async def test_dashboard_api_project_jobs_and_not_found(async_client: httpx.AsyncClient, active_runtime: Runtime, tmp_path) -> None:
    repo = repository(tmp_path)
    project = active_runtime.register_project(str(repo))

    res = await async_client.get(f"/dashboard/api/projects/{project.id}/jobs")
    assert res.status_code == 200
    assert res.json() == []

    res_404 = await async_client.get("/dashboard/api/projects/nonexistent-id/jobs")
    assert res_404.status_code == 404
    assert res_404.json() == {"error": "Unknown project: nonexistent-id"}


@pytest.mark.asyncio
async def test_dashboard_api_job_detail_and_events(async_client: httpx.AsyncClient, active_runtime: Runtime, tmp_path) -> None:
    repo = repository(tmp_path)
    project = active_runtime.register_project(str(repo))
    sub = await active_runtime.submit(project.id, "implement", "test prompt")
    job_id = sub.job_id

    res_job = await async_client.get(f"/dashboard/api/jobs/{job_id}")
    assert res_job.status_code == 200
    assert res_job.json()["id"] == job_id

    res_events = await async_client.get(f"/dashboard/api/jobs/{job_id}/events")
    assert res_events.status_code == 200
    events = res_events.json()
    assert isinstance(events, list)
    assert len(events) >= 1



@pytest.mark.asyncio
async def test_dashboard_api_job_not_found(async_client: httpx.AsyncClient) -> None:
    res = await async_client.get("/dashboard/api/jobs/nonexistent-id")
    assert res.status_code == 404
    assert res.json() == {"error": "Unknown job: nonexistent-id"}


@pytest.mark.asyncio
async def test_dashboard_api_job_events_not_found(async_client: httpx.AsyncClient) -> None:
    res = await async_client.get("/dashboard/api/jobs/nonexistent-id/events")
    assert res.status_code == 404
    assert res.json() == {"error": "Unknown job: nonexistent-id"}


@pytest.mark.asyncio
async def test_dashboard_api_targets(async_client: httpx.AsyncClient) -> None:
    res = await async_client.get("/dashboard/api/targets")
    assert res.status_code == 200
    targets = res.json()
    assert isinstance(targets, list)
    assert len(targets) > 0


@pytest.mark.asyncio
async def test_dashboard_api_profiles(async_client: httpx.AsyncClient) -> None:
    res = await async_client.get("/dashboard/api/profiles")
    assert res.status_code == 200
    data = res.json()
    assert "default" in data
    assert "available" in data


@pytest.mark.asyncio
async def test_dashboard_static_index(async_client: httpx.AsyncClient) -> None:
    res = await async_client.get("/dashboard")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")
    assert "<!DOCTYPE html>" in res.text or "<html" in res.text


@pytest.mark.asyncio
async def test_dashboard_static_assets(async_client: httpx.AsyncClient) -> None:
    res = await async_client.get("/dashboard/assets/styles.css")
    assert res.status_code == 200

    res_vendor = await async_client.get("/dashboard/assets/vendor/alpine.min.js")
    assert res_vendor.status_code == 200


@pytest.mark.asyncio
async def test_dashboard_api_503_when_no_runtime(monkeypatch) -> None:
    monkeypatch.setattr(openmcp.server, "_ACTIVE_RUNTIME", None)
    mcp._session_manager = None
    app = mcp.streamable_http_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765") as client:
        res = await client.get("/dashboard/api/status")
        assert res.status_code == 503
        assert res.json() == {"error": "OpenMCP runtime is not active"}
