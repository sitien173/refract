import asyncio
import json
import threading
from types import SimpleNamespace

import pytest

from refract.config import load_config
from refract.database import Database
from refract.drivers import DriverResult
from refract.runtime import Runtime
from refract.server import job_list, job_wait, project_resolve, task_guide
from refract.workers import run_sync


@pytest.mark.asyncio
async def test_runtime_tools_and_runner_never_query_sqlite_on_loop(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_text('''[daemon]
default_profile = "test"
[[targets]]
id = "a"
backend = "codex"
[profiles.test]
consult = ["a"]
''')
    runtime = Runtime(load_config(path))
    (runtime.config.home / "task_guide.json").write_text('{"recommendations": []}')
    root = tmp_path / "project"
    root.mkdir()
    loop_thread = threading.get_ident()
    connection = Database._connection.fget

    def worker_connection(self):
        assert threading.get_ident() != loop_thread
        return connection(self)

    monkeypatch.setattr(Database, "_connection", property(worker_connection))
    probes = []

    class Drivers:
        def supports_structured_streaming(self, target):
            assert threading.get_ident() != loop_thread
            probes.append(target.id)
            return True

        def available(self, target):
            assert threading.get_ident() != loop_thread
            return True

        async def execute(self, **kwargs):
            return DriverResult("SUCCESS", "session", "done", "", "")

    runtime.drivers = Drivers()
    ctx = SimpleNamespace(
        request_context=SimpleNamespace(lifespan_context=runtime),
        report_progress=lambda **kwargs: asyncio.sleep(0),
    )
    try:
        await runtime.start()
        assert probes == ["a"]
        project = json.loads(await project_resolve(str(root), ctx))["project"]
        assert json.loads(await task_guide(project["id"], ctx))["profiles"]["default"] == "test"
        submitted = await runtime.submit(project["id"], "consult", "hello")
        completed = await runtime.wait(submitted.job_id, 5)
        assert completed.state == "succeeded"
        assert json.loads(await job_wait(submitted.job_id, ctx))["result"]["text"] == "done"
        assert json.loads(await job_list(project["id"], ctx))["recent"][0]["id"] == submitted.job_id
    finally:
        await runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancellations", [1, 3])
@pytest.mark.parametrize("worker_fails", [False, True])
async def test_cancelled_worker_is_joined_before_resources_close(cancellations, worker_fails):
    entered = asyncio.Event()
    release = threading.Event()
    finished = threading.Event()
    loop = asyncio.get_running_loop()

    def blocking():
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(5)
        finished.set()
        if worker_fails:
            raise RuntimeError("worker failed during cancellation")

    task = asyncio.create_task(run_sync(blocking))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        for index in range(cancellations):
            task.cancel(f"cancel-{index}")
            for _ in range(3):
                await asyncio.sleep(0)
            assert not task.done()
            assert not finished.is_set()
        release.set()
        with pytest.raises(asyncio.CancelledError) as error:
            await task
        assert error.value.args == ("cancel-0",)
        assert finished.is_set()
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
