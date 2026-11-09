"""Claude helpers: a fake ``claude`` stub through the transport, and a direct parser driver."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest

from refract.backends import BackendParams, BackendResult
from refract.backends import claude
from refract.backends._process import ProcessOutcome

from tests.cli_stub import stub_cli


def stub_claude(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    lines: Iterable[str] = (),
    *,
    exit_code: int = 0,
    sleep_s: float = 0.0,
    record: Path | None = None,
    pid_file: Path | None = None,
) -> None:
    """Make ``claude`` resolve to a launcher that prints ``lines`` and exits with ``exit_code``."""
    stub_cli(
        monkeypatch,
        tmp_path,
        "claude",
        lines,
        exit_code=exit_code,
        sleep_s=sleep_s,
        record=record,
        pid_file=pid_file,
    )


async def feed_claude(
    params: BackendParams,
    lines: Iterable[str],
    process: ProcessOutcome | None = None,
) -> BackendResult:
    """Feed recorded stream lines through the Claude parser, then map the transport outcome."""
    emitter = params.emitter

    async def on_event(event: dict[str, Any]) -> None:
        emitter(event)

    run = claude.ClaudeRun(params, on_event if emitter is not None else None)
    for line in lines:
        await run.feed(line)
    result = run.outcome(process or ProcessOutcome())
    if params.cancel_event is not None and params.cancel_event.is_set():
        result.outcome = "FATAL"
        result.error_class = "cancelled"
        result.error = "backend command cancelled"
    return result


def drive_claude(
    params: BackendParams,
    lines: Iterable[str],
    process: ProcessOutcome | None = None,
) -> BackendResult:
    """Synchronous form of ``feed_claude`` for tests that do not run an event loop."""
    return asyncio.run(feed_claude(params, lines, process))


__all__ = ["drive_claude", "feed_claude", "stub_claude"]
