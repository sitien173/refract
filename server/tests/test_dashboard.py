from __future__ import annotations

import httpx
import pytest
import pytest_asyncio

import openmcp.server
from openmcp.runtime import Runtime
from openmcp.server import mcp
from tests.orchestration_helpers import config, repository


def _strict_config(port: int = 8765) -> str:
    return f"""[daemon]
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
"""


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
    assert "Task Guide" in res.text
    assert "fetchTaskGuide()" in res.text



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


def test_write_config_valid_and_backup(tmp_path) -> None:
    from openmcp.config_writer import write_config
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(_strict_config(), encoding="utf-8")

    new_cfg = write_config({"daemon": {"port": 9000}}, path=cfg_file)
    assert new_cfg.port == 9000
    assert cfg_file.read_text(encoding="utf-8").strip().startswith("[daemon]")

    bak_file = tmp_path / "config.toml.bak"
    assert bak_file.exists()
    assert "8765" in bak_file.read_text(encoding="utf-8")


def test_write_config_invalid_leaves_file_untouched(tmp_path) -> None:
    from openmcp.config_writer import write_config
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(_strict_config(), encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid"):
        write_config({"targets": [{"id": "bad", "backend": "invalid_backend"}]}, path=cfg_file)

    assert "8765" in cfg_file.read_text(encoding="utf-8")


@pytest.mark.parametrize("unsupported_key", ["routes", "routing_" + "profiles"])
def test_write_config_rejects_unsupported_dict_keys(tmp_path, unsupported_key) -> None:
    from openmcp.config_writer import write_config

    cfg_file = tmp_path / "config.toml"
    original = _strict_config()
    cfg_file.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError, match=unsupported_key):
        write_config({unsupported_key: [], "daemon": {"port": 9000}}, path=cfg_file)

    assert cfg_file.read_text(encoding="utf-8") == original


def test_write_config_preserves_comments(tmp_path) -> None:
    from openmcp.config_writer import write_config
    cfg_file = tmp_path / "config.toml"
    initial = "# Custom operator comment\n" + _strict_config()
    cfg_file.write_text(initial, encoding="utf-8")

    write_config({"daemon": {"host": "127.0.0.1", "port": 8888}}, path=cfg_file)
    text = cfg_file.read_text(encoding="utf-8")
    assert "# Custom operator comment" in text
    assert "8888" in text


def test_write_config_does_not_migrate_removed_profile_alias(tmp_path) -> None:
    from openmcp.config_writer import write_config

    legacy_profiles = "routing_" + "profiles"
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        f"""[daemon]
default_profile = "balanced"

[[targets]]
id = "primary"
backend = "codex"
capabilities = ["code", "review", "consult"]

[{legacy_profiles}.balanced]
implement = "primary"
review = "primary"
consult = "primary"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid configuration"):
        write_config(
            {
                "profiles": {
                    "balanced": {
                        "implement": "primary",
                        "review": "primary",
                        "consult": "primary",
                    }
                }
            },
            path=cfg_file,
        )

    assert legacy_profiles in cfg_file.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_dashboard_api_get_config(async_client: httpx.AsyncClient) -> None:
    res = await async_client.get("/dashboard/api/config")
    assert res.status_code == 200
    data = res.json()
    assert "daemon" in data
    assert "targets" in data
    assert "profiles" in data
    assert "logging" in data


@pytest.mark.asyncio
async def test_dashboard_api_put_config_valid(async_client: httpx.AsyncClient, active_runtime: Runtime, tmp_path) -> None:
    from dataclasses import replace
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("[daemon]\nport = 8765\n", encoding="utf-8")
    active_runtime.config = replace(active_runtime.config, config_path=cfg_file)

    # First GET current config
    get_res = await async_client.get("/dashboard/api/config")
    assert get_res.status_code == 200
    cfg_data = get_res.json()

    # Modify max_jobs
    cfg_data["daemon"]["max_jobs"] = 8

    put_res = await async_client.put("/dashboard/api/config", json=cfg_data)
    assert put_res.status_code == 200
    res_data = put_res.json()
    assert res_data["success"] is True
    assert "restart_required" in res_data
    assert "max_jobs" in res_data["restart_required"]


@pytest.mark.asyncio
async def test_dashboard_api_put_config_invalid(async_client: httpx.AsyncClient) -> None:
    invalid_payload = {
        "targets": [{"id": "invalid", "backend": "unknown_backend"}]
    }
    put_res = await async_client.put("/dashboard/api/config", json=invalid_payload)
    assert put_res.status_code == 400
    assert "error" in put_res.json()


def test_write_task_guide_valid_and_backup(tmp_path) -> None:
    from openmcp.config_writer import write_task_guide
    guide_file = tmp_path / "task_guide.json"
    guide_file.write_text('{"version": 1, "recommendations": [{"task": "t1", "profile": "p1"}]}', encoding="utf-8")

    new_guide = write_task_guide({"version": 2, "recommendations": [{"task": "t2", "profile": "p2"}]}, path=guide_file)
    assert new_guide["version"] == 2
    assert guide_file.exists()

    bak_file = tmp_path / "task_guide.json.bak"
    assert bak_file.exists()
    assert '"version": 1' in bak_file.read_text(encoding="utf-8")


def test_write_task_guide_invalid_leaves_file_untouched(tmp_path) -> None:
    from openmcp.config_writer import write_task_guide
    guide_file = tmp_path / "task_guide.json"
    guide_file.write_text('{"version": 1}', encoding="utf-8")

    with pytest.raises(ValueError, match="Task guide must be a non-empty JSON object"):
        write_task_guide({}, path=guide_file)

    assert '"version": 1' in guide_file.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_dashboard_api_get_task_guide(async_client: httpx.AsyncClient) -> None:
    res = await async_client.get("/dashboard/api/task-guide")
    assert res.status_code == 200
    assert isinstance(res.json(), dict)


@pytest.mark.asyncio
async def test_dashboard_api_put_task_guide_valid(async_client: httpx.AsyncClient, active_runtime: Runtime, tmp_path) -> None:
    payload = {"version": 1, "recommendations": [{"task": "test-task", "profile": "balanced"}]}
    put_res = await async_client.put("/dashboard/api/task-guide", json=payload)
    assert put_res.status_code == 200
    res_data = put_res.json()
    assert res_data.get("version") == 1 or res_data.get("guide", {}).get("version") == 1

    get_res = await async_client.get("/dashboard/api/task-guide")
    assert get_res.status_code == 200
    assert get_res.json().get("version") == 1


@pytest.mark.asyncio
async def test_dashboard_api_put_task_guide_invalid(async_client: httpx.AsyncClient) -> None:
    put_res = await async_client.put("/dashboard/api/task-guide", json={})
    assert put_res.status_code == 400
    assert "error" in put_res.json()

