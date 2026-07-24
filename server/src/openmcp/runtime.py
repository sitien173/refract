"""Public facade for durable direct-directory jobs."""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

from openmcp.config import DaemonConfig, load_config, load_project_config
from openmcp.database import Database
from openmcp.drivers import DriverRegistry
from openmcp.execution import JobRunner, TargetExecutor
from openmcp.logging_setup import get_logger
from openmcp.models import (
    ActionResult,
    DaemonReloadResult,
    DaemonStatusResult,
    JobView,
    ProjectView,
    SubmissionResult,
    TERMINAL_STATES,
    TargetView,
)
from openmcp.planning import execution_plan_data, resolve_execution_plan
from openmcp.scheduler import ProjectScheduler
from openmcp.workflows import get_workflow, validate_request


log = get_logger("runtime")


class OrchestrationError(ValueError):
    pass


class Runtime:
    def __init__(self, config: DaemonConfig) -> None:
        self.config = config
        self.config.home.mkdir(parents=True, exist_ok=True)
        self.database = Database(config.database_path)
        self._catalog = config
        self._closing = False
        self.target_executor = TargetExecutor(config, self.database, DriverRegistry())
        self.runner = JobRunner(self.database, self.target_executor, is_closing=lambda: self._closing)
        self.scheduler = ProjectScheduler(config.max_jobs, self.runner.run)
        log.debug("Runtime initialized", extra={"event": "runtime.initialized", "database": config.database_path.as_posix(), "max_jobs": config.max_jobs})

    @property
    def drivers(self) -> DriverRegistry:
        return self.target_executor.drivers

    @drivers.setter
    def drivers(self, value: DriverRegistry) -> None:
        self.target_executor.drivers = value

    async def start(self) -> None:
        self._closing = False
        interrupted = self.database.interrupt_active_jobs()
        await self.scheduler.start(self.database.queued_jobs())
        log.info("Scheduler started", extra={"event": "scheduler.started", "workers": self.scheduler.workers, "interrupted_jobs": len(interrupted), "queued_jobs": self.scheduler.queued_jobs})

    async def close(self) -> None:
        self._closing = True
        await self.scheduler.close()
        self.database.close()
        log.info("Scheduler stopped", extra={"event": "scheduler.stopped"})

    def register_project(self, path: str, alias: str = "") -> ProjectView:
        resolved = Path(path).expanduser().resolve()
        if not resolved.is_dir():
            raise OrchestrationError(f"Project path does not exist: {resolved}")
        resolved_alias = alias.strip() or resolved.name
        if not resolved_alias:
            raise OrchestrationError("Project alias cannot be empty")
        try:
            return self.database.upsert_project(project_id=str(uuid.uuid4()), alias=resolved_alias, root=resolved.as_posix())
        except sqlite3.IntegrityError as exc:
            constraint = str(exc).rsplit(":", 1)[-1].strip()
            if constraint == "projects.alias":
                message = f"Project alias already exists: {resolved_alias}"
            elif constraint == "projects.root":
                message = f"Project root already registered: {resolved.as_posix()}"
            else:
                message = "Project registration violates a database constraint"
            raise OrchestrationError(message) from exc

    async def submit(self, project_id: str, workflow_name: str, prompt: str, *, context_key: str = "", profile: str = "") -> SubmissionResult:
        project = self.database.project(project_id)
        if project is None:
            raise OrchestrationError(f"Unknown project: {project_id}")
        try:
            workflow = get_workflow(workflow_name)
            resolved_prompt = validate_request(workflow, prompt)
            catalog = load_project_config(Path(project.root), self._reload_catalog())
            selected_profile = profile.strip() or catalog.default_profile
            plan = resolve_execution_plan(workflow, catalog, selected_profile)
        except ValueError as exc:
            raise OrchestrationError(str(exc)) from exc
        job_id = str(uuid.uuid4())
        self.database.create_job(job_id=job_id, project_id=project.id, workflow=workflow.name, profile=selected_profile, prompt=resolved_prompt, execution_plan_json=json.dumps(execution_plan_data(plan), ensure_ascii=False), context_key=context_key.strip() or workflow.name)
        self.scheduler.enqueue(job_id, project.id)
        log.info("Job queued", extra={"event": "job.queued", "project_id": project.id, "job_id": job_id, "workflow": workflow.name, "profile": selected_profile})
        return SubmissionResult(job_id=job_id, state="queued")

    async def wait(self, job_id: str, timeout_s: int = 0) -> JobView:
        job = self.database.job(job_id)
        if job is None:
            raise OrchestrationError(f"Unknown job: {job_id}")
        if job.state in TERMINAL_STATES:
            return job
        await self.scheduler.wait(job_id, timeout_s)
        refreshed = self.database.job(job_id)
        if refreshed is None:
            raise OrchestrationError(f"Unknown job: {job_id}")
        return refreshed

    def cancel(self, job_id: str) -> ActionResult:
        job = self.database.job(job_id)
        if job is None:
            raise OrchestrationError(f"Unknown job: {job_id}")
        if job.state == "queued":
            location = self.scheduler.cancel(job_id)
            if location == "queued":
                self.database.finish_job(job_id, "cancelled")
                return ActionResult(success=True, job_id=job_id, state="cancelled")
            if location == "running":
                self.database.event(job_id, "job.cancellation_requested", {})
                return ActionResult(success=True, job_id=job_id, state="running")
        if job.state == "running" and self.scheduler.cancel(job_id) == "running":
            self.database.event(job_id, "job.cancellation_requested", {})
            return ActionResult(success=True, job_id=job_id, state="running")
        return ActionResult(success=False, job_id=job_id, state=job.state, error=f"Job cannot be cancelled from {job.state}")

    async def retry(self, job_id: str) -> SubmissionResult:
        job = self.database.job(job_id)
        if job is None:
            raise OrchestrationError(f"Unknown job: {job_id}")
        if job.state not in {"failed", "cancelled", "interrupted"}:
            raise OrchestrationError(f"Job cannot be retried from {job.state}")
        self.database.reset_retry(job_id)
        self.scheduler.enqueue(job_id, job.project_id)
        return SubmissionResult(job_id=job_id, state="queued")

    def status(self) -> DaemonStatusResult:
        return DaemonStatusResult(status="stopping" if self._closing else "running", workers=self.scheduler.workers, active_jobs=self.scheduler.active_jobs, queued_jobs=self.scheduler.queued_jobs)

    def reload(self) -> DaemonReloadResult:
        catalog = self._reload_catalog()
        restart_fields = ("home", "host", "port", "max_jobs", "history_turns", "history_bytes", "logging")
        restart_required = [field for field in restart_fields if getattr(self.config, field) != getattr(catalog, field)]
        return DaemonReloadResult(success=True, targets=len(catalog.targets), profiles=len(catalog.profiles), restart_required=restart_required)

    @property
    def catalog(self) -> DaemonConfig:
        return self._catalog

    def catalog_for_project(self, project_id: str) -> DaemonConfig:
        project = self.database.project(project_id)
        if project is None:
            raise OrchestrationError(f"Unknown project: {project_id}")
        try:
            return load_project_config(Path(project.root), self._reload_catalog())
        except ValueError as exc:
            raise OrchestrationError(str(exc)) from exc

    def targets(self) -> list[TargetView]:
        return self.target_executor.views(self._catalog.targets)

    def _reload_catalog(self) -> DaemonConfig:
        if self.config.config_path is None:
            return self._catalog
        self._catalog = load_config(self.config.config_path)
        return self._catalog


__all__ = ["OrchestrationError", "Runtime"]
