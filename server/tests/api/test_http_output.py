"""Dashboard read routes: the removed `/retry` route and the `/output` cursor."""

from __future__ import annotations

import json

import pytest
from starlette.applications import Starlette

from refract.api.http.common import DashboardState
from refract.api.http.routes import register_dashboard_routes
from tests.test_dashboard_api import api_request, valid_headers
from tests.test_runtime_v3 import _run, _runtime


@pytest.mark.asyncio
async def test_retry_route_is_gone() -> None:
    app = Starlette(routes=register_dashboard_routes(DashboardState()))

    status, body, _ = await api_request(app, "/dashboard/api/jobs/job-1/retry", headers=valid_headers())

    assert status == 404 and body["code"] == "not_found"


@pytest.mark.asyncio
async def test_output_stops_at_events_committed(tmp_path) -> None:
    runtime, project, _drivers = await _runtime(tmp_path)
    try:
        job = await _run(runtime, project)
        runtime.database.append_stream(job.id, [{"kind": "text", "data": {"n": 1}}, {"kind": "text", "data": {"n": 2}}])
        # A line written past the committed count, as after a crash between the write and the commit.
        with runtime.database.stream_path(job.id).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"kind": "text", "data": {"n": 3}}) + "\n")
        app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime)))

        status, body, _ = await api_request(app, f"/dashboard/api/jobs/{job.id}/output", method="GET")

        committed = runtime.database.job_record(job.id)["events_committed"]
        assert status == 200
        assert body["next"] == body["events"][-1]["seq"] == committed
        assert [event["seq"] for event in body["events"]][-2:] == [committed - 1, committed]
        assert all(event.get("data", {}).get("n") != 3 for event in body["events"])
        assert body["has_more"] is False and body["available"] is True

        status, body, _ = await api_request(
            app, f"/dashboard/api/jobs/{job.id}/output?after={committed}", method="GET"
        )
        assert status == 200 and body["events"] == [] and body["next"] == committed
    finally:
        await runtime.close()
