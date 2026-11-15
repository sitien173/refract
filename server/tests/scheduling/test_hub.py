from __future__ import annotations

import asyncio

import pytest

from refract.scheduling.hub import Hub


@pytest.mark.asyncio
async def test_publish_wakes_matching_subscriber_with_signal() -> None:
    hub = Hub()
    with hub.subscribe({"a"}) as sub:
        hub.publish("b", "queued")
        assert not await sub.wait(0.01)
        hub.publish("a", "terminal")
        assert await sub.wait(1)
        assert sub.drain() == [("a", "terminal")]


@pytest.mark.asyncio
async def test_signal_published_before_wait_is_not_lost() -> None:
    hub = Hub()
    with hub.subscribe({"a"}) as sub:
        hub.publish("a", "question")
        assert await sub.wait(1)


@pytest.mark.asyncio
async def test_subscriber_without_filter_sees_every_job() -> None:
    hub = Hub()
    with hub.subscribe() as sub:
        hub.publish("a", "queued")
        hub.publish("b", "answer")
        assert await sub.wait(1)
        assert sub.drain() == [("a", "queued"), ("b", "answer")]


@pytest.mark.asyncio
async def test_unknown_kind_is_rejected() -> None:
    with pytest.raises(ValueError):
        Hub().publish("a", "bogus")


@pytest.mark.asyncio
async def test_subscriber_removed_after_return() -> None:
    hub = Hub()
    with hub.subscribe({"a"}):
        assert hub.subscriber_count == 1
    assert hub.subscriber_count == 0


@pytest.mark.asyncio
async def test_subscriber_removed_after_timeout() -> None:
    hub = Hub()
    with hub.subscribe({"a"}) as sub:
        assert not await sub.wait(0.01)
    assert hub.subscriber_count == 0


@pytest.mark.asyncio
async def test_subscriber_removed_after_cancellation() -> None:
    hub = Hub()
    entered = asyncio.Event()

    async def waiter() -> None:
        with hub.subscribe({"a"}) as sub:
            entered.set()
            await sub.wait(30)

    task = asyncio.create_task(waiter())
    await entered.wait()
    assert hub.subscriber_count == 1
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert hub.subscriber_count == 0


@pytest.mark.asyncio
async def test_publish_from_another_thread_wakes_waiter() -> None:
    hub = Hub()
    with hub.subscribe({"a"}) as sub:
        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, hub.publish, "a", "terminal")
        assert await sub.wait(2)


@pytest.mark.asyncio
async def test_wake_interrupts_waiters_without_a_signal() -> None:
    hub = Hub()
    with hub.subscribe({"a"}) as sub, hub.subscribe({"b"}) as other:
        hub.wake("a")
        assert await sub.wait(1)
        assert sub.drain() == []
        assert not await other.wait(0.01)
        hub.wake()
        assert await other.wait(1)
