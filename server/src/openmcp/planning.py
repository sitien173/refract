"""Immutable target plan for one submitted job."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from openmcp.config import DaemonConfig, TargetConfig, TargetSelection
from openmcp.workflows import WorkflowDefinition, get_workflow


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


def _parse_selection(value: Any) -> TargetSelection:
    if not isinstance(value, dict):
        raise ValueError("Execution plan selection must be a mapping")
    raw_targets = value.get("targets", [])
    if not isinstance(raw_targets, list):
        raise ValueError("Execution plan selection targets must be a list")
    target_ids = tuple(str(item) for item in raw_targets)
    max_attempts = int(value.get("max_attempts", len(target_ids)))
    timeout_s = int(value.get("timeout_s", 0))
    if not target_ids or max_attempts < 1 or timeout_s < 0:
        raise ValueError("Execution plan has an invalid target selection")
    return TargetSelection(target_ids, max_attempts, timeout_s)


def _parse_targets(raw: Any) -> tuple[TargetConfig, ...]:
    if not isinstance(raw, list):
        raise ValueError("Execution plan targets must be a list")
    targets: list[TargetConfig] = []
    for value in raw:
        if not isinstance(value, dict):
            raise ValueError("Execution plan targets must contain mappings")
        try:
            targets.append(
                TargetConfig(
                    id=str(value["id"]),
                    backend=str(value["backend"]),
                    model=str(value.get("model", "")),
                    backend_profile=str(value.get("backend_profile", value.get("profile", ""))),
                    reasoning=str(value.get("reasoning", "")),
                    system_prompt=str(value.get("system_prompt", "")),
                    isolated=bool(value.get("isolated", False)),
                    read_only=bool(value.get("read_only", False)),
                    args=tuple(str(item) for item in value.get("args", [])),
                    capabilities=tuple(str(item) for item in value.get("capabilities", [])),
                    max_concurrency=int(value.get("max_concurrency", 1)),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Execution plan has an invalid target") from exc
    return tuple(targets)


@dataclass(slots=True, frozen=True)
class ExecutionPlan:
    profile: str
    workflow: str
    selection: TargetSelection
    targets: tuple[TargetConfig, ...]

    def target(self, target_id: str) -> TargetConfig:
        return next(target for target in self.targets if target.id == target_id)


def execution_plan_data(plan: ExecutionPlan) -> dict[str, Any]:
    return {
        "profile": plan.profile,
        "workflow": plan.workflow,
        "selection": _selection_data(plan.selection),
        "targets": [_target_data(target) for target in plan.targets],
    }


def parse_execution_plan(data: Any) -> ExecutionPlan:
    if not isinstance(data, dict):
        raise ValueError("Execution plan must be a mapping")
    if "selection" not in data:
        raise ValueError("Execution plan requires one workflow selection")
    workflow = str(data.get("workflow", ""))
    get_workflow(workflow)
    selection = _parse_selection(data["selection"])
    targets = _parse_targets(data.get("targets"))
    if set(selection.targets) - {target.id for target in targets}:
        raise ValueError("Execution plan references unknown targets")
    return ExecutionPlan(str(data.get("profile", "")), workflow, selection, targets)


def resolve_execution_plan(
    workflow: WorkflowDefinition,
    config: DaemonConfig,
    profile: str,
) -> ExecutionPlan:
    mapping = config.profiles.get(profile)
    if mapping is None:
        raise ValueError(f"Unknown profile: {profile}")
    selection = mapping.get(workflow.name)
    if selection is None:
        raise ValueError(f"Profile {profile!r} does not map workflow {workflow.name!r}")
    target_by_id = {target.id: target for target in config.targets}
    return ExecutionPlan(
        profile,
        workflow.name,
        selection,
        tuple(target_by_id[value] for value in selection.targets),
    )


def target_execution_key(target: TargetConfig) -> str:
    encoded = json.dumps(_target_data(target), sort_keys=True, separators=(",", ":")).encode()
    return f"{target.id}:{hashlib.sha256(encoded).hexdigest()[:16]}"


__all__ = [
    "ExecutionPlan",
    "execution_plan_data",
    "parse_execution_plan",
    "resolve_execution_plan",
    "target_execution_key",
]
