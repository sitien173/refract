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
existing ``refract.config`` loading semantics, so no second schema exists.
"""

from __future__ import annotations

import os
import stat as stat_module
import tempfile
import threading
import tomllib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import tomlkit
from tomlkit.items import Array, InlineTable, String, StringType, Table, Trivia

from refract.config import DaemonConfig, TargetConfig, load_config_bytes, load_project_config
from refract.config_inspection import (
    ConfigSource,
    ConfigurationLoadError,
    read_config_source,
)
from refract.logging_setup import get_logger
from refract.models import (
    ProfileEditorData,
    ProfileEditorResponse,
    ProfileReference,
    TargetEditorData,
    TargetReference,
    WorkflowPolicyData,
)
from refract.workflows import BUILTIN_WORKFLOWS

if os.name == "nt":
    import msvcrt
else:
    import fcntl

log = get_logger("config_mutation")
_T = TypeVar("_T")

_CONFLICT_MESSAGE = "Configuration source changed since the expected revision was read."
_UNCHANGED_MESSAGE = "No configuration file was changed."
_RETRY_EDIT_MESSAGE = "Reload the current configuration and retry the edit."


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
        references: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
        self.source_path = source_path
        self.current_revision = current_revision
        self.unchanged = unchanged
        self.recovery = recovery
        self.references = references


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


def _require_revision(
    path: Path, expected_revision: str | None, action: str = "edit"
) -> None:
    if expected_revision is None:
        raise ConfigurationMutationError(
            "An expected source revision is required before any file change.",
            code="revision_required",
            source_path=path.as_posix(),
            unchanged=_UNCHANGED_MESSAGE,
            recovery=f"Reload the current configuration and retry the {action}.",
        )


def _expected_source(path: Path, expected_revision: str | None) -> ConfigSource:
    source = _regular_source(path)
    if source.revision != expected_revision:
        raise ConfigurationMutationError(
            _CONFLICT_MESSAGE,
            code="configuration_conflict",
            source_path=path.as_posix(),
            current_revision=source.revision,
            unchanged=_UNCHANGED_MESSAGE,
            recovery=_RETRY_EDIT_MESSAGE,
        )
    return source


def _regular_source(path: Path) -> ConfigSource:
    """Read exact source bytes; reject symlinks and non-regular files."""
    if not path.exists() and not path.is_symlink():
        raise ConfigurationMutationError(
            "Configuration source does not exist.",
            code="not_found",
            source_path=path.as_posix(),
            unchanged=_UNCHANGED_MESSAGE,
        )
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


@contextmanager
def _file_lock(path: Path) -> Iterator[None]:
    """Hold an exclusive lock on a sibling lock file across check and replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path.parent / f".{path.name}.lock", "a+b") as handle:
        if os.name == "nt":
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def commit_bytes(
    path: Path,
    candidate: bytes,
    *,
    expected_revision: str | None,
    mode: _FileMode | None = None,
) -> ConfigSource:
    """Replace *path* with candidate bytes when it still matches *expected_revision*.

    The temporary file lands in the source directory so ``os.replace`` stays
    on one filesystem. A sibling lock file serializes the revision check and
    the replacement across processes. The file mode is preserved when a mode
    was captured. Raises ``ConfigurationMutationError`` with
    ``configuration_conflict`` when the on-disk revision no longer matches
    ``expected_revision``, or ``configuration_commit_failed`` when the
    replacement fails.
    """
    if expected_revision is None and (path.is_symlink() or not path.exists()):
        raise ConfigurationMutationError(
            "Configuration source must be an existing regular file.",
            code="not_found",
            source_path=path.as_posix(),
            unchanged=_UNCHANGED_MESSAGE,
        )
    with _file_lock(path):
        temporary = _write_temporary(path.parent, candidate, f".{path.name}.")
        try:
            if mode is not None:
                mode.apply(temporary)
            current = _regular_source(path)
            if expected_revision is not None and current.revision != expected_revision:
                raise ConfigurationMutationError(
                    _CONFLICT_MESSAGE,
                    code="configuration_conflict",
                    source_path=path.as_posix(),
                    current_revision=current.revision,
                    unchanged=_UNCHANGED_MESSAGE,
                    recovery=_RETRY_EDIT_MESSAGE,
                )
            os.replace(temporary, path)
            _fsync_directory(path.parent)
        except ConfigurationMutationError:
            raise
        except OSError as exc:
            raise ConfigurationMutationError(
                "Configuration source replacement failed.",
                code="configuration_commit_failed",
                source_path=path.as_posix(),
                unchanged=_UNCHANGED_MESSAGE,
                recovery="No change is active; the file on disk is unchanged.",
            ) from exc
        finally:
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
    with _file_lock(path):
        directory = path.parent
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
                    recovery=_RETRY_EDIT_MESSAGE,
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


def target_to_editor_data(target: Any) -> TargetEditorData:
    """Convert a TargetConfig or TOML target table into a strict editor data model."""
    if isinstance(target, TargetConfig):
        return TargetEditorData(
            id=target.id,
            backend=target.backend,
            model=target.model,
            backend_profile=target.backend_profile,
            reasoning=target.reasoning,
            system_prompt=target.system_prompt,
            isolated=target.isolated,
            read_only=target.read_only,
            args=list(target.args),
            max_concurrency=target.max_concurrency,
        )
    raw_args = target.get("args", [])
    args = [str(x) for x in raw_args] if isinstance(raw_args, (list, Array)) else []
    backend_profile = ""
    if "backend_profile" in target:
        backend_profile = str(target["backend_profile"])
    elif "profile" in target:
        backend_profile = str(target["profile"])
    return TargetEditorData(
        id=str(target.get("id", "")),
        backend=str(target.get("backend", "")),
        model=str(target.get("model", "")),
        backend_profile=backend_profile,
        reasoning=str(target.get("reasoning", "")),
        system_prompt=str(target.get("system_prompt", "")),
        isolated=bool(target.get("isolated", False)),
        read_only=bool(target.get("read_only", False)),
        args=args,
        max_concurrency=int(target.get("max_concurrency", 1)),
    )


def _build_profile_editor_response(
    catalog: DaemonConfig,
    profile_id: str,
    *,
    project_declaration: Any | None = None,
    scope: str = "global",
) -> ProfileEditorResponse:
    global_declarations = catalog.profile_declarations
    if scope == "project":
        declaration = (
            project_declaration
            if project_declaration is not None
            else catalog.project_profile_declarations.get(profile_id)
        )
    else:
        declaration = global_declarations.get(profile_id)
    extends = declaration.extends if declaration is not None else None
    declared_workflows = declaration.workflows if declaration is not None else {}
    effective_workflows = catalog.profiles.get(profile_id, {})

    declared: dict[str, WorkflowPolicyData | None] = {}
    effective: dict[str, WorkflowPolicyData | None] = {}
    inherited: dict[str, WorkflowPolicyData | None] = {}
    sources: dict[str, str] = {}

    for w in BUILTIN_WORKFLOWS:
        if w in declared_workflows:
            sel = declared_workflows[w]
            declared[w] = WorkflowPolicyData(
                targets=list(sel.targets),
                timeout_s=sel.timeout_s,
            )
        else:
            declared[w] = None

        if w in effective_workflows:
            eff_sel = effective_workflows[w]
            effective[w] = WorkflowPolicyData(
                targets=list(eff_sel.targets),
                timeout_s=eff_sel.timeout_s,
            )
        else:
            effective[w] = None

        if w in effective_workflows and w not in declared_workflows:
            eff_sel = effective_workflows[w]
            inherited[w] = WorkflowPolicyData(
                targets=list(eff_sel.targets),
                timeout_s=eff_sel.timeout_s,
            )
        else:
            inherited[w] = None

        if w in declared_workflows:
            sources[w] = "project" if scope == "project" else "declared"
        elif w in effective_workflows:
            if scope == "project":
                sources[w] = "global"
            else:
                curr = extends
                src = "inherited"
                seen = {profile_id}
                while curr and curr not in seen:
                    seen.add(curr)
                    parent_decl = global_declarations.get(curr)
                    if parent_decl and w in parent_decl.workflows:
                        src = curr
                        break
                    curr = parent_decl.extends if parent_decl else None
                sources[w] = src

    return ProfileEditorResponse(
        id=profile_id,
        extends=extends,
        workflows=dict(declared),
        declared=declared,
        inherited=inherited,
        effective=effective,
        sources=sources,
    )


def _apply_workflow_policy(
    service: ConfigurationMutationService,
    profile_table: Table,
    workflow: str,
    policy: WorkflowPolicyData,
) -> None:
    targets = list(policy.targets)
    requires_expansion = policy.timeout_s > 0
    kind = service.workflow_kind(profile_table, workflow)
    if requires_expansion:
        service.set_workflow_policy(
            profile_table,
            workflow,
            targets=targets,
            timeout_s=policy.timeout_s,
        )
    elif kind in ("inline", "table"):
        service.set_workflow_policy(
            profile_table,
            workflow,
            targets=targets,
            timeout_s=policy.timeout_s,
        )
    else:
        service.set_workflow_shorthand(profile_table, workflow, targets)



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
        return Path(project_root) / ".refract" / "config.toml"

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
        try:
            return load_config_bytes(candidate, source_path)
        except ConfigurationLoadError as exc:
            raise ConfigurationMutationError(
                str(exc),
                code="configuration_invalid",
                source_path=source_path.as_posix(),
                unchanged=_UNCHANGED_MESSAGE,
                recovery="Correct the configuration file and retry.",
            ) from exc

    def resolve_project_catalog(
        self, project_root: Path, candidate: bytes
    ) -> DaemonConfig:
        """Load a candidate project document against the runtime catalog."""
        try:
            return load_project_config(
                Path(project_root), self._runtime.catalog, candidate
            )
        except ConfigurationLoadError as exc:
            raise ConfigurationMutationError(
                str(exc),
                code="configuration_invalid",
                source_path=(
                    Path(project_root) / ".refract" / "config.toml"
                ).as_posix(),
                unchanged=_UNCHANGED_MESSAGE,
                recovery="Correct the project configuration file and retry.",
            ) from exc

    def _mutate(
        self, project_root: Path | None, expected_revision: str | None,
        edit: Callable[[tomlkit.TOMLDocument], _T], *, create: bool = False,
    ) -> tuple[MutationResult, _T]:
        with self._lock:
            path = self._resolve_source(project_root)
            _require_revision(path, expected_revision)
            if create and project_root is not None and not path.exists():
                if expected_revision != "":
                    raise ConfigurationMutationError(
                        _CONFLICT_MESSAGE, code="configuration_conflict",
                        source_path=path.as_posix(), current_revision="",
                        recovery=_RETRY_EDIT_MESSAGE,
                    )
                original = None
                document = tomlkit.document()
            else:
                original = _expected_source(path, expected_revision)
                document = self.read_document(original)
            value = edit(document)
            result = self._commit_document(
                document, project_root=project_root,
                expected_revision=expected_revision, original=original,
            )
            return result, value

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

    def target_table(self) -> Table:
        return tomlkit.table()

    def read_targets(self) -> tuple[SourceRead, list[TargetEditorData]]:
        """Return all global targets for the protected editor."""
        with self._lock:
            source_path = self._resolve_source(None)
            if not source_path.exists():
                return SourceRead(path=source_path, revision="", absent=True), []
            source = _regular_source(source_path)
            source_read = SourceRead(path=source_path, revision=source.revision, absent=False)
            document = self.read_document(source)
            targets_raw = document.get("targets", [])
            targets: list[TargetEditorData] = []
            if isinstance(targets_raw, (list, Array)):
                for item in targets_raw:
                    if isinstance(item, (dict, Table)):
                        targets.append(target_to_editor_data(item))
            return source_read, targets

    def get_target(self, target_id: str) -> tuple[SourceRead, TargetEditorData]:
        """Return one global target by identifier."""
        with self._lock:
            source_path = self._resolve_source(None)
            if not source_path.exists():
                raise ConfigurationMutationError(
                    f"Unknown target: {target_id}",
                    code="not_found",
                    source_path=source_path.as_posix(),
                    unchanged=_UNCHANGED_MESSAGE,
                    recovery="Create the target before inspecting it.",
                )
            source = _regular_source(source_path)
            source_read = SourceRead(path=source_path, revision=source.revision, absent=False)
            document = self.read_document(source)
            target = self.find_target(document, target_id)
            if target is None:
                raise ConfigurationMutationError(
                    f"Unknown target: {target_id}",
                    code="not_found",
                    source_path=source_path.as_posix(),
                    unchanged=_UNCHANGED_MESSAGE,
                    recovery="Create the target before inspecting it.",
                )
            return source_read, target_to_editor_data(target)

    def _reference_documents(self, document=None):
        """Read declared sources once for both reference queries."""
        if document is None:
            path = self._resolve_source(None)
            if path.exists():
                try:
                    document = self.read_document(_regular_source(path))
                except Exception:
                    log.warning("Global reference scan failed", exc_info=True,
                                extra={"event": "config_mutation.reference_scan_failed"})
        if document is not None:
            yield "global", None, document
        database = getattr(self._runtime, "database", None)
        if database is None:
            return
        for project in sorted(database.projects(), key=lambda project: project.id):
            path = self._resolve_source(Path(project.root))
            try:
                if path.is_file():
                    yield "project", project.id, tomllib.loads(path.read_text(encoding="utf-8"))
                else:
                    catalog = self._runtime.catalog_for_project_cached(project.id)
                    yield "project", project.id, {
                        "profiles": {
                            pid: {
                                "extends": declaration.extends,
                                **{wf: {"targets": list(selection.targets)}
                                   for wf, selection in declaration.workflows.items()},
                            }
                            for pid, declaration in catalog.project_profile_declarations.items()
                        }
                    }
            except Exception:
                log.warning("Project reference scan failed", exc_info=True,
                            extra={"event": "config_mutation.reference_scan_failed", "project_id": project.id})

    def find_target_references(
        self, target_id: str, document: tomlkit.TOMLDocument | None = None,
    ) -> list[TargetReference]:
        return [
            TargetReference(scope=scope, project_id=project_id,
                            profile_id=str(pid), workflow=str(workflow))
            for scope, project_id, source in self._reference_documents(document)
            for pid, declaration in sorted(source.get("profiles", {}).items())
            if isinstance(declaration, (dict, Table))
            for workflow, policy in sorted(declaration.items())
            if workflow != "extends" and target_id in _target_list(policy)
        ]

    def _new_target_table(self, target_id: str, data: TargetEditorData) -> Table:
        """Build a target declaration, omitting optional default values."""
        table = self.target_table()
        table["id"] = target_id
        table["backend"] = data.backend
        if data.model:
            table["model"] = data.model
        if data.backend_profile:
            table["backend_profile"] = data.backend_profile
        if data.reasoning:
            table["reasoning"] = data.reasoning
        if data.system_prompt:
            table["system_prompt"] = data.system_prompt
        if data.isolated:
            table["isolated"] = True
        if data.read_only:
            table["read_only"] = True
        if data.args:
            table["args"] = _string_array(list(data.args))
        if data.max_concurrency != 1:
            table["max_concurrency"] = data.max_concurrency
        return table

    def create_target(
        self,
        data: TargetEditorData,
        *,
        expected_revision: str,
    ) -> tuple[MutationResult, TargetEditorData]:
        def edit(document):
            source_path = self._resolve_source(None)
            if not data.id or not data.id.strip():
                raise ConfigurationMutationError(
                    "Target identifier cannot be empty.",
                    code="configuration_invalid",
                    source_path=source_path.as_posix(),
                    unchanged=_UNCHANGED_MESSAGE,
                    recovery="Specify a non-empty target identifier.",
                )
            target_id = data.id.strip()
            if self.find_target(document, target_id) is not None:
                raise ConfigurationMutationError(
                    f"Target {target_id!r} already exists.",
                    code="configuration_invalid",
                    source_path=source_path.as_posix(),
                    unchanged=_UNCHANGED_MESSAGE,
                    recovery="Choose a unique target identifier.",
                )
            targets = document.get("targets")
            if targets is None:
                targets = tomlkit.aot()
                document["targets"] = targets
            table = self._new_target_table(target_id, data)
            if isinstance(targets, Array):
                inline = tomlkit.inline_table()
                inline.update(table)
                targets.append(inline)
            else:
                targets.append(table)
            return target_to_editor_data(self.find_target(document, target_id) or table)

        return self._mutate(None, expected_revision, edit)

    def _update_target_model_settings(self, target: Table, data: TargetEditorData) -> None:
        """Update model selection and prompts, preserving the legacy profile key."""
        if data.model or "model" in target:
            self.set_target_value(target, "model", data.model)
        if "profile" in target:
            self.set_target_value(target, "profile", data.backend_profile)
        elif "backend_profile" in target or data.backend_profile:
            self.set_target_value(target, "backend_profile", data.backend_profile)
        if data.reasoning or "reasoning" in target:
            self.set_target_value(target, "reasoning", data.reasoning)
        if data.system_prompt or "system_prompt" in target:
            self.set_target_value(target, "system_prompt", data.system_prompt)

    def _update_target_execution_settings(self, target: Table, data: TargetEditorData) -> None:
        """Update execution options without introducing absent default keys."""
        if data.isolated or "isolated" in target:
            self.set_target_value(target, "isolated", data.isolated)
        if data.read_only or "read_only" in target:
            self.set_target_value(target, "read_only", data.read_only)
        if data.args or "args" in target:
            self.set_target_value(target, "args", list(data.args))
        if data.max_concurrency != 1 or "max_concurrency" in target:
            self.set_target_value(target, "max_concurrency", data.max_concurrency)

    def update_target(
        self,
        target_id: str,
        data: TargetEditorData,
        *,
        expected_revision: str,
    ) -> tuple[MutationResult, TargetEditorData]:
        def edit(document):
            source_path = self._resolve_source(None)
            if data.id != target_id:
                raise ConfigurationMutationError(
                    "Target identifier cannot be changed.",
                    code="configuration_invalid",
                    source_path=source_path.as_posix(),
                    unchanged=_UNCHANGED_MESSAGE,
                    recovery="Keep the existing target identifier when updating a target.",
                )
            target = self.find_target(document, target_id)
            if target is None:
                raise ConfigurationMutationError(
                    f"Unknown target: {target_id}",
                    code="not_found",
                    source_path=source_path.as_posix(),
                    unchanged=_UNCHANGED_MESSAGE,
                    recovery="Create the target before editing it.",
                )
            self.set_target_value(target, "backend", data.backend)
            self._update_target_model_settings(target, data)
            self._update_target_execution_settings(target, data)
            return target_to_editor_data(self.find_target(document, target_id) or target)

        return self._mutate(None, expected_revision, edit)

    def delete_target(
        self,
        target_id: str,
        *,
        expected_revision: str,
    ) -> tuple[MutationResult, str]:
        def edit(document):
            source_path = self._resolve_source(None)
            target = self.find_target(document, target_id)
            if target is None:
                raise ConfigurationMutationError(
                    f"Unknown target: {target_id}",
                    code="not_found",
                    source_path=source_path.as_posix(),
                    unchanged=_UNCHANGED_MESSAGE,
                    recovery="Verify the target identifier and retry.",
                )
            references = self.find_target_references(target_id, document=document)
            if references:
                raise ConfigurationMutationError(
                    f"Target {target_id!r} is referenced by existing profile declarations.",
                    code="referenced",
                    source_path=source_path.as_posix(),
                    unchanged=_UNCHANGED_MESSAGE,
                    recovery="Remove the profile workflow references before deleting the target.",
                    references=[ref.model_dump() for ref in references],
                )
            targets = document.get("targets")
            if targets is not None:
                targets.remove(target)
            return target_id

        return self._mutate(None, expected_revision, edit)

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
            existing["timeout_s"] = timeout_s
            return
        if isinstance(existing, Table):
            existing["targets"] = _string_array(targets)
            existing["timeout_s"] = timeout_s
            return
        policy = tomlkit.inline_table()
        policy["targets"] = _string_array(targets)
        policy["timeout_s"] = timeout_s
        profile[workflow] = policy

    def _profile_response(self, catalog, profile_id, project_root=None):
        return _build_profile_editor_response(
            catalog, profile_id,
            project_declaration=catalog.project_profile_declarations.get(profile_id)
            if project_root is not None else None,
            scope="project" if project_root is not None else "global",
        )

    def _read_profiles(self, project_root=None):
        with self._lock:
            path = self._resolve_source(project_root)
            base = self._runtime.catalog
            global_default = base.default_profile if project_root is not None else ""
            available = sorted(target.id for target in base.targets) if project_root is not None else []
            if not path.exists():
                return SourceRead(path, "", absent=True), [], global_default, global_default, available
            source = _regular_source(path)
            catalog = (self.resolve_global_catalog(source.data) if project_root is None
                       else self.resolve_project_catalog(project_root, source.data))
            ids = (set(catalog.profile_declarations) | set(catalog.profiles)
                   if project_root is None else catalog.project_profile_declarations)
            profiles = [self._profile_response(catalog, pid, project_root) for pid in sorted(ids)]
            return (SourceRead(path, source.revision), profiles,
                    global_default or catalog.default_profile, catalog.default_profile,
                    sorted(target.id for target in catalog.targets))

    def read_profiles(self):
        source, profiles, _, default, available = self._read_profiles()
        return source, profiles, default, available

    def read_project_overrides(self, project_root: Path):
        return self._read_profiles(project_root)

    def _get_profile(self, profile_id, project_root=None):
        source, profiles, global_default, default, available = self._read_profiles(project_root)
        profile = next((item for item in profiles if item.id == profile_id), None)
        if profile is None:
            label = "profile" if project_root is None else "project profile override"
            raise ConfigurationMutationError(
                f"Unknown {label}: {profile_id}", code="not_found",
                source_path=source.path.as_posix(),
                recovery="Create the profile before inspecting it.",
            )
        return source, profile, global_default, default, available

    def get_profile(self, profile_id: str):
        source, profile, _, default, available = self._get_profile(profile_id)
        return source, profile, default, available

    def get_project_override(self, project_root: Path, profile_id: str):
        return self._get_profile(profile_id, project_root)

    @staticmethod
    def _profile_extends_reference(profile_id, pid, declaration, scope, project_id, *, local):
        """Inspect one declaration, including implicit project shadowing."""
        if not isinstance(declaration, (dict, Table)):
            return None
        if pid == profile_id and (scope == "global" or local):
            return None
        extends = declaration.get("extends")
        if extends == profile_id or (
            scope == "project" and not local and extends is None and pid == profile_id
        ):
            return ProfileReference(
                scope=scope, project_id=project_id,
                profile_id=str(pid), relationship="extends",
            )
        return None

    @staticmethod
    def _profile_references(profile_id, sources, *, local=False):
        references = []
        for scope, project_id, source in sources:
            section = source.get("daemon" if scope == "global" else "project", {})
            if section.get("default_profile") == profile_id:
                references.append(ProfileReference(
                    scope=scope, project_id=project_id, profile_id=None,
                    relationship="default_profile",
                ))
            for pid, declaration in sorted(source.get("profiles", {}).items()):
                reference = ConfigurationMutationService._profile_extends_reference(
                    profile_id, pid, declaration, scope, project_id, local=local,
                )
                if reference is not None:
                    references.append(reference)
        return references

    def find_profile_references(
        self, profile_id: str, document: tomlkit.TOMLDocument | None = None,
    ) -> list[ProfileReference]:
        return self._profile_references(profile_id, self._reference_documents(document))

    def _profile_for_edit(self, document, action, profile_id, data, path, label):
        """Validate profile identity and prepare its declaration table."""
        if action == "create" and not profile_id.strip():
            raise ConfigurationMutationError(
                "Profile identifier cannot be empty.", code="configuration_invalid",
                source_path=path.as_posix(), recovery="Specify a non-empty profile identifier.",
            )
        if data is not None and action == "update" and data.id != profile_id:
            raise ConfigurationMutationError(
                "Profile identifier cannot be changed.", code="configuration_invalid",
                source_path=path.as_posix(), recovery="Keep the existing profile identifier.",
            )
        table = self.find_profile(document, profile_id)
        if action == "create":
            if table is not None:
                raise ConfigurationMutationError(
                    f"{label} {profile_id!r} already exists.", code="configuration_invalid",
                    source_path=path.as_posix(), recovery="Choose a unique profile identifier.",
                )
            table = self.profile_table(document, profile_id)
        elif table is None:
            raise ConfigurationMutationError(
                f"Unknown {label.lower()}: {profile_id}", code="not_found",
                source_path=path.as_posix(), recovery="Create the profile before editing it.",
            )
        return table

    def _delete_profile_declaration(self, document, profile_id, project_root, path, label):
        """Check references before removing a global or project declaration."""
        references = (
            self.find_profile_references(profile_id, document=document)
            if project_root is None else self._profile_references(
                profile_id, [("project", None, document)], local=True,
            )
        )
        if references:
            raise ConfigurationMutationError(
                f"{label} {profile_id!r} is referenced by configuration defaults or extends.",
                code="referenced", source_path=path.as_posix(),
                recovery="Remove default and extends references before deleting the profile.",
                references=[ref.model_dump() for ref in references],
            )
        profiles = document["profiles"]
        del profiles[profile_id]
        if project_root is not None and not profiles:
            del document["profiles"]

    def _apply_profile_data(self, table, action, data):
        """Apply inheritance and workflow edits without altering other keys."""
        if data.extends:
            self.set_profile_value(table, "extends", data.extends)
        elif action == "update":
            self.remove_profile_key(table, "extends")
        for workflow, policy in data.workflows.items():
            if policy is None:
                if action == "update":
                    self.remove_profile_key(table, workflow)
            else:
                _apply_workflow_policy(self, table, workflow, policy)

    def _mutate_profile(
        self, action, profile_id, data, expected_revision, project_root=None,
    ):
        def edit(document):
            path = self._resolve_source(project_root)
            label = "Profile" if project_root is None else "Project override"
            table = self._profile_for_edit(document, action, profile_id, data, path, label)
            if action == "delete":
                self._delete_profile_declaration(document, profile_id, project_root, path, label)
                return profile_id
            self._apply_profile_data(table, action, data)
            return profile_id

        result, _ = self._mutate(
            project_root, expected_revision, edit, create=action == "create",
        )
        if action == "delete":
            if project_root is None:
                return result, profile_id
            fallback = (self._profile_response(result.config, profile_id, project_root)
                        if profile_id in result.config.profiles else None)
            return result, fallback
        return result, self._profile_response(result.config, profile_id, project_root)

    def create_profile(self, data: ProfileEditorData, *, expected_revision: str):
        return self._mutate_profile("create", data.id.strip(), data, expected_revision)

    def update_profile(self, profile_id: str, data: ProfileEditorData, *, expected_revision: str):
        return self._mutate_profile("update", profile_id, data, expected_revision)

    def delete_profile(self, profile_id: str, *, expected_revision: str):
        return self._mutate_profile("delete", profile_id, None, expected_revision)

    def create_project_override(self, project_root: Path, data: ProfileEditorData, *, expected_revision: str):
        return self._mutate_profile("create", data.id.strip(), data, expected_revision, project_root)

    def update_project_override(self, project_root: Path, profile_id: str, data: ProfileEditorData, *, expected_revision: str):
        return self._mutate_profile("update", profile_id, data, expected_revision, project_root)

    def delete_project_override(self, project_root: Path, profile_id: str, *, expected_revision: str):
        result, fallback = self._mutate_profile("delete", profile_id, None, expected_revision, project_root)
        return result, profile_id, fallback

    # ------------------------------------------------------------------
    # Transactions.
    # ------------------------------------------------------------------

    def commit_document(
        self, document: tomlkit.TOMLDocument, *,
        project_root: Path | None = None, expected_revision: str | None = None,
    ) -> MutationResult:
        with self._lock:
            path = self._resolve_source(project_root)
            _require_revision(path, expected_revision)
            return self._commit_document(
                document, project_root=project_root, expected_revision=expected_revision,
                original=_expected_source(path, expected_revision),
            )

    def create_project_document(
        self, document: tomlkit.TOMLDocument, *, project_root: Path,
    ) -> MutationResult:
        with self._lock:
            return self._commit_document(
                document, project_root=project_root, expected_revision="", original=None,
            )

    def _commit_document(
        self, document, *, project_root, expected_revision, original,
    ) -> MutationResult:
        path = self._resolve_source(project_root)
        mode = _FileMode(path)
        candidate = self.candidate_bytes(document)
        if project_root is None:
            self._validate_registered_projects(self.resolve_global_catalog(candidate))
        else:
            self.resolve_project_catalog(project_root, candidate)
        committed = (
            create_bytes(path, candidate, mode=mode) if original is None
            else commit_bytes(path, candidate, expected_revision=expected_revision, mode=mode)
        )
        runtime = self._runtime
        try:
            if project_root is None:
                runtime._publish_configuration_locked()
            else:
                runtime._publish_project_configuration_locked(Path(project_root))
        except Exception as exc:
            if original is None:
                self._rollback_failed_creation(
                    path=path, candidate_revision=committed.revision, project_root=project_root,
                )
                message = "The project configuration was created but runtime publication failed. The created file was removed."
                unchanged = "The created project configuration was removed."
            else:
                self._rollback_failed_publication(
                    path=path, original=original, mode=mode,
                    candidate_revision=committed.revision, project_root=project_root,
                )
                message = "The configuration was replaced but runtime publication failed. The original file and runtime were restored."
                unchanged = "The configuration file and runtime were restored to their original state."
            raise ConfigurationMutationError(
                message, code="configuration_commit_failed", source_path=path.as_posix(),
                current_revision=original.revision if original else "",
                unchanged=unchanged, recovery="Retry the edit once the daemon is healthy.",
            ) from exc
        final = (runtime.catalog if project_root is None
                 else load_project_config(Path(project_root), runtime.catalog))
        return MutationResult(
            config=final, revision=committed.revision, source_path=path, changed=True,
        )

    def _validate_registered_projects(self, candidate: DaemonConfig) -> None:
        runtime = self._runtime
        database = getattr(runtime, "database", None)
        if database is None:
            return
        projects = database.projects()
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
        self._confirm_current(path, candidate_revision)
        try:
            commit_bytes(
                path,
                original.data,
                expected_revision=candidate_revision,
                mode=mode,
            )
        except ConfigurationMutationError as exc:
            if exc.code != "configuration_conflict":
                log.exception(
                    "Configuration rollback file restore failed",
                    extra={"event": "config_mutation.rollback_restore_failed", "path": str(path)},
                )
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
            ) from exc
        self._republish_original(path, project_root)

    def _rollback_failed_creation(
        self,
        *,
        path: Path,
        candidate_revision: str,
        project_root: Path,
    ) -> None:
        with _file_lock(path):
            self._confirm_current(path, candidate_revision)
            try:
                path.unlink()
                _fsync_directory(path.parent)
            except OSError:
                log.exception(
                    "Configuration rollback removal failed",
                    extra={"event": "config_mutation.rollback_removal_failed", "path": str(path)},
                )
                raise
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
    "target_to_editor_data",
]
