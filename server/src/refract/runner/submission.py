"""Admission: validate a request, plan it against the live catalog, and write the queued job row."""

from __future__ import annotations

import json
import math
import threading
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from refract.config.catalog import Catalog
from refract.config.inspection import sanitize_config_error
from refract.models import LIST_JOB_ID_ACTION, UNKNOWN_JOB_MESSAGE, OrchestrationError, ProjectView
from refract.runner.attempts import TargetExecutor
from refract.runner.planning import ExecutionPlan, execution_plan_data, resolve_execution_plan, target_execution_key
from refract.store.database import Database
from refract.workflows import get_workflow, validate_request

COPYABLE_STATES = frozenset({"succeeded", "failed", "cancelled", "interrupted"})


def validate_workflow_request(workflow_name: str, prompt: str) -> tuple[str, str]:
    try:
        workflow = get_workflow(workflow_name)
        return workflow, validate_request(workflow, prompt)
    except ValueError as exc:
        raise OrchestrationError(
            str(exc),
            code="invalid_request",
            next_action="Correct the workflow or prompt and call submit again.",
        ) from exc


def plan_error(exc: ValueError) -> OrchestrationError:
    code = "unknown_profile" if "Unknown profile" in str(exc) else "config_invalid"
    action = (
        "Call list and choose an available profile."
        if code == "unknown_profile"
        else "Fix the project configuration in .refract/config.toml."
    )
    return OrchestrationError(sanitize_config_error(exc), code=code, next_action=action)


class Admission:
    def __init__(
        self,
        database: Database,
        catalogs: Catalog,
        executor: TargetExecutor,
        lock: threading.RLock,
        is_closing: Callable[[], bool],
    ) -> None:
        self.database = database
        self.catalogs = catalogs
        self.executor = executor
        self.lock = lock
        self.is_closing = is_closing

    def prepare(self, job_id: str, project_id: str, workflow_name: str, prompt: str, **options: Any) -> tuple[ProjectView, str, str]:
        # One critical section from the closing check to the job row, so that
        # shutdown_if_idle can never latch between admission and create_job.
        with self.lock:
            return self.admit(job_id, project_id, workflow_name, prompt, **options)

    def admit(
        self, job_id: str, project_id: str, workflow_name: str, prompt: str, *,
        session: str = "", profile: str = "", fresh: bool = False, from_job: str = "", target: str = "", after: str = "",
    ) -> tuple[ProjectView, str, str]:
        if self.is_closing():
            raise OrchestrationError(
                "The daemon is stopping.",
                code="daemon_stopping",
                next_action="Wait, then call submit again.",
            )
        project = self.database.project(project_id)
        if project is None:
            raise OrchestrationError(
                "Project is not registered.",
                code="unknown_project",
                next_action="Call submit with a path inside a Git repository.",
            )
        workflow, resolved_prompt = validate_workflow_request(workflow_name, prompt)
        try:
            with self.lock:
                catalog = self.catalogs.project_catalog(Path(project.root), self.catalogs.reload_locked())
                selected_profile = profile.strip() or catalog.default_profile
                plan = resolve_execution_plan(workflow, catalog, selected_profile)
                if from_job:
                    plan = self._pin_target(plan, selected_profile, target, after)
                self.ensure_candidates_available(plan)
        except OrchestrationError:
            raise
        except ValueError as exc:
            raise plan_error(exc) from exc
        self.database.create_job(
            job_id=job_id,
            project_id=project.id,
            workflow=workflow,
            profile=selected_profile,
            prompt=resolved_prompt,
            plan_json=json.dumps(execution_plan_data(plan), ensure_ascii=False),
            session=session.strip() or workflow,
            fresh=fresh,
            from_job=from_job,
        )
        return project, workflow, selected_profile

    def prepare_from_job(self, new_id: str, job_id: str, project_id: str, target: str, fresh: bool | None) -> None:
        """Write a queued copy of a terminal job; only `target` and `fresh` may differ from the source."""
        job = self.database.job(job_id)
        if job is None or (project_id and job.project_id != project_id):
            raise OrchestrationError(UNKNOWN_JOB_MESSAGE, code="unknown_job", next_action=LIST_JOB_ID_ACTION)
        if job.state not in COPYABLE_STATES:
            raise OrchestrationError(
                f"Job cannot be copied from state {job.state}.",
                code="invalid_state",
                next_action="Call wait or submit a new job.",
            )
        record = self.database.job_record(job_id) or {}
        if record.get("content_pruned"):
            raise OrchestrationError(
                "The job's prompt was pruned and cannot be copied.",
                code="invalid_state",
                next_action="Call submit with a new prompt.",
            )
        self.prepare(
            new_id, job.project_id, job.workflow, str(record.get("prompt") or ""),
            session=job.session, profile=job.profile,
            fresh=bool(record.get("fresh", 0)) if fresh is None else fresh,
            from_job=job_id, target=target.strip(), after=job.target_id,
        )

    def _pin_target(self, plan: ExecutionPlan, selected_profile: str, target: str, after: str) -> ExecutionPlan:
        names = ", ".join(candidate.id for candidate in plan.targets)
        target_id = target
        if not target_id:
            ids = [candidate.id for candidate in plan.targets]
            following = plan.targets[ids.index(after) + 1:] if after in ids else plan.targets
            if not following:
                raise OrchestrationError(
                    "No target follows the job's target in profile order.",
                    code="targets_unavailable",
                    next_action=f"Call submit with from_job and target set to one of: {names}.",
                )
            self.ensure_candidates_available(replace(plan, targets=following))
            target_id = self.following_target(plan, after) or ""
        pinned = next((candidate for candidate in plan.targets if candidate.id == target_id), None)
        if pinned is None:
            raise OrchestrationError(
                f"Target {target_id!r} is not in profile {selected_profile}; profile targets: {names}.",
                code="invalid_request",
                next_action=f"Call submit with from_job and target set to one of: {names}.",
            )
        return replace(
            plan,
            selection=replace(plan.selection, targets=(pinned.id,)),
            targets=(pinned,),
            environment_targets=tuple(value for value in plan.environment_targets if value == pinned.id),
        )

    def following_target(self, plan: ExecutionPlan, after: str) -> str | None:
        """Return the next target after ``after`` in profile order whose circuit is closed."""
        ids = [target.id for target in plan.targets]
        start = ids.index(after) + 1 if after in ids else 0
        now = datetime.now(timezone.utc)
        for target in plan.targets[start:]:
            health = self.database.target_health(target_execution_key(target))
            if not self.executor.is_circuit_open(health.get("circuit_open_until", ""), now, health.get("probe_job_id", "")):
                return target.id
        return None

    def ensure_candidates_available(self, plan: ExecutionPlan) -> None:
        now = datetime.now(timezone.utc)
        opened = []
        for target in plan.targets:
            health = self.database.target_health(target_execution_key(target))
            if self.executor.is_circuit_open(health.get("circuit_open_until", ""), now, health.get("probe_job_id", "")):
                opened.append(health)
        if len(opened) != len(plan.targets):
            return
        cooldown = self.catalogs.current.breaker_base_cooldown_s
        delays = []
        for health in opened:
            until = health.get("circuit_open_until", "")
            try:
                delay = max(1, math.ceil((datetime.fromisoformat(until) - now).total_seconds())) if until and datetime.fromisoformat(until) > now else cooldown
            except ValueError:
                delay = cooldown
            delays.append(delay)
        raise OrchestrationError(
            "All candidate targets are temporarily unavailable.",
            code="targets_unavailable",
            next_action="Wait for a target to recover, then retry.",
            retry_after_s=min(delays),
        )
