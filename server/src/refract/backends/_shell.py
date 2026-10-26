"""Shared subprocess line-streaming helpers for backend CLIs."""

from __future__ import annotations

import os
import queue
import shutil
import subprocess
import threading
import time
from collections.abc import Callable, Generator, Iterator
from dataclasses import dataclass, field
from typing import Any

from refract.backends import BackendParams, parse_json_object
from refract.logging_setup import get_logger
from refract.processes import (
    prepare_command,
    process_group_kwargs,
    terminate_process_tree,
)


class ShellCommandCancelled(subprocess.SubprocessError):
    """Raised after a caller cancels an active backend process."""


class ShellCommandFailed(subprocess.SubprocessError):
    """Raised when a backend process exits unsuccessfully."""

    def __init__(self, returncode: int) -> None:
        self.returncode = returncode
        super().__init__(f"backend command exited with status {returncode}")


def _close_output(process: subprocess.Popen, suppress_errors: bool) -> None:
    if not process.stdout:
        return
    if suppress_errors:
        try:
            process.stdout.close()
        except OSError:
            pass
    else:
        process.stdout.close()


def _read_output(
    process: subprocess.Popen,
    output_queue: queue.Queue[str | None],
    line_transform: Callable[[str], str],
    suppress_stdout_close_errors: bool,
) -> None:
    try:
        if process.stdout:
            for line in iter(process.stdout.readline, ""):
                output_queue.put(line_transform(line))
    except (OSError, ValueError):
        # Cancellation may close the pipe while the reader is blocked.
        pass
    finally:
        _close_output(process, suppress_stdout_close_errors)
        output_queue.put(None)


def _write_input(process: subprocess.Popen, stdin_text: str) -> None:
    try:
        if process.stdin:
            process.stdin.write(stdin_text or "")
            process.stdin.close()
    except (OSError, ValueError):
        # The child may exit or be terminated before reading its input.
        pass


def _stream_stop_reason(deadline: float | None, cancel_event: threading.Event | None) -> str:
    if cancel_event is not None and cancel_event.is_set():
        return "cancelled"
    if deadline is not None and time.monotonic() > deadline:
        return "timeout"
    return ""


def _stream_output(
    process: subprocess.Popen,
    output_queue: queue.Queue[str | None],
    thread: threading.Thread,
    deadline: float | None,
    cancel_event: threading.Event | None,
) -> Generator[str, None, str]:
    while True:
        # Check before every read, including when output streams steadily.
        stop_reason = _stream_stop_reason(deadline, cancel_event)
        if stop_reason:
            return stop_reason
        try:
            line = output_queue.get(timeout=0.5)
        except queue.Empty:
            if process.poll() is not None and not thread.is_alive():
                return ""
            continue
        if line is None:
            return ""
        yield line


def _drain_output(output_queue: queue.Queue[str | None]) -> Iterator[str]:
    while not output_queue.empty():
        try:
            line = output_queue.get_nowait()
            if line is not None:
                yield line
        except queue.Empty:
            break


def stream_shell_command_lines(
    cmd: list[str],
    *,
    executable_name: str,
    cwd: str | None = None,
    timeout_s: int = 0,
    line_transform: Callable[[str], str],
    terminate_wait_s: int,
    errors: str | None = None,
    suppress_stdout_close_errors: bool = False,
    cancel_event: threading.Event | None = None,
    check_returncode: bool = False,
    stdin_text: str | None = None,
    env: dict[str, str] | None = None,
) -> Generator[str, None, None]:
    """Execute a command and stream combined stdout and stderr lines.

    ``stdin_text`` is written to the child's stdin and then closed. Prompts go
    there instead of argv to avoid argument length limits and ``ps`` exposure.
    """
    popen_cmd = cmd.copy()
    executable_path = shutil.which(executable_name) or cmd[0]
    popen_cmd[0] = executable_path
    popen_cmd = prepare_command(popen_cmd)

    popen_kwargs: dict[str, object] = {
        "shell": False,
        "stdin": subprocess.DEVNULL if stdin_text is None else subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "universal_newlines": True,
        "encoding": "utf-8",
        "cwd": cwd,
        **process_group_kwargs(),
    }
    if errors is not None:
        popen_kwargs["errors"] = errors
    if env is not None:
        merged_env = dict(os.environ)
        merged_env.update(env)
        popen_kwargs["env"] = merged_env

    process = subprocess.Popen(popen_cmd, **popen_kwargs)
    output_queue: queue.Queue[str | None] = queue.Queue()

    thread = threading.Thread(
        target=_read_output,
        args=(process, output_queue, line_transform, suppress_stdout_close_errors),
        daemon=True,
    )
    thread.start()
    if stdin_text is not None:
        threading.Thread(target=_write_input, args=(process, stdin_text), daemon=True).start()
    deadline = time.monotonic() + timeout_s if timeout_s and timeout_s > 0 else None

    try:
        stop_reason = yield from _stream_output(process, output_queue, thread, deadline, cancel_event)
    finally:
        terminate_process_tree(process, wait_s=terminate_wait_s)
        thread.join(timeout=terminate_wait_s)
        process.poll()

    yield from _drain_output(output_queue)

    if stop_reason == "timeout":
        raise subprocess.TimeoutExpired(cmd=popen_cmd, timeout=float(timeout_s or 0))
    if stop_reason == "cancelled":
        raise ShellCommandCancelled("backend command cancelled")
    if check_returncode and process.returncode:
        raise ShellCommandFailed(process.returncode)


@dataclass(slots=True)
class StreamOutcome:
    """Collected output of one backend run with each line parsed once."""

    lines: list[str] = field(default_factory=list)
    events: list[dict[str, Any] | None] = field(default_factory=list)
    error: str = ""
    error_class: str = ""

    def objects(self) -> Iterator[dict[str, Any]]:
        return (event for event in self.events if event is not None)


def consume_stream(
    run: Callable[..., Iterator[str]],
    cmd: list[str],
    params: BackendParams,
    *,
    cwd: str,
    name: str,
    on_event: Callable[[dict[str, Any]], None] | None = None,
    stdin_text: str | None = None,
) -> StreamOutcome:
    """Run a backend command, parse each line once, and map process failures.

    ``on_event`` receives each JSON object line while the command runs. Error
    text never includes exception strings, which can embed argv and the prompt.
    """
    log = get_logger(name)
    outcome = StreamOutcome()
    kwargs: dict[str, Any] = {"cwd": cwd, "timeout_s": params.timeout_s, "cancel_event": params.cancel_event}
    if stdin_text is not None:
        kwargs["stdin_text"] = stdin_text
    if params.env is not None:
        kwargs["env"] = params.env
    try:
        for line in run(cmd, **kwargs):
            event = parse_json_object(line.strip())
            outcome.lines.append(line)
            outcome.events.append(event)
            if on_event is not None and event is not None:
                on_event(event)
    except ShellCommandCancelled:
        outcome.error, outcome.error_class = "backend command cancelled", "cancelled"
        log.warning("%s subprocess cancelled", name)
    except subprocess.TimeoutExpired:
        outcome.error, outcome.error_class = f"{name} subprocess timed out after {params.timeout_s}s", "timeout"
        log.warning("%s subprocess timeout after %ss", name, params.timeout_s)
    except ShellCommandFailed as exc:
        outcome.error, outcome.error_class = str(exc), "execution_error"
        log.warning("%s subprocess exited with status %d", name, exc.returncode)
    except Exception as exc:  # noqa: BLE001
        outcome.error, outcome.error_class = f"{name} subprocess failed ({type(exc).__name__})", "execution_error"
        safe_error = RuntimeError(f"Unexpected backend error ({type(exc).__name__})")
        safe_error.__traceback__ = exc.__traceback__
        log.exception(
            "%s: unexpected error during stream type=%s", name, type(exc).__name__,
            exc_info=(type(safe_error), safe_error, safe_error.__traceback__),
        )
    return outcome


__all__ = [
    "ShellCommandCancelled",
    "ShellCommandFailed",
    "StreamOutcome",
    "consume_stream",
    "stream_shell_command_lines",
]
