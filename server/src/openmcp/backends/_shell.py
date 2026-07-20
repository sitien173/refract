"""Shared subprocess line-streaming helpers for backend CLIs."""

from __future__ import annotations

import queue
import shutil
import subprocess
import threading
import time
from collections.abc import Callable, Generator

from openmcp.processes import (
    prepare_command,
    process_group_kwargs,
    terminate_process_tree,
)


class ShellCommandCancelled(subprocess.SubprocessError):
    """Raised after a caller cancels an active backend process."""


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
) -> Generator[str, None, None]:
    """Execute a command and stream combined stdout and stderr lines."""
    popen_cmd = cmd.copy()
    executable_path = shutil.which(executable_name) or cmd[0]
    popen_cmd[0] = executable_path
    popen_cmd = prepare_command(popen_cmd)

    popen_kwargs: dict[str, object] = {
        "shell": False,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "universal_newlines": True,
        "encoding": "utf-8",
        "cwd": cwd,
        **process_group_kwargs(),
    }
    if errors is not None:
        popen_kwargs["errors"] = errors

    process = subprocess.Popen(popen_cmd, **popen_kwargs)
    output_queue: queue.Queue[str | None] = queue.Queue()

    def read_output() -> None:
        try:
            if process.stdout:
                for line in iter(process.stdout.readline, ""):
                    output_queue.put(line_transform(line))
        except (OSError, ValueError):
            # Cancellation may close the pipe while the reader is blocked.
            pass
        finally:
            if process.stdout:
                if suppress_stdout_close_errors:
                    try:
                        process.stdout.close()
                    except OSError:
                        pass
                else:
                    process.stdout.close()
            output_queue.put(None)

    thread = threading.Thread(target=read_output, daemon=True)
    thread.start()
    deadline = time.monotonic() + timeout_s if timeout_s and timeout_s > 0 else None
    timed_out = False
    cancelled = False

    try:
        while True:
            try:
                line = output_queue.get(timeout=0.5)
                if line is None:
                    break
                yield line
            except queue.Empty:
                if cancel_event is not None and cancel_event.is_set():
                    cancelled = True
                    break
                if deadline is not None and time.monotonic() > deadline:
                    timed_out = True
                    break
                if process.poll() is not None and not thread.is_alive():
                    break
    finally:
        terminate_process_tree(process, wait_s=terminate_wait_s)
        thread.join(timeout=terminate_wait_s)

    while not output_queue.empty():
        try:
            line = output_queue.get_nowait()
            if line is not None:
                yield line
        except queue.Empty:
            break

    if timed_out:
        raise subprocess.TimeoutExpired(cmd=popen_cmd, timeout=float(timeout_s or 0))
    if cancelled:
        raise ShellCommandCancelled("backend command cancelled")


__all__ = ["ShellCommandCancelled", "stream_shell_command_lines"]
