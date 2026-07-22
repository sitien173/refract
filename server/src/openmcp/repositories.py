"""Direct Git repository inspection and mutation."""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from openmcp.logging_setup import get_logger


log = get_logger("repositories")


class RepositoryError(RuntimeError):
    """Raised when a required Git operation cannot complete."""


@dataclass(slots=True, frozen=True)
class RepositoryState:
    root: Path
    head: str
    branch: str
    clean: bool


def _git(*args: str) -> str:
    executable = shutil.which("git")
    if executable is None:
        raise RepositoryError("Git was not found on PATH")
    started_at = time.monotonic()
    completed = subprocess.run(
        [executable, "-c", "core.quotepath=false", *args],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        check=False,
    )
    operation = args[2] if len(args) > 2 and args[0] == "-C" else args[0]
    if completed.returncode:
        error = completed.stderr.strip() or completed.stdout.strip()
        log.warning(
            "Git operation failed",
            extra={
                "event": "git.failed",
                "operation": operation,
                "return_code": completed.returncode,
                "duration_ms": round((time.monotonic() - started_at) * 1000, 2),
            },
        )
        raise RepositoryError(error or f"Git command failed: {' '.join(args)}")
    log.debug(
        "Git operation completed",
        extra={
            "event": "git.completed",
            "operation": operation,
            "duration_ms": round((time.monotonic() - started_at) * 1000, 2),
        },
    )
    return completed.stdout.strip()


def inspect_repository(path: Path) -> RepositoryState:
    resolved = path.expanduser().resolve()
    if not resolved.is_dir():
        raise RepositoryError(f"Project path does not exist: {resolved}")
    try:
        root = Path(_git("-C", str(resolved), "rev-parse", "--show-toplevel")).resolve()
        head_sha = _git("-C", str(root), "rev-parse", "HEAD")
    except RepositoryError as exc:
        raise RepositoryError(
            f"Project must be a Git repository: {resolved}: {exc}"
        ) from exc
    try:
        branch = _git("-C", str(root), "symbolic-ref", "--quiet", "--short", "HEAD")
    except RepositoryError as exc:
        raise RepositoryError("Project HEAD requires an attached branch") from exc
    status = _git(
        "-C", str(root), "status", "--porcelain=v1", "--untracked-files=all"
    )
    return RepositoryState(root=root, head=head_sha, branch=branch, clean=not status)


def head(path: Path) -> str:
    return _git("-C", str(path), "rev-parse", "HEAD")


def commit(path: Path, job_id: str, message: str = "") -> str:
    status = _git("-C", str(path), "status", "--porcelain=v1", "--untracked-files=all")
    if not status:
        return head(path)
    _git("-C", str(path), "add", "--all")
    _git("-C", str(path), "commit", "-m", message or f"openmcp: {job_id} implement")
    return head(path)


def reset(path: Path, commit_sha: str) -> None:
    _git("-C", str(path), "reset", "--hard", commit_sha)
    _git("-C", str(path), "clean", "-fd")


__all__ = [
    "RepositoryError",
    "RepositoryState",
    "commit",
    "head",
    "inspect_repository",
    "reset",
]
