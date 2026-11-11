import asyncio

import pytest

from refract.execution import TargetExecutor
from refract.scheduler import CancelEvent


@pytest.mark.asyncio
async def test_waiting_capacity_cancellation_preserves_permit():
    semaphore = asyncio.Semaphore(0)
    cancelled = CancelEvent()
    task = asyncio.create_task(TargetExecutor._acquire_target(semaphore, cancelled))
    await asyncio.sleep(0)
    cancelled.set()
    assert not await asyncio.wait_for(task, 1)
    semaphore.release()
    await asyncio.wait_for(semaphore.acquire(), 1)
    assert semaphore.locked()


@pytest.mark.asyncio
async def test_simultaneous_capacity_and_cancellation_returns_permit():
    semaphore = asyncio.Semaphore(0)
    cancelled = CancelEvent()
    task = asyncio.create_task(TargetExecutor._acquire_target(semaphore, cancelled))
    await asyncio.sleep(0)
    semaphore.release()
    cancelled.set()
    assert not await task
    await asyncio.wait_for(semaphore.acquire(), 1)
    assert semaphore.locked()


@pytest.mark.asyncio
async def test_capacity_task_cancellation_does_not_leak_permit():
    semaphore = asyncio.Semaphore(1)
    task = asyncio.create_task(TargetExecutor._acquire_target(semaphore, CancelEvent()))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.wait_for(semaphore.acquire(), 1)
    assert semaphore.locked()


@pytest.mark.asyncio
async def test_full_first_target_records_zero_skipped_targets(tmp_path):
    from dataclasses import replace
    from refract.config import TargetConfig, TargetSelection
    from refract.drivers import DriverResult
    from refract.planning import resolve_execution_plan
    from refract.runtime import Runtime
    from refract.workflows import get_workflow
    from tests.orchestration_helpers import FakeDrivers, config, repository, register_project

    root = repository(tmp_path)
    first = TargetConfig(id="full", backend="codex", max_concurrency=1)
    second = TargetConfig(id="available", backend="codex")
    selection = TargetSelection((first.id, second.id))
    catalog = replace(
        config(tmp_path / "home"), targets=(first, second),
        profiles={"balanced": {"implement": selection, "review": selection, "consult": selection}},
    )
    runtime = Runtime(catalog)

    class SelectedTargetDrivers(FakeDrivers):
        async def execute(self, *, target, **kwargs):
            assert target.id == "available"
            return DriverResult("SUCCESS", "sid", "done", "", "")

    runtime.drivers = SelectedTargetDrivers()
    runtime.target_executor._target_active[first.id] = 1
    plan = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")
    selected, rejected = runtime.target_executor._select_target(selection.targets, plan)
    assert selected is second
    assert rejected == 0
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        submission = await runtime.submit(project.id, "implement", "capacity metrics")
        job = await runtime.wait(submission.job_id, 10)
        assert job.state == "succeeded"
        row = runtime.database._connection.execute(
            "SELECT skipped_targets FROM job_metrics WHERE job_id=?", (submission.job_id,),
        ).fetchone()
        assert row["skipped_targets"] == 0
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_concurrent_probe_ownership_during_retries_blocks_other_probe(tmp_path):
    from dataclasses import replace
    from refract.config import RetryPolicy, TargetConfig, TargetSelection
    from refract.drivers import DriverResult
    from refract.planning import resolve_execution_plan, target_execution_key
    from refract.runtime import Runtime
    from refract.workflows import get_workflow
    from tests.orchestration_helpers import FakeDrivers, config, repository, register_project

    root = repository(tmp_path)
    base = config(tmp_path / "home")

    policy = RetryPolicy(1, ("rate_limit",), ())
    catalog = replace(
        base,
        targets=(TargetConfig(id="primary", backend="codex", retry=policy),),
        profiles={"balanced": {"implement": TargetSelection(("primary",)), "review": TargetSelection(("primary",)), "consult": TargetSelection(("primary",))}},
    )

    concurrent_admitted = []

    class ConcurrentProbeDrivers(FakeDrivers):
        def __init__(self, runtime, target_key):
            super().__init__()
            self.runtime = runtime
            self.target_key = target_key
            self.attempt = 0

        def supports_structured_streaming(self, target):
            return True

        async def execute(self, *, target, **kwargs):
            self.attempt += 1
            if self.attempt == 1:
                plan = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")
                admitted = self.runtime.target_executor._select_target(
                    ("primary",),
                    plan,
                    job_id="job-2",
                )
                concurrent_admitted.append(admitted)
                return DriverResult("RETRYABLE", "", "", "transient error", "rate_limit")
            return DriverResult("SUCCESS", "ok", "", "", "")

    runtime = Runtime(catalog)
    target = catalog.targets[0]
    target_key = target_execution_key(target)
    drivers = ConcurrentProbeDrivers(runtime, target_key)
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        with runtime.database._connection:
            runtime.database._connection.execute(
                "INSERT INTO target_health(target_id, consecutive_failures, circuit_open_until, cooldown_s, probe_job_id) VALUES (?, 1, '2000-01-01T00:00:00+00:00', 60, '')",
                (target_key,),
            )
        sub = await runtime.submit(project.id, "implement", "probe concurrency test")
        job = await runtime.wait(sub.job_id, 10)
        assert job.state == "succeeded"
        assert concurrent_admitted == [(None, 1)]
    finally:
        await runtime.close()
