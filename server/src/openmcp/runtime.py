"""Durable project orchestration runtime."""

from __future__ import annotations

import asyncio
import json
import random
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from openmcp.config import (
    DaemonConfig,
    RouteConfig,
    TargetConfig,
    load_config,
    load_project_config,
)
from openmcp.database import Database, utc_now
from openmcp.drivers import DriverRegistry, DriverResult
from openmcp.logging_setup import get_logger, log_context
from openmcp.models import (
    ActionResult,
    JobView,
    ModelTargetView,
    ProjectView,
    SubmissionResult,
)
from openmcp.overlays import (
    OverlayError,
    apply_overlays,
    capture_overlays,
    copy_overlays,
    discard_overlays,
    inherit_overlays,
    initialize_overlays,
    load_overlay_rules,
    preflight_overlays,
    rewind_overlays,
    restore_overlays,
    seal_overlays,
    validate_overlays,
)
from openmcp.planning import (
    ExecutionPlan,
    execution_plan_data,
    parse_execution_plan,
    resolve_execution_plan,
    target_execution_key,
)
from openmcp.workflows import (
    StageSpec,
    WorkflowSpec,
    load_workflow,
    parse_workflow,
    render_prompt,
    validate_inputs,
    workflow_data,
)
from openmcp.workspaces import WorkspaceError, WorkspaceManager, inspect_repository


log = get_logger("runtime")
_TERMINAL_STATES = {
    "succeeded",
    "failed",
    "cancelled",
    "interrupted",
    "integrated",
    "integration_conflict",
}
_LEGACY_ROLES = {
    "coding": "forge",
    "backend": "forge",
    "frontend": "canvas",
    "review": "sentinel",
    "reasoning": "sage",
}


class OrchestrationError(ValueError):
    pass


class Runtime:
    def __init__(self, config: DaemonConfig) -> None:
        self.config = config
        self.config.home.mkdir(parents=True, exist_ok=True)
        self.config.runs_path.mkdir(parents=True, exist_ok=True)
        self.database = Database(config.database_path)
        self.workspaces = WorkspaceManager(config.worktrees_path)
        self.drivers = DriverRegistry()
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._workers: list[asyncio.Task[None]] = []
        self._cancel_events: dict[str, threading.Event] = {}
        self._completion_events: dict[str, asyncio.Event] = {}
        self._target_semaphores: dict[str, asyncio.Semaphore] = {}
        self._target_active: dict[str, int] = {}
        self._catalog = config
        self._closing = False
        log.debug(
            "Runtime initialized",
            extra={
                "event": "runtime.initialized",
                "database": config.database_path.as_posix(),
                "max_jobs": config.max_jobs,
            },
        )

    async def start(self) -> None:
        self._closing = False
        log.info(
            "Starting scheduler",
            extra={"event": "scheduler.starting", "workers": self.config.max_jobs},
        )
        interrupted = self.database.interrupt_active_jobs()
        if interrupted:
            log.warning("Marked %d active records interrupted", len(interrupted))
        for job_id in set(interrupted) | set(self.database.terminal_job_ids()):
            record = self.database.job_record(job_id)
            if record is None:
                continue
            if record["state"] in {"failed", "cancelled", "interrupted"}:
                self.database.skip_unfinished_stages(job_id)
            if Path(record["worktree"]).exists():
                self._cleanup_terminal_workspace(job_id)
        self._workers = [
            asyncio.create_task(self._worker(), name=f"openmcp-worker-{index}")
            for index in range(self.config.max_jobs)
        ]
        queued = self.database.queued_job_ids()
        for job_id in queued:
            self._completion_events[job_id] = asyncio.Event()
            await self._queue.put(job_id)
        log.info(
            "Scheduler started",
            extra={
                "event": "scheduler.started",
                "workers": len(self._workers),
                "recovered_jobs": len(interrupted),
                "queued_jobs": len(queued),
            },
        )

    async def close(self) -> None:
        self._closing = True
        log.info(
            "Stopping scheduler",
            extra={"event": "scheduler.stopping", "active_jobs": len(self._cancel_events)},
        )
        for event in self._cancel_events.values():
            event.set()
        for _ in self._workers:
            await self._queue.put(None)
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self.database.close()
        log.info("Scheduler stopped", extra={"event": "scheduler.stopped"})

    def register_project(self, path: str, alias: str = "") -> ProjectView:
        try:
            state = inspect_repository(Path(path))
        except WorkspaceError as exc:
            raise OrchestrationError(str(exc)) from exc
        if not state.clean:
            raise OrchestrationError("Project worktree must be clean before registration")
        resolved_alias = alias.strip() or state.root.name
        if not resolved_alias:
            raise OrchestrationError("Project alias cannot be empty")
        try:
            project = self.database.upsert_project(
                project_id=str(uuid.uuid4()),
                alias=resolved_alias,
                root=state.root.as_posix(),
                head_commit=state.head,
                clean=state.clean,
            )
            log.info(
                "Project registered",
                extra={
                    "event": "project.registered",
                    "project_id": project.id,
                    "project_alias": project.alias,
                    "project_root": project.root,
                },
            )
            return project
        except sqlite3.IntegrityError as exc:
            raise OrchestrationError(
                f"Project alias already exists: {resolved_alias}"
            ) from exc


    async def submit(
        self,
        project_id: str,
        workflow_name: str,
        inputs: dict[str, Any],
        context_key: str = "",
        parent_job_id: str = "",
        routing_profile: str = "",
    ) -> SubmissionResult:
        project = self.database.project(project_id)
        if project is None:
            raise OrchestrationError(f"Unknown project: {project_id}")
        try:
            state = inspect_repository(Path(project.root))
        except WorkspaceError as exc:
            raise OrchestrationError(str(exc)) from exc
        if not state.clean:
            raise OrchestrationError("Project worktree must be clean before submission")
        self.database.upsert_project(
            project_id=project.id,
            alias=project.alias,
            root=state.root.as_posix(),
            head_commit=state.head,
            clean=True,
        )
        try:
            catalog = load_project_config(
                Path(project.root),
                self._reload_catalog(),
            )
        except ValueError as exc:
            raise OrchestrationError(str(exc)) from exc
        selected_profile = routing_profile.strip() or catalog.default_routing_profile
        workflow = load_workflow(Path(project.root), workflow_name)
        try:
            overlay_rules = load_overlay_rules(state.root, workflow.name)
        except OverlayError as exc:
            raise OrchestrationError(str(exc)) from exc
        try:
            execution_plan = resolve_execution_plan(
                workflow,
                catalog,
                selected_profile,
            )
        except ValueError as exc:
            raise OrchestrationError(str(exc)) from exc
        validate_inputs(workflow, inputs)
        base_commit = state.head
        integration_base = state.head
        if parent_job_id:
            parent = self.database.job(parent_job_id)
            if parent is None or parent.project_id != project.id:
                raise OrchestrationError(f"Unknown parent job: {parent_job_id}")
            if parent.state != "succeeded" or not parent.result.commit:
                raise OrchestrationError("Parent job must be successful")
            if state.head != parent.integration_base:
                raise OrchestrationError("Project HEAD changed after the parent job started")
            base_commit = parent.result.commit
            integration_base = parent.integration_base
        job_id = str(uuid.uuid4())
        try:
            worktree, branch = self.workspaces.create_job(
                state.root,
                job_id,
                base_commit,
            )
            overlay_root = self._overlay_root(job_id)
            initialize_overlays(
                state.root,
                worktree,
                overlay_root,
                overlay_rules,
            )
            if parent_job_id:
                inherit_overlays(
                    self._overlay_root(parent_job_id),
                    worktree,
                    overlay_root,
                )
            seal_overlays(overlay_root)
            self.database.create_job(
                job_id=job_id,
                project_id=project.id,
                workflow=workflow.name,
                routing_profile=selected_profile,
                workflow_json=json.dumps(workflow_data(workflow), ensure_ascii=False),
                execution_plan_json=json.dumps(
                    execution_plan_data(execution_plan),
                    ensure_ascii=False,
                ),
                result_stage=workflow.result_stage,
                inputs=inputs,
                context_key=context_key.strip() or workflow.name,
                parent_job_id=parent_job_id,
                base_commit=base_commit,
                integration_base=integration_base,
                branch=branch,
                worktree=worktree.as_posix(),
                stages=(
                    (stage.id, index, stage.mode)
                    for index, stage in enumerate(workflow.stages)
                ),
            )
        except Exception as exc:
            candidate = self.config.worktrees_path / job_id / "primary"
            self.workspaces.discard_job(
                state.root,
                candidate,
                f"openmcp/{job_id}",
            )
            if isinstance(exc, OverlayError):
                raise OrchestrationError(str(exc)) from exc
            raise
        self._completion_events[job_id] = asyncio.Event()
        await self._queue.put(job_id)
        log.info(
            "Job queued",
            extra={
                "event": "job.queued",
                "project_id": project.id,
                "job_id": job_id,
                "workflow": workflow.name,
                "routing_profile": selected_profile,
                "stage_count": len(workflow.stages),
                "parent_job_id": parent_job_id,
            },
        )
        return SubmissionResult(job_id=job_id, state="queued")

    async def wait(self, job_id: str, timeout_s: int = 0) -> JobView:
        job = self.database.job(job_id)
        if job is None:
            raise OrchestrationError(f"Unknown job: {job_id}")
        if job.state in _TERMINAL_STATES:
            return job
        event = self._completion_events.setdefault(job_id, asyncio.Event())
        try:
            if timeout_s > 0:
                await asyncio.wait_for(event.wait(), timeout_s)
            else:
                await event.wait()
        except TimeoutError:
            pass
        refreshed = self.database.job(job_id)
        if refreshed is None:
            raise OrchestrationError(f"Unknown job: {job_id}")
        return refreshed

    def cancel(self, job_id: str) -> ActionResult:
        job = self.database.job(job_id)
        if job is None:
            raise OrchestrationError(f"Unknown job: {job_id}")
        if job.state == "queued":
            self.database.set_job_state(job_id, "cancelled")
            self.database.skip_unfinished_stages(job_id)
            self._cleanup_terminal_workspace(job_id)
            self._signal_completion(job_id)
            log.info(
                "Queued job cancelled",
                extra={"event": "job.cancelled", "job_id": job_id},
            )
            return ActionResult(success=True, job_id=job_id, state="cancelled")
        if job.state != "running":
            return ActionResult(
                success=False,
                job_id=job_id,
                state=job.state,
                error=f"Job cannot be cancelled from {job.state}",
            )
        self._cancel_events.setdefault(job_id, threading.Event()).set()
        self.database.event(job_id, "job.cancellation_requested", {})
        log.info(
            "Job cancellation requested",
            extra={"event": "job.cancellation_requested", "job_id": job_id},
        )
        return ActionResult(success=True, job_id=job_id, state="running")

    async def retry(self, job_id: str, from_stage: str = "") -> SubmissionResult:
        job = self.database.job(job_id)
        record = self.database.job_record(job_id)
        if job is None or record is None:
            raise OrchestrationError(f"Unknown job: {job_id}")
        if job.state not in {"failed", "cancelled", "interrupted"}:
            raise OrchestrationError(f"Job cannot be retried from {job.state}")
        stages = self.database.stage_records(job_id)
        if not stages:
            raise OrchestrationError("Job has no persisted stages; cannot retry")
        workflow_document = json.loads(record["workflow_json"])
        if "result_stage" not in workflow_document and record["result_stage"]:
            workflow_document["result_stage"] = record["result_stage"]
        workflow = parse_workflow(workflow_document)
        selected = None
        if from_stage:
            selected = next((stage for stage in stages if stage["id"] == from_stage), None)
            if selected is None:
                raise OrchestrationError(f"Unknown stage: {from_stage}")
        else:
            selected = next(
                (
                    stage
                    for stage in stages
                    if stage["state"] in {"failed", "cancelled", "interrupted"}
                ),
                None,
            )
            selected = selected or next(
                (stage for stage in stages if stage["state"] != "succeeded"),
                None,
            )
            selected = selected or stages[-1]
        stage_by_id = {stage.id: stage for stage in workflow.stages}
        stage_states = {stage["id"]: stage["state"] for stage in stages}
        if set(stage_by_id) != set(stage_states):
            raise OrchestrationError(
                "Persisted job stages do not match its workflow; cannot retry"
            )
        selected_spec = stage_by_id[selected["id"]]
        blocked_dependencies = [
            dependency
            for dependency in selected_spec.needs
            if stage_states[dependency] != "succeeded"
        ]
        if blocked_dependencies:
            raise OrchestrationError(
                f"Retry stage {selected_spec.id!r} has unfinished dependencies: "
                f"{sorted(blocked_dependencies)}"
            )

        def depends_on(stage: StageSpec, dependency: str) -> bool:
            return dependency in stage.needs or any(
                depends_on(stage_by_id[value], dependency)
                for value in stage.needs
            )

        reset_ids = {
            stage.id
            for stage in workflow.stages
            if stage.id == selected_spec.id
            or depends_on(stage, selected_spec.id)
            or stage_states[stage.id] == "skipped"
        }
        project = self.database.project(job.project_id)
        if project is None:
            raise OrchestrationError(f"Unknown project: {job.project_id}")
        worktree = Path(record["worktree"])
        previous_overlay_stage = next(
            (
                stage
                for stage in reversed(stages)
                if stage["ordinal"] < selected["ordinal"]
                and stage["mode"] == "write"
                and stage["state"] == "succeeded"
            ),
            None,
        )
        try:
            self.workspaces.restore_job(Path(project.root), worktree, record["branch"])
            start_commit = selected["start_commit"] or record["base_commit"]
            patch_path = self.config.runs_path / job_id / f"retry-{utc_now().replace(':', '')}.patch"
            if self.workspaces.archive_patch(worktree, patch_path, start_commit):
                self.database.add_artifact(job_id, "retry_patch", patch_path.as_posix())
            self.workspaces.reset(worktree, start_commit)
            rewind_overlays(
                self._overlay_root(job_id),
                previous_overlay_stage["id"] if previous_overlay_stage else "",
            )
        except WorkspaceError as exc:
            raise OrchestrationError(str(exc)) from exc
        self.database.reset_retry(job_id, reset_ids)
        self._completion_events[job_id] = asyncio.Event()
        await self._queue.put(job_id)
        log.info(
            "Job queued for retry",
            extra={
                "event": "job.retried",
                "job_id": job_id,
                "from_stage": selected_spec.id,
                "reset_stages": sorted(reset_ids),
            },
        )
        return SubmissionResult(job_id=job_id, state="queued")

    def integrate(self, job_id: str) -> ActionResult:
        job = self.database.job(job_id)
        record = self.database.job_record(job_id)
        if job is None or record is None:
            raise OrchestrationError(f"Unknown job: {job_id}")
        if job.state not in {"succeeded", "integration_conflict"} or not job.result.commit:
            return ActionResult(
                success=False,
                job_id=job_id,
                state=job.state,
                error="Only successful jobs can be integrated",
            )
        if not any(stage.mode == "write" for stage in job.stages):
            return ActionResult(
                success=False,
                job_id=job_id,
                state=job.state,
                error="Read-only jobs do not require integration",
            )
        project = self.database.project(job.project_id)
        if project is None:
            raise OrchestrationError(f"Unknown project: {job.project_id}")
        try:
            preflight_overlays(
                Path(project.root),
                self._overlay_root(job_id),
            )
            self.workspaces.integrate(
                Path(project.root),
                job.integration_base,
                job.result.commit,
            )
            apply_overlays(
                Path(project.root),
                self._overlay_root(job_id),
            )
        except (OverlayError, WorkspaceError) as exc:
            self.database.set_job_state(job_id, "integration_conflict", error=str(exc))
            self._signal_completion(job_id)
            log.warning(
                "Job integration conflicted",
                extra={
                    "event": "job.integration_conflict",
                    "job_id": job_id,
                    "project_id": job.project_id,
                    "error": str(exc),
                },
            )
            return ActionResult(
                success=False,
                job_id=job_id,
                state="integration_conflict",
                error=str(exc),
            )
        updated = inspect_repository(Path(project.root))
        self.database.upsert_project(
            project_id=project.id,
            alias=project.alias,
            root=updated.root.as_posix(),
            head_commit=updated.head,
            clean=updated.clean,
        )
        current_id = job_id
        while current_id:
            current = self.database.job(current_id)
            current_record = self.database.job_record(current_id)
            if current is None or current_record is None:
                break
            if any(stage.mode == "write" for stage in current.stages):
                self.workspaces.cleanup_job(
                    Path(project.root),
                    Path(current_record["worktree"]),
                    current_record["branch"],
                )
                self.database.set_job_state(current_id, "integrated")
            current_id = current.parent_job_id
        self._signal_completion(job_id)
        log.info(
            "Job integrated",
            extra={
                "event": "job.integrated",
                "job_id": job_id,
                "project_id": job.project_id,
                "commit": job.result.commit,
            },
        )
        return ActionResult(success=True, job_id=job_id, state="integrated")

    @property
    def catalog(self) -> DaemonConfig:
        return self._catalog

    def catalog_for_project(self, project_id: str) -> DaemonConfig:
        project = self.database.project(project_id)
        if project is None:
            raise OrchestrationError(f"Unknown project: {project_id}")
        try:
            return load_project_config(
                Path(project.root),
                self._reload_catalog(),
            )
        except ValueError as exc:
            raise OrchestrationError(str(exc)) from exc

    def _reload_catalog(self) -> DaemonConfig:
        if self.config.config_path is None:
            return self._catalog
        catalog = load_config(self.config.config_path)
        self._catalog = catalog
        return catalog

    def _overlay_root(self, job_id: str) -> Path:
        return self.config.runs_path / job_id / "overlays"

    def _job_plan(
        self,
        job_id: str,
        record: dict[str, Any],
        workflow: WorkflowSpec,
    ) -> ExecutionPlan:
        if record["execution_plan_json"]:
            return parse_execution_plan(json.loads(record["execution_plan_json"]))
        catalog = self.catalog_for_project(record["project_id"])
        routing_profile = (
            record["routing_profile"] or catalog.default_routing_profile
        )
        try:
            plan = resolve_execution_plan(workflow, catalog, routing_profile)
        except ValueError as exc:
            raise OrchestrationError(str(exc)) from exc
        serialized = json.dumps(execution_plan_data(plan), ensure_ascii=False)
        self.database.set_execution_plan(job_id, routing_profile, serialized)
        record["routing_profile"] = routing_profile
        record["execution_plan_json"] = serialized
        return plan

    def _cleanup_terminal_workspace(self, job_id: str) -> None:
        record = self.database.job_record(job_id)
        if record is None or record["state"] not in _TERMINAL_STATES:
            return
        project = self.database.project(record["project_id"])
        if project is None:
            return
        stages = self.database.stage_records(job_id)
        has_write = any(stage["mode"] == "write" for stage in stages)
        worktree = Path(record["worktree"])
        repository = Path(project.root)
        if (
            worktree.exists()
            and has_write
            and record["state"] in {"failed", "cancelled", "interrupted"}
        ):
            try:
                discard_overlays(worktree, self._overlay_root(job_id))
                patch_path = self.config.runs_path / job_id / "terminal.patch"
                head = self.workspaces.head(worktree)
                if self.workspaces.archive_patch(worktree, patch_path, head):
                    self.database.add_artifact(
                        job_id,
                        "terminal_patch",
                        patch_path.as_posix(),
                    )
            except Exception as exc:
                log.warning("Patch archival failed for job %s: %s", job_id, exc)
                self.database.event(
                    job_id,
                    "job.cleanup_failed",
                    {"error": str(exc)},
                )
        try:
            if record["state"] == "succeeded" and not has_write:
                self.workspaces.discard_job(
                    repository,
                    worktree,
                    record["branch"],
                )
            else:
                self.workspaces.remove(repository, worktree)
        except Exception as exc:
            log.warning("Cleanup failed for job %s: %s", job_id, exc)
            self.database.event(job_id, "job.cleanup_failed", {"error": str(exc)})

    def targets(self) -> list[ModelTargetView]:
        now = datetime.now(timezone.utc)
        views: list[ModelTargetView] = []
        for target in self._catalog.targets:
            target_key = target_execution_key(target)
            health = self.database.target_health(target_key)
            open_until = str(health["circuit_open_until"])
            healthy = self.drivers.available(target) and not self._is_open(open_until, now)
            views.append(
                ModelTargetView(
                    id=target.id,
                    model=target.model,
                    capabilities=list(target.capabilities),
                    max_concurrency=target.max_concurrency,
                    active=self._target_active.get(target_key, 0),
                    healthy=healthy,
                    circuit_open_until=open_until,
                )
            )
        return views

    async def _worker(self) -> None:
        while True:
            job_id = await self._queue.get()
            try:
                if job_id is None:
                    return
                if self._closing:
                    continue
                record = self.database.job_record(job_id)
                if record is not None and record["state"] == "queued":
                    with log_context(
                        job_id=job_id,
                        project_id=record["project_id"],
                    ):
                        await self._run_job(job_id)
            except Exception as exc:
                log.exception("Unhandled scheduler failure for job %s", job_id)
                if job_id is not None:
                    self.database.set_job_state(job_id, "failed", error=f"scheduler: {exc}")
                    self.database.skip_unfinished_stages(job_id)
                    self._cleanup_terminal_workspace(job_id)
                    self._signal_completion(job_id)
            finally:
                self._queue.task_done()

    async def _run_job(self, job_id: str) -> None:
        started_at = time.monotonic()
        record = self.database.job_record(job_id)
        if record is None:
            return
        log.info(
            "Job started",
            extra={"event": "job.started", "workflow": record["workflow"]},
        )
        project = self.database.project(record["project_id"])
        if project is None:
            self.database.set_job_state(job_id, "failed", error="Project was removed")
            self._signal_completion(job_id)
            return
        worktree = Path(record["worktree"])
        cancel_event = threading.Event()
        self._cancel_events[job_id] = cancel_event
        self.database.set_job_state(job_id, "running")
        try:
            workflow_document = json.loads(record["workflow_json"])
            if "result_stage" not in workflow_document and record["result_stage"]:
                workflow_document["result_stage"] = record["result_stage"]
            for stage in workflow_document.get("stages", {}).values():
                if isinstance(stage, dict):
                    stage["route"] = _LEGACY_ROLES.get(
                        stage.get("route"),
                        stage.get("route"),
                    )
            workflow = parse_workflow(workflow_document)
            plan = self._job_plan(job_id, record, workflow)
            inputs = json.loads(record["inputs_json"])
            self.workspaces.restore_job(
                Path(project.root),
                worktree,
                record["branch"],
            )
            restore_overlays(worktree, self._overlay_root(job_id))
            while True:
                if cancel_event.is_set():
                    state = "interrupted" if self._closing else "cancelled"
                    self.database.set_job_state(job_id, state)
                    self.database.skip_unfinished_stages(job_id)
                    return
                stage_records = {value["id"]: value for value in self.database.stage_records(job_id)}
                remaining = [
                    stage
                    for stage in workflow.stages
                    if stage_records[stage.id]["state"] != "succeeded"
                ]
                if not remaining:
                    break
                ready = [
                    stage
                    for stage in remaining
                    if all(stage_records[dependency]["state"] == "succeeded" for dependency in stage.needs)
                ]
                if not ready:
                    raise OrchestrationError("Workflow has no runnable stages")
                readable = [stage for stage in ready if stage.mode == "read"]
                if readable:
                    results = await asyncio.gather(
                        *(
                            self._run_stage(
                                job_id,
                                project,
                                record,
                                plan,
                                inputs,
                                stage,
                                cancel_event,
                            )
                            for stage in readable
                        )
                    )
                    if not all(results):
                        self.database.skip_unfinished_stages(job_id)
                        return
                    continue
                if not await self._run_stage(
                    job_id,
                    project,
                    record,
                    plan,
                    inputs,
                    ready[0],
                    cancel_event,
                ):
                    self.database.skip_unfinished_stages(job_id)
                    return
            result_commit = self.workspaces.head(worktree)
            self.database.set_job_commit(job_id, result_commit)
            self.database.set_job_state(job_id, "succeeded")
        except Exception as exc:
            log.exception("Job %s failed", job_id)
            for stage_record in self.database.stage_records(job_id):
                if stage_record["state"] == "running":
                    self.database.set_stage_state(
                        job_id,
                        stage_record["id"],
                        "failed",
                        error=str(exc),
                    )
            self.database.set_job_state(job_id, "failed", error=str(exc))
            self.database.skip_unfinished_stages(job_id)
        finally:
            self._cancel_events.pop(job_id, None)
            self._cleanup_terminal_workspace(job_id)
            self._signal_completion(job_id)
            completed = self.database.job_record(job_id)
            log.info(
                "Job finished",
                extra={
                    "event": "job.finished",
                    "state": completed["state"] if completed else "unknown",
                    "duration_ms": round((time.monotonic() - started_at) * 1000, 2),
                },
            )

    async def _run_stage(
        self,
        job_id: str,
        project: ProjectView,
        job: dict[str, Any],
        plan: ExecutionPlan,
        inputs: dict[str, Any],
        stage: StageSpec,
        cancel_event: threading.Event,
    ) -> bool:
        records = self.database.stage_records(job_id)
        prior_results = {
            record["id"]: json.loads(record["outputs_json"])
            for record in records
            if record["state"] == "succeeded"
        }
        primary = Path(job["worktree"])
        prompt = render_prompt(
            stage,
            inputs=inputs,
            project_root=primary,
            stage_results=prior_results,
        )
        start_commit = self.workspaces.head(primary)
        self.database.set_stage_state(
            job_id,
            stage.id,
            "running",
            start_commit=start_commit,
        )
        stage_started_at = time.monotonic()
        log.info(
            "Stage started",
            extra={
                "event": "stage.started",
                "stage_id": stage.id,
                "stage_mode": stage.mode,
                "fanout": stage.fanout,
            },
        )

        async def run_worker(worker: int) -> dict[str, Any]:
            reader: Path | None = None
            try:
                if stage.mode == "read":
                    reader = self.workspaces.create_reader(
                        Path(project.root),
                        job_id,
                        stage.id,
                        worker,
                        start_commit,
                    )
                    copy_overlays(
                        primary,
                        reader,
                        self._overlay_root(job_id),
                    )
                    cwd = reader
                else:
                    cwd = primary
                result, target_id = await self._execute_with_route(
                    job_id=job_id,
                    project=project,
                    context_key=job["context_key"],
                    plan=plan,
                    stage=stage,
                    prompt=prompt,
                    cwd=cwd,
                    cancel_event=cancel_event,
                    lane=str(worker) if stage.fanout > 1 else "",
                )
                return {
                    "outcome": result.outcome,
                    "text": result.text,
                    "error": result.error,
                    "target_id": target_id,
                    "session_id": result.session_id,
                }
            except Exception as exc:
                return {
                    "outcome": "TARGET_FATAL",
                    "text": "",
                    "error": str(exc),
                    "target_id": "",
                    "session_id": "",
                }
            finally:
                if reader is not None:
                    self.workspaces.remove(Path(project.root), reader)

        outputs = await asyncio.gather(*(run_worker(index) for index in range(stage.fanout)))
        target_ids = ",".join(output["target_id"] for output in outputs)
        errors = [output["error"] for output in outputs if output["outcome"] != "SUCCESS"]
        if errors:
            if stage.mode == "write":
                discard_overlays(primary, self._overlay_root(job_id))
                patch_path = self.config.runs_path / job_id / f"{stage.id}-failed.patch"
                if self.workspaces.archive_patch(primary, patch_path, start_commit):
                    self.database.add_artifact(job_id, "failed_patch", patch_path.as_posix())
                self.workspaces.reset(primary, start_commit)
            state = (
                "interrupted"
                if cancel_event.is_set() and self._closing
                else "cancelled"
                if cancel_event.is_set()
                else "failed"
            )
            error = "\n".join(errors)
            self.database.set_stage_state(
                job_id,
                stage.id,
                state,
                target_id=target_ids,
                outputs=outputs,
                error=error,
            )
            self.database.set_job_state(job_id, state, error=error)
            log.warning(
                "Stage finished unsuccessfully",
                extra={
                    "event": "stage.finished",
                    "stage_id": stage.id,
                    "state": state,
                    "target_ids": target_ids,
                    "duration_ms": round((time.monotonic() - stage_started_at) * 1000, 2),
                },
            )
            return False

        commit = start_commit
        if stage.mode == "write":
            validate_overlays(primary, self._overlay_root(job_id))
            message = str(inputs.get("commit_message", "")).strip()
            commit = self.workspaces.commit(
                primary,
                job_id,
                stage.id,
                message=message,
            )
            capture_overlays(
                primary,
                self._overlay_root(job_id),
                stage.id,
            )
        text = "\n\n".join(output["text"] for output in outputs)
        transcript = self.config.runs_path / job_id / f"{stage.id}.txt"
        transcript.parent.mkdir(parents=True, exist_ok=True)
        transcript.write_text(text, encoding="utf-8")
        self.database.add_artifact(job_id, "transcript", transcript.as_posix())
        for output in outputs:
            output["commit"] = commit
        self.database.set_stage_state(
            job_id,
            stage.id,
            "succeeded",
            target_id=target_ids,
            text=text,
            outputs=outputs,
            error="",
            commit=commit,
        )
        log.info(
            "Stage succeeded",
            extra={
                "event": "stage.finished",
                "stage_id": stage.id,
                "state": "succeeded",
                "target_ids": target_ids,
                "duration_ms": round((time.monotonic() - stage_started_at) * 1000, 2),
            },
        )
        return True

    async def _execute_with_route(
        self,
        *,
        job_id: str,
        project: ProjectView,
        context_key: str,
        plan: ExecutionPlan,
        stage: StageSpec,
        prompt: str,
        cwd: Path,
        cancel_event: threading.Event,
        lane: str,
    ) -> tuple[DriverResult, str]:
        route = plan.route(stage.route)
        attempted: set[str] = set()
        last_target_id = ""
        last = DriverResult("TARGET_FATAL", "", "", "No healthy target", "no_target")
        for attempt in range(route.max_attempts):
            target = self._select_target(route, plan, attempted)
            if target is None:
                break
            attempted.add(target.id)
            last_target_id = target.id
            target_key = target_execution_key(target)
            session_id = self.database.session(
                project.id,
                context_key,
                stage.context,
                target_key,
                lane,
            )
            effective_prompt = prompt if session_id else self._with_history(
                project.id,
                context_key,
                stage.context,
                prompt,
            )
            self.database.event(
                job_id,
                "target.selected",
                {"stage": stage.id, "target": target.id, "attempt": attempt + 1},
            )
            semaphore = self._target_semaphores.setdefault(
                target_key,
                asyncio.Semaphore(target.max_concurrency),
            )
            self._target_active.setdefault(target_key, 0)
            attempt_started_at = time.monotonic()
            log.info(
                "Target attempt started",
                extra={
                    "event": "target.attempt_started",
                    "stage_id": stage.id,
                    "target_id": target.id,
                    "route": route.id,
                    "attempt": attempt + 1,
                    "timeout_s": stage.timeout_s or route.timeout_s,
                    "resumed_session": bool(session_id),
                },
            )
            async with semaphore:
                self._target_active[target_key] += 1
                try:
                    self.database.set_stage_state(
                        job_id,
                        stage.id,
                        "running",
                        target_id=target.id,
                        increment_attempts=True,
                    )
                    with log_context(stage_id=stage.id, target_id=target.id):
                        last = await self.drivers.execute(
                            target=target,
                            prompt=effective_prompt,
                            cwd=cwd,
                            session_id=session_id,
                            timeout_s=stage.timeout_s or route.timeout_s,
                            cancel_event=cancel_event,
                        )
                finally:
                    self._target_active[target_key] -= 1
            log.info(
                "Target attempt finished",
                extra={
                    "event": "target.attempt_finished",
                    "stage_id": stage.id,
                    "target_id": target.id,
                    "attempt": attempt + 1,
                    "outcome": last.outcome,
                    "error_code": last.error_code,
                    "duration_ms": round((time.monotonic() - attempt_started_at) * 1000, 2),
                },
            )
            if last.outcome == "SUCCESS":
                self.database.record_target_success(target_key)
                self.database.append_turn(
                    project_id=project.id,
                    context_key=context_key,
                    role=stage.context,
                    target_id=target.id,
                    target_key=target_key,
                    lane=lane,
                    session_id=last.session_id,
                    prompt=prompt,
                    response=last.text,
                )
                return last, target.id
            if last.outcome in {"CANCELLED", "REQUEST_FATAL"}:
                return last, target.id
            health = self.database.target_health(target_key)
            circuit_open_until = ""
            if int(health["consecutive_failures"]) + 1 >= 3:
                circuit_open_until = (
                    datetime.now(timezone.utc) + timedelta(seconds=60)
                ).isoformat()
            failures = self.database.record_target_failure(
                target_key,
                circuit_open_until,
            )
            if circuit_open_until:
                log.warning(
                    "Target circuit opened",
                    extra={
                        "event": "target.circuit_opened",
                        "stage_id": stage.id,
                        "target_id": target.id,
                        "consecutive_failures": failures,
                        "circuit_open_until": circuit_open_until,
                    },
                )
            if attempt + 1 < route.max_attempts:
                delay = min(8.0, 2.0**attempt) * random.uniform(0.8, 1.2)
                log.info(
                    "Retrying stage with another target",
                    extra={
                        "event": "target.retry_scheduled",
                        "stage_id": stage.id,
                        "target_id": target.id,
                        "delay_s": round(delay, 3),
                    },
                )
                await asyncio.sleep(delay)
        return last, last_target_id

    def _select_target(
        self,
        route: RouteConfig,
        plan: ExecutionPlan,
        attempted: set[str],
    ) -> TargetConfig | None:
        now = datetime.now(timezone.utc)
        candidates: list[tuple[float, int, int, TargetConfig]] = []
        for order, target_id in enumerate(route.targets):
            target = plan.target(target_id)
            if target.id in attempted:
                continue
            if not set(route.requires).issubset(target.capabilities):
                continue
            target_key = target_execution_key(target)
            health = self.database.target_health(target_key)
            if self._is_open(str(health["circuit_open_until"]), now):
                continue
            if not self.drivers.available(target):
                continue
            load = self._target_active.get(target_key, 0) / target.max_concurrency
            candidates.append((load, target.priority, order, target))
        return min(candidates, default=(0, 0, 0, None), key=lambda value: value[:3])[3]

    @staticmethod
    def _is_open(value: str, now: datetime) -> bool:
        if not value:
            return False
        try:
            return datetime.fromisoformat(value) > now
        except ValueError:
            return False

    def _with_history(self, project_id: str, context_key: str, role: str, prompt: str) -> str:
        turns = self.database.recent_turns(
            project_id,
            context_key,
            role,
            self.config.history_turns,
        )
        if not turns:
            return prompt
        blocks: list[str] = []
        size = 0
        for turn in reversed(turns):
            block = f"User:\n{turn['prompt']}\n\nAssistant:\n{turn['response']}"
            encoded = len(block.encode("utf-8"))
            if size + encoded > self.config.history_bytes:
                break
            blocks.append(block)
            size += encoded
        blocks.reverse()
        history = "\n\n---\n\n".join(blocks)
        return f"Previous context:\n\n{history}\n\nCurrent request:\n\n{prompt}"

    def _signal_completion(self, job_id: str) -> None:
        self._completion_events.setdefault(job_id, asyncio.Event()).set()


__all__ = ["Runtime", "OrchestrationError"]
