"""Config file loading, validation, and the project overlay."""

from __future__ import annotations

import json
import os
import re
import tomllib
from dataclasses import replace
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from refract.config.inspection import (
    ConfigIssue,
    ConfigSource,
    ConfigurationLoadError,
    Scope,
    issues_from_validation_error,
    make_issue,
    read_config_source,
    sha256_bytes,
    utc_now,
)
from refract.config.models import (
    CONFIG_FILE,
    REFRACT_DIR,
    ConfigFile,
    DaemonConfig,
    LoggingConfig,
    NotificationsConfig,
    ProfileDeclaration,
    ProfileFile,
    ProjectConfigFile,
    RetryPolicy,
    TargetConfig,
    TargetFile,
    TargetSelection,
    args_violation,
)

_ARGS_MESSAGES = {
    "args_nul": "args cannot contain NUL bytes",
    "args_reserved_token": "args cannot contain the reserved '--' token",
    "args_workspace_override": "args cannot override the workspace root",
}


class ProfileResolutionError(ValueError):
    """A profile chain error; ``code`` and ``profile`` locate it in the file."""

    def __init__(self, code: str, profile: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.profile = profile


def refract_home() -> Path:
    override = os.environ.get("REFRACT_HOME", "").strip()
    return Path(override).expanduser() if override else Path.home() / REFRACT_DIR


def load_guidance(
    home: Path,
    project_root: Path | None = None,
) -> dict[str, Any] | None:
    path = home / "task_guide.json"
    if project_root is not None:
        project_path = project_root / REFRACT_DIR / "task_guide.json"
        if project_path.exists():
            path = project_path
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid task guide: {path}: {exc.msg}") from exc
    if not isinstance(value, dict) or not value:
        raise ValueError("Task guide must be a non-empty JSON object")
    return value


def validate_target_args(
    target_id: str,
    backend: str,
    args: tuple[str, ...],
) -> None:
    """Reject argv that can override transport or workspace boundaries."""
    if not all(isinstance(value, str) for value in args):
        raise ValueError(f"Target {target_id!r} args must contain only strings")
    code = args_violation(backend, args)
    if code is not None:
        label = "Codex target" if code == "args_workspace_override" else "Target"
        raise ValueError(f"{label} {target_id!r} {_ARGS_MESSAGES[code]}")


# Profile resolution


def _snapshot_base(
    profile_id: str,
    parent: str,
    declarations: dict[str, ProfileDeclaration],
    snapshots: dict[str, dict[str, TargetSelection]] | None,
) -> dict[str, TargetSelection] | None:
    """Return the inherited base when the chain ends at ``parent``.

    ``None`` means ``parent`` is declared here and the walk continues into it.
    """
    unknown = ProfileResolutionError(
        "unknown_parent", profile_id, f"Profile {profile_id!r} extends unknown parent {parent!r}"
    )
    if parent == profile_id:
        if snapshots is None:
            raise ProfileResolutionError(
                "profile_cycle", profile_id, f"Profile inheritance cycle: {profile_id} -> {profile_id}"
            )
        if profile_id in snapshots:
            return dict(snapshots[profile_id])
        raise unknown
    if parent in declarations:
        return None
    if snapshots is not None and parent in snapshots:
        return dict(snapshots[parent])
    raise unknown


def _walk_profile_chain(
    start_profile: str,
    declarations: dict[str, ProfileDeclaration],
    snapshots: dict[str, dict[str, TargetSelection]] | None,
    memo: dict[str, dict[str, TargetSelection]],
) -> tuple[list[str], dict[str, TargetSelection]]:
    path: list[str] = []
    path_index: dict[str, int] = {}
    profile_id = start_profile
    while True:
        if profile_id in memo:
            return path, dict(memo[profile_id])
        if profile_id in path_index:
            cycle = path[path_index[profile_id]:] + [profile_id]
            raise ProfileResolutionError(
                "profile_cycle", profile_id, f"Profile inheritance cycle: {' -> '.join(cycle)}"
            )
        declaration = declarations[profile_id]
        path_index[profile_id] = len(path)
        path.append(profile_id)
        parent = declaration.extends
        if parent is None:
            return path, {}
        base = _snapshot_base(profile_id, parent, declarations, snapshots)
        if base is not None:
            return path, base
        profile_id = parent


def _resolve_profile_maps(
    declarations: dict[str, ProfileDeclaration],
    *,
    snapshots: dict[str, dict[str, TargetSelection]] | None = None,
) -> dict[str, dict[str, TargetSelection]]:
    memo: dict[str, dict[str, TargetSelection]] = {}
    for start_profile in declarations:
        if start_profile in memo:
            continue
        path, resolved = _walk_profile_chain(start_profile, declarations, snapshots, memo)
        for profile_id in reversed(path):
            resolved = dict(resolved)
            resolved.update(declarations[profile_id].workflows)
            memo[profile_id] = resolved
    return memo


def _declarations(profiles: dict[str, ProfileFile]) -> dict[str, ProfileDeclaration]:
    return {
        profile_id: ProfileDeclaration(
            profile.extends,
            {
                workflow: TargetSelection(tuple(selection.targets), selection.timeout_s)
                for workflow, selection in profile.workflows().items()
            },
        )
        for profile_id, profile in profiles.items()
    }


def _selection_issues(
    profiles: dict[str, ProfileFile], target_ids: set[str], scope: Scope
) -> list[ConfigIssue]:
    issues: list[ConfigIssue] = []
    for profile_id, profile in profiles.items():
        for workflow, selection in profile.workflows().items():
            base = ("profiles", profile_id, workflow, "targets")
            seen: set[str] = set()
            for index, target_id in enumerate(selection.targets):
                if target_id not in target_ids:
                    issues.append(make_issue("unknown_target", (*base, index), scope))
                elif target_id in seen:
                    issues.append(make_issue("duplicate_selection_target", (*base, index), scope))
                seen.add(target_id)
    return issues


def _resolve_or_issue(
    declarations: dict[str, ProfileDeclaration],
    scope: Scope,
    snapshots: dict[str, dict[str, TargetSelection]] | None = None,
) -> tuple[dict[str, dict[str, TargetSelection]], list[ConfigIssue]]:
    try:
        return _resolve_profile_maps(declarations, snapshots=snapshots), []
    except ProfileResolutionError as exc:
        loc = ("profiles", exc.profile, "extends")
        return {}, [make_issue(exc.code, loc, scope)]


# Runtime values


def _target(item: TargetFile) -> TargetConfig:
    return TargetConfig(
        id=item.id,
        backend=item.backend,
        model=item.model,
        backend_profile=item.backend_profile,
        reasoning=item.reasoning,
        system_prompt=item.system_prompt,
        args=tuple(item.args),
        max_concurrency=item.max_concurrency,
        retry=RetryPolicy(item.retry.attempts, tuple(item.retry.codes), tuple(item.retry.patterns)),
        env=dict(item.env),
    )


def _log_path(file: str | None, home: Path) -> Path | None:
    if file is None:
        return None
    candidate = Path(file).expanduser()
    return candidate if candidate.is_absolute() else home / candidate


# Source handling


def _source_error(
    issue: ConfigIssue, path: Path, source: ConfigSource | None
) -> ConfigurationLoadError:
    return ConfigurationLoadError(
        (issue,),
        path=path,
        revision=source.revision if source else "",
        modification_time=source.modification_time if source else "",
        attempted_at=source.loaded_at if source else "",
    )


def _parse(data: bytes, path: Path, source: ConfigSource | None, scope: Scope) -> dict[str, Any]:
    try:
        return tomllib.loads(data.decode("utf-8"))
    except UnicodeDecodeError as exc:
        issue = make_issue(
            "invalid_utf8", scope=scope, msg=f"Invalid config file: {path}: invalid UTF-8"
        )
        raise _source_error(issue, path, source) from exc
    except tomllib.TOMLDecodeError as exc:
        # Keep the parser location; the rest of its text can echo source content.
        where = re.search(r"\(at line (\d+), column (\d+)\)", str(exc))
        text = f"Invalid TOML syntax (at line {where.group(1)}, column {where.group(2)})" if where else "Invalid TOML syntax"
        raise _source_error(make_issue("toml_syntax", scope=scope, msg=text), path, source) from exc


def _validate(model: type, raw: dict[str, Any], path: Path, source: ConfigSource | None, scope: Scope) -> Any:
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        issues = issues_from_validation_error(exc, scope)
        raise ConfigurationLoadError(
            issues,
            path=path,
            revision=source.revision if source else "",
            modification_time=source.modification_time if source else "",
            attempted_at=source.loaded_at if source else "",
        ) from exc


def _raise_issues(issues: list[ConfigIssue], path: Path, source: ConfigSource | None) -> None:
    if issues:
        raise ConfigurationLoadError(
            tuple(issues),
            path=path,
            revision=source.revision if source else "",
            modification_time=source.modification_time if source else "",
            attempted_at=source.loaded_at if source else "",
        )


# Global config


def load_config(path: Path | None = None) -> DaemonConfig:
    home = refract_home()
    config_path = path or home / CONFIG_FILE
    try:
        source = read_config_source(config_path)
    except FileNotFoundError as exc:
        issue = make_issue("missing_file", msg=f"Missing config file: {config_path}")
        raise _source_error(issue, config_path, None) from exc
    except OSError as exc:
        issue = make_issue("unreadable_file", msg=f"Unable to read config file: {config_path}")
        raise _source_error(issue, config_path, None) from exc
    return _load_config_source(config_path, home, source)


def load_config_bytes(data: bytes, path: Path) -> DaemonConfig:
    """Load candidate global config bytes as if they were stored at path."""
    source = ConfigSource(
        path=path,
        data=data,
        revision=sha256_bytes(data),
        modification_time="",
        loaded_at=utc_now(),
    )
    return _load_config_source(path, refract_home(), source)


def _load_config_source(config_path: Path, home: Path, source: ConfigSource) -> DaemonConfig:
    raw = _parse(source.data, config_path, source, "global")
    parsed: ConfigFile = _validate(ConfigFile, raw, config_path, source, "global")
    targets = tuple(_target(item) for item in parsed.targets)
    issues: list[ConfigIssue] = []
    seen: set[str] = set()
    for index, target in enumerate(targets):
        if target.id in seen:
            issues.append(make_issue("duplicate_target", ("targets", index)))
        seen.add(target.id)
    issues += _selection_issues(parsed.profiles, seen, "global")
    declarations = _declarations(parsed.profiles)
    profiles: dict[str, dict[str, TargetSelection]] = {}
    if not issues:
        profiles, issues = _resolve_or_issue(declarations, "global")
    default_profile = parsed.daemon.default_profile
    if not issues and default_profile not in profiles:
        issues.append(make_issue("unknown_default_profile", ("daemon", "default_profile")))
    _raise_issues(issues, config_path, source)
    daemon = parsed.daemon
    return DaemonConfig(
        home=home,
        config_path=config_path,
        config_revision=source.revision,
        config_modification_time=source.modification_time,
        config_loaded_at=source.loaded_at,
        host=daemon.host,
        port=daemon.port,
        max_jobs=daemon.max_jobs,
        default_profile=default_profile,
        targets=targets,
        profiles=profiles,
        profile_declarations=declarations,
        logging=LoggingConfig(
            level=parsed.logging.level,
            file=_log_path(parsed.logging.file, home),
            max_bytes=parsed.logging.max_bytes,
            backup_count=parsed.logging.backup_count,
        ),
        notifications=NotificationsConfig(enabled=parsed.notifications.enabled),
        breaker_failure_threshold=daemon.breaker_failure_threshold,
        breaker_base_cooldown_s=daemon.breaker_base_cooldown_s,
        breaker_max_cooldown_s=daemon.breaker_max_cooldown_s,
        ask_timeout_s=daemon.ask_timeout_s,
    )


# Project overlay


def load_project_config(
    project_root: Path, base: DaemonConfig, data: bytes | None = None
) -> DaemonConfig:
    """Load a project overlay from disk, or from candidate bytes when given."""
    return _load_project_config_values(project_root, base, data)


def _project_targets(
    parsed: ProjectConfigFile, base: DaemonConfig
) -> tuple[list[TargetConfig], list[ConfigIssue]]:
    targets = list(base.targets)
    index_by_id = {target.id: index for index, target in enumerate(base.targets)}
    issues: list[ConfigIssue] = []
    seen: set[str] = set()
    for position, item in enumerate(parsed.targets or []):
        loc = ("targets", position, "id")
        if item.id not in index_by_id:
            issues.append(make_issue("project_unknown_target", loc, "project"))
        elif item.id in seen:
            issues.append(make_issue("project_duplicate_target", loc, "project"))
        else:
            index = index_by_id[item.id]
            targets[index] = replace(targets[index], env={**targets[index].env, **item.env})
        seen.add(item.id)
    return targets, issues


def _load_project_config_values(
    project_root: Path, base: DaemonConfig, data: bytes | None
) -> DaemonConfig:
    path = project_root / REFRACT_DIR / CONFIG_FILE
    if data is None:
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            return base
    raw = _parse(data, path, None, "project")
    parsed: ProjectConfigFile = _validate(ProjectConfigFile, raw, path, None, "project")
    targets, issues = _project_targets(parsed, base)
    profiles = {profile_id: dict(mapping) for profile_id, mapping in base.profiles.items()}
    declarations = dict(base.profile_declarations)
    if parsed.profiles is not None:
        issues += _selection_issues(parsed.profiles, {target.id for target in targets}, "project")
        project_declarations = _declarations(parsed.profiles)
        if not issues:
            resolved, issues = _resolve_or_issue(project_declarations, "project", base.profiles)
            profiles.update(resolved)
            declarations.update(project_declarations)
    _raise_issues(issues, path, None)
    return replace(
        base,
        targets=tuple(targets),
        profiles=profiles,
        profile_declarations=declarations,
    )


def resolve_target_environment(
    catalog: DaemonConfig,
    target: TargetConfig | str,
) -> dict[str, str]:
    """Return the literal environment overrides configured for a target."""
    if isinstance(target, str):
        target = next((item for item in catalog.targets if item.id == target), None)
        if target is None:
            raise ValueError("Unknown target")
    return dict(target.env)
