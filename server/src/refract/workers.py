"""Blocking work that must finish before its caller releases resources."""

import asyncio
from collections.abc import Callable
from contextlib import suppress


async def run_sync[**P, R](call: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs) -> R:
    task = asyncio.create_task(asyncio.to_thread(call, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # Repeated cancellation must not abandon a worker before DB shutdown.
        joined = asyncio.gather(task, return_exceptions=True)
        while not joined.done():
            with suppress(asyncio.CancelledError):
                await asyncio.shield(joined)
        raise
