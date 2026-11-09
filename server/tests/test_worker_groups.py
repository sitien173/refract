from __future__ import annotations

import os
import signal
import subprocess
import time
import uuid
from pathlib import Path

import pytest

from refract.backends._process import run_process
from refract.drivers import DriverResult
from refract.runtime import Runtime
from tests.orchestration_helpers import FakeDrivers, config, register_project, repository

pytestmark = pytest.mark.skipif(not Path("/proc").is_dir(), reason="worker group guard needs /proc")


class SpawningDrivers(FakeDrivers):
    async def execute(self, *, cwd: Path, env=None, **kwargs) -> DriverResult:
        lines: list[str] = []

        async def collect(line: str) -> None:
            lines.append(line)

        await run_process(["sh", "-c", 'printf "%s\\n" "$REFRACT_JOB_ID"'], None, env, str(cwd), None, None, collect)
        return DriverResult("SUCCESS", "session", "".join(lines).strip(), "", "")


def _group_alive(group_id: int) -> bool:
    try:
        os.killpg(group_id, 0)
    except ProcessLookupError:
        return False
    return True


def _spawn_group(env_job_id: str | None) -> subprocess.Popen[bytes]:
    env = dict(os.environ)
    env.pop("REFRACT_JOB_ID", None)
    if env_job_id is not None:
        env["REFRACT_JOB_ID"] = env_job_id
    return subprocess.Popen(["sh", "-c", "sleep 60 & wait"], start_new_session=True, env=env)


def _running_job(runtime: Runtime, root: Path, pgid: int, job_id: str) -> str:
    project = register_project(runtime, str(root))
    runtime.database.create_job(job_id=job_id, project_id=project.id, workflow="consult", profile="balanced",
                                prompt="p", execution_plan_json="{}", session="s")
    with runtime.database._connection:
        runtime.database._connection.execute("UPDATE jobs SET state='running', pgid=? WHERE id=?", (pgid, job_id))
    return job_id


@pytest.mark.asyncio
async def test_worker_runs_with_job_id_and_records_process_group(tmp_path: Path) -> None:
    root = repository(tmp_path)
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = SpawningDrivers()
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        submitted = await runtime.submit(project.id, "consult", "p")
        job = await runtime.wait(submitted.job_id, 5)
        assert job.state == "succeeded"
        assert job.result.text == submitted.job_id
        pgid = runtime.database.job_record(submitted.job_id)["pgid"]
        assert isinstance(pgid, int)
        assert pgid > 0
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_restart_kills_worker_group_of_interrupted_job(tmp_path: Path) -> None:
    root = repository(tmp_path)
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = FakeDrivers()
    job_id = str(uuid.uuid4())
    worker = _spawn_group(job_id)
    try:
        time.sleep(0.2)
        _running_job(runtime, root, worker.pid, job_id)
        await runtime.start()
        try:
            assert runtime.database.job_record(job_id)["state"] == "interrupted"
            worker.wait(timeout=5)
            deadline = time.monotonic() + 5
            while _group_alive(worker.pid) and time.monotonic() < deadline:
                time.sleep(0.05)
            assert not _group_alive(worker.pid)
        finally:
            await runtime.close()
    finally:
        if _group_alive(worker.pid):
            os.killpg(worker.pid, signal.SIGKILL)
        worker.wait(timeout=5)


@pytest.mark.asyncio
@pytest.mark.parametrize("marker", [None, "other-job"])
async def test_restart_leaves_group_without_matching_job_id(tmp_path: Path, marker: str | None) -> None:
    root = repository(tmp_path)
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = FakeDrivers()
    unrelated = _spawn_group(marker)
    try:
        time.sleep(0.2)
        job_id = _running_job(runtime, root, unrelated.pid, str(uuid.uuid4()))
        await runtime.start()
        try:
            assert runtime.database.job_record(job_id)["state"] == "interrupted"
            time.sleep(0.2)
            assert unrelated.poll() is None
            assert _group_alive(unrelated.pid)
        finally:
            await runtime.close()
    finally:
        os.killpg(unrelated.pid, signal.SIGKILL)
        unrelated.wait(timeout=5)

