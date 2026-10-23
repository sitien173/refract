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
