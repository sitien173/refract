from __future__ import annotations

import asyncio
import threading

import pytest

from refract.scheduling.cancel import CancelEvent


@pytest.mark.asyncio
async def test_wait_async_returns_when_already_set() -> None:
    event = CancelEvent()
    event.set()
    await asyncio.wait_for(event.wait_async(), 1)


@pytest.mark.asyncio
async def test_wait_async_wakes_on_set_from_another_thread() -> None:
    event = CancelEvent()
    waiter = asyncio.create_task(event.wait_async())
    await asyncio.sleep(0)
    assert not waiter.done()
    threading.Thread(target=event.set).start()
    await asyncio.wait_for(waiter, 2)
    assert event.is_set()


@pytest.mark.asyncio
async def test_every_waiter_wakes_and_cancelled_waiters_are_dropped() -> None:
    event = CancelEvent()
    first, second, dropped = (asyncio.create_task(event.wait_async()) for _ in range(3))
    await asyncio.sleep(0)
    dropped.cancel()
    await asyncio.gather(dropped, return_exceptions=True)
    event.set()
    await asyncio.wait_for(asyncio.gather(first, second), 1)
    assert not event._waiters
