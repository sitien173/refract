"""Managed project context files for harnesses without a system-prompt flag.

codex reads ``AGENTS.override.md`` in a shadowing slot: writing one at the
project root suppresses the repository's own root ``AGENTS.md``. To preserve
project guidance, the generated file composes the instruction followed by the
root ``AGENTS.md`` content verbatim. agy (Phase 5) reuses the same helpers with
a different target filename.

Safety rules (see PLAN phase 4 consultation constraints):

- Never alter a file Git tracks; detect index membership through Git itself,
  even when the working-tree copy has been deleted.
- Refuse symlinks, hardlink hazards, directories, and untracked foreign files.
  Create exclusively with ``O_EXCL`` after validation.
- Hide generated files through ``$GIT_COMMON_DIR/info/exclude`` resolved by
  Git, so every linked worktree honors the exclusion. Anchor patterns to the
  repository root so ``git check-ignore`` confirms them from any worktree.
- Scrub repository-affecting ``GIT_*`` environment variables from internal Git
  calls so a worker's environment cannot redirect them.
- Only a confirmed non-repository is treated as non-Git; any other Git failure
  fails closed (raises).
- Cleanup deletes only regular files whose content carries the managed marker.
- Cleanup and sweep atomically quarantine the candidate to a unique
  same-directory path, validate marker, regular single-link identity, and
  original-path Git tracking there, then delete only the quarantined managed
  inode; non-managed or tracked content is restored without overwriting
  another path, or preserved and reported when restoration is impossible.
- Replacement binds to the exact prevalidated inode and rechecks Git tracking
  after opening that inode, before mutation; any identity change fails closed.
- Sweep deletes only marker-bearing untracked files, and skips Git entirely
  when no candidate file exists.
"""

from __future__ import annotations

import itertools
import os
import stat
import subprocess
import threading
from pathlib import Path

from openmcp.logging_setup import get_logger


log = get_logger("context_files")

#: Header marker for generated files. Cleanup and sweep delete only files whose
#: content starts with this marker, so foreign files are never touched.
MANAGED_MARKER = "<!-- openmcp-context-instruction v1 -->"

#: Environment variables that change which repository Git operates on. They are
#: scrubbed from internal Git calls so a worker cannot redirect them.
_GIT_REDIRECT_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CEILING_DIRECTORIES",
    "GIT_DISCOVERY_ACROSS_FILESYSTEM",
    "GIT_NAMESPACE",
)

_exclude_lock = threading.Lock()


def _scrubbed_env() -> dict[str, str]:
    """Return the current environment with repository-redirecting vars removed."""
    env = os.environ.copy()
    for name in _GIT_REDIRECT_VARS:
        env.pop(name, None)
    return env


def _git(
    root: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run Git in ``root`` with a scrubbed environment, failing closed."""
    try:
        return subprocess.run(
            ["git", "-C", os.fspath(root), *args],
            check=check,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=_scrubbed_env(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(f"Git failed for {root}: {exc}") from exc


def git_repository_root(path: Path) -> Path | None:
    """Resolve the Git common directory's worktree root, or ``None`` if the
    path is confirmed not to be inside a repository.

    Returns ``None`` only when Git reports "not a git repository". Any other
    failure raises so callers fail closed rather than guess.
    """
    completed = _git(path, "rev-parse", "--show-toplevel", check=False)
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        if "not a git repository" in stderr:
            return None
        raise ValueError(f"Git could not resolve repository for {path}: {stderr}")
    root = completed.stdout.strip()
    if not root:
        raise ValueError(f"Git returned no repository root for {path}")
    return Path(root)


def _common_dir(root: Path) -> Path:
    completed = _git(root, "rev-parse", "--git-common-dir", check=True)
    value = completed.stdout.strip()
    if not value:
        raise ValueError(f"Git returned no common dir for {root}")
    common = Path(value)
    if not common.is_absolute():
        common = root / common
    return common.resolve()


def _relative(root: Path, path: Path) -> str:
    """Return ``path`` relative to the repository root as a slash path."""
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"Path {path} is outside repository root {root}") from exc
    return relative.as_posix()


def is_tracked(root: Path, path: Path) -> bool:
    """Return whether ``path`` is in the Git index, even if deleted on disk."""
    rel = _relative(root, path)
    completed = _git(root, "ls-files", "--stage", "--", rel, check=False)
    if completed.returncode != 0:
        raise ValueError(f"Git could not inspect index for {path}: {completed.stderr}")
    return bool(completed.stdout.strip())


def managed_exclude_block(relpath: str) -> str:
    """Return the delimited exclude block for one managed relative path."""
    return (
        f"# BEGIN openmcp-context-instruction: {relpath}\n"
        f"/{relpath}\n"
        "# END openmcp-context-instruction\n"
    )


def _ensure_exclude(root: Path, relpath: str) -> Path:
    """Append the managed block to ``$GIT_COMMON_DIR/info/exclude`` once.

    The block is anchored to the repository root (``/<relpath>``) so
    ``git check-ignore`` confirms it from any linked worktree. Unrelated
    exclude content is preserved verbatim. A lock serializes concurrent
    updates from parallel jobs in one repository.
    """
    common = _common_dir(root)
    exclude = common / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    block = managed_exclude_block(relpath)
    begin_marker = f"# BEGIN openmcp-context-instruction: {relpath}"
    with _exclude_lock:
        if exclude.exists():
            existing = exclude.read_text(encoding="utf-8")
            if begin_marker in existing:
                return exclude
        else:
            existing = ""
        with exclude.open("a", encoding="utf-8") as handle:
            if existing and not existing.endswith("\n"):
                handle.write("\n")
            handle.write(block)
    return exclude


def _confirm_excluded(root: Path, relpath: str) -> None:
    """Verify Git actually ignores the generated path from this worktree."""
    completed = _git(root, "check-ignore", "--", relpath, check=False)
    if completed.returncode != 0:
        raise ValueError(f"Generated path {relpath} is not Git-ignored in {root}")


def _compose_codex_content(instruction: str, root: Path) -> bytes:
    """Compose the codex file: instruction followed by root ``AGENTS.md``.

    ``AGENTS.override.md`` shadows ``AGENTS.md`` within a directory, so the
    repository's own root guidance must be inlined verbatim. Composition uses
    bytes so a foreign-encoded ``AGENTS.md`` is preserved exactly.
    """
    parts = [MANAGED_MARKER.encode(), b"\n", instruction.encode("utf-8"), b"\n"]
    agents = root / "AGENTS.md"
    if agents.is_file() and not agents.is_symlink():
        parts.append(agents.read_bytes())
    return b"".join(parts)


def _file_identity(path: Path) -> tuple[int, int] | None:
    """Return ``(st_dev, st_ino)`` for ``path`` or ``None`` if absent."""
    try:
        info = path.stat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ValueError(f"Cannot stat {path}: {exc}") from exc
    return (info.st_dev, info.st_ino)


def _fd_identity(fd: int) -> tuple[int, int]:
    """Return ``(st_dev, st_ino)`` for an open descriptor."""
    info = os.fstat(fd)
    return (info.st_dev, info.st_ino)


def _refuse_existing_target(target: Path, root: Path) -> tuple[int, int] | None:
    """Validate that an existing target path is a managed leftover.

    Refuses symlinks (a symlink could point at a tracked or foreign file),
    directories, and hardlinked regular files (the inode may be a tracked or
    foreign file), plus any untracked file that is not ours.

    Returns the validated inode identity ``(st_dev, st_ino)`` of the managed
    leftover, or ``None`` when the target is absent. The caller must bind the
    later replacement to this exact inode so a race-swapped path cannot be
    mutated.
    """
    if target.is_symlink():
        raise ValueError(f"Target path is a symlink: {target}")
    if target.is_dir():
        raise ValueError(f"Target path is a directory: {target}")
    if not target.exists():
        return None
    stat = target.stat()
    if stat.st_nlink > 1:
        raise ValueError(f"Target path is a hardlink: {target}")
    try:
        content = target.read_bytes()
    except OSError as exc:
        raise ValueError(f"Target path is not readable: {target}") from exc
    if not content.startswith(MANAGED_MARKER.encode()):
        raise ValueError(f"Target path is a foreign file: {target}")
    return (stat.st_dev, stat.st_ino)


def _open_managed_for_replacement(target: Path, expected: tuple[int, int]) -> int:
    """Open an existing managed leftover for in-place replacement.

    Opens with ``O_NOFOLLOW`` so a symlink swapped in after validation cannot
    redirect the write, and validates marker, single-link metadata, and inode
    identity through the same descriptor before returning it. The descriptor
    must resolve to exactly the prevalidated inode ``expected``; any identity
    change fails closed. Raises ``ValueError`` for any foreign, symlink,
    directory, hardlinked, or identity-changed target. The returned descriptor
    is the authoritative handle for truncation and writing; the pathname is
    never used again for mutation, so a concurrent rename to a foreign or
    tracked file cannot be deleted or overwritten.
    """
    flags = os.O_RDWR
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(target, flags)
    except OSError as exc:
        if isinstance(exc, FileNotFoundError):
            raise ValueError(f"Target path disappeared: {target}") from exc
        raise ValueError(f"Target path cannot be opened: {target}") from exc
    try:
        stat = os.fstat(fd)
        if os.path.islink(target):
            raise ValueError(f"Target path is a symlink: {target}")
        if stat.st_nlink > 1:
            raise ValueError(f"Target path is a hardlink: {target}")
        if _fd_identity(fd) != expected:
            raise ValueError(f"Target path changed identity: {target}")
        try:
            content = os.read(fd, len(MANAGED_MARKER.encode()) + 1)
        except OSError as exc:
            raise ValueError(f"Target path is not readable: {target}") from exc
        if not content.startswith(MANAGED_MARKER.encode()):
            raise ValueError(f"Target path is a foreign file: {target}")
        os.lseek(fd, 0, os.SEEK_SET)
        return fd
    except Exception:
        os.close(fd)
        raise


def _is_path_tracked(repo_root: Path, target: Path) -> bool:
    """Return whether the original path is in the Git index (or its inode is).

    Used after opening a candidate inode: recheck that the pathname is still
    untracked so a race that staged a tracked marker file at this path fails
    closed before any mutation.
    """
    if repo_root is None:
        return False
    return is_tracked(repo_root, target)


def _recheck_tracked_after_open(repo_root: Path, target: Path) -> None:
    """Fail closed if the opened inode's path became Git-tracked.

    Runs before any mutation of the descriptor. A race that swaps the path to
    a tracked marker file after the earlier index check is detected here, and
    the identity check in ``_open_managed_for_replacement`` guarantees the
    descriptor is the prevalidated inode, so a tracked file is never modified.
    """
    if _is_path_tracked(repo_root, target):
        raise ValueError(f"Target path became tracked by Git: {target}")


def _replace_managed_file(
    target: Path,
    content: bytes,
    expected: tuple[int, int],
    repo_root: Path | None,
) -> None:
    """Atomically replace an existing managed leftover through its descriptor.

    The existing regular single-link file is opened with ``O_NOFOLLOW``,
    validated through that same descriptor (marker, inode link count, exact
    prevalidated inode identity, Git tracking recheck), then truncated and
    rewritten. The pathname is never unlinked based on earlier validation, so a
    replacement race that swaps the path to a foreign or tracked file cannot
    delete or modify it.
    """
    fd = _open_managed_for_replacement(target, expected)
    try:
        _recheck_tracked_after_open(repo_root, target)
        os.ftruncate(fd, 0)
        os.write(fd, content)
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_target(
    target: Path,
    content: bytes,
    *,
    present: bool,
    expected: tuple[int, int] | None,
    repo_root: Path | None,
) -> None:
    """Write ``content`` to ``target`` inode-safely.

    If ``present``, the existing managed leftover (whose identity was captured
    by ``_refuse_existing_target`` as ``expected``) is replaced through its
    descriptor (``O_NOFOLLOW``, marker validated through the same fd, exact
    inode identity, Git-tracking recheck); if absent, the file is created
    exclusively with ``O_EXCL``. A race cannot turn a refusal into a
    destructive unlink or an overwrite of a foreign or tracked file.
    """
    if present:
        assert expected is not None
        _replace_managed_file(target, content, expected, repo_root)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise ValueError(f"Target path already exists: {target}") from exc


def materialize_context_file(
    root: Path,
    target: Path,
    instruction: str,
) -> list[Path]:
    """Materialize the composed context file at ``target``.

    The supplied ``root`` is the project root and is preserved for composition
    (reading the project's own ``AGENTS.md``) and for the target path. The Git
    top-level is resolved only for index and exclusion operations, so a
    project rooted in a repository subdirectory still composes from its own
    ``AGENTS.md``.

    Refuses tracked, symlink, hardlink, directory, and foreign targets in both
    Git and non-Git projects before any replacement. The file is created fresh
    (``O_EXCL``) with the managed marker, the instruction, and (for codex) the
    project's ``AGENTS.md`` inlined verbatim, then hidden from Git through the
    shared exclude file. Returns the paths created.
    """
    project_root = root
    repo_root = git_repository_root(root)
    if repo_root is None:
        log.warning(
            "Project root is not a git repository; materializing without exclusion",
            extra={"event": "context_file.non_git", "root": str(root)},
        )
    else:
        relpath = _relative(repo_root, target)
        if is_tracked(repo_root, target):
            raise ValueError(f"Target path is tracked by Git: {target}")

    # Refuse symlinks, directories, hardlinks, and foreign files identically
    # in Git and non-Git projects before any replacement of the target. This
    # pathname-level refusal is a fast pre-check that also captures the exact
    # inode identity of a managed leftover; the authoritative inode-safe
    # validation happens through the descriptor in _write_target, bound to that
    # identity and with a Git-tracking recheck, so a race cannot swap in a
    # foreign or tracked file between here and the write.
    expected = _refuse_existing_target(target, project_root)

    if repo_root is not None:
        _ensure_exclude(repo_root, relpath)
        _confirm_excluded(repo_root, relpath)

    if not instruction and not (project_root / "AGENTS.md").exists():
        # Nothing to deliver; do not create a file.
        return []

    content = _compose_codex_content(instruction, project_root)
    # Existence is re-checked inside the write: if the path now holds a foreign
    # or tracked file, the descriptor open with O_NOFOLLOW, the exact-inode
    # identity check, and the Git-tracking recheck refuse it, and the pathname
    # is never unlinked. If the path is absent, the exclusive create races to
    # claim it.
    _write_target(
        target,
        content,
        present=expected is not None,
        expected=expected,
        repo_root=repo_root,
    )
    return [target]


def _quarantine_candidate(target: Path) -> Path | None:
    """Atomically move ``target`` to a unique same-directory quarantine path.

    Returns the quarantine path, or ``None`` when the target does not exist.
    The move is a same-directory ``os.rename`` (atomic on POSIX), so a
    concurrent writer cannot interleave between the existence check and the
    move, and the original path is vacated in one step. The quarantine name is
    unique per call so two cleanup/sweep operations cannot collide.
    """
    if not target.exists():
        return None
    directory = target.parent
    name = target.name
    for index in itertools.count():
        candidate = directory / f".{name}.openmcp-quarantine-{os.getpid()}-{index}"
        try:
            os.rename(target, candidate)
            return candidate
        except FileNotFoundError:
            return None
        except OSError:
            if index >= 100:
                raise ValueError(
                    f"Cannot quarantine {target}: quarantine names are exhausted"
                )
            # The quarantine name already exists; try the next unique name.
            continue


def _validate_quarantined(
    root: Path,
    target: Path,
    quarantine: Path,
) -> bool:
    """Validate a quarantined candidate before deleting it.

    Returns ``True`` when the quarantined file is a regular single-link file
    whose content carries the managed marker and whose original path is
    untracked, so it is safe to delete. Returns ``False`` for anything else;
    the caller restores it without overwriting another path or preserves the
    bytes and reports failure.
    """
    if quarantine.is_symlink() or not quarantine.is_file():
        return False
    try:
        info = quarantine.stat()
    except OSError:
        return False
    if not stat.S_ISREG(info.st_mode) or info.st_nlink > 1:
        return False
    try:
        content = quarantine.read_bytes()
    except OSError:
        return False
    if not content.startswith(MANAGED_MARKER.encode()):
        return False
    repo_root = git_repository_root(root)
    if repo_root is not None and is_tracked(repo_root, target):
        # The original path became tracked; never delete its inode.
        return False
    return True


def _restore_quarantined(target: Path, quarantine: Path) -> None:
    """Restore ``quarantine`` to ``target`` without overwriting another path.

    If ``target`` is still absent, rename the quarantined file back. If
    ``target`` now holds another file (a concurrent writer claimed the path),
    the quarantined bytes are preserved at the quarantine path and a failure
    is reported, never deleting or overwriting data.
    """
    if not quarantine.exists():
        return
    if target.exists():
        raise ValueError(
            f"Cannot restore quarantined file {quarantine}: target {target} "
            "was replaced concurrently; preserved quarantined bytes"
        )
    try:
        os.rename(quarantine, target)
    except OSError as exc:
        raise ValueError(
            f"Cannot restore quarantined file {quarantine} to {target}: {exc}; "
            "preserved quarantined bytes"
        ) from exc


def _delete_quarantined(quarantine: Path) -> None:
    """Delete the quarantined managed inode synchronously."""
    try:
        quarantine.unlink()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise ValueError(f"Failed to remove quarantined file {quarantine}: {exc}") from exc


def _quarantine_flow(root: Path, target: Path) -> list[Path]:
    """Shared race-safe cleanup/sweep: quarantine, validate, delete or restore.

    Returns the list of removed paths. The candidate is atomically moved to a
    unique same-directory quarantine path, validated there (marker, regular
    single-link identity, original-path Git tracking), and only the quarantined
    managed inode is deleted. Non-managed or tracked content is restored to the
    original path without overwriting another path; when restoration is
    impossible the quarantined bytes are preserved and a failure is reported
    rather than deleting data.
    """
    quarantine = _quarantine_candidate(target)
    if quarantine is None:
        return []
    if _validate_quarantined(root, target, quarantine):
        _delete_quarantined(quarantine)
        return [target]
    _restore_quarantined(target, quarantine)
    return []


def cleanup_context_file(root: Path, target: Path) -> list[Path]:
    """Remove the managed file synchronously through a race-safe quarantine.

    Deletes only a regular single-link marker-bearing untracked file. The
    candidate is atomically quarantined first, validated at the quarantine
    path, and only the quarantined managed inode is deleted; foreign, symlink,
    hardlink, directory, and tracked targets are restored untouched. Runs
    synchronously so a crash between materialize and cleanup is the only
    leftover path, which the startup sweep covers.
    """
    return _quarantine_flow(root, target)


def sweep_context_files(root: Path, target: Path) -> list[Path]:
    """Remove managed marker-bearing leftovers for a project.

    Skips Git entirely when no candidate file exists, so a clean project never
    pays a Git invocation. When a candidate exists, it is atomically
    quarantined, validated at the quarantine path (marker, regular single-link
    identity, original-path Git tracking), and only the quarantined managed
    inode is deleted. Tracked and foreign content is restored untouched.
    """
    if not target.exists() or target.is_symlink():
        return []
    return _quarantine_flow(root, target)


__all__ = [
    "MANAGED_MARKER",
    "cleanup_context_file",
    "git_repository_root",
    "is_tracked",
    "managed_exclude_block",
    "materialize_context_file",
    "sweep_context_files",
]
