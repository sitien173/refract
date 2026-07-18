"""Cross-platform subprocess lifecycle helpers.

Backend CLIs often launch child processes (for example, an npm ``.cmd``
launcher starts Node on Windows).  Keeping process-group creation and teardown
in one module prevents cancellation from leaking those children.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def prepare_command(command: list[str]) -> list[str]:
    """Use a safe native launcher for a resolved command.

    npm exposes both ``.cmd`` and ``.ps1`` shims on Windows. Passing untrusted
    prompt text through a batch shim lets ``cmd.exe`` interpret characters such
    as ``&`` and ``%``. Prefer the companion PowerShell shim, whose ``-File``
    arguments retain their literal values.
    """
    if os.name != "nt" or not command:
        return command
    executable = Path(command[0])
    if executable.suffix.lower() not in {".bat", ".cmd"}:
        return command
    powershell_shim = executable.with_suffix(".ps1")
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if not powershell_shim.is_file() or powershell is None:
        raise OSError(
            f"Windows batch launcher {executable} requires a matching .ps1 shim "
            "and PowerShell so arguments can be passed safely"
        )
    return [
        powershell,
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        os.fspath(powershell_shim),
        *command[1:],
    ]


def process_group_kwargs() -> Mapping[str, Any]:
    """Return ``Popen`` options for a new, independently cancellable group."""
    if os.name == "nt":
        return {
            "creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        }
    return {"start_new_session": True}


def _wait(process: subprocess.Popen[str], timeout_s: float) -> bool:
    try:
        process.wait(timeout=max(0.0, timeout_s))
    except subprocess.TimeoutExpired:
        return False
    except OSError:
        return process.poll() is not None
    return True


def _taskkill(process_id: int, *, force: bool, timeout_s: float) -> None:
    taskkill = shutil.which("taskkill")
    if taskkill is None:
        return
    command = [taskkill, "/PID", str(process_id), "/T"]
    if force:
        command.append("/F")
    try:
        subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            shell=False,
            timeout=max(1.0, timeout_s),
        )
    except (OSError, subprocess.SubprocessError):
        return


def _terminate_windows(process: subprocess.Popen[str], wait_s: float) -> None:
    # CREATE_NEW_PROCESS_GROUP lets console applications receive CTRL_BREAK.
    # If a wrapper does not handle it, taskkill /T is the Windows-native tree
    # fallback; terminating only the .cmd/Node launcher can orphan its child.
    try:
        process.send_signal(signal.CTRL_BREAK_EVENT)
    except (AttributeError, OSError, ValueError):
        pass
    # Snapshot and stop the tree while the launcher PID still identifies it.
    # This also handles non-console descendants that cannot receive CTRL_BREAK.
    _taskkill(process.pid, force=False, timeout_s=wait_s)

    if _wait(process, wait_s):
        return
    _taskkill(process.pid, force=True, timeout_s=wait_s)
    if process.poll() is None:
        try:
            process.kill()
        except OSError:
            return
        _wait(process, wait_s)


def _process_group_exists(group_id: int) -> bool:
    try:
        os.killpg(group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminate_posix(process: subprocess.Popen[str], wait_s: float) -> None:
    group_id = process.pid
    deadline = time.monotonic() + max(0.0, wait_s)
    try:
        os.killpg(group_id, signal.SIGTERM)
    except ProcessLookupError:
        return
    except OSError:
        try:
            process.terminate()
        except OSError:
            return

    _wait(process, max(0.0, deadline - time.monotonic()))
    while _process_group_exists(group_id) and time.monotonic() < deadline:
        time.sleep(0.05)
    if not _process_group_exists(group_id):
        return
    try:
        os.killpg(group_id, signal.SIGKILL)
    except ProcessLookupError:
        return
    except OSError:
        try:
            process.kill()
        except OSError:
            return
    _wait(process, wait_s)


def terminate_process_tree(
    process: subprocess.Popen[str],
    *,
    wait_s: float,
) -> None:
    """Stop a process and descendants created in its OpenMCP process group."""
    # Do not return solely because the launcher exited: descendants may still
    # own the output pipe or remain in the POSIX process group.
    if os.name == "nt":
        if process.poll() is not None:
            return
        _terminate_windows(process, wait_s)
    else:
        _terminate_posix(process, wait_s)


__all__ = ["prepare_command", "process_group_kwargs", "terminate_process_tree"]
