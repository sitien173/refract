from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from refract.runtime import OrchestrationError, Runtime
from tests.orchestration_helpers import BlockingDrivers, FakeDrivers, config, register_project, repository


async def _runtime(tmp_path: Path, drivers=None, *, start: bool = True, **overrides):
    root = repository(tmp_path)
    runtime = Runtime(replace(config(tmp_path / "home"), **overrides))
    runtime.drivers = drivers or FakeDrivers()
    if start:
        await runtime.start()
    return runtime, register_project(runtime, str(root))


@pytest.mark.asyncio
async def test_wait_jobs_returns_job_that_finished_before_the_call(tmp_path) -> None:
    runtime, project = await _runtime(tmp_path)
    try:
        submission = await runtime.submit(project.id, "implement", "inspect")
        assert (await runtime.wait(submission.job_id, 10)).state == "succeeded"
        result = await asyncio.wait_for(runtime.wait_jobs([submission.job_id], 0), 1)
        assert result.ready
        assert result.job.state == "succeeded"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_wait_jobs_returns_first_ready_job_in_input_order(tmp_path) -> None:
    runtime, project = await _runtime(tmp_path)
    try:
        first = await runtime.submit(project.id, "implement", "one")
        second = await runtime.submit(project.id, "review", "two")
        await runtime.wait(first.job_id, 10)
        await runtime.wait(second.job_id, 10)
        result = await runtime.wait_jobs([second.job_id, first.job_id], 1)
        assert result.job.id == second.job_id
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_wait_jobs_rejects_more_than_sixteen_ids(tmp_path) -> None:
    runtime, _ = await _runtime(tmp_path, start=False)
    try:
        with pytest.raises(OrchestrationError) as raised:
            await runtime.wait_jobs([f"job-{n}" for n in range(17)], 0.01)
        assert raised.value.code == "invalid_request"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_wait_jobs_reports_job_interrupted_by_simulated_restart(tmp_path) -> None:
    runtime, project = await _runtime(tmp_path, start=False)
    try:
        submission = await runtime.submit(project.id, "implement", "inspect")
        runtime.database.start_job(submission.job_id)
        waiter = asyncio.create_task(runtime.wait_jobs([submission.job_id], 10))
        await asyncio.sleep(0.05)
        assert not waiter.done()
        await runtime.start()  # the restart pass marks running jobs interrupted and publishes terminal
        result = await asyncio.wait_for(waiter, 5)
        assert result.ready
        assert result.job.state == "interrupted"
        # A call made after the restart sees the same state with no signal.
        assert (await runtime.wait_jobs([submission.job_id], 1)).job.state == "interrupted"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_terminal_is_published_after_session_lock_and_slot_are_released(tmp_path) -> None:
    runtime, project = await _runtime(tmp_path)
    seen: list[tuple[int, int]] = []
    original = runtime.hub.publish

    def recording_publish(job_id: str, kind: str) -> None:
        if kind == "terminal":
            seen.append((runtime.scheduler.active_jobs, len(runtime.target_executor._session_locks)))
        original(job_id, kind)

    runtime.hub.publish = recording_publish
    try:
        submission = await runtime.submit(project.id, "implement", "inspect")
        assert (await runtime.wait(submission.job_id, 10)).state == "succeeded"
        assert seen == [(0, 0)]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_cancel_status_terminated_for_queued_job(tmp_path) -> None:
    runtime, project = await _runtime(tmp_path, start=False)
    try:
        submission = await runtime.submit(project.id, "implement", "inspect")
        assert await runtime.cancel_job(submission.job_id) == "terminated"
        assert runtime.database.job(submission.job_id).state == "cancelled"
        assert (await runtime.wait_jobs([submission.job_id], 1)).job.state == "cancelled"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_cancel_status_requested_for_running_job(tmp_path) -> None:
    drivers = BlockingDrivers()
    runtime, project = await _runtime(tmp_path, drivers)
    try:
        submission = await runtime.submit(project.id, "implement", "block")
        await asyncio.wait_for(drivers.started.wait(), 5)
        assert await runtime.cancel_job(submission.job_id) == "requested"
        assert (await runtime.wait_jobs([submission.job_id], 10)).job.state == "cancelled"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_cancel_status_already_terminal_never_overwrites(tmp_path) -> None:
    runtime, project = await _runtime(tmp_path)
    try:
        submission = await runtime.submit(project.id, "implement", "inspect")
        assert (await runtime.wait(submission.job_id, 10)).state == "succeeded"
        assert await runtime.cancel_job(submission.job_id) == "already_terminal"
        assert runtime.database.job(submission.job_id).state == "succeeded"
        assert await runtime.cancel_job(submission.job_id) == "already_terminal"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_cancel_unknown_job_raises(tmp_path) -> None:
    runtime, _ = await _runtime(tmp_path, start=False)
    try:
        with pytest.raises(OrchestrationError) as raised:
            await runtime.cancel_job("missing")
        assert raised.value.code == "unknown_job"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_hub_subscribers_removed_after_return_timeout_and_cancellation(tmp_path) -> None:
    runtime, project = await _runtime(tmp_path, start=False)
    try:
        submission = await runtime.submit(project.id, "implement", "inspect")
        job_id = submission.job_id
        hub = runtime.hub

        # Timeout: the job is queued and never runs.
        result = await runtime.wait_jobs([job_id], 0.05)
        assert not result.ready
        assert hub.subscriber_count == 0

        # Cancellation of the waiting task.
        waiter = asyncio.create_task(runtime.wait_jobs([job_id], 10))
        await asyncio.sleep(0.02)
        assert hub.subscriber_count == 1
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)
        assert hub.subscriber_count == 0

        # Return: the waiter wakes on the terminal signal.
        waiter = asyncio.create_task(runtime.wait_jobs([job_id], 10))
        await asyncio.sleep(0.02)
        await runtime.cancel_job(job_id)
        assert (await asyncio.wait_for(waiter, 5)).ready
        assert hub.subscriber_count == 0
    finally:
        await runtime.close()
