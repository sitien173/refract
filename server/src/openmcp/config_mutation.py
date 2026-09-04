"""Safe TOML configuration mutation transactions.

Phase 1 of dashboard target-profile CRUD provides one tested transaction
boundary for configuration-file writes. It owns candidate-loading and TOML
document mutation primitives, synchronized commit with atomic replacement,
runtime publication, and proven rollback. HTTP routes are intentionally not
exposed here; later phases add the dashboard editor endpoints on top of this
service.

Revisions are the SHA-256 digest of the exact source bytes. Mutation never
normalizes unrelated TOML regions; ``tomlkit`` renders untouched nodes from
their original trivia. Candidate configuration is validated through the
existing ``openmcp.config`` loading semantics, so no second schema exists.
"""

from __future__ import annotations

import ctypes
import errno
import hashlib
import os
import shutil
import sqlite3
import stat as stat_module
import sys
import tempfile
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomlkit
from tomlkit.items import Array, InlineTable, String, StringType, Table, Trivia

from openmcp.config import DaemonConfig, load_config, load_project_config
from openmcp.config_inspection import (
    ConfigSource,
    ConfigurationLoadError,
    read_config_source,
)
from openmcp.logging_setup import get_logger

log = get_logger("config_mutation")

_CONFLICT_MESSAGE = "Configuration source changed since the expected revision was read."
_UNCHANGED_MESSAGE = "No configuration file was changed."


class ConfigurationMutationError(ValueError):
    """A user-safe configuration mutation failure.

    The message never contains system prompts, backend arguments, provider
    secrets, or arbitrary configuration values.
    """

    code = "configuration_invalid"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        source_path: str = "",
        current_revision: str = "",
        unchanged: str = _UNCHANGED_MESSAGE,
        recovery: str = "",
    ) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
        self.source_path = source_path
        self.current_revision = current_revision
        self.unchanged = unchanged
        self.recovery = recovery


@dataclass(frozen=True, slots=True)
class SourceRead:
    """Current source identity: path, exact-byte revision, and presence."""

    path: Path
    revision: str
    absent: bool = False


@dataclass(frozen=True, slots=True)
class MutationResult:
    """Successful commit evidence for one source file.

    ``changed`` is false for publication refreshes of an unchanged source, and
    true for an atomic replacement. ``rolled_back`` is true when a failed
    publication restored the exact original source bytes.
    """

    config: DaemonConfig
    revision: str
    source_path: Path
    changed: bool
    rolled_back: bool = False


class _FileMode:
    """Captured mode application that fails before replacement if preservation fails."""

    def __init__(self, path: Path) -> None:
        self._source_path = path
        self._value: int | None = None
        try:
            self._value = stat_module.S_IMODE(path.stat().st_mode)
        except OSError:
            self._value = None

    def value(self) -> int | None:
        return self._value

    def apply(self, path: Path) -> None:
        if self._value is None:
            return
        try:
            os.chmod(path, self._value)
        except OSError as exc:
            log.error(
                "Failed to preserve configuration file mode",
                extra={"event": "config_mutation.mode_apply_failed", "path": str(path)},
                exc_info=True,
            )
            raise ConfigurationMutationError(
                "Failed to preserve configuration file mode.",
                code="configuration_commit_failed",
                source_path=self._source_path.as_posix(),
                unchanged=_UNCHANGED_MESSAGE,
                recovery="No change is active; the file on disk is unchanged.",
            ) from exc


def load_source(path: Path) -> ConfigSource:
    """Read exact source bytes; reject symlinks and non-regular files."""
    if path.is_symlink() or not path.exists():
        raise ConfigurationMutationError(
            "Configuration source must be an existing regular file.",
            code="not_found",
            source_path=path.as_posix(),
            unchanged=_UNCHANGED_MESSAGE,
        )
    if not path.is_file():
        raise ConfigurationMutationError(
            "Configuration source must be a regular file.",
            code="configuration_conflict",
            source_path=path.as_posix(),
            unchanged=_UNCHANGED_MESSAGE,
        )
    try:
        return read_config_source(path)
    except OSError as exc:
        raise ConfigurationMutationError(
            "Configuration source could not be read.",
            code="configuration_commit_failed",
            source_path=path.as_posix(),
            unchanged=_UNCHANGED_MESSAGE,
        ) from exc


def _regular_source(path: Path) -> ConfigSource:
    """Read exact source bytes; reject symlinks and non-regular files."""
    if path.is_symlink() or not path.is_file():
        raise ConfigurationMutationError(
            "Configuration source must be a regular file.",
            code="configuration_conflict",
            source_path=path.as_posix(),
            unchanged=_UNCHANGED_MESSAGE,
        )
    try:
        return read_config_source(path)
    except OSError as exc:
        raise ConfigurationMutationError(
            "Configuration source could not be read.",
            code="configuration_commit_failed",
            source_path=path.as_posix(),
            unchanged=_UNCHANGED_MESSAGE,
        ) from exc


def _fsync_directory(path: Path) -> None:
    """Synchronize a directory where the platform supports it, bounded."""
    if os.name == "nt":
        return
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        fd = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        log.warning(
            "Directory synchronization is unavailable",
            extra={
                "event": "config_mutation.directory_fsync_unavailable",
                "path": str(path),
            },
            exc_info=True,
        )
    finally:
        os.close(fd)


def _write_temporary(directory: Path, candidate: bytes, prefix: str) -> Path:
    """Write *candidate* into *directory*, fsync, and return the temp path."""
    try:
        handle = tempfile.NamedTemporaryFile(
            mode="wb",
            dir=directory,
            prefix=prefix,
            suffix=".tmp",
            delete=False,
        )
    except OSError as exc:
        raise ConfigurationMutationError(
            "Configuration source directory is not writable.",
            code="configuration_commit_failed",
            unchanged=_UNCHANGED_MESSAGE,
        ) from exc
    temporary = Path(handle.name)
    try:
        try:
            handle.write(candidate)
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            handle.close()
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise ConfigurationMutationError(
            "Configuration source write failed.",
            code="configuration_commit_failed",
            unchanged=_UNCHANGED_MESSAGE,
        ) from exc
    return temporary


_AT_FDCWD = -100
_RENAME_EXCHANGE = 2


def _load_renameat2() -> Any:
    if sys.platform != "linux":
        return None
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        if hasattr(libc, "renameat2"):
            func = libc.renameat2
            func.argtypes = [
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            ]
            func.restype = ctypes.c_int
            return func
    except Exception:
        pass
    return None


_renameat2 = _load_renameat2()


def _atomic_exchange(src: Path, dst: Path) -> None:
    """Atomically exchange two paths on Linux using renameat2(RENAME_EXCHANGE).

    Fails closed when the platform or filesystem does not support atomic exchange.
    """
    if _renameat2 is None:
        raise ConfigurationMutationError(
            "Atomic configuration exchange is not supported on this platform.",
            code="configuration_commit_failed",
            source_path=dst.as_posix(),
            unchanged=_UNCHANGED_MESSAGE,
        )
    src_bytes = os.fsencode(src)
    dst_bytes = os.fsencode(dst)
    ret = _renameat2(
        ctypes.c_int(_AT_FDCWD),
        src_bytes,
        ctypes.c_int(_AT_FDCWD),
        dst_bytes,
        ctypes.c_uint(_RENAME_EXCHANGE),
    )
    if ret != 0:
        err = ctypes.get_errno()
        if err in (errno.ENOSYS, errno.EINVAL, errno.ENOTSUP):
            raise ConfigurationMutationError(
                f"Atomic configuration exchange is not supported: {os.strerror(err)}",
                code="configuration_commit_failed",
                source_path=dst.as_posix(),
                unchanged=_UNCHANGED_MESSAGE,
            )
        raise OSError(err, os.strerror(err), dst.as_posix())


def _restore_exchanged_state(
    *,
    temporary: Path,
    path: Path,
    published_revision: str,
    max_retries: int | None = None,
) -> bool:
    """Restore *temporary* to *path* only when *path* still matches *published_revision*.

    Returns True if the exchanged-out state was safely restored to *path*.
    Returns False if a newer edit was detected at *path*, leaving the newer edit in place.
    Fails closed and leaves *temporary* intact if compensation cannot safely
    restore the newer edit to *path*.
    """
    try:
        current = read_config_source(path)
    except OSError:
        return False
    if current.revision != published_revision:
        return False

    try:
        original_temp_rev = read_config_source(temporary).revision
    except OSError:
        return False

    _atomic_exchange(temporary, path)
    _fsync_directory(path.parent)

    try:
        swapped_back = read_config_source(temporary)
    except OSError as exc:
        raise ConfigurationMutationError(
            "Failed to verify exchanged state after publication restore. "
            "Configuration state is retained in temporary file.",
            code="configuration_commit_failed",
            source_path=path.as_posix(),
            recovery="Inspect the configuration file and retained temporary file.",
        ) from exc

    if swapped_back.revision == published_revision:
        return True

    # An atomic replacement occurred after validation, trapping the newer edit in temporary.
    # Compensate by restoring the newer edit to path, handling any further replacements during compensation.
    expected_trapped = original_temp_rev
    retries = 0
    while True:
        if max_retries is not None and retries >= max_retries:
            raise ConfigurationMutationError(
                "Compensation retry limit exhausted while restoring external configuration. "
                "Configuration state is retained in temporary file.",
                code="configuration_commit_failed",
                source_path=path.as_posix(),
                recovery="Inspect the configuration file and retained temporary file.",
            )
        retries += 1
        try:
            to_put_rev = read_config_source(temporary).revision
        except Exception as exc:
            raise ConfigurationMutationError(
                "Failed to read trapped configuration state during compensation. "
                "Configuration state is retained in temporary file.",
                code="configuration_commit_failed",
                source_path=path.as_posix(),
                recovery="Inspect the configuration file and retained temporary file.",
            ) from exc

        try:
            _atomic_exchange(temporary, path)
            _fsync_directory(path.parent)
        except Exception as exc:
            raise ConfigurationMutationError(
                "Failed to atomically exchange configuration during compensation. "
                "Configuration state is retained in temporary file.",
                code="configuration_commit_failed",
                source_path=path.as_posix(),
                recovery="Inspect the configuration file and retained temporary file.",
            ) from exc

        try:
            trapped = read_config_source(temporary)
        except Exception as exc:
            raise ConfigurationMutationError(
                "Failed to verify trapped configuration state during compensation. "
                "Configuration state is retained in temporary file.",
                code="configuration_commit_failed",
                source_path=path.as_posix(),
                recovery="Inspect the configuration file and retained temporary file.",
            ) from exc

        if trapped.revision == expected_trapped:
            break
        expected_trapped = to_put_rev

    return False


def commit_bytes(
    path: Path,
    candidate: bytes,
    *,
    expected_revision: str | None,
    mode: _FileMode | None = None,
) -> ConfigSource:
    """Atomically exchange *path* with candidate bytes when matching *expected_revision*.

    Writes land in the source directory so the atomic exchange operates on the
    same filesystem. The file mode is preserved when a mode was captured.
    Returns the source metadata for the exact new bytes. Raises
    ``ConfigurationMutationError`` with ``configuration_conflict`` when the
    on-disk revision no longer matches ``expected_revision``, or
    ``configuration_commit_failed`` when exchange fails or the platform is
    unsupported.
    """
    if expected_revision is not None:
        current = _regular_source(path)
        if current.revision != expected_revision:
            raise ConfigurationMutationError(
                _CONFLICT_MESSAGE,
                code="configuration_conflict",
                source_path=path.as_posix(),
                current_revision=current.revision,
                unchanged=_UNCHANGED_MESSAGE,
                recovery="Reload the current configuration and retry the edit.",
            )
    elif path.is_symlink() or not path.exists():
        raise ConfigurationMutationError(
            "Configuration source must be an existing regular file.",
            code="not_found",
            source_path=path.as_posix(),
            unchanged=_UNCHANGED_MESSAGE,
        )
    elif not path.is_file():
        raise ConfigurationMutationError(
            "Configuration source must be a regular file.",
            code="configuration_conflict",
            source_path=path.as_posix(),
            unchanged=_UNCHANGED_MESSAGE,
        )
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    temporary = _write_temporary(directory, candidate, f".{path.name}.")
    candidate_revision = hashlib.sha256(candidate).hexdigest()
    retain_temporary = False
    try:
        if mode is not None:
            mode.apply(temporary)
        if expected_revision is not None:
            current = _regular_source(path)
            if current.revision != expected_revision:
                raise ConfigurationMutationError(
                    _CONFLICT_MESSAGE,
                    code="configuration_conflict",
                    source_path=path.as_posix(),
                    current_revision=current.revision,
                    unchanged=_UNCHANGED_MESSAGE,
                    recovery="Reload the current configuration and retry the edit.",
                )
        elif path.is_symlink() or not path.is_file():
            raise ConfigurationMutationError(
                "Configuration source must be a regular file.",
                code="configuration_conflict",
                source_path=path.as_posix(),
                unchanged=_UNCHANGED_MESSAGE,
            )
        _atomic_exchange(temporary, path)
        _fsync_directory(directory)
        exchanged = read_config_source(temporary)
        if expected_revision is not None and exchanged.revision != expected_revision:
            try:
                restored = _restore_exchanged_state(
                    temporary=temporary,
                    path=path,
                    published_revision=candidate_revision,
                )
            except ConfigurationMutationError:
                retain_temporary = True
                raise
            if restored:
                raise ConfigurationMutationError(
                    _CONFLICT_MESSAGE,
                    code="configuration_conflict",
                    source_path=path.as_posix(),
                    current_revision=exchanged.revision,
                    unchanged=_UNCHANGED_MESSAGE,
                    recovery="Reload the current configuration and retry the edit.",
                )
            raise ConfigurationMutationError(
                "Configuration changed during publication and state is uncertain.",
                code="configuration_conflict",
                source_path=path.as_posix(),
                unchanged=_UNCHANGED_MESSAGE,
                recovery="Inspect the configuration file and reload the daemon.",
            )
    except Exception as exc:
        if not retain_temporary:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        if isinstance(exc, ConfigurationMutationError):
            raise
        raise ConfigurationMutationError(
            "Configuration source replacement failed.",
            code="configuration_commit_failed",
            source_path=path.as_posix(),
            unchanged=_UNCHANGED_MESSAGE,
            recovery="No change is active; the file on disk is unchanged.",
        ) from exc
    finally:
        if not retain_temporary:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
    return read_config_source(path)


def create_bytes(
    path: Path,
    candidate: bytes,
    *,
    mode: _FileMode | None = None,
) -> ConfigSource:
    """Atomically create *path* without overwriting a concurrent creation.

    The candidate is written to a temporary sibling and published with a
    no-replace link so a file created between the caller's absence check and
    this publication is never clobbered. Returns the source metadata for the
    exact new bytes.
    """
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    temporary = _write_temporary(directory, candidate, f".{path.name}.")
    try:
        if mode is not None:
            mode.apply(temporary)
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            current = _regular_source(path)
            raise ConfigurationMutationError(
                _CONFLICT_MESSAGE,
                code="configuration_conflict",
                source_path=path.as_posix(),
                current_revision=current.revision,
                unchanged=_UNCHANGED_MESSAGE,
                recovery="Reload the current configuration and retry the edit.",
            ) from exc
        _fsync_directory(directory)
    except Exception as exc:
        if isinstance(exc, ConfigurationMutationError):
            raise
        raise ConfigurationMutationError(
            "Configuration source creation failed.",
            code="configuration_commit_failed",
            source_path=path.as_posix(),
            unchanged=_UNCHANGED_MESSAGE,
        ) from exc
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return read_config_source(path)


def restore_bytes(
    path: Path,
    original: ConfigSource,
    mode: _FileMode | None = None,
    *,
    expected_revision: str | None = None,
) -> None:
    """Atomically restore the exact original bytes of *path*.

    When *expected_revision* is provided, the current source must match it both
    before temporary creation and immediately before replacement. Restoration
    reuses the same atomic temporary write path as a normal commit.
    """
    if expected_revision is not None:
        current = _regular_source(path)
        if current.revision != expected_revision:
            log.error(
                "Configuration rollback skipped: the source changed after commit",
                extra={"event": "config_mutation.rollback_skipped", "path": str(path)},
            )
            raise ConfigurationMutationError(
                "Configuration publication failed and the file changed again "
                "before rollback. Configuration state is uncertain.",
                code="configuration_commit_failed",
                source_path=path.as_posix(),
                recovery="Inspect the configuration file and reload the daemon.",
            )
    elif path.is_symlink() or not path.is_file():
        raise ConfigurationMutationError(
            "Configuration source must be a regular file.",
            code="configuration_conflict",
            source_path=path.as_posix(),
            unchanged=_UNCHANGED_MESSAGE,
        )
    directory = path.parent
    temporary = _write_temporary(directory, original.data, f".{path.name}.")
    retain_temporary = False
    try:
        if mode is not None:
            mode.apply(temporary)
        if expected_revision is not None:
            current = _regular_source(path)
            if current.revision != expected_revision:
                log.error(
                    "Configuration rollback skipped: the source changed after commit",
                    extra={"event": "config_mutation.rollback_skipped", "path": str(path)},
                )
                raise ConfigurationMutationError(
                    "Configuration publication failed and the file changed again "
                    "before rollback. Configuration state is uncertain.",
                    code="configuration_commit_failed",
                    source_path=path.as_posix(),
                    recovery="Inspect the configuration file and reload the daemon.",
                )
        elif path.is_symlink() or not path.is_file():
            raise ConfigurationMutationError(
                "Configuration source must be a regular file.",
                code="configuration_conflict",
                source_path=path.as_posix(),
                unchanged=_UNCHANGED_MESSAGE,
            )
        _atomic_exchange(temporary, path)
        _fsync_directory(directory)
        exchanged = read_config_source(temporary)
        if expected_revision is not None and exchanged.revision != expected_revision:
            try:
                _restore_exchanged_state(
                    temporary=temporary,
                    path=path,
                    published_revision=original.revision,
                )
            except ConfigurationMutationError:
                retain_temporary = True
                raise
            log.error(
                "Configuration rollback skipped: the source changed after commit",
                extra={"event": "config_mutation.rollback_skipped", "path": str(path)},
            )
            raise ConfigurationMutationError(
                "Configuration publication failed and the file changed again "
                "before rollback. Configuration state is uncertain.",
                code="configuration_commit_failed",
                source_path=path.as_posix(),
                recovery="Inspect the configuration file and reload the daemon.",
            )
    except Exception as exc:
        if not retain_temporary:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        if isinstance(exc, ConfigurationMutationError):
            raise
        raise ConfigurationMutationError(
            "Configuration source replacement failed.",
            code="configuration_commit_failed",
            source_path=path.as_posix(),
            unchanged=_UNCHANGED_MESSAGE,
            recovery="No change is active; the file on disk is unchanged.",
        ) from exc
    finally:
        if not retain_temporary:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# String/array helpers that preserve the flavor and trivia of edited nodes.
# ---------------------------------------------------------------------------


def _replace_string(container: Any, key: str, value: str) -> None:
    existing = container.get(key)
    if isinstance(existing, String):
        flavor = existing._t
        if flavor is StringType.SLL and ("'" in value or "\n" in value):
            flavor = StringType.SLB
        elif flavor is StringType.MLL and "'''" in value:
            flavor = StringType.MLB
        body = String.from_raw(value, flavor)
        container[key] = String(
            flavor,
            str(body),
            body._original,
            Trivia(
                indent=existing.trivia.indent,
                comment_ws=existing.trivia.comment_ws,
                comment=existing.trivia.comment,
                trail=existing.trivia.trail,
            ),
        )
        return
    container[key] = String.from_raw(value, StringType.SLB)


def _string_item(value: str) -> String:
    return String.from_raw(value, StringType.SLB)


def _string_array(values: list[str]) -> Array:
    array = tomlkit.array()
    for value in values:
        array.append(_string_item(value))
    return array


def _replace_array_values(array: Array, values: list[str]) -> None:
    if len(array):
        del array[:]
    for value in values:
        array.append(_string_item(value))


def _target_list(value: object) -> list[str]:
    """Return target identifiers from any accepted declaration shape."""
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, Array)):
        return [str(item) for item in value]
    if isinstance(value, dict):
        raw = value.get("targets", [])
        if isinstance(raw, str):
            return [raw]
        if isinstance(raw, (list, Array)):
            return [str(item) for item in raw]
    return []


class ConfigurationMutationService:
    """Synchronized, atomic configuration-file mutation with publication.

    One service instance serializes global mutations, project mutations,
    configuration reloads, and runtime publication behind a single lock. The
    lock spans validation, replacement, and publication so callers never
    observe disk-new with runtime-old state.
    """

    def __init__(self, runtime: object) -> None:
        self._runtime = runtime
        self._lock = threading.RLock()

    @property
    def lock(self) -> threading.RLock:
        """The synchronization boundary shared with planning and reload paths."""
        return self._lock

    def _resolve_source(self, project_root: Path | None) -> Path:
        runtime = self._runtime
        if project_root is None:
            config_path = getattr(runtime.config, "config_path", None)
            if config_path is None:
                raise ConfigurationMutationError(
                    "No global configuration source is configured.",
                    code="configuration_invalid",
                    unchanged=_UNCHANGED_MESSAGE,
                )
            return Path(config_path)
        return Path(project_root) / ".openmcp" / "config.toml"

    def source_read(self, project_root: Path | None = None) -> SourceRead:
        """Return the current identity of one configuration source."""
        path = self._resolve_source(project_root)
        if not path.exists():
            return SourceRead(path=path, revision="", absent=True)
        source = _regular_source(path)
        return SourceRead(path=path, revision=source.revision, absent=False)

    # ------------------------------------------------------------------
    # Candidate loading and TOML document mutation primitives.
    # ------------------------------------------------------------------

    def parse_document(self, data: bytes) -> tomlkit.TOMLDocument:
        try:
            return tomlkit.parse(data.decode("utf-8"))
        except (UnicodeDecodeError, tomlkit.TOMLKitError) as exc:
            raise ConfigurationMutationError(
                "Invalid TOML syntax",
                code="configuration_invalid",
                unchanged=_UNCHANGED_MESSAGE,
            ) from exc

    def read_document(self, source: ConfigSource) -> tomlkit.TOMLDocument:
        return self.parse_document(source.data)

    def candidate_bytes(self, document: tomlkit.TOMLDocument) -> bytes:
        return tomlkit.dumps(document).encode("utf-8")

    def resolve_global_catalog(self, candidate: bytes) -> DaemonConfig:
        """Load a candidate global document through existing semantics."""
        source_path = self._resolve_source(None)
        temporary = self._validation_copy(source_path, candidate)
        try:
            return load_config(temporary)
        except ConfigurationLoadError as exc:
            raise ConfigurationMutationError(
                str(exc),
                code="configuration_invalid",
                source_path=source_path.as_posix(),
                unchanged=_UNCHANGED_MESSAGE,
                recovery="Correct the configuration file and retry.",
            ) from exc
        finally:
            temporary.unlink(missing_ok=True)

    def resolve_project_catalog(
        self, project_root: Path, candidate: bytes
    ) -> DaemonConfig:
        """Load a candidate project document against the runtime catalog."""
        temporary_root = Path(tempfile.mkdtemp(prefix="openmcp-config-validate-"))
        try:
            config_dir = temporary_root / ".openmcp"
            config_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "config.toml").write_bytes(candidate)
            try:
                return load_project_config(temporary_root, self._runtime.catalog)
            except ConfigurationLoadError as exc:
                raise ConfigurationMutationError(
                    str(exc),
                    code="configuration_invalid",
                    source_path=(
                        Path(project_root) / ".openmcp" / "config.toml"
                    ).as_posix(),
                    unchanged=_UNCHANGED_MESSAGE,
                    recovery="Correct the project configuration file and retry.",
                ) from exc
        finally:
            try:
                shutil.rmtree(temporary_root)
            except Exception:
                log.exception(
                    "Project validation temporary cleanup failed",
                    extra={
                        "event": "config_mutation.validation_cleanup_failed",
                        "path": str(temporary_root),
                    },
                )
                raise

    @staticmethod
    def _validation_copy(source_path: Path, candidate: bytes) -> Path:
        directory = source_path.parent
        directory.mkdir(parents=True, exist_ok=True)
        try:
            handle = tempfile.NamedTemporaryFile(
                mode="wb",
                dir=directory,
                prefix=f".{source_path.name}.",
                suffix=".validate.tmp",
                delete=False,
            )
        except OSError as exc:
            raise ConfigurationMutationError(
                "Configuration source directory is not writable.",
                code="configuration_commit_failed",
                unchanged=_UNCHANGED_MESSAGE,
            ) from exc
        temporary = Path(handle.name)
        try:
            handle.write(candidate)
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            handle.close()
        return temporary

    # --- target primitives --------------------------------------------------

    def find_target(
        self, document: tomlkit.TOMLDocument, target_id: str
    ) -> Table | None:
        targets = document.get("targets")
        if targets is None:
            return None
        for target in targets:
            raw = target.get("id")
            if raw is not None and str(raw) == target_id:
                return target
        return None

    def set_target_value(
        self,
        target: Table,
        key: str,
        value: object,
    ) -> None:
        if isinstance(value, str):
            _replace_string(target, key, value)
        elif isinstance(value, list):
            target[key] = _string_array(value)
        else:
            target[key] = value

    def remove_target_key(self, target: Table, key: str) -> None:
        if key in target:
            del target[key]

    def target_table(self) -> Table:
        return tomlkit.table()

    def set_target_argument(self, target: Table, index: int, value: str) -> None:
        args = target.get("args")
        if args is None:
            args = tomlkit.array()
            target["args"] = args
        args[index] = _string_item(value)

    # --- profile primitives --------------------------------------------------

    def _profiles_table(self, document: tomlkit.TOMLDocument) -> Any | None:
        return document.get("profiles")

    def find_profile(
        self, document: tomlkit.TOMLDocument, profile_id: str
    ) -> Table | None:
        profiles = self._profiles_table(document)
        if profiles is None:
            return None
        raw = profiles.get(profile_id)
        if raw is None:
            return None
        if not isinstance(raw, Table):
            raise ConfigurationMutationError(
                "Profile declaration must be a table.",
                code="configuration_invalid",
                unchanged=_UNCHANGED_MESSAGE,
            )
        return raw

    def profile_table(
        self, document: tomlkit.TOMLDocument, profile_id: str
    ) -> Table:
        profiles = self._profiles_table(document)
        if profiles is None:
            profiles = tomlkit.table()
            document["profiles"] = profiles
        existing = profiles.get(profile_id)
        if existing is not None and isinstance(existing, Table):
            return existing
        table = tomlkit.table()
        profiles[profile_id] = table
        return table

    def set_profile_value(self, profile: Table, key: str, value: object) -> None:
        if isinstance(value, str):
            _replace_string(profile, key, value)
        else:
            profile[key] = value

    def remove_profile_key(self, profile: Table, key: str) -> None:
        if key in profile:
            del profile[key]

    def workflow_kind(self, profile: Table, workflow: str) -> str:
        existing = profile.get(workflow)
        if isinstance(existing, String):
            return "string"
        if isinstance(existing, Array):
            return "array"
        if isinstance(existing, InlineTable):
            return "inline"
        if isinstance(existing, Table):
            return "table"
        return "none"

    def workflow_targets(self, profile: Table, workflow: str) -> list[str]:
        existing = profile.get(workflow)
        if existing is None:
            return []
        return _target_list(existing)

    def set_workflow_shorthand(
        self,
        profile: Table,
        workflow: str,
        targets: list[str],
    ) -> None:
        """Write a single target as a shorthand string, otherwise an array."""
        if len(targets) == 1:
            _replace_string(profile, workflow, targets[0])
        else:
            existing = profile.get(workflow)
            if isinstance(existing, Array):
                _replace_array_values(existing, targets)
            else:
                profile[workflow] = _string_array(targets)

    def set_workflow_policy(
        self,
        profile: Table,
        workflow: str,
        *,
        targets: list[str],
        max_attempts: int,
        timeout_s: int,
    ) -> None:
        """Write a complete workflow policy.

        Existing inline or sub-table policies are mutated in place so their
        single-line or multiline layout survives. String or array shorthand is
        replaced by an inline policy only when a policy is required.
        """
        existing = profile.get(workflow)
        if isinstance(existing, InlineTable):
            existing["targets"] = _string_array(targets)
            existing["max_attempts"] = max_attempts
            existing["timeout_s"] = timeout_s
            return
        if isinstance(existing, Table):
            existing["targets"] = _string_array(targets)
            existing["max_attempts"] = max_attempts
            existing["timeout_s"] = timeout_s
            return
        policy = tomlkit.inline_table()
        policy["targets"] = _string_array(targets)
        policy["max_attempts"] = max_attempts
        policy["timeout_s"] = timeout_s
        profile[workflow] = policy

    # ------------------------------------------------------------------
    # Transactions.
    # ------------------------------------------------------------------

    def commit_document(
        self,
        document: tomlkit.TOMLDocument,
        *,
        project_root: Path | None = None,
        expected_revision: str | None = None,
        validate_registered_projects: bool = False,
    ) -> MutationResult:
        """Atomically commit one validated document and publish the result.

        The lock spans candidate validation, replacement, and runtime
        publication. ``project_root=None`` targets the global configuration
        source; otherwise ``<project_root>/.openmcp/config.toml`` is edited.
        """
        with self._lock:
            source_path = self._resolve_source(project_root)
            if expected_revision is None:
                raise ConfigurationMutationError(
                    "An expected source revision is required before any file "
                    "change.",
                    code="revision_required",
                    source_path=source_path.as_posix(),
                    unchanged=_UNCHANGED_MESSAGE,
                    recovery="Reload the current configuration and retry the edit.",
                )
            mode = _FileMode(source_path)
            original = _regular_source(source_path)
            if original.revision != expected_revision:
                raise ConfigurationMutationError(
                    _CONFLICT_MESSAGE,
                    code="configuration_conflict",
                    source_path=source_path.as_posix(),
                    current_revision=original.revision,
                    unchanged=_UNCHANGED_MESSAGE,
                    recovery="Reload the current configuration and retry the edit.",
                )
            candidate = self.candidate_bytes(document)
            if project_root is None:
                validated = self.resolve_global_catalog(candidate)
                self._validate_registered_projects(validated)
            else:
                validated = self.resolve_project_catalog(project_root, candidate)

            committed = commit_bytes(
                source_path, candidate, expected_revision=expected_revision, mode=mode
            )
            runtime = self._runtime
            try:
                if project_root is None:
                    runtime._publish_configuration_locked()
                else:
                    runtime._publish_project_configuration_locked(Path(project_root))
            except Exception as exc:
                self._rollback_failed_publication(
                    path=source_path,
                    original=original,
                    mode=mode,
                    candidate_revision=committed.revision,
                    project_root=project_root,
                )
                raise ConfigurationMutationError(
                    "The configuration was replaced but runtime publication "
                    "failed. The original file and runtime were restored.",
                    code="configuration_commit_failed",
                    source_path=source_path.as_posix(),
                    current_revision=original.revision,
                    unchanged="The configuration file and runtime were restored to "
                    "their original state.",
                    recovery="Retry the edit once the daemon is healthy.",
                ) from exc
            if project_root is None:
                final = runtime.catalog
            else:
                final = load_project_config(Path(project_root), runtime.catalog)
            return MutationResult(
                config=final,
                revision=committed.revision,
                source_path=source_path,
                changed=True,
            )

    def create_project_document(
        self,
        document: tomlkit.TOMLDocument,
        *,
        project_root: Path,
    ) -> MutationResult:
        """Create a minimal project configuration file atomically.

        The file must currently be absent; a concurrent creation is reported as
        a conflict without any write. The candidate is validated before
        publication, so no partial or invalid project file can appear.
        """
        with self._lock:
            path = Path(project_root) / ".openmcp" / "config.toml"
            candidate = self.candidate_bytes(document)
            # Validate before any file exists; invalid candidates never create.
            self.resolve_project_catalog(project_root, candidate)
            mode = _FileMode(path)
            committed = create_bytes(path, candidate, mode=mode)
            runtime = self._runtime
            try:
                runtime._publish_project_configuration_locked(Path(project_root))
            except Exception as exc:
                self._rollback_failed_creation(
                    path=path,
                    mode=mode,
                    candidate_revision=committed.revision,
                    project_root=project_root,
                )
                raise ConfigurationMutationError(
                    "The project configuration was created but runtime "
                    "publication failed. The created file was removed.",
                    code="configuration_commit_failed",
                    source_path=path.as_posix(),
                    unchanged="The created project configuration was removed.",
                    recovery="Retry the edit once the daemon is healthy.",
                ) from exc
            final = load_project_config(Path(project_root), runtime.catalog)
            return MutationResult(
                config=final,
                revision=committed.revision,
                source_path=path,
                changed=True,
            )

    def _validate_registered_projects(self, candidate: DaemonConfig) -> None:
        runtime = self._runtime
        database = getattr(runtime, "database", None)
        if database is None:
            return
        try:
            projects = database.projects()
        except sqlite3.ProgrammingError:
            db_path = getattr(getattr(runtime, "config", None), "database_path", None)
            if db_path is None or not Path(db_path).exists():
                return
            conn = sqlite3.connect(db_path)
            try:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("SELECT * FROM projects ORDER BY alias").fetchall()
                projects = [database._project_view(row) for row in rows]
            finally:
                conn.close()
        for project in projects:
            try:
                load_project_config(Path(project.root), candidate)
            except ConfigurationLoadError as exc:
                raise ConfigurationMutationError(
                    "The global change would invalidate a registered project "
                    "configuration.",
                    code="configuration_invalid",
                    unchanged=_UNCHANGED_MESSAGE,
                    recovery="Adjust the global change or the project "
                    "configuration and retry.",
                ) from exc

    def _rollback_failed_publication(
        self,
        *,
        path: Path,
        original: ConfigSource,
        mode: _FileMode,
        candidate_revision: str,
        project_root: Path | None,
    ) -> None:
        """Prove the failed candidate is still current, then restore originals."""
        current = self._confirm_current(path, candidate_revision)
        if current is None:
            return
        try:
            restore_bytes(
                path,
                original,
                mode=mode,
                expected_revision=candidate_revision,
            )
        except Exception:
            log.exception(
                "Configuration rollback file restore failed",
                extra={"event": "config_mutation.rollback_restore_failed", "path": str(path)},
            )
            raise
        self._republish_original(path, project_root)

    def _rollback_failed_creation(
        self,
        *,
        path: Path,
        mode: _FileMode,
        candidate_revision: str,
        project_root: Path,
    ) -> None:
        current = self._confirm_current(path, candidate_revision)
        if current is None:
            return
        directory = path.parent
        tombstone = _write_temporary(directory, b"", f".{path.name}.del.")
        delete_target: Path | None = None
        retain_tombstone = False
        retain_delete_target = False
        try:
            _atomic_exchange(tombstone, path)
            _fsync_directory(directory)
            exchanged = read_config_source(tombstone)
            empty_revision = hashlib.sha256(b"").hexdigest()
            if exchanged.revision != candidate_revision:
                try:
                    _restore_exchanged_state(
                        temporary=tombstone,
                        path=path,
                        published_revision=empty_revision,
                    )
                except ConfigurationMutationError:
                    retain_tombstone = True
                    raise
                log.error(
                    "Configuration rollback skipped: the source changed after commit",
                    extra={"event": "config_mutation.rollback_skipped", "path": str(path)},
                )
                raise ConfigurationMutationError(
                    "Configuration publication failed and the file changed again "
                    "before rollback. Configuration state is uncertain.",
                    code="configuration_commit_failed",
                    source_path=path.as_posix(),
                    recovery="Inspect the configuration file and reload the daemon.",
                )
            delete_target = directory / f".{path.name}.del.{uuid.uuid4().hex}.tmp"
            try:
                os.replace(path, delete_target)
                _fsync_directory(directory)
                removed = read_config_source(delete_target)
                if removed.revision != empty_revision:
                    if not path.exists():
                        os.replace(delete_target, path)
                        _fsync_directory(directory)
                    else:
                        try:
                            _restore_exchanged_state(
                                temporary=delete_target,
                                path=path,
                                published_revision=empty_revision,
                            )
                        except ConfigurationMutationError:
                            retain_delete_target = True
                            raise
                    log.error(
                        "Configuration rollback skipped: the source changed after commit",
                        extra={"event": "config_mutation.rollback_skipped", "path": str(path)},
                    )
                    raise ConfigurationMutationError(
                        "Configuration publication failed and the file changed again "
                        "before rollback. Configuration state is uncertain.",
                        code="configuration_commit_failed",
                        source_path=path.as_posix(),
                        recovery="Inspect the configuration file and reload the daemon.",
                    )
                delete_target.unlink(missing_ok=True)
                _fsync_directory(directory)
            except OSError as exc:
                if not path.exists():
                    pass
                else:
                    raise
        except Exception:
            log.exception(
                "Configuration rollback removal failed",
                extra={"event": "config_mutation.rollback_removal_failed", "path": str(path)},
            )
            raise
        finally:
            if delete_target is not None and not retain_delete_target:
                try:
                    delete_target.unlink(missing_ok=True)
                except OSError:
                    pass
            if not retain_tombstone:
                try:
                    tombstone.unlink(missing_ok=True)
                except OSError:
                    pass
        self._republish_original(path, project_root)

    @staticmethod
    def _confirm_current(path: Path, candidate_revision: str) -> ConfigSource | None:
        """Return the current source only when it still equals the candidate."""
        try:
            current = read_config_source(path)
        except OSError:
            log.error(
                "Configuration rollback cannot confirm the source state",
                extra={"event": "config_mutation.rollback_unconfirmed", "path": str(path)},
            )
            raise ConfigurationMutationError(
                "Configuration publication failed and the file state cannot be "
                "confirmed. Configuration state is uncertain.",
                code="configuration_commit_failed",
                source_path=path.as_posix(),
                recovery="Inspect the configuration file and reload the daemon.",
            )
        if current.revision != candidate_revision:
            log.error(
                "Configuration rollback skipped: the source changed after commit",
                extra={"event": "config_mutation.rollback_skipped", "path": str(path)},
            )
            raise ConfigurationMutationError(
                "Configuration publication failed and the file changed again "
                "before rollback. Configuration state is uncertain.",
                code="configuration_commit_failed",
                source_path=path.as_posix(),
                recovery="Inspect the configuration file and reload the daemon.",
            )
        return current

    def _republish_original(self, path: Path, project_root: Path | None) -> None:
        """Reload the restored file; failures are logged, never fatal here."""
        runtime = self._runtime
        try:
            if project_root is None:
                runtime._publish_configuration_locked()
            else:
                runtime._publish_project_configuration_locked(Path(project_root))
        except Exception:
            log.exception(
                "Configuration rollback republish failed",
                extra={"event": "config_mutation.rollback_republish_failed", "path": str(path)},
            )


__all__ = [
    "ConfigurationMutationError",
    "load_source",
    "ConfigurationMutationService",
    "MutationResult",
    "SourceRead",
    "commit_bytes",
    "create_bytes",
    "restore_bytes",
]
