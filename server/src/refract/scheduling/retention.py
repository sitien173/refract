"""History retention: prune old transcript content and job rows, once at start and then hourly."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from refract.logging_setup import get_logger
from refract.store.database import Database
from refract.store.pool import run_on

log = get_logger("runtime")
RETENTION_INTERVAL_S = 3600
DEFAULT_RETENTION_DAYS = 7
JOB_ROWS_RETENTION_DAYS = 365


def prune(database: Database, days: int = DEFAULT_RETENTION_DAYS) -> None:
    now = datetime.now(timezone.utc)
    database.prune_retention(
        content_before=(now - timedelta(days=days)).isoformat(),
        rows_before=(now - timedelta(days=JOB_ROWS_RETENTION_DAYS)).isoformat(),
    )


class RetentionSweep:
    """Runs `prune` on the store executor every `RETENTION_INTERVAL_S` until stopped."""

    def __init__(self, database: Database, prune_now: Callable[[], None]) -> None:
        self.database = database
        self.prune_now = prune_now
        self.task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self.task = asyncio.create_task(self._run(), name="refract-retention")

    async def stop(self) -> None:
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(RETENTION_INTERVAL_S)
            try:
                await run_on(self.database.executor, self.prune_now)
            except Exception:
                log.warning("History retention failed", exc_info=True, extra={"event": "history.retention_failed"})
