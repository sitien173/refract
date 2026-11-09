import asyncio
from dataclasses import replace

import pytest

from refract.config import DaemonConfig
from refract.runtime import Runtime


def test_lifecycle_retention_preserves_active_and_recent_jobs(tmp_path):
    runtime = Runtime(DaemonConfig(home=tmp_path))
    db = runtime.database
    try:
        db.upsert_project(project_id="p", root="/p")
        for name in ["old", "recent", "active"]:
            db.create_job(job_id=name, project_id="p", workflow="consult", profile="p",
                          prompt="hello", execution_plan_json="{}", session="k")
            if name != "active":
                db.finish_job(name, "succeeded")
            with db._connection:
                if name != "recent":
                    db._connection.execute("UPDATE jobs SET updated_at='2000-01-01' WHERE id=?", (name,))
        for name in ["old", "recent", "active"]:
            db.append_stream(name, [{"attempt": 1, "kind": "assistant_message", "data": {"text": "hello"}}])
        runtime.prune_retained_transcripts()
        assert db.job("old") is None
        assert not db.stream_path("old").exists()
        assert db.job("recent") is not None
        assert db.stream_path("recent").exists()
        assert db.job("active") is not None
        assert db.stream_path("active").exists()
    finally:
        db.close()


@pytest.mark.asyncio
async def test_periodic_retention_retries_and_stops_on_close(tmp_path, monkeypatch):
    import refract.runtime as runtime_module

    runtime = Runtime(DaemonConfig(home=tmp_path))
    monkeypatch.setattr(runtime_module, "RETENTION_INTERVAL_S", 0.001)
    calls = 0
    retried = asyncio.Event()

    def prune():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("temporary failure")
        if calls >= 3:
            retried.set()
        return 0

    monkeypatch.setattr(runtime, "prune_retained_transcripts", prune)
    await runtime.start()
    task = runtime._retention_task
    try:
        await asyncio.wait_for(retried.wait(), 2)
    finally:
        await runtime.close()
    assert task.done()
    assert runtime._retention_task is None


