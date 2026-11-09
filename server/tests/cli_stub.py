"""Install fake backend CLI executables and drive backends through the real transport."""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import threading
from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path
from typing import Any

import pytest

from refract.backends import BackendParams, BackendResult
from refract.backends._process import ProcessOutcome
from refract.config import TargetConfig
from refract.drivers import DriverRegistry, DriverResult
from tests.launchers import install_launcher

FAKE_CLI = Path(__file__).parent / "fixtures" / "fake_cli" / "fake_cli.py"


class ShellCommandFailed(subprocess.SubprocessError):
    """Raised by a generator fake to report a nonzero exit through ``shell_fake_as_process``."""

    def __init__(self, returncode: int) -> None:
        super().__init__(f"backend command exited with status {returncode}")
        self.returncode = returncode


def stub_cli(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    executable: str,
    lines: Iterable[str] = (),
    *,
    exit_code: int = 0,
    sleep_s: float = 0.0,
    record: Path | None = None,
    pid_file: Path | None = None,
    raw_hex: Iterable[str] = (),
    log_text: str | None = None,
    last_message: str | None = None,
) -> None:
    """Make ``executable`` resolve to a launcher that runs ``FAKE_CLI``.

    ``lines`` are printed after ``raw_hex`` entries, which are written as raw bytes.
    ``last_message`` is written to the ``-o`` path when the backend passes one.
    ``shutil.which`` still resolves every other executable name normally.
    """
    bin_dir = tmp_path / f"fake-{executable}-bin"
    bin_dir.mkdir(exist_ok=True)
    config = tmp_path / f"fake-{executable}.json"
    config.write_text(
        json.dumps({
            "name": executable,
            "lines": list(lines),
            "raw_hex": list(raw_hex),
            "exit_code": exit_code,
            "sleep_s": sleep_s,
            "record": None if record is None else str(record),
            "pid_file": None if pid_file is None else str(pid_file),
            "log_text": log_text,
            "last_message": last_message,
        }),
        encoding="utf-8",
    )
    launcher = install_launcher(bin_dir, executable, FAKE_CLI, [str(config)])

    previous = shutil.which
    fake_path = str(launcher)
    monkeypatch.setattr(
        shutil,
        "which",
        lambda name, *args, **kwargs: fake_path if name == executable else previous(name, *args, **kwargs),
    )


def fake_run_process(
    lines: Iterable[str] = (),
    outcome: ProcessOutcome | None = None,
) -> Callable[..., Awaitable[ProcessOutcome]]:
    """Stand-in for a backend module's ``run_process``: feed ``lines`` to the parser, then return ``outcome``."""
    collected = list(lines)

    async def run(argv, stdin, env, cwd, deadline, cancel, on_line):
        for line in collected:
            await on_line(line)
        return outcome or ProcessOutcome()

    return run


def shell_fake_as_process(fake: Callable[..., Iterable[str]]) -> Callable[..., Awaitable[ProcessOutcome]]:
    """Adapt a ``run_shell_command``-style generator fake to ``run_process``. It receives argv and ``cwd``."""

    async def run(argv, stdin, env, cwd, deadline, cancel, on_line):
        try:
            for line in fake(argv, cwd=cwd):
                await on_line(line)
        except subprocess.TimeoutExpired:
            return ProcessOutcome(error="subprocess timed out", error_class="timeout")
        except ShellCommandFailed as exc:
            return ProcessOutcome(
                returncode=exc.returncode,
                error=f"backend command exited with status {exc.returncode}",
                error_class="execution_error",
            )
        return ProcessOutcome()

    return run


def execute_sync(execute: Callable[..., Awaitable[BackendResult]], params: BackendParams) -> BackendResult:
    """Run an async backend ``execute`` to completion. A set ``params.emitter`` becomes the ``on_event`` sink.

    A set ``params.cancel_event`` is mirrored into the ``asyncio.Event`` the backend receives, as the driver does.
    """
    emitter = params.emitter

    async def on_event(event: dict[str, Any]) -> None:
        emitter(event)

    async def run() -> BackendResult:
        cancel = asyncio.Event()

        async def mirror() -> None:
            while not params.cancel_event.is_set():
                await asyncio.sleep(0.01)
            cancel.set()

        watcher = asyncio.create_task(mirror()) if params.cancel_event is not None else None
        try:
            return await execute(params, cancel=cancel, on_event=on_event if emitter is not None else None)
        finally:
            if watcher is not None:
                watcher.cancel()

    return asyncio.run(run())


async def run_target(
    backend: str,
    cwd: Path,
    *,
    prompt: str = "p",
    session_id: str = "",
    timeout_s: int = 0,
    cancel_event: threading.Event | None = None,
    events: list[dict[str, Any]] | None = None,
) -> DriverResult:
    """Run one backend through ``DriverRegistry`` and collect its stream events."""
    sink = events if events is not None else []

    async def on_event(event: dict[str, Any]) -> None:
        sink.append(event)

    return await DriverRegistry().execute(
        target=TargetConfig(id=backend, backend=backend),
        prompt=prompt,
        cwd=cwd,
        session_id=session_id,
        timeout_s=timeout_s,
        cancel_event=cancel_event or threading.Event(),
        on_event=on_event,
    )


__all__ = ["FAKE_CLI", "execute_sync", "fake_run_process", "run_target", "shell_fake_as_process", "stub_cli"]
