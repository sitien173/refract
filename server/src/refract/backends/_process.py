"""Asyncio subprocess transport for backend CLIs."""

from __future__ import annotations

import asyncio
import os
import shutil
import time
from collections import deque
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass

from refract.logging_setup import get_logger
from refract.processes import kill_process_tree, prepare_command, process_group_kwargs

log = get_logger("backends")

TAIL_BYTES = 64 * 1024
LINE_LIMIT_BYTES = 1024 * 1024
EXIT_GRACE_S = 2.0
POLL_INTERVAL_S = 0.1

LineHandler = Callable[[str], Awaitable[None]]
SpawnHook = Callable[[int], Awaitable[None]]

# Set by the job runner to record each worker's process group for crash cleanup.
spawn_hook: ContextVar[SpawnHook | None] = ContextVar("spawn_hook", default=None)


@dataclass(slots=True)
class ProcessOutcome:
    """Exit status, newest output tail, and the failure that ended the run, if any."""

    returncode: int | None = None
    tail: str = ""
    error: str = ""
    error_class: str = ""


class OutputTail:
    """Newest lines within ``TAIL_BYTES``. The newest line is always kept, even when larger."""

    def __init__(self) -> None:
        self._lines: deque[tuple[str, int]] = deque()
        self._size = 0

    def append(self, line: str) -> None:
        size = len(line.encode("utf-8")) + 1
        self._lines.append((line, size))
        self._size += size
        while self._size > TAIL_BYTES and len(self._lines) > 1:
            self._size -= self._lines.popleft()[1]

    def text(self) -> str:
        return "\n".join(line for line, _ in self._lines)


async def _write_stdin(stdin: asyncio.StreamWriter, payload: bytes) -> None:
    stdin.write(payload)
    await stdin.drain()
    stdin.close()


async def _discard_until_eof(stdout: asyncio.StreamReader) -> None:
    """Drain the killed group's leftover output so asyncio can close the pipe transport."""
    try:
        while await asyncio.wait_for(stdout.read(64 * 1024), EXIT_GRACE_S):
            pass
    except asyncio.TimeoutError:
        pass


def _stdin_failure(writer: asyncio.Future[None] | None) -> BaseException | None:
    if writer is None or not writer.done() or writer.cancelled():
        return None
    return writer.exception()


def _stdin_outcome(failure: BaseException) -> tuple[str, str]:
    return f"stdin write failed: {type(failure).__name__}: {failure}", "stdin_failed"


def _stop_reason(
    now: float,
    deadline: float | None,
    cancel: asyncio.Event | None,
    writer: asyncio.Future[None] | None,
    outcome: ProcessOutcome,
) -> str:
    """Return the first stop reason in check order: cancel, deadline, stdin failure. Empty means keep going."""
    if cancel is not None and cancel.is_set():
        return "cancelled"
    if deadline is not None and now >= deadline:
        return "timeout"
    failure = _stdin_failure(writer)
    if failure is None:
        return ""
    outcome.error, outcome.error_class = _stdin_outcome(failure)
    return "failed"


def _note_exit(process: asyncio.subprocess.Process, exited_at: float | None, now: float) -> float | None:
    """Return when the leader was first seen exited, or ``exited_at`` unchanged while it still runs."""
    if process.returncode is not None and exited_at is None:
        return now
    return exited_at


async def _read_one(
    stdout: asyncio.StreamReader,
    tail: OutputTail,
    on_line: LineHandler,
    outcome: ProcessOutcome,
) -> str:
    """Read and handle one line. Return "" to keep looping, "eof" at end of output, or "failed"."""
    try:
        raw = await asyncio.wait_for(stdout.readline(), POLL_INTERVAL_S)
    except asyncio.TimeoutError:
        return ""
    except ValueError:
        outcome.error, outcome.error_class = "output line exceeds 1 MiB", "execution_error"
        return "failed"
    if not raw:
        return "eof"
    line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
    tail.append(line)
    try:
        await on_line(line)
    except Exception as exc:  # noqa: BLE001 - a parser or emitter failure fails the attempt
        outcome.error, outcome.error_class = f"{type(exc).__name__}: {exc}", "execution_error"
        return "failed"
    return ""


async def _pump(
    process: asyncio.subprocess.Process,
    writer: asyncio.Future[None] | None,
    deadline: float | None,
    cancel: asyncio.Event | None,
    on_line: LineHandler,
    tail: OutputTail,
    outcome: ProcessOutcome,
) -> str:
    """Poll the child until a stop reason, leader exit plus grace, or EOF. Return the stop reason or ""."""
    assert process.stdout is not None
    exited_at: float | None = None
    eof = False
    while True:
        now = time.monotonic()
        stop = _stop_reason(now, deadline, cancel, writer, outcome)
        if stop:
            return stop
        exited_at = _note_exit(process, exited_at, now)
        if exited_at is not None and (eof or now - exited_at >= EXIT_GRACE_S):
            return ""
        if eof:
            await asyncio.sleep(POLL_INTERVAL_S)
            continue
        step = await _read_one(process.stdout, tail, on_line, outcome)
        if step == "failed":
            return step
        eof = step == "eof"


async def _finish_stdin(writer: asyncio.Future[None], outcome: ProcessOutcome) -> str:
    """Give the stdin writer ``EXIT_GRACE_S`` to finish. Return "failed" when it failed, else ""."""
    await asyncio.wait({writer}, timeout=EXIT_GRACE_S)
    failure = _stdin_failure(writer)
    if failure is None:
        return ""
    outcome.error, outcome.error_class = _stdin_outcome(failure)
    return "failed"


def _map_stop(outcome: ProcessOutcome, stop: str, name: str) -> None:
    """Set the final error from the stop reason, or from a nonzero exit when nothing stopped the run."""
    if stop == "cancelled":
        outcome.error, outcome.error_class = "backend command cancelled", "cancelled"
    elif stop == "timeout":
        outcome.error, outcome.error_class = f"{name} subprocess timed out", "timeout"
    elif not stop and outcome.returncode:
        outcome.error = f"backend command exited with status {outcome.returncode}"
        outcome.error_class = "execution_error"


async def _spawn(
    command: list[str],
    payload: bytes | None,
    env: dict[str, str] | None,
    cwd: str | None,
) -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        *command,
        stdin=asyncio.subprocess.DEVNULL if payload is None else asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=cwd,
        env=None if env is None else {**os.environ, **env},
        limit=LINE_LIMIT_BYTES,
        **process_group_kwargs(),
    )


async def run_process(
    argv: list[str],
    stdin: str | None,
    env: dict[str, str] | None,
    cwd: str | None,
    deadline: float | None,
    cancel: asyncio.Event | None,
    on_line: LineHandler,
) -> ProcessOutcome:
    """Run ``argv`` in a new process group and await ``on_line`` for each output line.

    stderr is merged into stdout. ``stdin`` is UTF-8 encoded before spawn, written,
    then closed. The process group is killed on every exit path. ``deadline`` (a
    ``time.monotonic`` value) and a set ``cancel`` event kill it at once. After the
    leader exits, the pipe gets ``EXIT_GRACE_S`` to reach EOF before the group is killed.
    """
    try:
        payload = None if stdin is None else stdin.encode("utf-8")
    except UnicodeEncodeError as exc:
        return ProcessOutcome(error=f"prompt is not valid UTF-8: {exc}", error_class="request_fatal")

    name = os.path.basename(argv[0])
    started_at = time.monotonic()
    command = prepare_command([shutil.which(argv[0]) or argv[0], *argv[1:]])
    process = await _spawn(command, payload, env, cwd)
    assert process.stdout is not None
    writer = asyncio.ensure_future(_write_stdin(process.stdin, payload)) if payload is not None else None
    tail = OutputTail()
    outcome = ProcessOutcome()
    try:
        hook = spawn_hook.get()
        if hook is not None:
            await hook(process.pid)
        stop = await _pump(process, writer, deadline, cancel, on_line, tail, outcome)
        if not stop and writer is not None:
            stop = await _finish_stdin(writer, outcome)
    finally:
        if writer is not None and not writer.done():
            writer.cancel()
        kill_process_tree(process.pid)
        await process.wait()
        if process.stdin is not None:
            process.stdin.close()
        await _discard_until_eof(process.stdout)
        outcome.returncode = process.returncode
        outcome.tail = tail.text()

    _map_stop(outcome, stop, name)
    if outcome.error_class:
        log.warning("%s subprocess ended class=%s after %.2fs", name, outcome.error_class, time.monotonic() - started_at)
    return outcome


__all__ = ["LineHandler", "OutputTail", "ProcessOutcome", "run_process"]
