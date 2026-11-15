"""In-process wake signals; the DB stays the source of truth.

A signal carries only `(job_id, kind)`. Subscribers re-read the DB on every wake-up, so
signals may coalesce and a subscriber never trusts the signal as state.
"""

from __future__ import annotations

import asyncio
import threading
from collections import deque
from collections.abc import Callable, Iterable
from typing import Literal, get_args

Kind = Literal["queued", "terminal", "question", "answer"]
KINDS: frozenset[str] = frozenset(get_args(Kind))
Signal = tuple[str, str]
_BACKLOG = 1024


def call_soon_safely(loop: asyncio.AbstractEventLoop, call: Callable[..., object], *args: object) -> None:
    """Hand `call` to `loop`; a loop that closes before the hand-off is skipped, so other targets still get theirs."""
    if loop.is_closed():
        return
    try:
        loop.call_soon_threadsafe(call, *args)
    except RuntimeError:
        pass


class Subscription:
    """One subscriber. Use as a context manager so it is removed on return, timeout, and cancellation."""

    def __init__(self, hub: Hub, job_ids: frozenset[str] | None) -> None:
        self._hub = hub
        self._job_ids = job_ids
        self._loop = asyncio.get_running_loop()
        self._wake = asyncio.Event()
        self._signals: deque[Signal] = deque(maxlen=_BACKLOG)
        self._overflowed = False

    def __enter__(self) -> Subscription:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Remove the subscription from the hub; safe to call more than once."""
        self._hub._remove(self)

    def _accepts(self, job_id: str) -> bool:
        return self._job_ids is None or job_id in self._job_ids

    def _deliver(self, signal: Signal) -> None:
        if len(self._signals) == _BACKLOG:
            self._overflowed = True
        self._signals.append(signal)
        self._wake.set()

    def clear(self) -> None:
        """Forget earlier wake-ups. Call before each DB read so a later signal is never missed."""
        self._wake.clear()

    def drain(self) -> list[Signal]:
        signals = list(self._signals)
        self._signals.clear()
        return signals

    def take_overflow(self) -> bool:
        """True once if the backlog evicted signals since the last call; the caller must re-read state."""
        overflowed, self._overflowed = self._overflowed, False
        return overflowed

    async def wait(self, timeout_s: float | None = None) -> bool:
        """True when a signal arrived since the last `clear`; False on timeout."""
        try:
            await asyncio.wait_for(self._wake.wait(), timeout_s)
        except TimeoutError:
            return False
        return True


class Hub:
    def __init__(self) -> None:
        self._subscribers: set[Subscription] = set()
        self._lock = threading.Lock()

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    def subscribe(self, job_ids: Iterable[str] | None = None) -> Subscription:
        """Subscribe to the listed jobs, or to every job when `job_ids` is None. Call from a running loop."""
        subscription = Subscription(self, None if job_ids is None else frozenset(job_ids))
        with self._lock:
            self._subscribers.add(subscription)
        return subscription

    def publish(self, job_id: str, kind: str) -> None:
        """Wake matching subscribers; safe from any thread."""
        if kind not in KINDS:
            raise ValueError(f"Unknown hub signal kind: {kind!r}")
        with self._lock:
            targets = [sub for sub in self._subscribers if sub._accepts(job_id)]
        for sub in targets:
            call_soon_safely(sub._loop, sub._deliver, (job_id, kind))

    def wake(self, job_id: str | None = None) -> None:
        """Wake subscribers of `job_id`, or all of them, with no signal so they re-check local state."""
        with self._lock:
            targets = [sub for sub in self._subscribers if job_id is None or sub._accepts(job_id)]
        for sub in targets:
            call_soon_safely(sub._loop, sub._wake.set)

    def _remove(self, subscription: Subscription) -> None:
        with self._lock:
            self._subscribers.discard(subscription)


__all__ = ["Hub", "Kind", "KINDS", "Signal", "Subscription"]
