"""Backlog overflow: a slow subscriber is flagged, and MCP wait never depends on the evicted signals."""

from __future__ import annotations

import asyncio

import pytest

from refract.scheduling.hub import Hub
from tests.test_runtime_v3 import _Drivers, _runtime


@pytest.mark.asyncio
async def test_overflow_is_flagged_once_and_wake_stays_set() -> None:
    hub = Hub()
    with hub.subscribe() as subscription:
        subscription.clear()
        for n in range(1025):
            hub.publish(f"job-{n}", "queued")
        await asyncio.sleep(0.05)

        assert await subscription.wait(1.0)
        assert [job for job, _ in subscription.drain()][0] == "job-1"
        assert subscription.take_overflow() is True
        assert subscription.take_overflow() is False


@pytest.mark.asyncio
async def test_no_overflow_at_exactly_the_backlog() -> None:
    hub = Hub()
    with hub.subscribe() as subscription:
        for n in range(1024):
            hub.publish(f"job-{n}", "queued")
        await asyncio.sleep(0.05)

        assert len(subscription.drain()) == 1024
        assert subscription.take_overflow() is False


@pytest.mark.asyncio
async def test_wait_is_correct_when_its_signals_were_evicted(tmp_path) -> None:
    gate = asyncio.Event()

    class Gated(_Drivers):
        async def execute(self, **kwargs):
            await gate.wait()
            return await super().execute(**kwargs)

    runtime, project, _drivers = await _runtime(tmp_path, Gated())
    try:
        submitted = await runtime.submit(project.id, "consult", "x", session="s")
        waiter = asyncio.ensure_future(runtime.wait(submitted.job_id, 10))
        await asyncio.sleep(0.05)
        for _ in range(3000):
            runtime.hub.publish(submitted.job_id, "queued")
        await asyncio.sleep(0.1)
        assert not waiter.done()

        gate.set()
        assert (await waiter).state == "succeeded"
    finally:
        gate.set()
        await runtime.close()
