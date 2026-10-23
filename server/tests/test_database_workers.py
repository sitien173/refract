import asyncio
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from starlette.requests import Request
from starlette.responses import Response

from refract.dashboard import _loopback_route
from refract.database import Database


def test_database_workers_have_independent_connections_and_transactions(tmp_path):
    db = Database(tmp_path / "workers.db")
    barrier = threading.Barrier(4)

    def write(i):
        connection = db._connection
        barrier.wait(timeout=5)
        db.upsert_project(project_id=str(i), alias=str(i), root=f"/{i}")
        return connection

    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            connections = list(pool.map(write, range(4)))
        assert len({id(c) for c in [db._connection, *connections]}) == 5
        assert len(db.projects()) == 4
    finally:
        db.close()
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        db.projects()


@pytest.mark.asyncio
async def test_dashboard_blocking_routes_run_off_loop():
    loop_thread = threading.get_ident()
    entered = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()

    def endpoint(request):
        assert threading.get_ident() != loop_thread
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(timeout=5)
        return Response("done")

    route = _loopback_route("/test", endpoint, ["GET"])
    request = Request({"type": "http", "headers": [(b"host", b"localhost")],
                       "client": ("127.0.0.1", 1234), "scheme": "http"})
    task = asyncio.create_task(route.endpoint(request))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        release.set()
        assert (await task).body == b"done"
    finally:
        release.set()
        await task
