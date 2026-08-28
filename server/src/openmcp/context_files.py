"""Managed project context files for harnesses without a system-prompt flag.

codex reads ``AGENTS.override.md`` in a shadowing slot: writing one at the
project root suppresses the repository's own root ``AGENTS.md``. To preserve
project guidance, the generated file composes the instruction followed by the
root ``AGENTS.md`` content verbatim. agy (Phase 5) reuses the same helpers with
a different target filename.

Safety rules (see PLAN phase 4 consultation constraints and remediation):

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
- The actual per-worktree Git ``index.lock`` is acquired with
  ``O_CREAT|O_EXCL`` before the final tracked check and any existing-file
  relocation or fresh write, making the tracked check plus materialization
  mutually exclusive with Git index mutations. Retries are bounded and a
  foreign lock is never removed; release only when the path identity matches
  the lock descriptor.
- Quarantine uses ``secrets.token_hex`` names inside a 0700 trash directory.
  Destinations are reserved with ``O_CREAT|O_EXCL`` and ``os.rename`` may
  overwrite only that reservation. Quarantined payloads are never deleted.
  Confirmed managed files are moved out of the project path into Git common
  storage (or an excluded same-filesystem worktree trash fallback). Foreign or
  tracked race-swapped content is restored with a no-overwrite link; if
  restoration loses a race, its bytes are preserved in quarantine and logged.
- Cleanup and sweep leave target paths absent for managed files without
  pathname deletion of payloads. No predictable quarantine names. No pruning
  in this phase.
"""

from __future__ import annotations

import os
import secrets
import stat
import subprocess
import threading
import time
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
_lock_retries = 50
_lock_delay_s = 0.02


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


def _git_path(root: Path, name: str) -> Path:
    """Resolve an absolute Git path such as ``index.lock`` through Git."""
    completed = _git(root, "rev-parse", "--git-path", name, check=True)
    value = completed.stdout.strip()
    if not value:
        raise ValueError(f"Git returned no path for {name!r} in {root}")
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    return path.resolve()


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


def _compose_content(instruction: str, root: Path, kind: str) -> bytes:
    """Compose the context file payload for ``target``.

    For codex, ``AGENTS.override.md`` shadows ``AGENTS.md`` within a
    directory, so the repository's own root guidance must be inlined verbatim:
    the payload is the instruction followed by the root ``AGENTS.md`` content.
    Composition uses bytes so a foreign-encoded ``AGENTS.md`` is preserved
    exactly.

    For agy, ``GEMINI.md`` and ``AGENTS.md`` load additively, so the payload
    is the instruction only and no composition is applied; a sibling
    ``AGENTS.md`` is never inlined or modified.
    """
    parts = [MANAGED_MARKER.encode(), b"\n", instruction.encode("utf-8"), b"\n"]
    if kind == "codex":
        agents = root / "AGENTS.md"
        if agents.is_file() and not agents.is_symlink():
            parts.append(agents.read_bytes())
    return b"".join(parts)


class _IndexLock:
    """The actual per-worktree Git ``index.lock`` held exclusively.

    Acquired with ``O_CREAT|O_EXCL`` so acquisition is atomic and never
    clobbers a lock Git or another worker holds. Retries are bounded. A
    foreign lock (one we did not create) is never removed. The lock is
    released only when the path identity matches the descriptor we hold, so a
    race-swapped lock path cannot be removed either.
    """

    def __init__(self, root: Path) -> None:
        self._path = _git_path(root, "index.lock")
        self._fd: int | None = None

    def acquire(self) -> None:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        for attempt in range(_lock_retries):
            try:
                fd = os.open(self._path, flags, 0o644)
                self._fd = fd
                return
            except FileExistsError:
                # A foreign lock exists; wait and retry, never removing it.
                if attempt + 1 >= _lock_retries:
                    raise ValueError(
                        f"Git index lock is held by another process: {self._path}"
                    )
                time.sleep(_lock_delay_s)
            except OSError as exc:
                raise ValueError(
                    f"Cannot acquire Git index lock {self._path}: {exc}"
                ) from exc

    def release(self) -> None:
        if self._fd is None:
            return
        try:
            identity = _fd_identity(self._fd)
            path_identity = _file_identity(self._path)
            if path_identity == identity:
                os.unlink(self._path)
        except OSError:
            log.warning(
                "Failed to release Git index lock",
                extra={"event": "context_file.index_lock_release_failed", "path": str(self._path)},
                exc_info=True,
            )
        finally:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

    def __enter__(self) -> "_IndexLock":
        self.acquire()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.release()


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
    *,
    kind: str = "codex",
) -> list[Path]:
    """Materialize the context file at ``target``.

    The supplied ``root`` is the project root and is preserved for composition
    (reading the project's own ``AGENTS.md`` for codex) and for the target
    path. The Git top-level is resolved only for index and exclusion
    operations, so a project rooted in a repository subdirectory still
    composes from its own ``AGENTS.md``.

    ``kind`` selects the backend file contract: ``"codex"`` composes the
    instruction followed by the root ``AGENTS.md`` verbatim into
    ``AGENTS.override.md``; ``"agy"`` writes ``GEMINI.md`` containing only
    the instruction, because agy loads ``GEMINI.md`` and ``AGENTS.md``
    additively and never needs composition.

    Refuses tracked, symlink, hardlink, directory, and foreign targets in both
    Git and non-Git projects before any replacement. The file is created fresh
    (``O_EXCL``) with the managed marker and the instruction, then hidden from
    Git through the shared exclude file. Returns the paths created.
    """
    project_root = root
    repo_root = git_repository_root(root)
    if kind not in {"codex", "agy"}:
        raise ValueError(f"Unknown context file kind: {kind}")
    if repo_root is None:
        log.warning(
            "Project root is not a git repository; materializing without exclusion",
            extra={"event": "context_file.non_git", "root": str(root)},
        )
        expected = _refuse_existing_target(target, project_root)
        if not instruction:
            return []
        content = _compose_content(instruction, project_root, kind)
        _write_target(
            target,
            content,
            present=expected is not None,
            expected=expected,
            repo_root=None,
        )
        return [target]

    relpath = _relative(repo_root, target)
    if not instruction:
        # Nothing to deliver; do not create a file.
        return []

    # Acquire the actual per-worktree Git index.lock before the final tracked
    # check and any existing-file relocation or fresh write. This makes the
    # tracked check plus materialization mutually exclusive with Git index
    # mutations: a concurrent `git add` cannot stage our path while we hold the
    # lock, and we cannot read a half-mutated index. A foreign lock is never
    # removed; retries are bounded.
    with _IndexLock(repo_root):
        if is_tracked(repo_root, target):
            raise ValueError(f"Target path is tracked by Git: {target}")
        # Refuse under the lock so the final tracked check precedes any
        # content-based refusal, matching task_guide error ordering.
        expected = _refuse_existing_target(target, project_root)
        _ensure_exclude(repo_root, relpath)
        _confirm_excluded(repo_root, relpath)
        content = _compose_content(instruction, project_root, kind)
        _write_target(
            target,
            content,
            present=expected is not None,
            expected=expected,
            repo_root=repo_root,
        )
    return [target]


class _Quarantine:
    """Race-safe payload holding inside a 0700 trash directory.

    Quarantine names are ``secrets.token_hex`` values (unpredictable), inside
    a trash directory created with mode 0700 in Git common storage, with an
    excluded same-filesystem worktree trash fallback. Destinations are
    reserved with ``O_CREAT|O_EXCL`` and ``os.rename`` may overwrite only that
    reservation. Quarantined payloads are never deleted in this phase.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._directory = self._trash_directory()

    def _trash_directory(self) -> Path:
        repo_root = git_repository_root(self._root)
        if repo_root is not None:
            try:
                common = _common_dir(repo_root)
                directory = common / "openmcp-trash"
                directory.mkdir(parents=True, exist_ok=True)
                os.chmod(directory, 0o700)
                return directory
            except Exception:
                log.warning(
                    "Falling back to worktree trash directory",
                    extra={"event": "context_file.trash_fallback", "root": str(self._root)},
                    exc_info=True,
                )
        directory = self._root / ".openmcp-trash"
        directory.mkdir(parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
        if repo_root is not None:
            # The fallback trash lives inside the worktree; keep it
            # Git-invisible through the managed exclude block.
            try:
                rel = _relative(repo_root, directory)
                _ensure_exclude(repo_root, rel)
            except Exception:
                log.warning(
                    "Could not exclude fallback trash directory",
                    extra={"event": "context_file.trash_exclude_failed", "root": str(self._root)},
                    exc_info=True,
                )
        return directory

    def reserve(self) -> Path:
        """Atomically reserve a unique quarantine destination."""
        directory = self._directory
        for _ in range(100):
            candidate = directory / f"{secrets.token_hex(16)}.q"
            try:
                fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
                return candidate
            except FileExistsError:
                continue
        raise ValueError(f"Cannot reserve quarantine destination in {directory}")

    def move_into(self, source: Path) -> Path:
        """Atomically move ``source`` into the reserved quarantine destination.

        The destination was reserved with ``O_CREAT|O_EXCL`` by ``reserve()``;
        ``os.rename`` overwrites only that empty reservation, never a foreign
        file. The payload is preserved in quarantine; it is never deleted.
        """
        destination = self.reserve()
        try:
            os.rename(source, destination)
        except OSError as exc:
            raise ValueError(f"Cannot quarantine {source}: {exc}") from exc
        return destination

    def restore(self, destination: Path, target: Path, *, symlink_target: str | None = None) -> bool:
        """Restore a quarantined payload to ``target`` without overwriting.

        Uses ``os.link`` (no-overwrite) for regular files: if the target path
        was concurrently claimed, the link fails with ``EEXIST`` and the
        payload stays in quarantine. For a symlink candidate, the symlink is
        recreated from its recorded target; if the path was concurrently
        claimed, the symlink is not created and the payload stays preserved.
        Returns ``True`` when restored, ``False`` when preserved.
        """
        if not (destination.exists() or destination.is_symlink()):
            return True
        if symlink_target is not None:
            try:
                os.symlink(symlink_target, target)
                return True
            except FileExistsError:
                log.warning(
                    "Quarantined symlink preserved; target was concurrently claimed",
                    extra={
                        "event": "context_file.quarantine_preserved",
                        "quarantine": str(destination),
                        "target": str(target),
                    },
                )
                return False
            except OSError as exc:
                raise ValueError(
                    f"Cannot restore quarantined symlink {destination}: {exc}"
                ) from exc
        try:
            os.link(destination, target)
            return True
        except FileExistsError:
            log.warning(
                "Quarantined payload preserved; target was concurrently claimed",
                extra={
                    "event": "context_file.quarantine_preserved",
                    "quarantine": str(destination),
                    "target": str(target),
                },
            )
            return False
        except OSError as exc:
            raise ValueError(
                f"Cannot restore quarantined file {destination}: {exc}"
            ) from exc


def _validate_quarantined(
    quarantine: Path,
    *,
    repo_root: Path | None,
    original: Path,
) -> bool:
    """Validate a quarantined candidate before considering it managed.

    Returns ``True`` when the quarantined file is a regular single-link file
    whose content carries the managed marker and whose original path is
    untracked, so it is safe to consider ours. Returns ``False`` for anything
    else; the caller restores it without overwriting another path or preserves
    the bytes and logs.
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
    if repo_root is not None and is_tracked(repo_root, original):
        # The original path became tracked; never treat it as ours.
        return False
    return True


def _quarantine_flow(root: Path, target: Path, *, allow_symlink: bool = False) -> list[Path]:
    """Shared race-safe cleanup/sweep: quarantine, validate, keep or restore.

    Returns the list of removed (now absent) target paths. The candidate is
    atomically moved to a unique 0700 trash destination, validated there
    (marker, regular single-link identity, original-path Git tracking). A
    confirmed managed file is left in quarantine (the target path is absent;
    no pathname deletion of the payload). Foreign or tracked content is
    restored with a no-overwrite link (or symlink recreation for symlink
    candidates); if restoration loses a race, the bytes are preserved in
    quarantine and logged.
    """
    quarantine = _Quarantine(root)
    repo_root = git_repository_root(root)
    symlink_target: str | None = None
    destination = quarantine.move_into(target)
    if destination.is_symlink():
        # A symlink candidate was moved (rename preserves the stored target).
        # It is never managed; record its target for no-overwrite restore.
        try:
            symlink_target = os.readlink(destination)
        except OSError:
            symlink_target = None
        if not allow_symlink or symlink_target is None:
            quarantine.restore(destination, target, symlink_target=symlink_target)
            return []
    if _validate_quarantined(destination, repo_root=repo_root, original=target):
        # Managed: target path is now absent; payload stays in quarantine.
        return [target]
    restored = quarantine.restore(destination, target, symlink_target=symlink_target)
    if not restored:
        # Preserved and logged; target path was concurrently claimed.
        return []
    return []


def cleanup_context_file(root: Path, target: Path) -> list[Path]:
    """Remove the managed file synchronously through a race-safe quarantine.

    The candidate is atomically moved to a unique 0700 trash destination,
    validated there, and a confirmed managed file is left in quarantine so the
    target path is absent without any pathname deletion of the payload.
    Foreign, symlink, hardlink, directory, and tracked content is restored
    untouched. Runs synchronously so a crash between materialize and cleanup
    is the only leftover path, which the startup sweep covers.
    """
    if not target.exists():
        return []
    return _quarantine_flow(root, target, allow_symlink=True)


def sweep_context_files(root: Path, target: Path) -> list[Path]:
    """Remove managed marker-bearing leftovers for a project.

    Skips Git entirely when no candidate file exists, so a clean project never
    pays a Git invocation. When a candidate exists, it is atomically moved to
    a unique 0700 trash destination, validated there, and a confirmed managed
    file is left in quarantine so the target path is absent. Tracked and
    foreign content is restored untouched. Symlinks are never swept.
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
