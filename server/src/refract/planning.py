"""Immutable target plan for one submitted job."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

from refract.config import (
    DaemonConfig,
    RetryPolicy,
    TargetConfig,
    TargetSelection,
    validate_target_args,
)
from refract.drivers import DriverRegistry
from refract.workflows import get_workflow


def _target_identity_data(target: TargetConfig) -> dict[str, Any]:
    return {
        "id": target.id,
        "backend": target.backend,
        "model": target.model,
        "backend_profile": target.backend_profile,
        "reasoning": target.reasoning,
        "system_prompt": target.system_prompt,
        "args": list(target.args),
        "max_concurrency": target.max_concurrency,
    }


def _target_data(target: TargetConfig) -> dict[str, Any]:
    value = _target_identity_data(target)
    if target.retry != RetryPolicy():
        value["retry"] = {
            "attempts": target.retry.attempts,
            "codes": list(target.retry.codes),
            "patterns": list(target.retry.patterns),
        }
    if target.context_window is not None:
        value["context_window"] = target.context_window
    return value


def _selection_data(selection: TargetSelection) -> dict[str, Any]:
    return {
        "targets": list(selection.targets),
        "timeout_s": selection.timeout_s,
    }


def _parse_selection(value: Any) -> TargetSelection:
    if not isinstance(value, dict):
        raise ValueError("Execution plan selection must be a mapping")
    raw_targets = value.get("targets", [])
    if not isinstance(raw_targets, list):
        raise ValueError("Execution plan selection targets must be a list")
    if not all(isinstance(item, str) and item for item in raw_targets):
        raise ValueError("Execution plan target identifiers must be strings")
    target_ids = tuple(raw_targets)
    timeout_s = value.get("timeout_s", 0)
    if (
        not target_ids
        or len(set(target_ids)) != len(target_ids)
        or isinstance(timeout_s, bool)
        or not isinstance(timeout_s, int)
        or timeout_s < 0
    ):
        raise ValueError("Execution plan has an invalid target selection")
    return TargetSelection(target_ids, timeout_s)


def _parse_retry(raw: Any) -> RetryPolicy:
    if raw is None:
        return RetryPolicy()
    attempts = raw.get("attempts", 0) if isinstance(raw, dict) else None
    codes = raw.get("codes", []) if isinstance(raw, dict) else None
    patterns = raw.get("patterns", []) if isinstance(raw, dict) else None
    if (
        not isinstance(raw, dict)
        or set(raw) - {"attempts", "codes", "patterns"}
        or isinstance(attempts, bool)
        or not isinstance(attempts, int)
        or attempts < 0
        or not isinstance(codes, list)
        or not isinstance(patterns, list)
        or not all(isinstance(item, str) and item for item in [*codes, *patterns])
    ):
        raise ValueError("Execution plan target has invalid retry settings")
    return RetryPolicy(attempts, tuple(codes), tuple(patterns))


def _parse_context_window(value: Any) -> int | None:
    if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 1):
        raise ValueError
    return value


def _parse_targets(raw: Any) -> tuple[TargetConfig, ...]:
    if not isinstance(raw, list):
        raise ValueError("Execution plan targets must be a list")
    targets: list[TargetConfig] = []
    for value in raw:
        if not isinstance(value, dict):
            raise ValueError("Execution plan targets must contain mappings")
        try:
            target_id = value["id"]
            backend = value["backend"]
            args = value.get("args", [])
            max_concurrency = value.get("max_concurrency", 1)
            # Plans stored before isolated and read_only were removed must not
            # run without the restrictions they requested.
            if value.get("isolated") or value.get("read_only"):
                raise ValueError
            text_values = (
                value.get("model", ""),
                value.get("backend_profile", ""),
                value.get("reasoning", ""),
                value.get("system_prompt", ""),
            )
            retry = _parse_retry(value.get("retry"))
            context_window = _parse_context_window(value.get("context_window"))
            if (
                not isinstance(target_id, str)
                or not target_id
                or backend not in {"agy", "codex", "pi", "claude"}
                or not isinstance(args, list)
                or not all(isinstance(item, str) for item in args)
                or isinstance(max_concurrency, bool)
                or not isinstance(max_concurrency, int)
                or max_concurrency < 1
                or not all(isinstance(item, str) for item in text_values)
            ):
                raise ValueError
            validate_target_args(target_id, backend, tuple(args))
            targets.append(
                TargetConfig(
                    id=target_id,
                    backend=backend,
                    model=text_values[0],
                    backend_profile=text_values[1],
                    reasoning=text_values[2],
                    system_prompt=text_values[3],
                    args=tuple(args),
                    max_concurrency=max_concurrency,
                    context_window=context_window,
                    retry=retry,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Execution plan has an invalid target") from exc
    if len({target.id for target in targets}) != len(targets):
        raise ValueError("Execution plan target identifiers must be unique")
    return tuple(targets)


@dataclass(slots=True, frozen=True)
class ExecutionPlan:
    profile: str
    workflow: str
    selection: TargetSelection
    targets: tuple[TargetConfig, ...]
    environment_targets: tuple[str, ...] = ()

    def target(self, target_id: str) -> TargetConfig:
        return next(target for target in self.targets if target.id == target_id)


def execution_plan_data(plan: ExecutionPlan) -> dict[str, Any]:
    data: dict[str, Any] = {
        "profile": plan.profile,
        "workflow": plan.workflow,
        "selection": _selection_data(plan.selection),
        "targets": [_target_data(target) for target in plan.targets],
    }
    if plan.environment_targets:
        data["environment_targets"] = list(plan.environment_targets)
    return data


def parse_execution_plan(data: Any) -> ExecutionPlan:
    if not isinstance(data, dict):
        raise ValueError("Execution plan must be a mapping")
    if "selection" not in data:
        raise ValueError("Execution plan requires one workflow selection")
    workflow = get_workflow(str(data.get("workflow", "")))
    selection = _parse_selection(data["selection"])
    targets = _parse_targets(data.get("targets"))
    if set(selection.targets) - {target.id for target in targets}:
        raise ValueError("Execution plan references unknown targets")
    raw_environment_targets = data.get("environment_targets", [])
    if (
        not isinstance(raw_environment_targets, list)
        or not all(isinstance(value, str) and value for value in raw_environment_targets)
        or len(set(raw_environment_targets)) != len(raw_environment_targets)
        or set(raw_environment_targets) - {target.id for target in targets}
    ):
        raise ValueError("Execution plan has invalid environment metadata")
    return ExecutionPlan(
        str(data.get("profile", "")),
        workflow,
        selection,
        targets,
        tuple(raw_environment_targets),
    )


def resolve_execution_plan(
    workflow: str,
    config: DaemonConfig,
    profile: str,
) -> ExecutionPlan:
    mapping = config.profiles.get(profile)
    if mapping is None:
        raise ValueError(f"Unknown profile: {profile}")
    selection = mapping.get(workflow)
    if selection is None:
        raise ValueError(f"Profile {profile!r} does not map workflow {workflow!r}")
    target_by_id = {target.id: target for target in config.targets}
    targets = tuple(target_by_id[value] for value in selection.targets)
    return ExecutionPlan(
        profile,
        workflow,
        selection,
        targets,
        tuple(target.id for target in targets if target.env),
    )


def target_execution_key(target: TargetConfig) -> str:
    # Removed fields keep their former defaults so existing session keys stay stable.
    identity = {"isolated": False, "read_only": False, **_target_identity_data(target)}
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    return f"{target.id}:{hashlib.sha256(encoded).hexdigest()[:16]}"


__all__ = [
    "ExecutionPlan",
    "execution_plan_data",
    "parse_execution_plan",
    "resolve_execution_plan",
    "target_execution_key",
]
