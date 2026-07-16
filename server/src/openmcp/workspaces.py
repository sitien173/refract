"""Git repository inspection and isolated worktree management."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class WorkspaceError(RuntimeError):
    pass


@dataclass(slots=True, frozen=True)
class RepositoryState:
    root: Path
    head: str
    clean: bool


def _git(*args: str, cwd: Path | None = None) -> str:
    git = shutil.which("git")
    if git is None:
        raise WorkspaceError("Git was not found on PATH")
    completed = subprocess.run(
        [git, *args],
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        check=False,
    )
    if completed.returncode:
        error = completed.stderr.strip() or completed.stdout.strip()
        raise WorkspaceError(error or f"Git command failed: {' '.join(args)}")
    return completed.stdout.strip()


def inspect_repository(path: Path) -> RepositoryState:
    resolved = path.expanduser().resolve()
    if not resolved.is_dir():
        raise WorkspaceError(f"Project path does not exist: {resolved}")
    try:
        root = Path(_git("-C", str(resolved), "rev-parse", "--show-toplevel")).resolve()
        head = _git("-C", str(root), "rev-parse", "HEAD")
        status = _git("-C", str(root), "status", "--porcelain=v1", "--untracked-files=all")
    except WorkspaceError as exc:
        raise WorkspaceError(f"Project must be a Git repository: {resolved}: {exc}") from exc
    return RepositoryState(root=root, head=head, clean=not status)


def ignored_paths(repository: Path, relatives: Iterable[str]) -> set[str]:
    values = sorted(set(relatives))
    if not values:
        return set()
    git = shutil.which("git")
    if git is None:
        raise WorkspaceError("Git was not found on PATH")
    completed = subprocess.run(
        [git, "-C", str(repository), "check-ignore", "-z", "--stdin"],
        input="\0".join(values) + "\0",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        check=False,
    )
    if completed.returncode in {0, 1}:
        return set(completed.stdout.rstrip("\0").split("\0")) - {""}
    error = completed.stderr.strip() or completed.stdout.strip()
    raise WorkspaceError(error or "Could not inspect ignored paths")


class WorkspaceManager:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def create_job(self, repository: Path, job_id: str, base_commit: str) -> tuple[Path, str]:
        path = self.root / job_id / "primary"
        path.parent.mkdir(parents=True, exist_ok=True)
        branch = f"openmcp/{job_id}"
        _git(
            "-C",
            str(repository),
            "worktree",
            "add",
            "-b",
            branch,
            str(path),
            base_commit,
        )
        return path, branch

    def create_reader(
        self,
        repository: Path,
        job_id: str,
        stage_id: str,
        worker: int,
        commit: str,
    ) -> Path:
        path = self.root / job_id / "readers" / f"{stage_id}-{worker}"
        if path.exists():
            self.remove(repository, path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _git(
            "-C",
            str(repository),
            "worktree",
            "add",
            "--detach",
            str(path),
            commit,
        )
        return path

    def restore_job(self, repository: Path, path: Path, branch: str) -> None:
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        _git("-C", str(repository), "worktree", "add", str(path), branch)

    def remove(self, repository: Path, path: Path) -> None:
        if path.exists():
            try:
                _git("-C", str(repository), "worktree", "remove", "--force", str(path))
            except WorkspaceError:
                shutil.rmtree(path, ignore_errors=True)
                _git("-C", str(repository), "worktree", "prune")
        parent = path.parent
        while parent != self.root and parent.is_relative_to(self.root):
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent

    @staticmethod
    def head(path: Path) -> str:
        return _git("-C", str(path), "rev-parse", "HEAD")

    @staticmethod
    def commit(
        path: Path,
        job_id: str,
        stage_id: str,
        *,
        message: str = "",
    ) -> str:
        status = _git("-C", str(path), "status", "--porcelain=v1", "--untracked-files=all")
        if not status:
            return WorkspaceManager.head(path)
        _git("-C", str(path), "add", "--all")
        commit_message = message or f"openmcp: {job_id} {stage_id}"
        _git("-C", str(path), "commit", "-m", commit_message)
        return WorkspaceManager.head(path)

    @staticmethod
    def archive_patch(path: Path, destination: Path, base_commit: str = "") -> bool:
        status = _git("-C", str(path), "status", "--porcelain=v1", "--untracked-files=all")
        head = WorkspaceManager.head(path)
        if not status and (not base_commit or head == base_commit):
            return False
        if status:
            _git("-C", str(path), "add", "--intent-to-add", ".")
        diff_args = ["-C", str(path), "diff", "--binary"]
        if base_commit:
            diff_args.append(base_commit)
        patch = _git(*diff_args)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(patch + "\n", encoding="utf-8")
        return True

    @staticmethod
    def reset(path: Path, commit: str) -> None:
        _git("-C", str(path), "reset", "--hard", commit)
        _git("-C", str(path), "clean", "-fd")

    @staticmethod
    def integrate(repository: Path, base_commit: str, result_commit: str) -> None:
        state = inspect_repository(repository)
        if not state.clean:
            raise WorkspaceError("Project worktree is not clean")
        if state.head != base_commit:
            raise WorkspaceError("Project HEAD changed after job submission")
        _git(
            "-C",
            str(repository),
            "merge-base",
            "--is-ancestor",
            base_commit,
            result_commit,
        )
        _git("-C", str(repository), "merge", "--ff-only", result_commit)

    def cleanup_job(self, repository: Path, path: Path, branch: str) -> None:
        self.remove(repository, path)
        try:
            _git("-C", str(repository), "branch", "-d", branch)
        except WorkspaceError:
            pass

    def discard_job(self, repository: Path, path: Path, branch: str) -> None:
        self.remove(repository, path)
        try:
            _git("-C", str(repository), "branch", "-D", branch)
        except WorkspaceError:
            pass


__all__ = [
    "RepositoryState",
    "WorkspaceError",
    "WorkspaceManager",
    "inspect_repository",
    "ignored_paths",
]
