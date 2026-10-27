"""Immutable target plan for one submitted job."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, Mapping

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
        "isolated": target.isolated,
        "read_only": target.read_only,
        "args": list(target.args),
        "max_concurrency": target.max_concurrency,
    }


def _target_data(target: TargetConfig) -> dict[str, Any]:
    value = _target_identity_data(target)
    if target.retry_policy:
        value["retry_policy"] = target.retry_policy
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
            isolated = value.get("isolated", False)
            read_only = value.get("read_only", False)
            text_values = (
                value.get("model", ""),
                value.get("backend_profile", value.get("profile", "")),
                value.get("reasoning", ""),
                value.get("system_prompt", ""),
            )
            if (
                "retry" in value
                or "retryAttempt" in value
                or "retry_attempt" in value
            ):
                raise ValueError("Execution plan target cannot declare inline retry settings")
            if "retryPolicy" in value:
                raise ValueError("Execution plan target has unsupported settings")
            raw_retry_policy = value.get("retry_policy", "")
            if (
                not isinstance(target_id, str)
                or not target_id
                or backend not in {"agy", "codex", "pi", "claude"}
                or not isinstance(args, list)
                or not all(isinstance(item, str) for item in args)
                or isinstance(max_concurrency, bool)
                or not isinstance(max_concurrency, int)
                or max_concurrency < 1
                or not isinstance(isolated, bool)
                or not isinstance(read_only, bool)
                or not all(isinstance(item, str) for item in text_values)
                or not isinstance(raw_retry_policy, str)
            ):
                raise ValueError
            validate_target_args(
                target_id, backend, tuple(args), isolated=isolated
            )
            targets.append(
                TargetConfig(
                    id=target_id,
                    backend=backend,
                    model=text_values[0],
                    backend_profile=text_values[1],
                    reasoning=text_values[2],
                    system_prompt=text_values[3],
                    isolated=isolated,
                    read_only=read_only,
                    args=tuple(args),
                    max_concurrency=max_concurrency,
                    retry_policy=raw_retry_policy,
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
    retry_policies: Mapping[str, RetryPolicy] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "retry_policies",
            MappingProxyType(dict(self.retry_policies)),
        )

    def target(self, target_id: str) -> TargetConfig:
        return next(target for target in self.targets if target.id == target_id)

    def retry_policy(self, target_id: str) -> RetryPolicy:
        target = self.target(target_id)
        if not target.retry_policy:
            return RetryPolicy()
        if target.retry_policy not in self.retry_policies:
            raise ValueError(
                f"Execution plan target {target.id!r} references unknown retry policy: {target.retry_policy!r}"
            )
        return self.retry_policies[target.retry_policy]


def _retry_policy_data(policy: RetryPolicy) -> dict[str, Any]:
    return {
        "retry_attempt": policy.retry_attempt,
        "error_codes": list(policy.error_codes),
        "error_patterns": list(policy.error_patterns),
    }


def _parse_retry_policies(
    raw: Any, targets: tuple[TargetConfig, ...]
) -> dict[str, RetryPolicy]:
    if not isinstance(raw, dict):
        raise ValueError("Execution plan retry_policies must be a mapping")
    policies: dict[str, RetryPolicy] = {}
    allowed = {
        "retry_attempt",
        "error_codes",
        "error_patterns",
    }
    for name, val in raw.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError(
                "Execution plan retry policy name must be a non-empty string"
            )
        if not isinstance(val, dict):
            raise ValueError(
                f"Execution plan retry policy {name!r} must be a mapping"
            )
        unknown = set(val) - allowed
        if unknown:
            raise ValueError(
                f"Execution plan retry policy {name!r} has unsupported settings"
            )
        raw_attempt = val.get("retry_attempt", 0)
        if (
            isinstance(raw_attempt, bool)
            or not isinstance(raw_attempt, int)
            or raw_attempt < 0
        ):
            raise ValueError(
                f"Execution plan retry policy {name!r} retryAttempt must be a non-negative integer"
            )
        raw_codes = val.get("error_codes", [])
        if not isinstance(raw_codes, list) or not all(
            isinstance(x, str) and x for x in raw_codes
        ):
            raise ValueError(
                f"Execution plan retry policy {name!r} errorCodes must be a list of non-empty strings"
            )
        raw_patterns = val.get("error_patterns", [])
        if not isinstance(raw_patterns, list) or not all(
            isinstance(x, str) and x for x in raw_patterns
        ):
            raise ValueError(
                f"Execution plan retry policy {name!r} errorPatterns must be a list of non-empty strings"
            )
        policies[name] = RetryPolicy(
            retry_attempt=raw_attempt,
            error_codes=tuple(raw_codes),
            error_patterns=tuple(raw_patterns),
        )
    for target in targets:
        if target.retry_policy and target.retry_policy not in policies:
            raise ValueError(
                f"Execution plan target {target.id!r} references unknown retry policy: {target.retry_policy!r}"
            )
    return policies


def execution_plan_data(plan: ExecutionPlan) -> dict[str, Any]:
    data: dict[str, Any] = {
        "profile": plan.profile,
        "workflow": plan.workflow,
        "selection": _selection_data(plan.selection),
        "targets": [_target_data(target) for target in plan.targets],
    }
    if plan.retry_policies:
        data["retry_policies"] = {
            name: _retry_policy_data(policy)
            for name, policy in sorted(plan.retry_policies.items())
        }
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
    if "retry_policies" in data:
        raw_policies = data["retry_policies"]
        if not isinstance(raw_policies, dict):
            raise ValueError("Execution plan retry_policies must be a mapping")
    else:
        raw_policies = {}
    retry_policies = _parse_retry_policies(raw_policies, targets)
    return ExecutionPlan(
        str(data.get("profile", "")),
        workflow,
        selection,
        targets,
        retry_policies,
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
    retry_policies: dict[str, RetryPolicy] = {}
    for target in targets:
        if target.retry_policy:
            if target.retry_policy not in config.retry_policies:
                raise ValueError(
                    f"Profile target {target.id!r} references unknown retry policy: {target.retry_policy!r}"
                )
            retry_policies[target.retry_policy] = config.retry_policies[target.retry_policy]
    return ExecutionPlan(
        profile,
        workflow,
        selection,
        targets,
        retry_policies,
    )


def target_execution_key(target: TargetConfig) -> str:
    encoded = json.dumps(_target_identity_data(target), sort_keys=True, separators=(",", ":")).encode()
    return f"{target.id}:{hashlib.sha256(encoded).hexdigest()[:16]}"


def next_target_token(
    config_revision: str, project_id: str, profile: str, workflow: str, target: TargetConfig
) -> str:
    value = json.dumps(
        [config_revision, project_id, profile, workflow, target_execution_key(target)],
        separators=(",", ":"),
    )
    return "nt_" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def resolve_next_target(
    token: str, config_revision: str, project_id: str, plan: ExecutionPlan
) -> TargetConfig | None:
    for target in plan.targets:
        if token == next_target_token(config_revision, project_id, plan.profile, plan.workflow, target):
            return target
    return None


__all__ = [
    "ExecutionPlan",
    "execution_plan_data",
    "parse_execution_plan",
    "resolve_execution_plan",
    "target_execution_key",
    "next_target_token",
    "resolve_next_target",
]
