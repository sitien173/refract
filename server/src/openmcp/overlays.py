"""Project-local ignored files exposed to selected workflows."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from openmcp.workspaces import WorkspaceError, ignored_paths


_CONFIG_NAME = ".openmcp.local.toml"
_MANIFEST_NAME = "manifest.json"


class OverlayError(ValueError):
    pass


@dataclass(slots=True, frozen=True)
class OverlayRule:
    include: tuple[str, ...]
    exclude: tuple[str, ...] = ()


def _strings(value: Any, label: str, *, required: bool = False) -> tuple[str, ...]:
    if value is None and not required:
        return ()
    if not isinstance(value, list) or not value:
        raise OverlayError(f"{label} must be a non-empty list")
    resolved = tuple(str(item).strip() for item in value)
    if any(not item for item in resolved):
        raise OverlayError(f"{label} cannot contain empty values")
    return resolved


def _validate_pattern(pattern: str) -> None:
    path = PurePosixPath(pattern)
    if path.is_absolute() or ".." in path.parts:
        raise OverlayError(f"Overlay pattern must stay inside the project: {pattern}")
    if "\\" in pattern:
        raise OverlayError(f"Overlay pattern must use forward slashes: {pattern}")


def load_overlay_rules(project_root: Path, workflow: str) -> tuple[OverlayRule, ...]:
    path = project_root / _CONFIG_NAME
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ()
    except tomllib.TOMLDecodeError as exc:
        raise OverlayError(f"Invalid overlay configuration: {path}: {exc}") from exc
    unsupported = set(raw) - {"overlays"}
    if unsupported:
        raise OverlayError(f"Unsupported local config sections: {sorted(unsupported)}")
    entries = raw.get("overlays", [])
    if not isinstance(entries, list):
        raise OverlayError("overlays must be TOML tables")
    rules: list[OverlayRule] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise OverlayError(f"overlays[{index}] must be a TOML table")
        unknown = set(entry) - {"include", "exclude", "workflows"}
        if unknown:
            raise OverlayError(
                f"overlays[{index}] has unsupported fields: {sorted(unknown)}"
            )
        include = _strings(entry.get("include"), f"overlays[{index}].include", required=True)
        exclude = _strings(entry.get("exclude"), f"overlays[{index}].exclude")
        workflows = _strings(
            entry.get("workflows"),
            f"overlays[{index}].workflows",
            required=True,
        )
        for pattern in (*include, *exclude):
            _validate_pattern(pattern)
        if workflow in workflows:
            rules.append(OverlayRule(include=include, exclude=exclude))
    return tuple(rules)


def _safe_path(root: Path, relative: str) -> Path:
    value = PurePosixPath(relative)
    if value.is_absolute() or not value.parts or ".." in value.parts:
        raise OverlayError(f"Invalid overlay path: {relative}")
    path = root.joinpath(*value.parts)
    current = root
    for part in value.parts:
        current /= part
        if current.is_symlink():
            raise OverlayError(f"Overlay paths cannot contain symlinks: {relative}")
    return path


def _glob(root: Path, pattern: str) -> set[Path]:
    try:
        return {
            path
            for path in root.glob(pattern)
            if path.is_file() or path.is_symlink()
        }
    except ValueError as exc:
        raise OverlayError(f"Invalid overlay pattern {pattern!r}: {exc}") from exc


def _matching_files(root: Path, rules: tuple[OverlayRule, ...]) -> dict[str, Path]:
    matches: dict[str, Path] = {}
    for rule in rules:
        included = set().union(*(_glob(root, pattern) for pattern in rule.include))
        excluded = set().union(*(_glob(root, pattern) for pattern in rule.exclude))
        for path in included - excluded:
            relative = path.relative_to(root).as_posix()
            _safe_path(root, relative)
            matches[relative] = path
    return matches


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy(source: Path, destination_root: Path, relative: str) -> None:
    destination = _safe_path(destination_root, relative)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _atomic_copy(source: Path, destination_root: Path, relative: str) -> None:
    destination = _safe_path(destination_root, relative)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.openmcp-",
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _rules_data(rules: tuple[OverlayRule, ...]) -> list[dict[str, list[str]]]:
    return [
        {"include": list(rule.include), "exclude": list(rule.exclude)}
        for rule in rules
    ]


def _state_path(state_root: Path) -> Path:
    return state_root / _MANIFEST_NAME


def _load_state(state_root: Path) -> dict[str, Any] | None:
    path = _state_path(state_root)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        raise OverlayError(f"Invalid overlay state: {path}: {exc.msg}") from exc
    if state.get("version") != 1:
        raise OverlayError(f"Unsupported overlay state: {path}")
    return state


def _state_rules(state: dict[str, Any]) -> tuple[OverlayRule, ...]:
    return tuple(
        OverlayRule(
            include=tuple(entry["include"]),
            exclude=tuple(entry["exclude"]),
        )
        for entry in state["rules"]
    )


def _write_state(state_root: Path, state: dict[str, Any]) -> None:
    state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    _state_path(state_root).write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _save_checkpoint(
    state_root: Path,
    state: dict[str, Any],
    name: str,
) -> None:
    checkpoint = state_root / "checkpoints" / name
    shutil.rmtree(checkpoint, ignore_errors=True)
    result = state_root / "result"
    for relative, action in state["changes"].items():
        if action == "write":
            _copy(_safe_path(result, relative), checkpoint, relative)


def _validate_ignored(repository: Path, files: dict[str, Path]) -> None:
    try:
        ignored = ignored_paths(repository, files)
    except WorkspaceError as exc:
        raise OverlayError(str(exc)) from exc
    visible = sorted(files.keys() - ignored)
    if visible:
        raise OverlayError(f"Overlay file must be ignored by Git: {visible[0]}")


def initialize_overlays(
    repository: Path,
    worktree: Path,
    state_root: Path,
    rules: tuple[OverlayRule, ...],
) -> None:
    if not rules:
        return
    state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    state_root.chmod(0o700)
    files = _matching_files(repository, rules)
    _validate_ignored(repository, files)
    originals = {relative: _digest(path) for relative, path in files.items()}
    baseline = state_root / "baseline"
    for relative, source in files.items():
        _copy(source, worktree, relative)
        _copy(source, baseline, relative)
    _validate_ignored(worktree, _matching_files(worktree, rules))
    _write_state(
        state_root,
        {
            "version": 1,
            "rules": _rules_data(rules),
            "originals": originals,
            "changes": {},
            "start_changes": {},
            "stage_changes": {},
        },
    )


def validate_overlays(worktree: Path, state_root: Path) -> None:
    state = _load_state(state_root)
    if state is None:
        return
    _validate_ignored(worktree, _matching_files(worktree, _state_rules(state)))


def capture_overlays(
    worktree: Path,
    state_root: Path,
    checkpoint: str = "",
) -> None:
    state = _load_state(state_root)
    if state is None:
        return
    rules = _state_rules(state)
    files = _matching_files(worktree, rules)
    _validate_ignored(worktree, files)
    originals: dict[str, str] = state["originals"]
    changes = {
        relative: "write"
        for relative, path in files.items()
        if originals.get(relative) != _digest(path)
    }
    changes.update(
        {
            relative: "delete"
            for relative in originals.keys() - files.keys()
        }
    )
    result = state_root / "result"
    shutil.rmtree(result, ignore_errors=True)
    for relative, action in changes.items():
        if action == "write":
            _copy(files[relative], result, relative)
    state["changes"] = changes
    if checkpoint:
        state["stage_changes"][checkpoint] = dict(changes)
        _save_checkpoint(state_root, state, checkpoint)
    _write_state(state_root, state)


def seal_overlays(state_root: Path) -> None:
    state = _load_state(state_root)
    if state is None:
        return
    state["start_changes"] = dict(state["changes"])
    _save_checkpoint(state_root, state, "_start")
    _write_state(state_root, state)


def rewind_overlays(state_root: Path, checkpoint: str = "") -> None:
    state = _load_state(state_root)
    if state is None:
        return
    if checkpoint:
        try:
            changes = state["stage_changes"][checkpoint]
        except KeyError as exc:
            raise OverlayError(f"Missing overlay checkpoint: {checkpoint}") from exc
        name = checkpoint
    else:
        changes = state["start_changes"]
        name = "_start"
    result = state_root / "result"
    shutil.rmtree(result, ignore_errors=True)
    saved = state_root / "checkpoints" / name
    for relative, action in changes.items():
        if action == "write":
            _copy(_safe_path(saved, relative), result, relative)
    state["changes"] = dict(changes)
    _write_state(state_root, state)


def restore_overlays(worktree: Path, state_root: Path) -> None:
    state = _load_state(state_root)
    if state is None:
        return
    rules = _state_rules(state)
    current = _matching_files(worktree, rules)
    _validate_ignored(worktree, current)
    for path in current.values():
        path.unlink()
    baseline = state_root / "baseline"
    for relative in state["originals"]:
        _copy(_safe_path(baseline, relative), worktree, relative)
    result = state_root / "result"
    for relative, action in state["changes"].items():
        destination = _safe_path(worktree, relative)
        if action == "delete":
            destination.unlink(missing_ok=True)
        else:
            _copy(_safe_path(result, relative), worktree, relative)
    _validate_ignored(worktree, _matching_files(worktree, rules))


def copy_overlays(source: Path, destination: Path, state_root: Path) -> None:
    state = _load_state(state_root)
    if state is None:
        return
    files = _matching_files(source, _state_rules(state))
    _validate_ignored(source, files)
    for relative, path in files.items():
        _copy(path, destination, relative)
    _validate_ignored(destination, _matching_files(destination, _state_rules(state)))


def discard_overlays(worktree: Path, state_root: Path) -> None:
    state = _load_state(state_root)
    if state is None:
        return
    for path in _matching_files(worktree, _state_rules(state)).values():
        path.unlink()


def inherit_overlays(
    parent_state_root: Path,
    worktree: Path,
    state_root: Path,
) -> None:
    parent = _load_state(parent_state_root)
    state = _load_state(state_root)
    if parent is None or state is None:
        return
    rules = _state_rules(state)
    parent_result = parent_state_root / "result"
    writes = _matching_files(parent_result, rules)
    for relative, source in writes.items():
        _copy(source, worktree, relative)
    for relative, action in parent["changes"].items():
        if action == "delete" and relative in state["originals"]:
            _safe_path(worktree, relative).unlink(missing_ok=True)
    capture_overlays(worktree, state_root)


def preflight_overlays(repository: Path, state_root: Path) -> None:
    state = _load_state(state_root)
    if state is None:
        return
    originals: dict[str, str] = state["originals"]
    for relative in state["changes"]:
        path = _safe_path(repository, relative)
        if path.exists() and not path.is_file():
            raise OverlayError(f"Overlay path is not a regular file: {relative}")
        current = _digest(path) if path.is_file() else None
        if current != originals.get(relative):
            raise OverlayError(
                f"Overlay file changed after job submission: {relative}"
            )


def apply_overlays(repository: Path, state_root: Path) -> None:
    state = _load_state(state_root)
    if state is None:
        return
    preflight_overlays(repository, state_root)
    result = state_root / "result"
    for relative, action in state["changes"].items():
        destination = _safe_path(repository, relative)
        if action == "delete":
            destination.unlink(missing_ok=True)
        else:
            _atomic_copy(_safe_path(result, relative), repository, relative)


__all__ = [
    "OverlayError",
    "OverlayRule",
    "apply_overlays",
    "capture_overlays",
    "copy_overlays",
    "discard_overlays",
    "inherit_overlays",
    "initialize_overlays",
    "load_overlay_rules",
    "preflight_overlays",
    "rewind_overlays",
    "restore_overlays",
    "seal_overlays",
    "validate_overlays",
]
