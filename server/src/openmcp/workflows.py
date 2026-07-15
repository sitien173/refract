"""Versioned workflow loading, validation, and prompt rendering."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml


_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_VARIABLE_RE = re.compile(r"\$\{([^}]+)\}")


@dataclass(slots=True, frozen=True)
class InputSpec:
    type: str = "string"
    required: bool = False


@dataclass(slots=True, frozen=True)
class StageSpec:
    id: str
    mode: str
    route: str
    prompt: str
    needs: tuple[str, ...] = ()
    context: str = ""
    fanout: int = 1
    timeout_s: int = 0


@dataclass(slots=True, frozen=True)
class WorkflowSpec:
    version: int
    name: str
    inputs: dict[str, InputSpec]
    stages: tuple[StageSpec, ...]
    digest: str


def _digest(data: dict[str, Any]) -> str:
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _builtin(name: str) -> WorkflowSpec | None:
    definitions = {
        "single-read": ("read", "forge", "worker"),
        "single-write": ("write", "forge", "worker"),
        "forge-read": ("read", "forge", "forge"),
        "forge-write": ("write", "forge", "forge"),
        "canvas-read": ("read", "canvas", "canvas"),
        "canvas-write": ("write", "canvas", "canvas"),
        "sage-read": ("read", "sage", "sage"),
        "sentinel-read": ("read", "sentinel", "sentinel"),
    }
    definition = definitions.get(name)
    if definition is None:
        return None
    mode, route, context = definition
    data = {
        "version": 1,
        "name": name,
        "inputs": {
            "prompt": {"type": "string", "required": True},
            "commit_message": {"type": "string", "required": False},
        },
        "stages": {
            "execute": {
                "mode": mode,
                "route": route,
                "context": context,
                "prompt": "${inputs.prompt}",
            }
        },
    }
    return parse_workflow(data, known_routes=None)


def _parse_inputs(raw: Any) -> dict[str, InputSpec]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("Workflow inputs must be a mapping")
    parsed: dict[str, InputSpec] = {}
    for name, definition in raw.items():
        if not _NAME_RE.fullmatch(str(name)) or not isinstance(definition, dict):
            raise ValueError(f"Invalid workflow input {name!r}")
        input_type = str(definition.get("type", "string"))
        if input_type not in {"string", "integer", "number", "boolean", "object", "array"}:
            raise ValueError(f"Unsupported input type {input_type!r}")
        parsed[str(name)] = InputSpec(
            type=input_type,
            required=bool(definition.get("required", False)),
        )
    return parsed


def _parse_stages(raw: Any) -> tuple[StageSpec, ...]:
    if not isinstance(raw, dict) or not raw:
        raise ValueError("Workflow stages must be a non-empty mapping")
    stages: list[StageSpec] = []
    for stage_id, definition in raw.items():
        stage_id = str(stage_id)
        if not _NAME_RE.fullmatch(stage_id) or not isinstance(definition, dict):
            raise ValueError(f"Invalid workflow stage {stage_id!r}")
        mode = str(definition.get("mode", "read"))
        route = str(definition.get("route", "default"))
        prompt = definition.get("prompt")
        needs = definition.get("needs", [])
        fanout = int(definition.get("fanout", 1))
        timeout_s = int(definition.get("timeout_s", 0))
        if mode not in {"read", "write"}:
            raise ValueError(f"Stage {stage_id!r} has invalid mode {mode!r}")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"Stage {stage_id!r} requires a prompt")
        if not isinstance(needs, list):
            raise ValueError(f"Stage {stage_id!r} needs must be a list")
        if fanout < 1 or fanout > 16:
            raise ValueError(f"Stage {stage_id!r} fanout must be between 1 and 16")
        if mode == "write" and fanout != 1:
            raise ValueError(f"Write stage {stage_id!r} cannot use fanout")
        stages.append(
            StageSpec(
                id=stage_id,
                mode=mode,
                route=route,
                prompt=prompt,
                needs=tuple(str(value) for value in needs),
                context=str(definition.get("context", stage_id)),
                fanout=fanout,
                timeout_s=max(0, timeout_s),
            )
        )
    return tuple(stages)


def _validate_graph(stages: tuple[StageSpec, ...]) -> None:
    by_id = {stage.id: stage for stage in stages}
    for stage in stages:
        unknown = set(stage.needs) - by_id.keys()
        if unknown:
            raise ValueError(f"Stage {stage.id!r} has unknown dependencies: {sorted(unknown)}")
        if stage.id in stage.needs:
            raise ValueError(f"Stage {stage.id!r} depends on itself")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(stage_id: str) -> None:
        if stage_id in visiting:
            raise ValueError("Workflow dependency graph contains a cycle")
        if stage_id in visited:
            return
        visiting.add(stage_id)
        for dependency in by_id[stage_id].needs:
            visit(dependency)
        visiting.remove(stage_id)
        visited.add(stage_id)

    for stage in stages:
        visit(stage.id)

    def depends_on(stage_id: str, dependency: str) -> bool:
        return any(
            value == dependency or depends_on(value, dependency)
            for value in by_id[stage_id].needs
        )

    writes = [stage.id for stage in stages if stage.mode == "write"]
    for index, left in enumerate(writes):
        for right in writes[index + 1:]:
            if not depends_on(left, right) and not depends_on(right, left):
                raise ValueError(f"Write stages {left!r} and {right!r} must be ordered")


def _validate_variables(workflow: WorkflowSpec) -> None:
    stage_ids = {stage.id for stage in workflow.stages}
    input_ids = set(workflow.inputs)
    for stage in workflow.stages:
        for variable in _VARIABLE_RE.findall(stage.prompt):
            parts = variable.split(".")
            valid = False
            if len(parts) == 2 and parts[0] == "inputs":
                valid = parts[1] in input_ids
            elif parts == ["project", "root"]:
                valid = True
            elif len(parts) == 3 and parts[0] == "stages":
                valid = parts[1] in stage_ids and parts[2] in {"text", "outputs", "commit"}
            if not valid:
                raise ValueError(f"Stage {stage.id!r} has unknown variable {variable!r}")


def parse_workflow(data: Any, known_routes: set[str] | None) -> WorkflowSpec:
    if not isinstance(data, dict):
        raise ValueError("Workflow document must be a mapping")
    version = int(data.get("version", 0))
    name = str(data.get("name", ""))
    if version != 1:
        raise ValueError(f"Unsupported workflow version {version!r}")
    if not _NAME_RE.fullmatch(name):
        raise ValueError(f"Invalid workflow name {name!r}")
    inputs = _parse_inputs(data.get("inputs"))
    stages = _parse_stages(data.get("stages"))
    _validate_graph(stages)
    if known_routes is not None:
        unknown_routes = {stage.route for stage in stages} - known_routes
        if unknown_routes:
            raise ValueError(f"Unknown workflow routes: {sorted(unknown_routes)}")
    canonical = {
        "version": version,
        "name": name,
        "inputs": {key: asdict(value) for key, value in inputs.items()},
        "stages": [asdict(stage) for stage in stages],
    }
    workflow = WorkflowSpec(
        version=version,
        name=name,
        inputs=inputs,
        stages=stages,
        digest=_digest(canonical),
    )
    _validate_variables(workflow)
    return workflow


def workflow_data(workflow: WorkflowSpec) -> dict[str, Any]:
    stages: dict[str, dict[str, Any]] = {}
    for stage in workflow.stages:
        value = {
            key: item
            for key, item in asdict(stage).items()
            if key != "id"
        }
        value["needs"] = list(stage.needs)
        stages[stage.id] = value
    return {
        "version": workflow.version,
        "name": workflow.name,
        "inputs": {key: asdict(value) for key, value in workflow.inputs.items()},
        "stages": stages,
    }


def load_workflow(project_root: Path, name: str, known_routes: set[str]) -> WorkflowSpec:
    builtin = _builtin(name)
    if builtin is not None:
        return parse_workflow(workflow_data(builtin), known_routes)
    if not _NAME_RE.fullmatch(name):
        raise ValueError(f"Invalid workflow name {name!r}")
    path = project_root / ".openmcp" / "workflows" / f"{name}.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Workflow {name!r} does not exist") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"Workflow {name!r} is invalid YAML: {exc}") from exc
    workflow = parse_workflow(data, known_routes)
    if workflow.name != name:
        raise ValueError(f"Workflow file name and workflow name differ: {name!r}")
    return workflow


def validate_inputs(workflow: WorkflowSpec, values: dict[str, Any]) -> None:
    unknown = set(values) - workflow.inputs.keys()
    missing = {name for name, spec in workflow.inputs.items() if spec.required and name not in values}
    if unknown:
        raise ValueError(f"Unknown workflow inputs: {sorted(unknown)}")
    if missing:
        raise ValueError(f"Missing workflow inputs: {sorted(missing)}")


def render_prompt(
    stage: StageSpec,
    *,
    inputs: dict[str, Any],
    project_root: Path,
    stage_results: dict[str, list[dict[str, Any]]],
) -> str:
    def replace(match: re.Match[str]) -> str:
        variable = match.group(1)
        parts = variable.split(".")
        if parts[0] == "inputs":
            value = inputs[parts[1]]
        elif parts == ["project", "root"]:
            value = project_root.as_posix()
        else:
            results = stage_results.get(parts[1], [])
            if parts[2] == "outputs":
                value = [result.get("text", "") for result in results]
            else:
                value = results[-1].get(parts[2], "") if results else ""
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False)

    return _VARIABLE_RE.sub(replace, stage.prompt)


__all__ = [
    "InputSpec",
    "StageSpec",
    "WorkflowSpec",
    "load_workflow",
    "parse_workflow",
    "render_prompt",
    "validate_inputs",
    "workflow_data",
]
