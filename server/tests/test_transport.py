"""Transport tests for run_process against fake CLI scripts."""

from __future__ import annotations

import asyncio
import hashlib
import sys
import time
from pathlib import Path

from refract.backends._process import run_process

FAKE_CLI = Path(__file__).parent / "fixtures" / "fake_cli"


def fake(script: str, *args: object) -> list[str]:
    return [sys.executable, str(FAKE_CLI / script), *(str(arg) for arg in args)]


def _is_running(pid: int) -> bool:
    """Return False for an exited or zombie PID."""
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as handle:
            state = handle.read().rsplit(")", 1)[1].split()[0]
    except (FileNotFoundError, ProcessLookupError):
        return False
    return state != "Z"


def _wait_gone(pid: int, timeout_s: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if not _is_running(pid):
            return True
        time.sleep(0.05)
    return not _is_running(pid)


def _run(argv, *, stdin=None, timeout_s=None, cancel=None, on_line=None):
    lines: list[str] = []

    async def collect(line: str) -> None:
        lines.append(line)
        if on_line is not None:
            await on_line(line)

    deadline = time.monotonic() + timeout_s if timeout_s is not None else None
    outcome = asyncio.run(run_process(argv, stdin, None, None, deadline, cancel, collect))
    return outcome, lines


def test_stderr_is_merged_into_stdout_and_exit_status_is_returned() -> None:
    outcome, lines = _run(fake("emit_both.py"))

    assert sorted(lines) == ["err-line", "out-line"]
    assert outcome.returncode == 0
    assert outcome.error == ""


def test_one_mib_prompt_reaches_stdin_reading_child_intact() -> None:
    prompt = "p" * (1024 * 1024)
    outcome, lines = _run(fake("echo_stdin.py"), stdin=prompt)

    data = prompt.encode("utf-8")
    assert lines == [str(len(data)), hashlib.sha256(data).hexdigest()]
    assert outcome.error == ""


def test_non_utf8_output_is_decoded_with_replacement_characters() -> None:
    outcome, lines = _run(fake("non_utf8.py"))

    assert lines == ["�ok"]
    assert outcome.error == ""


def test_grandchild_holding_stdout_does_not_stall_after_parent_exit(tmp_path: Path) -> None:
    pid_file = tmp_path / "grandchild.pid"
    started = time.monotonic()
    outcome, lines = _run(fake("grandchild.py", pid_file), timeout_s=30)
    elapsed = time.monotonic() - started

    assert lines == ["parent-done"]
    assert outcome.returncode == 0
    assert outcome.error == ""
    assert elapsed < 5
    assert _wait_gone(int(pid_file.read_text(encoding="utf-8")))


def test_timeout_kills_the_whole_process_group(tmp_path: Path) -> None:
    pid_file = tmp_path / "grandchild.pid"
    started = time.monotonic()
    outcome, _ = _run(fake("spawn_and_sleep.py", pid_file), timeout_s=0.5)
    elapsed = time.monotonic() - started

    grandchild = int(pid_file.read_text(encoding="utf-8"))
    assert outcome.error_class == "timeout"
    assert elapsed < 5
    assert _wait_gone(grandchild)


def test_cancel_kills_the_process_group_immediately(tmp_path: Path) -> None:
    pid_file = tmp_path / "grandchild.pid"
    cancel = asyncio.Event()
    started = time.monotonic()

    async def cancel_on_ready(line: str) -> None:
        if line == "ready":
            cancel.set()

    outcome, _ = _run(fake("spawn_and_sleep.py", pid_file), cancel=cancel, on_line=cancel_on_ready)
    elapsed = time.monotonic() - started

    grandchild = int(pid_file.read_text(encoding="utf-8"))
    assert outcome.error_class == "cancelled"
    assert elapsed < 5
    assert _wait_gone(grandchild)


def test_cancelled_caller_task_propagates_cancelled_error() -> None:
    async def scenario() -> None:
        async def on_line(line: str) -> None:
            return None

        task = asyncio.create_task(run_process(fake("sleeper.py"), None, None, None, None, None, on_line))
        await asyncio.sleep(0.5)
        task.cancel()
        await task

    try:
        asyncio.run(scenario())
    except asyncio.CancelledError:
        return
    raise AssertionError("CancelledError was swallowed")


def test_stdin_write_failure_is_reported_as_request_error() -> None:
    outcome, _ = _run(fake("exit_now.py"), stdin="x" * (1024 * 1024))

    assert outcome.error_class == "stdin_failed"
    assert outcome.error.startswith("stdin write failed:")


def test_parser_exception_fails_attempt_and_kills_group(tmp_path: Path) -> None:
    pid_file = tmp_path / "grandchild.pid"

    async def explode(line: str) -> None:
        if line == "ready":
            raise ValueError("boom")

    outcome, _ = _run(fake("spawn_and_sleep.py", pid_file), on_line=explode, timeout_s=30)

    grandchild = int(pid_file.read_text(encoding="utf-8"))
    assert outcome.error == "ValueError: boom"
    assert outcome.error_class == "execution_error"
    assert _wait_gone(grandchild)


def test_nonzero_exit_reports_status_and_keeps_output() -> None:
    outcome, lines = _run(fake("exit_status.py"))

    assert lines == ["failing"]
    assert outcome.returncode == 3
    assert outcome.error == "backend command exited with status 3"
    assert outcome.error_class == "execution_error"


def test_tail_keeps_last_64_kib_while_every_line_reaches_the_parser() -> None:
    count = 20_000
    outcome, lines = _run(fake("many_lines.py", count))

    assert len(lines) == count
    assert len(outcome.tail.encode("utf-8")) <= 64 * 1024
    assert outcome.tail.endswith(lines[-1])
    assert lines[0] not in outcome.tail


def test_line_longer_than_one_mib_fails_the_attempt() -> None:
    outcome, _ = _run(fake("long_line.py"), timeout_s=30)

    assert outcome.error == "output line exceeds 1 MiB"
    assert outcome.error_class == "execution_error"



def test_unencodable_prompt_fails_before_the_child_starts(tmp_path: Path) -> None:
    marker = tmp_path / "started"
    argv = [sys.executable, "-c", f"open({str(marker)!r}, 'w').close()"]

    outcome, lines = _run(argv, stdin="bad \ud800 prompt")

    assert outcome.error_class == "request_fatal"
    assert "UTF-8" in outcome.error
    assert lines == []
    assert not marker.exists()
