"""Immutable execution plans for submitted workflows."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from openmcp.config import DaemonConfig, TargetConfig, TargetSelection
from openmcp.workflows import WorkflowSpec


@dataclass(slots=True, frozen=True)
class ExecutionPlan:
    profile: str
    workflow_targets: tuple[tuple[str, TargetSelection], ...]
    targets: tuple[TargetConfig, ...]

    def selection(self, workflow: str) -> TargetSelection:
        return dict(self.workflow_targets)[workflow]

    def target(self, target_id: str) -> TargetConfig:
        return next(target for target in self.targets if target.id == target_id)


def _target_data(target: TargetConfig) -> dict[str, Any]:
    value = asdict(target)
    value["capabilities"] = list(target.capabilities)
    value["args"] = list(target.args)
    return value


def _selection_data(selection: TargetSelection) -> dict[str, Any]:
    return {
        "targets": list(selection.targets),
        "max_attempts": selection.max_attempts,
        "timeout_s": selection.timeout_s,
    }


def execution_plan_data(plan: ExecutionPlan) -> dict[str, Any]:
    return {
        "profile": plan.profile,
        "workflows": {
            workflow: _selection_data(selection)
            for workflow, selection in plan.workflow_targets
        },
        "targets": [_target_data(target) for target in plan.targets],
    }


def _parse_selection(value: Any) -> TargetSelection:
    if isinstance(value, str):
        target_ids = (value,)
        max_attempts = 1
        timeout_s = 0
    elif isinstance(value, list):
        target_ids = tuple(str(item) for item in value)
        max_attempts = len(target_ids)
        timeout_s = 0
    elif isinstance(value, dict):
        raw_targets = value.get("targets", [])
        if isinstance(raw_targets, str):
            target_ids = (raw_targets,)
        elif isinstance(raw_targets, list):
            target_ids = tuple(str(item) for item in raw_targets)
        else:
            target_ids = ()
        max_attempts = int(value.get("max_attempts", len(target_ids)))
        timeout_s = int(value.get("timeout_s", 0))
    else:
        target_ids = ()
        max_attempts = 0
        timeout_s = 0
    if not target_ids or max_attempts < 1 or timeout_s < 0:
        raise ValueError("Execution plan has an invalid workflow target selection")
    return TargetSelection(
        targets=target_ids,
        max_attempts=max_attempts,
        timeout_s=timeout_s,
    )


def _legacy_workflow_targets(data: dict[str, Any]) -> dict[str, TargetSelection]:
    mapping = data.get("role_routes")
    groups = data.get("routes")
    if not isinstance(mapping, dict) or not isinstance(groups, list):
        raise ValueError("Execution plan workflows must be a mapping")
    by_id: dict[str, TargetSelection] = {}
    for value in groups:
        if not isinstance(value, dict):
            continue
        target_ids = tuple(str(item) for item in value.get("targets", []))
        by_id[str(value["id"])] = TargetSelection(
            targets=target_ids,
            max_attempts=int(value.get("max_attempts", 2)),
            timeout_s=int(value.get("timeout_s", 0)),
        )
    try:
        return {
            str(workflow): by_id[str(group_id)]
            for workflow, group_id in mapping.items()
        }
    except KeyError as exc:
        raise ValueError("Execution plan references an unknown legacy route") from exc


def parse_execution_plan(data: Any) -> ExecutionPlan:
    if not isinstance(data, dict):
        raise ValueError("Execution plan must be a mapping")
    raw_targets = data.get("targets")
    if not isinstance(raw_targets, list):
        raise ValueError("Execution plan targets must be a list")
    targets = tuple(
        TargetConfig(
            id=str(value["id"]),
            backend=str(value["backend"]),
            model=str(value.get("model", "")),
            backend_profile=str(
                value.get("backend_profile", value.get("profile", ""))
            ),
            reasoning=str(value.get("reasoning", "")),
            system_prompt=str(value.get("system_prompt", "")),
            isolated=bool(value.get("isolated", False)),
            read_only=bool(value.get("read_only", False)),
            args=tuple(str(item) for item in value.get("args", [])),
            capabilities=tuple(str(item) for item in value.get("capabilities", [])),
            max_concurrency=int(value.get("max_concurrency", 1)),
        )
        for value in raw_targets
        if isinstance(value, dict)
    )
    raw_workflows = data.get("workflows")
    if isinstance(raw_workflows, dict):
        workflows = {
            str(workflow): _parse_selection(value)
            for workflow, value in raw_workflows.items()
        }
    else:
        workflows = _legacy_workflow_targets(data)
    target_ids = {target.id for target in targets}
    if any(set(selection.targets) - target_ids for selection in workflows.values()):
        raise ValueError("Execution plan references unknown targets")
    return ExecutionPlan(
        profile=str(data.get("profile", data.get("routing_profile", ""))),
        workflow_targets=tuple(workflows.items()),
        targets=targets,
    )


def resolve_execution_plan(
    workflow: WorkflowSpec,
    config: DaemonConfig,
    profile: str,
) -> ExecutionPlan:
    mapping = config.profiles.get(profile)
    if mapping is None:
        raise ValueError(f"Unknown profile: {profile}")
    workflow_names = {stage.role for stage in workflow.stages}
    missing = workflow_names - mapping.keys()
    if missing:
        raise ValueError(
            f"Profile {profile!r} does not map workflows: {sorted(missing)}"
        )
    workflow_targets = tuple(
        sorted((name, mapping[name]) for name in workflow_names)
    )
    target_ids = {
        target_id
        for _, selection in workflow_targets
        for target_id in selection.targets
    }
    target_by_id = {target.id: target for target in config.targets}
    return ExecutionPlan(
        profile=profile,
        workflow_targets=workflow_targets,
        targets=tuple(target_by_id[target_id] for target_id in sorted(target_ids)),
    )


def target_execution_key(target: TargetConfig) -> str:
    data = _target_data(target)
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return f"{target.id}:{hashlib.sha256(encoded).hexdigest()[:16]}"


__all__ = [
    "ExecutionPlan",
    "execution_plan_data",
    "parse_execution_plan",
    "resolve_execution_plan",
    "target_execution_key",
]
