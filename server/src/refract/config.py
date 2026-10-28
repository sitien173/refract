"""Daemon configuration loading."""

from __future__ import annotations

import json
import math
import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from refract.logging_setup import get_logger

from refract.config_inspection import (
    ConfigSource,
    ConfigurationLoadError,
    read_config_source,
    sha256_bytes,
    utc_now,
)
from refract.workflows import get_workflow

log = get_logger("config")
DEFAULT_PORT = 8765
DEFAULT_ASK_TIMEOUT_S = 300


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
    retry_policy: str = ""
    envs_vars: tuple[str, ...] = field(default_factory=tuple, repr=False)
    envs: dict[str, str] = field(default_factory=dict, repr=False)


@dataclass(slots=True, frozen=True)
class RetryPolicy:
    retry_attempt: int = 0
    error_codes: tuple[str, ...] = ()
    error_patterns: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class TargetSelection:
    """Targets and timeout for one workflow inside a profile."""

    targets: tuple[str, ...]
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
class NotificationsConfig:
    """Desktop notification settings."""

    enabled: bool = False


@dataclass(slots=True, frozen=True)
class LangfuseConfig:
    """Langfuse observability client configuration."""

    enabled: bool = False
    base_url: str = "http://localhost:3000"
    environment: str = ""
    sample_rate: float = 1.0


@dataclass(slots=True, frozen=True)
class DaemonConfig:
    home: Path
    host: str = "127.0.0.1"
    port: int = DEFAULT_PORT
    max_jobs: int = 4
    history_turns: int = 8
    history_bytes: int = 65536
    default_profile: str = ""
    targets: tuple[TargetConfig, ...] = field(default_factory=tuple)
    profiles: dict[str, dict[str, TargetSelection]] = field(default_factory=dict)
    profile_declarations: dict[str, ProfileDeclaration] = field(default_factory=dict)
    # Project declarations are retained separately so dashboard attribution
    # does not infer provenance from value equality.
    project_profile_declarations: dict[str, ProfileDeclaration] = field(default_factory=dict)
    config_path: Path | None = None
    config_revision: str = ""
    config_modification_time: str = ""
    config_loaded_at: str = ""
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    notifications: NotificationsConfig = field(default_factory=NotificationsConfig)
    langfuse: LangfuseConfig = field(default_factory=LangfuseConfig)
    retry_policies: dict[str, RetryPolicy] = field(default_factory=dict)
    breaker_failure_threshold: int = 3
    breaker_base_cooldown_s: int = 60
    breaker_max_cooldown_s: int = 900
    ask_timeout_s: int = DEFAULT_ASK_TIMEOUT_S
    envs: dict[str, dict[str, str]] = field(default_factory=dict, repr=False)

    @property
    def database_path(self) -> Path:
        return self.home / "refract.db"

    @property
    def revision(self) -> str:
        """The global source revision used by this catalog."""
        return self.config_revision



def refract_home() -> Path:
    override = os.environ.get("REFRACT_HOME", "").strip()
    return Path(override).expanduser() if override else Path.home() / ".refract"


def load_task_guide(
    home: Path,
    project_root: Path | None = None,
) -> dict[str, Any]:
    project_path = (
        project_root / ".refract" / "task_guide.json"
        if project_root is not None
        else None
    )
    legacy_project_path = (
        project_root / ".refract" / "task_routes.json"
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
        timeout_s = 0
    elif isinstance(raw, list):
        if not all(isinstance(value, str) for value in raw):
            raise ValueError(
                f"Profile {profile_id!r} workflow {workflow!r} targets "
                "must contain only strings"
            )
        selected = tuple(value.strip() for value in raw)
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
        if "max_attempts" in raw:
            # Accepted so older files still load; nothing reads the value.
            log.warning(
                "Deprecated profile workflow key max_attempts",
                extra={"event": "config.deprecated_key", "profile": profile_id, "workflow": workflow, "key": "max_attempts"},
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
        timeout_s = 0

    unknown_targets = set(selected) - target_by_id.keys()
    if not selected or unknown_targets or len(set(selected)) != len(selected):
        raise ValueError(
            f"Profile {profile_id!r} workflow {workflow!r} has invalid targets: "
            f"{sorted(unknown_targets)}"
        )
    return TargetSelection(targets=selected, timeout_s=timeout_s)


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


def _retry_policies(raw: Any) -> dict[str, RetryPolicy]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("[retryPolicies] must be a TOML table")
    policies: dict[str, RetryPolicy] = {}
    for policy_id, mapping in raw.items():
        if not isinstance(policy_id, str) or not policy_id.strip():
            raise ValueError("Invalid retry policy declaration")
        if not isinstance(mapping, dict):
            raise ValueError(f"Retry policy {policy_id!r} must be a TOML table")
        unknown = set(mapping) - {"retryAttempt", "errorCodes", "errorPatterns"}
        if unknown:
            raise ValueError(
                f"Retry policy {policy_id!r} has unsupported settings: {sorted(unknown)}"
            )
        raw_attempt = mapping.get("retryAttempt", 0)
        if (
            isinstance(raw_attempt, bool)
            or not isinstance(raw_attempt, int)
            or raw_attempt < 0
        ):
            raise ValueError(
                f"Retry policy {policy_id!r} retryAttempt must be a non-negative integer"
            )
        raw_codes = mapping.get("errorCodes", [])
        if not isinstance(raw_codes, list) or not all(
            isinstance(value, str) and value for value in raw_codes
        ):
            raise ValueError(
                f"Retry policy {policy_id!r} errorCodes must be a list of non-empty strings"
            )
        raw_patterns = mapping.get("errorPatterns", [])
        if not isinstance(raw_patterns, list) or not all(
            isinstance(value, str) and value for value in raw_patterns
        ):
            raise ValueError(
                f"Retry policy {policy_id!r} errorPatterns must be a list of non-empty strings"
            )
        policies[policy_id] = RetryPolicy(
            retry_attempt=raw_attempt,
            error_codes=tuple(raw_codes),
            error_patterns=tuple(raw_patterns),
        )
    return policies


def _validate_env_mapping(mapping: Any, *, context: str) -> dict[str, str]:
    if not isinstance(mapping, dict):
        raise ValueError(f"{context} must be a TOML table")
    result: dict[str, str] = {}
    for key, val in mapping.items():
        if not isinstance(key, str) or not key:
            raise ValueError(f"Environment key cannot be empty in {context}")
        if "=" in key:
            raise ValueError(f"Environment key cannot contain '=' in {context}")
        if "\x00" in key:
            raise ValueError(f"Environment key cannot contain NUL bytes in {context}")
        if key.startswith("REFRACT_ASK_"):
            raise ValueError(f"Environment keys cannot use protected prefix REFRACT_ASK_ in {context}")
        if isinstance(val, bool) or not isinstance(val, str):
            raise ValueError(f"Environment values must be strings in {context}")
        if "\x00" in val:
            raise ValueError(f"Environment values cannot contain NUL bytes in {context}")
        result[key] = val
    return result


def _envs(raw: Any) -> dict[str, dict[str, str]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("[envs] must be a TOML table")
    result: dict[str, dict[str, str]] = {}
    for name, mapping in raw.items():
        if not isinstance(name, str) or not name or "\x00" in name:
            raise ValueError("Invalid environment set declaration")
        if not isinstance(mapping, dict):
            raise ValueError(f"Environment set {name!r} must be a TOML table")
        result[name] = _validate_env_mapping(
            mapping, context=f"Environment set {name!r}"
        )
    return result


def _targets(
    raw: Any,
    retry_policies: dict[str, RetryPolicy] | None = None,
    envs: dict[str, dict[str, str]] | None = None,
) -> tuple[TargetConfig, ...]:
    if isinstance(raw, dict) and not raw:
        raise ValueError("[targets] must contain at least one target")
    if not isinstance(raw, list):
        raise ValueError("[targets] must be a TOML array of tables")
    if not raw:
        raise ValueError("[targets] must contain at least one target")
    available_policies = retry_policies or {}
    targets: list[TargetConfig] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Each target must be a TOML table")
        raw_target_id = item.get("id", "")
        raw_backend = item.get("backend", "")
        target_id = raw_target_id.strip() if isinstance(raw_target_id, str) else ""
        backend = raw_backend.strip() if isinstance(raw_backend, str) else ""
        if not target_id or backend not in {"agy", "codex", "pi", "claude"}:
            # Do not echo the complete declaration: it may contain prompts or
            # other operator-supplied sensitive values.
            raise ValueError("Invalid target declaration")
        if "retry" in item or "retryAttempt" in item or "retry_attempt" in item:
            raise ValueError(
                f"Target {target_id!r} cannot declare inline retry settings"
            )
        if "retry_policy" in item:
            raise ValueError(
                f"Target {target_id!r} has unsupported settings: ['retry_policy']"
            )
        raw_retry_policy = item.get("retryPolicy")
        if raw_retry_policy is not None:
            if not isinstance(raw_retry_policy, str) or not raw_retry_policy.strip():
                raise ValueError(
                    f"Target {target_id!r} retryPolicy must be a non-empty string"
                )
            retry_policy = raw_retry_policy.strip()
            if retry_policy not in available_policies:
                raise ValueError(
                    f"Target {target_id!r} references unknown retry policy: {retry_policy!r}"
                )
        else:
            retry_policy = ""
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
        raw_envs_vars = item.get("envs_vars", [])
        if not isinstance(raw_envs_vars, list) or not all(
            isinstance(value, str) for value in raw_envs_vars
        ):
            raise ValueError(
                f"Target {target_id!r} envs_vars must be a list of strings"
            )
        available_envs = envs or {}
        for var_set in raw_envs_vars:
            if var_set not in available_envs:
                raise ValueError(
                    f"Target {target_id!r} references unknown environment set: {var_set!r}"
                )
        envs_vars = tuple(raw_envs_vars)
        raw_envs = item.get("envs", {})
        if not isinstance(raw_envs, dict):
            raise ValueError(f"Target {target_id!r} envs must be a TOML table")
        target_envs = _validate_env_mapping(
            raw_envs, context=f"Target {target_id!r} envs"
        )
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
                retry_policy=retry_policy,
                envs_vars=envs_vars,
                envs=target_envs,
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
    raw_file = raw.get("file", "refract.log")
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


def _notifications_config(raw: Any) -> NotificationsConfig:
    if raw is None:
        return NotificationsConfig()
    if not isinstance(raw, dict):
        raise ValueError("[notifications] must be a TOML table")
    unknown = set(raw) - {"enabled"}
    if unknown:
        raise ValueError(f"Unsupported notifications settings: {sorted(unknown)}")
    if "enabled" in raw and not isinstance(raw["enabled"], bool):
        raise ValueError("notifications.enabled must be true or false")
    return NotificationsConfig(enabled=raw.get("enabled", False))


def _langfuse_config(raw: Any) -> LangfuseConfig:
    if raw is None:
        return LangfuseConfig()
    if not isinstance(raw, dict):
        raise ValueError("[langfuse] must be a TOML table")
    unknown = set(raw) - {
        "enabled",
        "base_url",
        "environment",
        "sample_rate",
    }
    if unknown:
        raise ValueError(f"Unsupported langfuse settings: {sorted(unknown)}")
    if "enabled" in raw and not isinstance(raw["enabled"], bool):
        raise ValueError("langfuse.enabled must be true or false")
    enabled = raw.get("enabled", False)

    base_url = raw.get("base_url", "http://localhost:3000")
    if not isinstance(base_url, str) or not base_url.strip():
        raise ValueError("langfuse.base_url must be an http or https URL")
    base_url = base_url.strip()
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("langfuse.base_url must be an http or https URL")

    environment = raw.get("environment", "")
    if not isinstance(environment, str):
        raise ValueError("langfuse.environment must be a string")

    raw_sample_rate = raw.get("sample_rate", 1.0)
    if isinstance(raw_sample_rate, bool) or not isinstance(raw_sample_rate, (int, float)):
        raise ValueError("langfuse.sample_rate must be a number between 0.0 and 1.0")
    sample_rate = float(raw_sample_rate)
    if not (0.0 <= sample_rate <= 1.0) or not math.isfinite(sample_rate):
        raise ValueError("langfuse.sample_rate must be between 0.0 and 1.0")

    return LangfuseConfig(
        enabled=enabled,
        base_url=base_url,
        environment=environment,
        sample_rate=sample_rate,
    )


def load_config(path: Path | None = None) -> DaemonConfig:
    home = refract_home()
    config_path = path or home / "config.toml"
    try:
        source = read_config_source(config_path)
    except FileNotFoundError as exc:
        raise ConfigurationLoadError(
            f"Missing config file: {config_path}", path=config_path
        ) from exc
    except OSError as exc:
        raise ConfigurationLoadError(
            f"Unable to read config file: {config_path}", path=config_path
        ) from exc
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


def _load_config_source(
    config_path: Path, home: Path, source: ConfigSource
) -> DaemonConfig:
    try:
        # Decode and parse the same buffer that was hashed above.
        raw = tomllib.loads(source.data.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ConfigurationLoadError(
            f"Invalid config file: {config_path}: invalid UTF-8",
            path=config_path,
            revision=source.revision,
            modification_time=source.modification_time,
            attempted_at=source.loaded_at,
        ) from exc
    except ValueError as exc:
        raise ConfigurationLoadError(
            str(exc),
            path=config_path,
            revision=source.revision,
            modification_time=source.modification_time,
            attempted_at=source.loaded_at,
        ) from exc
    try:
        return _load_config_values(config_path, home, raw, source)
    except ConfigurationLoadError:
        raise
    except ValueError as exc:
        raise ConfigurationLoadError(
            str(exc),
            path=config_path,
            revision=source.revision,
            modification_time=source.modification_time,
            attempted_at=source.loaded_at,
        ) from exc


def _load_config_values(
    config_path: Path, home: Path, raw: dict[str, Any], source: Any
) -> DaemonConfig:
    unsupported = set(raw) - {
        "daemon",
        "logging",
        "targets",
        "profiles",
        "notifications",
        "retryPolicies",
        "envs",
        "langfuse",
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
        "breaker_failure_threshold",
        "breaker_base_cooldown_s",
        "breaker_max_cooldown_s",
        "ask_timeout_s",
    }
    if unsupported_daemon:
        raise ValueError(f"Unsupported daemon settings: {sorted(unsupported_daemon)}")
    if "targets" not in raw:
        raise ValueError("Missing required [targets] section")
    if "profiles" not in raw:
        raise ValueError("Missing required [profiles] section")
    shared_envs = _envs(raw.get("envs"))
    retry_policies = _retry_policies(raw.get("retryPolicies"))
    targets = _targets(raw["targets"], retry_policies, shared_envs)
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
    port = _positive_int(daemon.get("port"), DEFAULT_PORT, "[daemon].port")
    if port > 65535:
        raise ValueError("[daemon].port must not exceed 65535")
    breaker_base = _positive_int(daemon.get("breaker_base_cooldown_s"), 60, "[daemon].breaker_base_cooldown_s")
    breaker_max = _positive_int(daemon.get("breaker_max_cooldown_s"), 900, "[daemon].breaker_max_cooldown_s")
    if breaker_max < breaker_base:
        raise ValueError("[daemon].breaker_max_cooldown_s must be >= breaker_base_cooldown_s")
    return DaemonConfig(
        home=home,
        config_path=config_path,
        config_revision=source.revision,
        config_modification_time=source.modification_time,
        config_loaded_at=source.loaded_at,
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
        notifications=_notifications_config(raw.get("notifications")),
        langfuse=_langfuse_config(raw.get("langfuse")),
        retry_policies=retry_policies,
        breaker_failure_threshold=_positive_int(daemon.get("breaker_failure_threshold"), 3, "[daemon].breaker_failure_threshold"),
        breaker_base_cooldown_s=breaker_base,
        breaker_max_cooldown_s=breaker_max,
        ask_timeout_s=_positive_int(daemon.get("ask_timeout_s"), DEFAULT_ASK_TIMEOUT_S, "[daemon].ask_timeout_s"),
        envs=shared_envs,
    )


def load_project_config(
    project_root: Path, base: DaemonConfig, data: bytes | None = None
) -> DaemonConfig:
    """Load a project overlay from disk, or from candidate bytes when given."""
    try:
        return _load_project_config_values(project_root, base, data)
    except ConfigurationLoadError:
        raise
    except ValueError as exc:
        path = project_root / ".refract" / "config.toml"
        raise ConfigurationLoadError(
            str(exc), path=path
        ) from exc


def _load_project_config_values(
    project_root: Path, base: DaemonConfig, data: bytes | None
) -> DaemonConfig:
    path = project_root / ".refract" / "config.toml"
    if data is None:
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            return base
    raw = tomllib.loads(data.decode("utf-8"))
    unsupported = set(raw) - {
        "project",
        "profiles",
        "envs",
        "targets",
    }
    if unsupported:
        raise ValueError(f"Unsupported project config sections: {sorted(unsupported)}")

    project = raw.get("project", {})
    if not isinstance(project, dict):
        raise ValueError("[project] must be a TOML table")
    unsupported_project = set(project) - {"default_profile"}
    if unsupported_project:
        raise ValueError(f"Unsupported project settings: {sorted(unsupported_project)}")

    if "envs" in raw:
        project_envs = _envs(raw["envs"])
        merged_envs: dict[str, dict[str, str]] = {
            k: dict(v) for k, v in base.envs.items()
        }
        for proj_set_name, proj_set_map in project_envs.items():
            if proj_set_name in merged_envs:
                merged_envs[proj_set_name].update(proj_set_map)
            else:
                merged_envs[proj_set_name] = dict(proj_set_map)
    else:
        merged_envs = {k: dict(v) for k, v in base.envs.items()}

    targets = [replace(t, envs=dict(t.envs)) for t in base.targets]
    target_by_id = {t.id: (i, t) for i, t in enumerate(base.targets)}
    if "targets" in raw:
        raw_targets = raw["targets"]
        if not isinstance(raw_targets, list):
            raise ValueError("[targets] must be a TOML array of tables")
        seen_target_ids: set[str] = set()
        for item in raw_targets:
            if not isinstance(item, dict):
                raise ValueError("Each target must be a TOML table")
            raw_target_id = item.get("id")
            if not isinstance(raw_target_id, str) or not raw_target_id.strip():
                raise ValueError("Target override must specify an id string")
            target_id = raw_target_id.strip()
            if target_id not in target_by_id:
                raise ValueError(f"Unknown project target override: {target_id!r}")
            if target_id in seen_target_ids:
                raise ValueError(f"Duplicate project target override: {target_id!r}")
            seen_target_ids.add(target_id)
            unsupported_fields = set(item) - {"id", "envs_vars", "envs"}
            if unsupported_fields:
                raise ValueError(
                    f"Project target override {target_id!r} has unsupported settings: {sorted(unsupported_fields)}"
                )
            idx, base_target = target_by_id[target_id]
            if "envs_vars" in item:
                raw_vars = item["envs_vars"]
                if not isinstance(raw_vars, list) or not all(
                    isinstance(v, str) for v in raw_vars
                ):
                    raise ValueError(
                        f"Target {target_id!r} envs_vars must be a list of strings"
                    )
                for var_set in raw_vars:
                    if var_set not in merged_envs:
                        raise ValueError(
                            f"Target {target_id!r} references unknown environment set: {var_set!r}"
                        )
                new_envs_vars = tuple(raw_vars)
            else:
                new_envs_vars = base_target.envs_vars
            if "envs" in item:
                raw_target_envs = item["envs"]
                if not isinstance(raw_target_envs, dict):
                    raise ValueError(f"Target {target_id!r} envs must be a TOML table")
                proj_local = _validate_env_mapping(
                    raw_target_envs, context=f"Target {target_id!r} envs"
                )
                new_envs = dict(base_target.envs)
                new_envs.update(proj_local)
            else:
                new_envs = dict(base_target.envs)
            targets[idx] = replace(
                base_target,
                envs_vars=new_envs_vars,
                envs=new_envs,
            )

    if "profiles" not in raw:
        profiles = {profile_id: dict(mapping) for profile_id, mapping in base.profiles.items()}
        profile_declarations = dict(base.profile_declarations)
        project_declarations = {}
    else:
        project_declarations = _profile_declarations(raw["profiles"], tuple(targets))
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
    return DaemonConfig(
        home=base.home,
        host=base.host,
        port=base.port,
        max_jobs=base.max_jobs,
        history_turns=base.history_turns,
        history_bytes=base.history_bytes,
        default_profile=default_profile,
        targets=tuple(targets),
        profiles=profiles,
        profile_declarations=profile_declarations,
        project_profile_declarations=project_declarations,
        config_path=base.config_path,
        config_revision=base.config_revision,
        config_modification_time=base.config_modification_time,
        config_loaded_at=base.config_loaded_at,
        logging=base.logging,
        notifications=base.notifications,
        langfuse=base.langfuse,
        retry_policies=base.retry_policies,
        breaker_failure_threshold=base.breaker_failure_threshold,
        breaker_base_cooldown_s=base.breaker_base_cooldown_s,
        breaker_max_cooldown_s=base.breaker_max_cooldown_s,
        ask_timeout_s=base.ask_timeout_s,
        envs=merged_envs,
    )


def _parse_env_template(template: str) -> tuple[list[tuple[bool, str]], set[str]]:
    """Parse an environment value template into chunks of (is_ref, value) and refs."""
    chunks: list[tuple[bool, str]] = []
    refs: set[str] = set()
    i = 0
    n = len(template)
    cur_literal: list[str] = []

    def flush_literal() -> None:
        if cur_literal:
            chunks.append((False, "".join(cur_literal)))
            cur_literal.clear()

    while i < n:
        if template[i:i + 2] == "$$":
            cur_literal.append("$")
            i += 2
        elif template[i:i + 2] == "${":
            close_idx = template.find("}", i + 2)
            if close_idx == -1:
                raise ValueError("Unterminated environment reference")
            ref_name = template[i + 2:close_idx]
            if not ref_name or not ref_name.strip():
                raise ValueError("Empty environment reference")
            if "=" in ref_name or "\x00" in ref_name:
                raise ValueError("Malformed environment reference")
            if ref_name.startswith("REFRACT_ASK_"):
                raise ValueError("Protected environment reference")
            flush_literal()
            chunks.append((True, ref_name))
            refs.add(ref_name)
            i = close_idx + 1
        elif template[i] == "$":
            cur_literal.append("$")
            i += 1
        else:
            cur_literal.append(template[i])
            i += 1

    flush_literal()
    return chunks, refs


def resolve_target_environment(
    catalog: DaemonConfig,
    target: TargetConfig | str,
    inherited: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Resolve configured environment overrides for a target iteratively."""
    if isinstance(target, str):
        target_obj: TargetConfig | None = None
        for t in catalog.targets:
            if t.id == target:
                target_obj = t
                break
        if target_obj is None:
            raise ValueError("Unknown target")
    else:
        target_obj = target

    inherited_map: Mapping[str, str] = os.environ if inherited is None else inherited

    # Merge configured namespace: selected shared sets in order, then target local envs
    configured_raw: dict[str, str] = {}
    for set_name in target_obj.envs_vars:
        if set_name in catalog.envs:
            configured_raw.update(catalog.envs[set_name])
    configured_raw.update(target_obj.envs)

    if not configured_raw:
        return {}

    parsed_chunks: dict[str, list[tuple[bool, str]]] = {}
    unresolved_deps: dict[str, set[str]] = {}
    dependents: dict[str, set[str]] = {k: set() for k in configured_raw}

    for key, raw_val in configured_raw.items():
        chunks, refs = _parse_env_template(raw_val)
        parsed_chunks[key] = chunks

        if key in refs:
            raise ValueError("Environment reference cycle detected")

        configured_deps: set[str] = set()
        for ref in refs:
            if ref in configured_raw:
                configured_deps.add(ref)
            elif ref in inherited_map:
                pass
            else:
                raise ValueError("Missing environment reference")

        unresolved_deps[key] = configured_deps
        for dep in configured_deps:
            dependents[dep].add(key)

    ready: list[str] = [k for k, deps in unresolved_deps.items() if not deps]
    resolved: dict[str, str] = {}

    while ready:
        curr = ready.pop()
        parts: list[str] = []
        for is_ref, val in parsed_chunks[curr]:
            if is_ref:
                if val in resolved:
                    parts.append(resolved[val])
                elif val in inherited_map:
                    parts.append(inherited_map[val])
                else:
                    raise ValueError("Missing environment reference")
            else:
                parts.append(val)
        resolved[curr] = "".join(parts)

        for dep_key in dependents[curr]:
            unresolved_deps[dep_key].discard(curr)
            if not unresolved_deps[dep_key]:
                ready.append(dep_key)

    if len(resolved) < len(configured_raw):
        raise ValueError("Environment reference cycle detected")

    return resolved


__all__ = [
    "DaemonConfig",
    "LangfuseConfig",
    "LoggingConfig",
    "NotificationsConfig",
    "ProfileDeclaration",
    "RetryPolicy",
    "TargetConfig",
    "TargetSelection",
    "_langfuse_config",
    "load_config",
    "load_project_config",
    "load_task_guide",
    "refract_home",
    "resolve_target_environment",
    "validate_target_args",
]
