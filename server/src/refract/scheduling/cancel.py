"""Thread-safe cancellation with an event-loop waiter."""

from __future__ import annotations

import asyncio
import threading

from refract.scheduling.hub import call_soon_safely


class CancelEvent(threading.Event):
    """A `threading.Event` that coroutines on any loop can also await."""

    def __init__(self) -> None:
        super().__init__()
        self._waiters: list[tuple[asyncio.AbstractEventLoop, asyncio.Event]] = []
        self._waiters_lock = threading.Lock()

    def set(self) -> None:
        with self._waiters_lock:
            super().set()
            waiters = tuple(self._waiters)
        for loop, event in waiters:
            call_soon_safely(loop, event.set)

    async def wait_async(self) -> None:
        """Return once the event is set; wake-up comes from `set`, never from polling."""
        event = asyncio.Event()
        entry = (asyncio.get_running_loop(), event)
        with self._waiters_lock:
            if self.is_set():
                return
            self._waiters.append(entry)
        try:
            await event.wait()
        finally:
            with self._waiters_lock:
                self._waiters.remove(entry)
