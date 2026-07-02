"""Shared subprocess line-streaming helpers for backend CLIs."""

from __future__ import annotations

import queue
import shutil
import subprocess
import threading
import time
from collections.abc import Callable, Generator


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
) -> Generator[str, None, None]:
    """Execute a command and stream combined stdout and stderr lines."""
    popen_cmd = cmd.copy()
    executable_path = shutil.which(executable_name) or cmd[0]
    popen_cmd[0] = executable_path

    popen_kwargs: dict[str, object] = {
        "shell": False,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "universal_newlines": True,
        "encoding": "utf-8",
        "cwd": cwd,
    }
    if errors is not None:
        popen_kwargs["errors"] = errors

    process = subprocess.Popen(popen_cmd, **popen_kwargs)
    output_queue: queue.Queue[str | None] = queue.Queue()

    def read_output() -> None:
        if process.stdout:
            for line in iter(process.stdout.readline, ""):
                output_queue.put(line_transform(line))
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
    deadline = time.time() + timeout_s if timeout_s and timeout_s > 0 else None
    timed_out = False

    try:
        while True:
            try:
                line = output_queue.get(timeout=0.5)
                if line is None:
                    break
                yield line
            except queue.Empty:
                if deadline is not None and time.time() > deadline:
                    timed_out = True
                    break
                if process.poll() is not None and not thread.is_alive():
                    break
    finally:
        if process.poll() is None:
            try:
                process.terminate()
                try:
                    process.wait(timeout=terminate_wait_s)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            except OSError:
                pass
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
