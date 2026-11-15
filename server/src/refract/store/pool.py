"""Connections and a fixed-size DB executor; each transaction runs wholly on one thread."""

from __future__ import annotations

import asyncio
import contextvars
import functools
import sqlite3
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any, Concatenate

DEFAULT_SIZE = 4


@contextmanager
def tx(connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """BEGIN IMMEDIATE, then commit on success or roll back on error; join a transaction already open."""
    if connection.in_transaction:
        yield connection
        return
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield connection
    except BaseException:
        connection.rollback()
        raise
    connection.commit()


def writes[**P, R](call: Callable[Concatenate[sqlite3.Connection, P], R]) -> Callable[Concatenate[sqlite3.Connection, P], R]:
    """Run a store write in its own transaction, or inside the caller's open one."""

    @functools.wraps(call)
    def wrapper(connection: sqlite3.Connection, /, *args: P.args, **kwargs: P.kwargs) -> R:
        with tx(connection):
            return call(connection, *args, **kwargs)

    return wrapper


class Pool:
    """One SQLite connection per thread plus a fixed set of executor threads for callers that hand off work."""

    def __init__(self, path: Path, size: int = DEFAULT_SIZE) -> None:
        self._path = path
        self._local = threading.local()
        self._connections: list[sqlite3.Connection] = []
        self._lock = threading.Lock()
        self._closed = False
        self._executor = ThreadPoolExecutor(max_workers=size, thread_name_prefix="refract-db")

    @property
    def executor(self) -> ThreadPoolExecutor:
        return self._executor

    @property
    def connection(self) -> sqlite3.Connection:
        if self._closed:
            raise sqlite3.ProgrammingError("Cannot operate on a closed database.")
        connection = getattr(self._local, "connection", None)
        if connection is None:
            with self._lock:
                if self._closed:
                    raise sqlite3.ProgrammingError("Cannot operate on a closed database.")
                # Each thread exclusively uses its own connection. Disabling affinity
                # lets close() shut every connection from the owner's thread.
                connection = sqlite3.connect(self._path, check_same_thread=False)
                connection.row_factory = sqlite3.Row
                try:
                    connection.execute("PRAGMA journal_mode=WAL")
                    connection.execute("PRAGMA synchronous=NORMAL")
                    connection.execute("PRAGMA foreign_keys=ON")
                except Exception:
                    connection.close()
                    raise
                self._connections.append(connection)
                self._local.connection = connection
        return connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with tx(self.connection) as connection:
            yield connection

    def submit(self, call: Callable[..., Any], /, *args: Any) -> Future[Any]:
        """Run `call(connection, *args)` on an executor thread, on that thread's connection."""
        return self._executor.submit(lambda: call(self.connection, *args))

    def run(self, call: Callable[..., Any], /, *args: Any) -> Any:
        return self.submit(call, *args).result()

    def close(self) -> None:
        self._executor.shutdown(wait=True)
        with self._lock:
            self._closed = True
            for connection in self._connections:
                connection.close()
            self._connections.clear()


async def _run_on[**P, R](executor: Executor | None, call: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs) -> R:
    loop = asyncio.get_running_loop()
    bound = functools.partial(contextvars.copy_context().run, call, *args, **kwargs)
    task = asyncio.ensure_future(loop.run_in_executor(executor, bound))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # Repeated cancellation must not abandon a worker before DB shutdown.
        joined = asyncio.gather(task, return_exceptions=True)
        while not joined.done():
            with suppress(asyncio.CancelledError):
                await asyncio.shield(joined)
        raise


async def run_sync[**P, R](call: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs) -> R:
    """Run non-DB blocking work on the default executor."""
    return await _run_on(None, call, *args, **kwargs)


async def run_db[**P, R](call: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs) -> R:
    """Run a bound `Database` method on the store pool's fixed executor."""
    owner = getattr(call, "__self__", None)
    return await _run_on(getattr(owner, "executor", None), call, *args, **kwargs)


async def run_on[**P, R](executor: Executor, call: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs) -> R:
    """Run `call` on an explicit executor, such as `Database.executor`, with the same shield on cancel."""
    return await _run_on(executor, call, *args, **kwargs)
