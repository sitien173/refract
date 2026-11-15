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


def kill_process_tree(process_id: int) -> None:
    """Kill a POSIX process group or Windows process tree without waiting."""
    if os.name == "nt":
        _taskkill(process_id, force=True, timeout_s=5)
        return
    try:
        os.killpg(process_id, signal.SIGKILL)
    except OSError:
        return


def _group_members(group_id: int) -> list[Path]:
    members = []
    try:
        entries = list(Path("/proc").iterdir())
    except OSError:
        return members
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
        except (OSError, IndexError):
            continue
        if fields[2:3] == [str(group_id)]:
            members.append(entry)
    return members


def kill_stale_group(group_id: int, job_id: str) -> bool:
    """Kill a worker process group left by a crashed daemon. Return whether it was killed.

    A PGID can be reused by an unrelated process once the old group is gone. Workers run
    with ``REFRACT_JOB_ID`` in their environment, so the group is killed only when a member
    read from ``/proc`` carries this job's ID. Without ``/proc`` nothing is killed.
    """
    marker = f"REFRACT_JOB_ID={job_id}".encode()
    for member in _group_members(group_id):
        try:
            environ = (member / "environ").read_bytes().split(b"\0")
        except OSError:
            continue
        if marker in environ:
            try:
                os.killpg(group_id, signal.SIGKILL)
            except ProcessLookupError:
                return False
            return True
    return False


__all__ = ["kill_process_tree", "kill_stale_group", "prepare_command", "process_group_kwargs"]
