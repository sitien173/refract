"""Immutable routing plans for submitted workflows."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from openmcp.config import DaemonConfig, RouteConfig, TargetConfig
from openmcp.workflows import WorkflowSpec


@dataclass(slots=True, frozen=True)
class ExecutionPlan:
    routing_profile: str
    role_routes: tuple[tuple[str, str], ...]
    routes: tuple[RouteConfig, ...]
    targets: tuple[TargetConfig, ...]

    def route_id(self, role: str) -> str:
        return dict(self.role_routes)[role]

    def route(self, role: str) -> RouteConfig:
        route_id = self.route_id(role)
        return next(route for route in self.routes if route.id == route_id)

    def target(self, target_id: str) -> TargetConfig:
        return next(target for target in self.targets if target.id == target_id)


def _target_data(target: TargetConfig) -> dict[str, Any]:
    value = asdict(target)
    value["capabilities"] = list(target.capabilities)
    value["args"] = list(target.args)
    return value


def execution_plan_data(plan: ExecutionPlan) -> dict[str, Any]:
    return {
        "routing_profile": plan.routing_profile,
        "role_routes": dict(plan.role_routes),
        "routes": [
            {
                **asdict(route),
                "requires": list(route.requires),
                "targets": list(route.targets),
            }
            for route in plan.routes
        ],
        "targets": [_target_data(target) for target in plan.targets],
    }


def parse_execution_plan(data: Any) -> ExecutionPlan:
    if not isinstance(data, dict):
        raise ValueError("Execution plan must be a mapping")
    raw_role_routes = data.get("role_routes")
    raw_routes = data.get("routes")
    raw_targets = data.get("targets")
    if not isinstance(raw_role_routes, dict):
        raise ValueError("Execution plan roles must be a mapping")
    if not isinstance(raw_routes, list) or not isinstance(raw_targets, list):
        raise ValueError("Execution plan routes and targets must be lists")
    routes = tuple(
        RouteConfig(
            id=str(value["id"]),
            requires=tuple(str(item) for item in value.get("requires", [])),
            targets=tuple(str(item) for item in value.get("targets", [])),
            max_attempts=int(value.get("max_attempts", 2)),
            timeout_s=int(value.get("timeout_s", 0)),
        )
        for value in raw_routes
        if isinstance(value, dict)
    )
    targets = tuple(
        TargetConfig(
            id=str(value["id"]),
            backend=str(value["backend"]),
            model=str(value.get("model", "")),
            profile=str(value.get("profile", "")),
            reasoning=str(value.get("reasoning", "")),
            system_prompt=str(value.get("system_prompt", "")),
            isolated=bool(value.get("isolated", False)),
            read_only=bool(value.get("read_only", False)),
            args=tuple(str(item) for item in value.get("args", [])),
            capabilities=tuple(str(item) for item in value.get("capabilities", [])),
            max_concurrency=int(value.get("max_concurrency", 1)),
            priority=int(value.get("priority", 100)),
        )
        for value in raw_targets
        if isinstance(value, dict)
    )
    role_routes = tuple(
        (str(role), str(route_id))
        for role, route_id in raw_role_routes.items()
    )
    route_ids = {route.id for route in routes}
    target_ids = {target.id for target in targets}
    if set(dict(role_routes).values()) - route_ids:
        raise ValueError("Execution plan references unknown routes")
    if any(set(route.targets) - target_ids for route in routes):
        raise ValueError("Execution plan references unknown targets")
    return ExecutionPlan(
        routing_profile=str(data.get("routing_profile", "")),
        role_routes=role_routes,
        routes=routes,
        targets=targets,
    )


def resolve_execution_plan(
    workflow: WorkflowSpec,
    config: DaemonConfig,
    routing_profile: str,
) -> ExecutionPlan:
    mapping = config.routing_profiles.get(routing_profile)
    if mapping is None:
        raise ValueError(f"Unknown routing profile: {routing_profile}")
    roles = {stage.route for stage in workflow.stages}
    missing = roles - mapping.keys()
    if missing:
        raise ValueError(
            f"Routing profile {routing_profile!r} does not map roles: {sorted(missing)}"
        )
    route_by_id = {route.id: route for route in config.routes}
    role_routes = tuple(sorted((role, mapping[role]) for role in roles))
    routes = tuple(
        route_by_id[route_id]
        for route_id in sorted({route_id for _, route_id in role_routes})
    )
    target_ids = {target_id for route in routes for target_id in route.targets}
    target_by_id = {target.id: target for target in config.targets}
    return ExecutionPlan(
        routing_profile=routing_profile,
        role_routes=role_routes,
        routes=routes,
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
