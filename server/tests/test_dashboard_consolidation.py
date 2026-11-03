import asyncio

import pytest
from starlette.requests import Request

from refract.config import DaemonConfig
from refract.dashboard import DashboardState, register_dashboard_routes
from refract.runtime import Runtime


@pytest.mark.asyncio
async def test_sse_closes_after_terminal_commit_and_final_cursor(tmp_path):
    runtime = Runtime(DaemonConfig(home=tmp_path))
    db = runtime.database
    db.upsert_project(project_id="p", alias="p", root="/p")
    db.create_job(job_id="j", project_id="p", workflow="consult", profile="p",
                  prompt="hello", execution_plan_json="{}", context_key="k")
    route = next(route for route in register_dashboard_routes(DashboardState(runtime=runtime))
                 if route.path.endswith("/output/updates"))
    req = Request({"type": "http", "headers": [(b"host", b"localhost")],
                   "client": ("127.0.0.1", 1234), "scheme": "http", "path_params": {"job_id": "j"}})
    try:
        response = await route.endpoint(req)
        iterator = response.body_iterator
        assert b"id: 0" in await anext(iterator)
        final = db.append_stream_events("j", [{"kind": "attempt.finished", "data": {}}])[-1].id
        db.finish_job("j", "succeeded")
        await runtime._job_terminal("j", "succeeded")
        assert f"id: {final}".encode() in await asyncio.wait_for(anext(iterator), 2)
        next_event = anext(iterator)
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(next_event, 2)
        assert not runtime.stream_hub._subscribers
    finally:
        await runtime.close()
