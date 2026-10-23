import asyncio
import json
import threading

import pytest
from starlette.requests import Request

from refract.config import DaemonConfig
from refract.dashboard import DashboardState, register_dashboard_routes
from refract.runtime import Runtime
from refract.server import create_application
from tests.test_dashboard import active_runtime, request


@pytest.mark.asyncio
async def test_mutation_worker_does_not_block_dashboard_reads(active_runtime, monkeypatch):
    runtime = active_runtime
    app = create_application()
    revision = runtime.catalog.config_revision
    entered = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    loop_thread = threading.get_ident()
    original = runtime.mutations.create_target

    def create(*args, **kwargs):
        assert threading.get_ident() != loop_thread
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(timeout=5)
        return original(*args, **kwargs)

    monkeypatch.setattr(runtime.mutations, "create_target", create)
    task = asyncio.create_task(request(
        app, "/dashboard/api/configuration/targets", method="POST",
        headers=(("x-refract-csrf", "test-token"), ("If-Match", revision),
                 ("Origin", "http://127.0.0.1:8765")),
        body=json.dumps({"id": "new", "backend": "codex"}).encode(),
    ))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert (await request(app, "/dashboard/api/status"))[0] == 200
        release.set()
        status, headers, body = await task
        assert status == 200
        assert json.loads(body)["target"]["id"] == "new"
        assert headers[b"etag"]
    finally:
        release.set()
        await task


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
