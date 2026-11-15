from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from refract.store.database import Database
from refract.store.pool import run_db


class _OnDatabase:
    """A callable whose `__self__` is the database, like a bound Database method."""

    def __init__(self, db: Database, call: Callable[[], Any]) -> None:
        self.__self__ = db
        self._call = call

    def __call__(self) -> Any:
        return self._call()


@pytest.mark.asyncio
async def test_run_db_uses_the_store_pool_executor(tmp_path: Path) -> None:
    db = Database(tmp_path / "refract.db")
    try:
        names = {await run_db(_OnDatabase(db, lambda: threading.current_thread().name)) for _ in range(12)}
        assert all(name.startswith("refract-db") for name in names)
        assert len(names) <= 4
    finally:
        db.close()


@pytest.mark.asyncio
async def test_run_db_keeps_shield_on_cancel(tmp_path: Path) -> None:
    db = Database(tmp_path / "refract.db")
    release, started, finished = threading.Event(), threading.Event(), threading.Event()

    def blocking() -> None:
        started.set()
        release.wait(5)
        finished.set()

    try:
        task = asyncio.create_task(run_db(_OnDatabase(db, blocking)))
        await asyncio.get_running_loop().run_in_executor(None, started.wait, 5)
        task.cancel()
        await asyncio.wait({task}, timeout=0.05)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished.is_set()
    finally:
        db.close()
