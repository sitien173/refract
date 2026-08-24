"""Daemon configuration loading."""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from openmcp.workflows import get_workflow


@dataclass(slots=True, frozen=True)
class TargetConfig:
    id: str
    backend: str
    model: str = ""
    backend_profile: str = ""
    reasoning: str = ""
    system_prompt: str = ""
    isolated: bool = False
    read_only: bool = False
    args: tuple[str, ...] = ()
    max_concurrency: int = 1


@dataclass(slots=True, frozen=True)
class TargetSelection:
    """Targets and retry policy for one workflow inside a profile."""

    targets: tuple[str, ...]
    max_attempts: int
    timeout_s: int = 0


@dataclass(slots=True, frozen=True)
class ProfileDeclaration:
    """Normalized raw declaration for one profile."""

    extends: str | None = None
    workflows: dict[str, TargetSelection] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class LoggingConfig:
    """Application log sinks and retention policy."""

    level: str = "INFO"
    format: str = "text"
    file: Path | None = None
    console: bool = False
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 5
    capture_warnings: bool = True


@dataclass(slots=True, frozen=True)
class DaemonConfig:
    home: Path
    host: str = "127.0.0.1"
    port: int = 8765
    max_jobs: int = 4
    history_turns: int = 8
    history_bytes: int = 65536
    default_profile: str = ""
    targets: tuple[TargetConfig, ...] = field(default_factory=tuple)
    profiles: dict[str, dict[str, TargetSelection]] = field(default_factory=dict)
    profile_declarations: dict[str, ProfileDeclaration] = field(default_factory=dict)
    config_path: Path | None = None
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    @property
    def database_path(self) -> Path:
        return self.home / "openmcp.db"



def openmcp_home() -> Path:
    override = os.environ.get("OPENMCP_HOME", "").strip()
    return Path(override).expanduser() if override else Path.home() / ".openmcp"


def load_task_guide(
    home: Path,
    project_root: Path | None = None,
) -> dict[str, Any]:
    project_path = (
        project_root / ".openmcp" / "task_guide.json"
        if project_root is not None
        else None
    )
    legacy_project_path = (
        project_root / ".openmcp" / "task_routes.json"
        if project_root is not None
        else None
    )
    if project_path is not None and project_path.exists():
        path = project_path
    elif legacy_project_path is not None and legacy_project_path.exists():
        path = legacy_project_path
    else:
        path = home / "task_guide.json"
        legacy_path = home / "task_routes.json"
        if not path.exists() and legacy_path.exists():
            path = legacy_path
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Missing task guide: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid task guide: {path}: {exc.msg}") from exc
    if not isinstance(value, dict) or not value:
        raise ValueError("Task guide must be a non-empty JSON object")
    # Normalize the previous decision-table keys for current MCP clients.
    legacy_recommendations = value.get("routes")
    if isinstance(legacy_recommendations, list):
        if "recommendations" not in value:
            value = {**value, "recommendations": legacy_recommendations}
        value.pop("routes", None)
    recommendations = value.get("recommendations")
    if isinstance(recommendations, list):
        normalized: list[Any] = []
        for recommendation in recommendations:
            if not isinstance(recommendation, dict):
                normalized.append(recommendation)
                continue
            item = dict(recommendation)
            if "routing_profile" in item:
                item.setdefault("profile", item["routing_profile"])
                item.pop("routing_profile")
            normalized.append(item)
        value["recommendations"] = normalized
    columns = value.get("columns")
    if isinstance(columns, list):
        value["columns"] = [
            "profile" if column == "routing_profile" else column
            for column in columns
        ]
    return value


def _positive_int(value: Any, default: int, name: str) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _boolean(value: Any, default: bool, name: str) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be true or false")
    return value


def _renamed_value(mapping: dict[str, Any], name: str, legacy: str) -> Any:
    """Read a renamed setting while rejecting ambiguous mixed configuration."""
    if name in mapping and legacy in mapping:
        raise ValueError(f"Use {name!r}, not both {name!r} and legacy {legacy!r}")
    return mapping.get(name, mapping.get(legacy))


def _target_selection(
    raw: Any,
    *,
    profile_id: str,
    workflow: str,
    target_by_id: dict[str, TargetConfig],
) -> TargetSelection:
    if isinstance(raw, str):
        name = raw.strip()
        selected = (name,) if name else ()
        max_attempts = len(selected)
        timeout_s = 0
    elif isinstance(raw, list):
        if not all(isinstance(value, str) for value in raw):
            raise ValueError(
                f"Profile {profile_id!r} workflow {workflow!r} targets "
                "must contain only strings"
            )
        selected = tuple(value.strip() for value in raw)
        max_attempts = len(selected)
        timeout_s = 0
    elif isinstance(raw, dict):
        allowed = {"targets", "max_attempts", "timeout_s"}
        unknown_options = set(raw) - allowed
        if unknown_options:
            raise ValueError(
                f"Profile {profile_id!r} workflow {workflow!r} has unsupported "
                f"settings: {sorted(unknown_options)}"
            )
        raw_targets = raw.get("targets", [])
        if isinstance(raw_targets, str):
            selected = (raw_targets.strip(),)
        elif isinstance(raw_targets, list):
            if not all(isinstance(value, str) for value in raw_targets):
                raise ValueError(
                    f"Profile {profile_id!r} workflow {workflow!r} targets "
                    "must contain only strings"
                )
            selected = tuple(value.strip() for value in raw_targets)
        else:
            selected = ()
        max_attempts = _positive_int(
            raw.get("max_attempts"), len(selected), "max_attempts"
        )
        raw_timeout = raw.get("timeout_s", 0)
        if (
            isinstance(raw_timeout, bool)
            or not isinstance(raw_timeout, int)
            or raw_timeout < 0
        ):
            raise ValueError("timeout_s must be a non-negative integer")
        timeout_s = raw_timeout
    else:
        selected = ()
        max_attempts = 0
        timeout_s = 0

    unknown_targets = set(selected) - target_by_id.keys()
    if not selected or unknown_targets or len(set(selected)) != len(selected):
        raise ValueError(
            f"Profile {profile_id!r} workflow {workflow!r} has invalid targets: "
            f"{sorted(unknown_targets)}"
        )
    return TargetSelection(
        targets=selected,
        max_attempts=max_attempts,
        timeout_s=timeout_s,
    )


def _profile_declarations(
    raw: Any,
    targets: tuple[TargetConfig, ...],
) -> dict[str, ProfileDeclaration]:
    if not isinstance(raw, dict) or not raw:
        raise ValueError("[profiles] must contain at least one profile")
    target_by_id = {target.id: target for target in targets}
    declarations: dict[str, ProfileDeclaration] = {}
    for raw_profile_id, mapping in raw.items():
        profile_id = str(raw_profile_id)
        if not isinstance(mapping, dict) or not mapping:
            raise ValueError(
                f"Profile {profile_id!r} must declare extends or a workflow"
            )
        raw_extends = mapping.get("extends")
        if raw_extends is None:
            extends = None
        elif not isinstance(raw_extends, str) or not raw_extends.strip():
            raise ValueError(
                f"Profile {profile_id!r} extends must be a non-empty string"
            )
        else:
            extends = raw_extends.strip()
        workflows: dict[str, TargetSelection] = {}
        for raw_workflow, value in mapping.items():
            if raw_workflow == "extends":
                continue
            workflow = get_workflow(str(raw_workflow))
            workflows[workflow] = _target_selection(
                value,
                profile_id=profile_id,
                workflow=workflow,
                target_by_id=target_by_id,
            )
        declarations[profile_id] = ProfileDeclaration(extends, workflows)
    return declarations


def _resolve_profile_maps(
    declarations: dict[str, ProfileDeclaration],
    *,
    snapshots: dict[str, dict[str, TargetSelection]] | None = None,
) -> dict[str, dict[str, TargetSelection]]:
    memo: dict[str, dict[str, TargetSelection]] = {}
    for start_profile in declarations:
        if start_profile in memo:
            continue
        path: list[str] = []
        path_index: dict[str, int] = {}
        profile_id = start_profile
        while True:
            if profile_id in memo:
                resolved = dict(memo[profile_id])
                break
            if profile_id in path_index:
                cycle = path[path_index[profile_id]:] + [profile_id]
                raise ValueError(
                    f"Profile inheritance cycle: {' -> '.join(cycle)}"
                )
            declaration = declarations[profile_id]
            path_index[profile_id] = len(path)
            path.append(profile_id)
            parent = declaration.extends
            if parent is None:
                resolved = {}
                break
            if parent == profile_id:
                if snapshots is None:
                    cycle = [profile_id, profile_id]
                    raise ValueError(
                        f"Profile inheritance cycle: {' -> '.join(cycle)}"
                    )
                if profile_id in snapshots:
                    resolved = dict(snapshots[profile_id])
                    break
                raise ValueError(
                    f"Profile {profile_id!r} extends unknown parent {parent!r}"
                )
            if parent in declarations:
                profile_id = parent
                continue
            if snapshots is not None and parent in snapshots:
                resolved = dict(snapshots[parent])
                break
            raise ValueError(
                f"Profile {profile_id!r} extends unknown parent {parent!r}"
            )

        for profile_id in reversed(path):
            resolved = dict(resolved)
            resolved.update(declarations[profile_id].workflows)
            memo[profile_id] = resolved
    return memo


def validate_target_args(
    target_id: str,
    backend: str,
    args: tuple[str, ...],
    *,
    isolated: bool = False,
) -> None:
    """Reject argv that can override transport or isolation boundaries."""
    if not all(isinstance(value, str) for value in args):
        raise ValueError(f"Target {target_id!r} args must contain only strings")
    if any("\x00" in value for value in args):
        raise ValueError(f"Target {target_id!r} args cannot contain NUL bytes")
    if "--" in args:
        raise ValueError(
            f"Target {target_id!r} args cannot contain the reserved '--' token"
        )
    if backend == "codex" and any(
        value in {"--cd", "-C"}
        or value.startswith("--cd=")
        or (value.startswith("-C") and len(value) > 2)
        for value in args
    ):
        raise ValueError(
            f"Codex target {target_id!r} args cannot override the workspace root"
        )
    forbidden_isolated_pi_args = {"--extension", "-e", "--skill", "--prompt-template"}
    if backend == "pi" and isolated and any(
        value in forbidden_isolated_pi_args
        or value.startswith(("--extension=", "--skill=", "--prompt-template="))
        for value in args
    ):
        raise ValueError(
            f"Isolated Pi target {target_id!r} cannot explicitly load extensions, "
            "skills, or prompt templates"
        )


def _targets(raw: Any) -> tuple[TargetConfig, ...]:
    if isinstance(raw, dict) and not raw:
        raise ValueError("[targets] must contain at least one target")
    if not isinstance(raw, list):
        raise ValueError("[targets] must be a TOML array of tables")
    if not raw:
        raise ValueError("[targets] must contain at least one target")
    targets: list[TargetConfig] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Each target must be a TOML table")
        raw_target_id = item.get("id", "")
        raw_backend = item.get("backend", "")
        target_id = raw_target_id.strip() if isinstance(raw_target_id, str) else ""
        backend = raw_backend.strip() if isinstance(raw_backend, str) else ""
        if not target_id or backend not in {"agy", "codex", "pi", "claude"}:
            raise ValueError(f"Invalid target: {item!r}")
        args = item.get("args", [])
        if not isinstance(args, list) or not all(isinstance(value, str) for value in args):
            raise ValueError(f"Target {target_id!r} args must be a list of strings")
        isolated = _boolean(item.get("isolated"), False, f"Target {target_id!r} isolated")
        read_only = _boolean(
            item.get("read_only"), False, f"Target {target_id!r} read_only"
        )
        text_fields = {
            "model": item.get("model", ""),
            "reasoning": item.get("reasoning", ""),
            "system_prompt": item.get("system_prompt", ""),
        }
        invalid_text = [
            name for name, value in text_fields.items() if not isinstance(value, str)
        ]
        if invalid_text:
            raise ValueError(
                f"Target {target_id!r} settings must be strings: {invalid_text}"
            )
        raw_backend_profile = _renamed_value(item, "backend_profile", "profile")
        if raw_backend_profile is None:
            backend_profile = ""
        elif isinstance(raw_backend_profile, str):
            backend_profile = raw_backend_profile
        else:
            raise ValueError(
                f"Target {target_id!r} backend_profile must be a string"
            )
        validate_target_args(target_id, backend, tuple(args), isolated=isolated)
        targets.append(
            TargetConfig(
                id=target_id,
                backend=backend,
                model=text_fields["model"],
                backend_profile=backend_profile,
                reasoning=text_fields["reasoning"],
                system_prompt=text_fields["system_prompt"],
                isolated=isolated,
                read_only=read_only,
                args=tuple(args),
                max_concurrency=_positive_int(
                    item.get("max_concurrency"),
                    1,
                    f"Target {target_id!r} max_concurrency",
                ),
            )
        )
    if len({target.id for target in targets}) != len(targets):
        raise ValueError("Target identifiers must be unique")
    return tuple(targets)


def _logging_config(raw: Any, home: Path) -> LoggingConfig:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("[logging] must be a TOML table")
    unknown = set(raw) - {
        "level",
        "format",
        "file",
        "console",
        "max_bytes",
        "backup_count",
        "capture_warnings",
    }
    if unknown:
        raise ValueError(f"Unsupported logging settings: {sorted(unknown)}")
    level = str(raw.get("level", "INFO")).strip().upper()
    if level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
        raise ValueError(f"Invalid logging level: {level!r}")
    log_format = str(raw.get("format", "text")).strip().lower()
    if log_format not in {"text", "json"}:
        raise ValueError("Logging format must be 'text' or 'json'")
    raw_file = raw.get("file", "openmcp.log")
    if raw_file is None or raw_file is False or str(raw_file).strip().lower() in {
        "",
        "none",
        "off",
    }:
        log_file = None
    elif not isinstance(raw_file, str):
        raise ValueError("logging.file must be a path string or false")
    else:
        candidate = Path(raw_file).expanduser()
        log_file = candidate if candidate.is_absolute() else home / candidate

    for name in ("console", "capture_warnings"):
        if name in raw and not isinstance(raw[name], bool):
            raise ValueError(f"logging.{name} must be true or false")
    try:
        max_bytes = int(raw.get("max_bytes", 10 * 1024 * 1024))
        backup_count = int(raw.get("backup_count", 5))
    except (TypeError, ValueError) as exc:
        raise ValueError("Logging retention settings must be integers") from exc
    if isinstance(raw.get("max_bytes"), bool) or max_bytes < 1:
        raise ValueError("logging.max_bytes must be at least 1")
    if isinstance(raw.get("backup_count"), bool) or backup_count < 0:
        raise ValueError("logging.backup_count must be at least 0")
    return LoggingConfig(
        level=level,
        format=log_format,
        file=log_file,
        console=raw.get("console", False),
        max_bytes=max_bytes,
        backup_count=backup_count,
        capture_warnings=raw.get("capture_warnings", True),
    )


def load_config(path: Path | None = None) -> DaemonConfig:
    home = openmcp_home()
    config_path = path or home / "config.toml"
    try:
        raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Missing config file: {config_path}") from exc
    unsupported = set(raw) - {
        "daemon",
        "logging",
        "targets",
        "profiles",
    }
    if unsupported:
        raise ValueError(f"Unsupported config sections: {sorted(unsupported)}")
    daemon = raw.get("daemon", {})
    if not isinstance(daemon, dict):
        raise ValueError("[daemon] must be a TOML table")
    unsupported_daemon = set(daemon) - {
        "host",
        "port",
        "max_jobs",
        "history_turns",
        "history_bytes",
        "default_profile",
    }
    if unsupported_daemon:
        raise ValueError(f"Unsupported daemon settings: {sorted(unsupported_daemon)}")
    if "targets" not in raw:
        raise ValueError("Missing required [targets] section")
    if "profiles" not in raw:
        raise ValueError("Missing required [profiles] section")
    targets = _targets(raw["targets"])
    profile_declarations = _profile_declarations(raw["profiles"], targets)
    profiles = _resolve_profile_maps(profile_declarations)
    default_profile = str(daemon.get("default_profile", "")).strip()
    if not default_profile:
        raise ValueError("[daemon].default_profile must be set")
    if default_profile not in profiles:
        raise ValueError(
            f"Unknown [daemon].default_profile: {default_profile!r}"
        )
    host = daemon.get("host", "127.0.0.1")
    if not isinstance(host, str) or not host.strip():
        raise ValueError("[daemon].host must be a non-empty string")
    port = _positive_int(daemon.get("port"), 8765, "[daemon].port")
    if port > 65535:
        raise ValueError("[daemon].port must not exceed 65535")
    return DaemonConfig(
        home=home,
        config_path=config_path,
        host=host.strip(),
        port=port,
        max_jobs=_positive_int(daemon.get("max_jobs"), 4, "[daemon].max_jobs"),
        history_turns=_positive_int(
            daemon.get("history_turns"), 8, "[daemon].history_turns"
        ),
        history_bytes=_positive_int(
            daemon.get("history_bytes"), 65536, "[daemon].history_bytes"
        ),
        default_profile=default_profile,
        targets=targets,
        profiles=profiles,
        profile_declarations=profile_declarations,
        logging=_logging_config(raw.get("logging"), home),
    )


def load_project_config(project_root: Path, base: DaemonConfig) -> DaemonConfig:
    path = project_root / ".openmcp" / "config.toml"
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return base
    unsupported = set(raw) - {
        "project",
        "profiles",
    }
    if unsupported:
        raise ValueError(f"Unsupported project config sections: {sorted(unsupported)}")

    project = raw.get("project", {})
    if not isinstance(project, dict):
        raise ValueError("[project] must be a TOML table")
    unsupported_project = set(project) - {"default_profile"}
    if unsupported_project:
        raise ValueError(f"Unsupported project settings: {sorted(unsupported_project)}")

    if "profiles" not in raw:
        profiles = {profile_id: dict(mapping) for profile_id, mapping in base.profiles.items()}
        profile_declarations = dict(base.profile_declarations)
    else:
        project_declarations = _profile_declarations(raw["profiles"], base.targets)
        project_profiles = _resolve_profile_maps(
            project_declarations,
            snapshots=base.profiles,
        )
        profiles = {profile_id: dict(mapping) for profile_id, mapping in base.profiles.items()}
        profiles.update(project_profiles)
        profile_declarations = dict(base.profile_declarations)
        profile_declarations.update(project_declarations)

    default_profile = str(project.get("default_profile", base.default_profile)).strip()
    if default_profile not in profiles:
        raise ValueError(f"Unknown project profile: {default_profile!r}")
    return replace(
        base,
        default_profile=default_profile,
        profiles=profiles,
        profile_declarations=profile_declarations,
    )


__all__ = [
    "DaemonConfig",
    "LoggingConfig",
    "ProfileDeclaration",
    "TargetConfig",
    "TargetSelection",
    "load_config",
    "load_project_config",
    "load_task_guide",
    "openmcp_home",
    "validate_target_args",
]
