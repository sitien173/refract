"""`POST /dashboard/api/jobs` with `from_job`: the same path and error codes as the MCP `submit` tool."""

from __future__ import annotations

import json
from typing import get_args

import pytest
from starlette.applications import Starlette

from refract.api.http.common import DashboardState
from refract.api.http.routes import register_dashboard_routes
from refract.models import ERROR_CODES
from tests.test_dashboard_api import api_request, valid_headers
from tests.test_runtime_v3 import _open_circuit, _run, _runtime

_JOBS = "/dashboard/api/jobs"


async def _post(app: Starlette, payload: object) -> tuple[int, dict, dict[str, str]]:
    return await api_request(app, _JOBS, headers=valid_headers(), body=json.dumps(payload).encode())


@pytest.mark.asyncio
async def test_from_job_queues_a_copy_and_reports_the_source(tmp_path) -> None:
    runtime, project, drivers = await _runtime(tmp_path)
    try:
        source = await _run(runtime, project, prompt="original")
        app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime)))

        status, body, headers = await _post(app, {"from_job": source.id})

        assert status == 200
        assert body["from_job"] == source.id and body["state"] == "queued" and body["job_id"] != source.id
        assert headers["cache-control"] == "no-store"
        copy = await runtime.wait(body["job_id"], 5)
        assert copy.from_job == source.id and copy.state == "succeeded"
        assert runtime.database.job_record(copy.id)["prompt"] == "original"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_from_job_target_and_fresh_override_the_source(tmp_path) -> None:
    runtime, project, drivers = await _runtime(tmp_path)
    try:
        source = await _run(runtime, project)
        app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime)))

        status, body, _ = await _post(app, {"from_job": source.id, "target": "a", "fresh": True})

        assert status == 200
        copy = await runtime.wait(body["job_id"], 5)
        assert copy.target_id == "a"
        assert runtime.database.job_record(copy.id)["fresh"] == 1
    finally:
        await runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [{}, {"from_job": ""}, {"from_job": 7}, {"from_job": "x", "target": 3}, {"from_job": "x", "fresh": "yes"}, []],
)
async def test_from_job_rejects_malformed_bodies_without_calling_runtime(payload) -> None:
    class Untouched:
        async def submit_from_job(self, *_args, **_kwargs):
            raise AssertionError("runtime must not be called")

    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=Untouched())))

    status, body, _ = await _post(app, payload)

    assert status == 400 and body["code"] == "invalid_request"


@pytest.mark.asyncio
async def test_from_job_error_codes_match_submit(tmp_path) -> None:
    runtime, project, _drivers = await _runtime(tmp_path)
    try:
        source = await _run(runtime, project)
        app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime)))
        seen: dict[str, tuple[int, dict, dict[str, str]]] = {}

        seen["unknown_job"] = await _post(app, {"from_job": "no-such-job"})

        runtime.database._connection.execute("UPDATE jobs SET state='running' WHERE id=?", (source.id,))
        runtime.database._connection.commit()
        seen["invalid_state"] = await _post(app, {"from_job": source.id})
        runtime.database._connection.execute("UPDATE jobs SET state='succeeded' WHERE id=?", (source.id,))
        runtime.database._connection.commit()

        seen["invalid_request"] = await _post(app, {"from_job": source.id, "target": "nope"})

        _open_circuit(runtime, "b")
        seen["targets_unavailable"] = await _post(app, {"from_job": source.id})

        assert {code: result[0] for code, result in seen.items()} == {
            "unknown_job": 404, "invalid_state": 409, "invalid_request": 400, "targets_unavailable": 503,
        }
        for code, (_status, body, _headers) in seen.items():
            assert body["code"] == code and code in get_args(ERROR_CODES)
        assert int(seen["targets_unavailable"][2]["retry-after"]) >= 1
    finally:
        await runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ({"prompt": "new work"}, "prompt"),
        ({"workflow": "consult"}, "workflow"),
        ({"profile": "fast"}, "profile"),
        ({"session": "s"}, "session"),
        ({"prompt": "p", "session": "s"}, "prompt, session"),
        ({"bogus": 1}, "bogus"),
    ],
)
async def test_from_job_rejects_conflicting_and_unknown_fields(extra, message) -> None:
    class Untouched:
        async def submit_from_job(self, *_args, **_kwargs):
            raise AssertionError("runtime must not be called")

    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=Untouched())))

    status, body, _ = await _post(app, {"from_job": "x", **extra})

    assert status == 400 and body["code"] == "invalid_request"
    assert message in body["error"]


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["prompt", "workflow", "profile", "session"])
async def test_from_job_conflict_rule_matches_mcp_submit(tmp_path, monkeypatch, field) -> None:
    from starlette.applications import Starlette

    from tests.orchestration_helpers import git, register_project
    from tests.test_server import _connected_client

    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        root = tmp_path / "project"
        root.mkdir()
        git(root, "init", "-q")
        project = register_project(runtime, str(root))
        runtime.database.create_job(
            job_id="parity-src", project_id=project.id, workflow="review", profile="balanced",
            prompt="src", plan_json="{}", session="src",
        )
        runtime.database.finish_job("parity-src", "failed")
        app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime)))

        async def mcp(value: str) -> tuple[bool, str]:
            response = await client.call_tool("submit", {"path": str(root), "from_job": "parity-src", field: value})
            payload = json.loads(response.content[0].text)
            return response.is_error, payload.get("code", "") if response.is_error else ""

        async def http(value: str) -> tuple[bool, str]:
            status, body, _ = await _post(app, {"from_job": "parity-src", field: value})
            return status != 200, body.get("code", "") if status != 200 else ""

        assert await http("") == await mcp("") == (False, "")
        assert await http("x") == await mcp("x") == (True, "invalid_request")
