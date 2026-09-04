"""Public facade for durable direct-directory jobs."""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

from openmcp.config import DaemonConfig, load_config, load_project_config
from openmcp.config_inspection import bound_error, utc_now
from openmcp.context_files import sweep_context_files
from openmcp.database import Database
from openmcp.drivers import DriverRegistry
from openmcp.execution import JobNotifier, JobRunner, TargetExecutor
from openmcp.logging_setup import get_logger
from openmcp.models import (
    ActionResult,
    ConfigHealth,
    ContextInstructionsResult,
    DaemonStatusResult,
    JobView,
    ProjectView,
    SubmissionResult,
    TERMINAL_STATES,
    TargetView,
    job_resource_uri,
)
from openmcp.planning import execution_plan_data, resolve_execution_plan
from openmcp.scheduler import ProjectScheduler
from openmcp.workflows import get_workflow, validate_request


log = get_logger("runtime")


class OrchestrationError(ValueError):
    pass


async def _noop_notifier(_: str) -> None:
    return None


class Runtime:
    def __init__(self, config: DaemonConfig, *, notifier: JobNotifier | None = None) -> None:
        self.config = config
        self.config.home.mkdir(parents=True, exist_ok=True)
        self.database = Database(config.database_path)
        self._catalog = config
        self._config_health = self._seed_config_health(config)
        self._closing = False
        self.notifier = notifier or _noop_notifier
        self.target_executor = TargetExecutor(config, self.database, DriverRegistry())
        self.runner = JobRunner(
            self.database,
            self.target_executor,
            is_closing=lambda: self._closing,
            notifier=self._notify_job_resource,
        )
        self.scheduler = ProjectScheduler(config.max_jobs, self.runner.run)
        log.debug("Runtime initialized", extra={"event": "runtime.initialized", "database": config.database_path.as_posix(), "max_jobs": config.max_jobs})

    async def _notify_job_resource(self, resource_uri: str) -> None:
        try:
            await self.notifier(resource_uri)
        except Exception:
            log.warning(
                "Job resource notification failed",
                extra={"event": "job.resource_notification_failed", "resource_uri": resource_uri},
                exc_info=True,
            )

    @property
    def drivers(self) -> DriverRegistry:
        return self.target_executor.drivers

    @drivers.setter
    def drivers(self, value: DriverRegistry) -> None:
        self.target_executor.drivers = value

    async def start(self) -> None:
        self._closing = False
        interrupted = self.database.interrupt_active_jobs()
        for job in interrupted:
            await self._notify_job_resource(job_resource_uri(job["id"]))
        self._sweep_project_context_files()
        await self.scheduler.start(self.database.queued_jobs())
        log.info("Scheduler started", extra={"event": "scheduler.started", "workers": self.scheduler.workers, "interrupted_jobs": len(interrupted), "queued_jobs": self.scheduler.queued_jobs})

    def _sweep_project_context_files(self) -> None:
        """Remove managed marker-bearing leftovers for every registered project."""
        for project in self.database.projects():
            root = Path(project.root)
            for filename in ("AGENTS.override.md", "GEMINI.md"):
                try:
                    sweep_context_files(root, root / filename)
                except Exception:
                    log.warning(
                        "Context file sweep failed",
                        extra={"event": "context_file.sweep_failed", "project_id": project.id, "root": project.root, "filename": filename},
                        exc_info=True,
                    )

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
            instruction = self.database.context_instruction(project.id, workflow)
            plan = resolve_execution_plan(workflow, catalog, selected_profile, instruction)
        except ValueError as exc:
            raise OrchestrationError(str(exc)) from exc
        job_id = str(uuid.uuid4())
        self.database.create_job(job_id=job_id, project_id=project.id, workflow=workflow, profile=selected_profile, prompt=resolved_prompt, execution_plan_json=json.dumps(execution_plan_data(plan), ensure_ascii=False), context_key=context_key.strip() or workflow, config_revision=catalog.config_revision)
        await self._notify_job_resource(job_resource_uri(job_id))
        self.scheduler.enqueue(job_id, project.id)
        log.info("Job queued", extra={"event": "job.queued", "project_id": project.id, "job_id": job_id, "workflow": workflow, "profile": selected_profile})
        return SubmissionResult(job_id=job_id, state="queued", resource_uri=job_resource_uri(job_id))

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

    async def cancel(self, job_id: str) -> ActionResult:
        job = self.database.job(job_id)
        if job is None:
            raise OrchestrationError(f"Unknown job: {job_id}")
        if job.state == "queued":
            location = self.scheduler.cancel(job_id)
            if location == "queued":
                self.database.finish_job(job_id, "cancelled")
                await self._notify_job_resource(job_resource_uri(job_id))
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
        await self._notify_job_resource(job_resource_uri(job_id))
        self.scheduler.enqueue(job_id, job.project_id)
        return SubmissionResult(job_id=job_id, state="queued", resource_uri=job_resource_uri(job_id))

    def status(self) -> DaemonStatusResult:
        return DaemonStatusResult(status="stopping" if self._closing else "running", workers=self.scheduler.workers, active_jobs=self.scheduler.active_jobs, queued_jobs=self.scheduler.queued_jobs)

    def set_context_instruction(self, project_id: str, workflow: str, instruction: str) -> ContextInstructionsResult:
        project = self.database.project(project_id)
        if project is None:
            raise OrchestrationError(f"Unknown project: {project_id}")
        try:
            resolved_workflow = get_workflow(workflow)
        except ValueError as exc:
            raise OrchestrationError(str(exc)) from exc
        self.database.set_context_instruction(project.id, resolved_workflow, instruction)
        return ContextInstructionsResult(
            project_id=project.id,
            instructions=self.database.context_instructions(project.id),
        )

    def context_instructions(self, project_id: str) -> ContextInstructionsResult:
        project = self.database.project(project_id)
        if project is None:
            raise OrchestrationError(f"Unknown project: {project_id}")
        return ContextInstructionsResult(
            project_id=project.id,
            instructions=self.database.context_instructions(project.id),
        )

    @property
    def catalog(self) -> DaemonConfig:
        return self._catalog

    @property
    def config_health(self) -> ConfigHealth:
        return self._config_health.model_copy()

    def configuration_health(self) -> ConfigHealth:
        """Return global configuration health, separately from daemon status."""
        return self.config_health

    @staticmethod
    def _seed_config_health(config: DaemonConfig) -> ConfigHealth:
        loaded_at = config.config_loaded_at or utc_now()
        source_path = config.config_path.as_posix() if config.config_path else ""
        return ConfigHealth(
            attempted_at=loaded_at,
            successful_at=loaded_at,
            source_path=source_path,
            modification_time=config.config_modification_time,
            revision=config.config_revision,
            valid=True,
            last_known_good_revision=config.config_revision,
        )

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
        try:
            catalog = load_config(self.config.config_path)
        except ValueError as exc:
            attempted_at = getattr(exc, "attempted_at", utc_now())
            source_path = getattr(exc, "path", self.config.config_path)
            revision = getattr(exc, "revision", "")
            modification = getattr(exc, "modification_time", "")
            self._config_health = self._config_health.model_copy(
                update={
                    "attempted_at": attempted_at,
                    "source_path": Path(source_path).as_posix(),
                    "modification_time": modification,
                    "revision": revision,
                    "valid": False,
                    "latest_error": bound_error(exc),
                }
            )
            raise
        previous = self._config_health
        self._catalog = catalog
        self._config_health = ConfigHealth(
            attempted_at=catalog.config_loaded_at or utc_now(),
            successful_at=catalog.config_loaded_at or utc_now(),
            source_path=catalog.config_path.as_posix() if catalog.config_path else "",
            modification_time=catalog.config_modification_time,
            revision=catalog.config_revision,
            valid=True,
            latest_error="",
            last_known_good_revision=catalog.config_revision
            or previous.last_known_good_revision,
        )
        return self._catalog


__all__ = ["OrchestrationError", "Runtime"]
