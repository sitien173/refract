"""Public facade for durable direct-directory jobs."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from collections import deque
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from openmcp.config import DaemonConfig, load_config, load_project_config
from openmcp.config_inspection import bound_error, sanitize_config_error, utc_now
from openmcp.config_mutation import ConfigurationMutationService
from openmcp.database import Database
from openmcp.drivers import DriverRegistry
from openmcp.execution import JobNotifier, JobRunner, TargetExecutor
from openmcp.logging_setup import get_logger
from openmcp.models import (
    ActionResult,
    ConfigHealth,
    DaemonStatusResult,
    JobView,
    ProjectView,
    SubmissionResult,
    TERMINAL_STATES,
    TargetView,
)
from openmcp.notifications import send_job_notification
from openmcp.planning import derive_access_mode, execution_plan_data, resolve_execution_plan
from openmcp.scheduler import ProjectScheduler
from openmcp.streaming import DEFAULT_RETENTION_DAYS, JobStreamHub
from openmcp.workflows import get_workflow, validate_request


log = get_logger("runtime")


class OrchestrationError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "internal_error",
        next_action: str = "Retry once, then report the request ID.",
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.next_action = next_action
        self.retryable = retryable


async def _noop_notifier(_: str) -> None:
    return None


class Runtime:
    def __init__(self, config: DaemonConfig, *, notifier: JobNotifier | None = None) -> None:
        self.config = config
        self.config.home.mkdir(parents=True, exist_ok=True)
        self.database = Database(config.database_path)
        self.stream_hub = JobStreamHub()
        orig_append = self.database.append_stream_events

        def _append_and_publish(job_id: str, events: list[Any]) -> list[JobStreamEvent]:
            persisted = orig_append(job_id, events)
            if persisted:
                self.stream_hub.publish(job_id, persisted[-1].id)
            return persisted

        self.database.append_stream_events = _append_and_publish
        self._catalog = config
        self._config_health = self._seed_config_health(config)
        self._closing = False
        self.notifier = notifier or _noop_notifier
        self.target_executor = TargetExecutor(config, self.database, DriverRegistry())
        self.runner = JobRunner(
            self.database,
            self.target_executor,
            is_closing=lambda: self._closing,
            notifier=self._notify_job,
            on_terminal=self._job_terminal,
        )
        self.scheduler = ProjectScheduler(
            config.max_jobs,
            self.runner.run,
            max_project_readers=config.max_project_readers,
            is_ready=self._dependencies_succeeded,
        )
        self.mutations = ConfigurationMutationService(self)
        log.debug("Runtime initialized", extra={"event": "runtime.initialized", "database": config.database_path.as_posix(), "max_jobs": config.max_jobs})

    async def _notify_job(self, job_id: str) -> None:
        job: JobView | None = None
        lookup_error: Exception | None = None
        if self._catalog.notifications.enabled:
            try:
                job = self.database.job(job_id)
            except Exception as exc:
                lookup_error = exc
        try:
            await self.notifier(job_id)
        except Exception:
            log.warning(
                "Job resource notification failed",
                extra={"event": "job.resource_notification_failed", "job_id": job_id},
                exc_info=True,
            )
        if not self._catalog.notifications.enabled:
            return
        if lookup_error is not None:
            log.warning(
                "Desktop notification failed",
                extra={"event": "job.desktop_notification_failed", "job_id": job_id},
                exc_info=(
                    type(lookup_error),
                    lookup_error,
                    lookup_error.__traceback__,
                ),
            )
            return
        if job is None or job.state not in TERMINAL_STATES:
            return
        try:
            project = self.database.project(job.project_id)
            if project is None:
                return
            ok = await asyncio.to_thread(send_job_notification, job, project.alias)
            if not ok:
                log.warning(
                    "Desktop notification failed",
                    extra={"event": "job.desktop_notification_failed", "job_id": job_id},
                )
        except Exception:
            log.warning(
                "Desktop notification failed",
                extra={"event": "job.desktop_notification_failed", "job_id": job_id},
                exc_info=True,
            )

    @property
    def drivers(self) -> DriverRegistry:
        return self.target_executor.drivers

    @drivers.setter
    def drivers(self, value: DriverRegistry) -> None:
        self.target_executor.drivers = value

    def prune_retained_transcripts(self, days: int = DEFAULT_RETENTION_DAYS) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        pruned = self.database.prune_terminal_stream_events(cutoff)
        if pruned > 0:
            log.info(
                "Pruned expired stream transcripts",
                extra={"event": "stream.retention_pruned", "deleted_events": pruned},
            )
        return pruned

    async def start(self) -> None:
        self._closing = False
        self.prune_retained_transcripts()
        interrupted = self.database.interrupt_active_jobs()
        changed_terminal_ids: list[str] = [str(job["id"]) for job in interrupted]
        for job in interrupted:
            changed_terminal_ids.extend(
                self._job_terminal(str(job["id"]), "interrupted")
            )
        # Repair queued records against terminal parents before any admission or
        # notifier await, including crashes between parent commit and cascade.
        for job_id, _project_id in self.database.queued_jobs():
            changed_terminal_ids.extend(self._cancel_for_failed_parent(job_id))
        for job_id in dict.fromkeys(changed_terminal_ids):
            await self._notify_job(job_id)
        await self.scheduler.start()
        for job_id, _project_id in self.database.queued_jobs():
            self._enqueue_record(job_id)
        log.info("Scheduler started", extra={"event": "scheduler.started", "workers": self.scheduler.workers, "interrupted_jobs": len(interrupted), "queued_jobs": self.scheduler.queued_jobs})


    def _dependencies_succeeded(self, job_id: str) -> bool:
        return all(
            (record := self.database.job_record(dependency_id)) is not None
            and record["state"] == "succeeded"
            for dependency_id in self.database.dependencies_for_job(job_id)
        )

    def _enqueue_record(self, job_id: str) -> None:
        record = self.database.job_record(job_id)
        if record is None or record["state"] != "queued":
            return
        self.scheduler.enqueue(
            job_id,
            str(record["project_id"]),
            access_mode=record.get("access_mode", "exclusive"),
            workflow=str(record["workflow"]),
            context_key=str(record["context_key"]),
        )

    def _failed_dependency(self, job_id: str) -> tuple[str, str] | None:
        for dependency_id in self.database.dependencies_for_job(job_id):
            record = self.database.job_record(dependency_id)
            if record is not None and record["state"] in {"failed", "cancelled", "interrupted"}:
                return dependency_id, str(record["state"])
        return None

    def _cancel_queued_dependent(
        self, job_id: str, dependency_id: str, dependency_state: str
    ) -> list[str]:
        record = self.database.job_record(job_id)
        if record is None or record["state"] != "queued":
            return []
        reason = f"Dependency {dependency_id} ended in state {dependency_state}"
        self.database.finish_job(job_id, "cancelled", error=reason)
        self.database.event(
            job_id,
            "job.dependency_cancelled",
            {
                "dependency_job_id": dependency_id,
                "dependency_state": dependency_state,
                "reason": reason,
            },
        )
        self.scheduler.cancel(job_id)
        self.scheduler.complete(job_id)
        return [job_id]

    def _cancel_for_failed_parent(self, job_id: str) -> list[str]:
        cause = self._failed_dependency(job_id)
        if cause is None:
            return []
        cancelled = self._cancel_queued_dependent(job_id, *cause)
        if not cancelled:
            return []
        return [*cancelled, *self._cascade_unsuccessful(job_id, "cancelled")]

    def _cascade_unsuccessful(self, job_id: str, state: str) -> list[str]:
        if state == "succeeded":
            return []
        cancelled: list[str] = []
        pending = deque([(job_id, state)])
        while pending:
            parent_id, parent_state = pending.popleft()
            for dependent_id in self.database.dependents_for_job(parent_id):
                newly_cancelled = self._cancel_queued_dependent(
                    dependent_id, parent_id, parent_state
                )
                for child_id in newly_cancelled:
                    if child_id not in cancelled:
                        cancelled.append(child_id)
                        pending.append((child_id, "cancelled"))
        return cancelled

    def _job_terminal(self, job_id: str, state: str) -> list[str]:
        try:
            return self._cascade_unsuccessful(job_id, state)
        finally:
            self.scheduler.complete(job_id, signal=False)
            self.scheduler.reevaluate()

    def waiting_metadata(self, job_id: str) -> tuple[list[str], str]:
        """Derive queued dependency and admission blockers without changing state."""
        record = self.database.job_record(job_id)
        if record is None or record["state"] != "queued":
            return [], ""
        waiting_on: list[str] = []
        for dependency_id in self.database.dependencies_for_job(job_id):
            dependency = self.database.job_record(dependency_id)
            if dependency is None or dependency["state"] != "succeeded":
                waiting_on.append(dependency_id)
        if waiting_on:
            return waiting_on, f"waiting on dependency {waiting_on[0]}"
        return [], self.scheduler.waiting_reason(job_id)

    async def close(self) -> None:
        self._closing = True
        await self.scheduler.close()
        self.database.close()
        log.info("Scheduler stopped", extra={"event": "scheduler.stopped"})

    def resolve_project(self, path: str, alias: str = "") -> ProjectView:
        """Resolve a canonical directory idempotently, creating a unique alias if needed."""
        resolved = Path(path).expanduser().resolve()
        if not resolved.is_dir():
            raise OrchestrationError(
                "Project path must be an existing directory.",
                code="invalid_path",
                next_action="Pass the absolute Git root of an existing directory.",
            )
        root = resolved.as_posix()
        projects = self.database.projects()
        existing = next((project for project in projects if project.root == root), None)
        if existing is not None:
            return existing

        explicit_alias = alias.strip()
        if explicit_alias and any(project.alias == explicit_alias for project in projects):
            raise OrchestrationError(
                "Project alias is already in use.",
                code="alias_taken",
                next_action="Pass a unique alias or omit alias to use an available default.",
            )
        base_alias = explicit_alias or resolved.name
        if not base_alias:
            raise OrchestrationError(
                "A project alias is required for this directory.",
                code="invalid_path",
                next_action="Pass a non-empty alias for the existing directory.",
            )
        suffix = 1
        candidate = base_alias
        while any(project.alias == candidate for project in projects):
            suffix += 1
            candidate = f"{base_alias}-{suffix}"

        while True:
            connection = self.database._connection
            try:
                # Serialize the final root/alias check with insertion. upsert_project
                # updates aliases for an existing root, so it must never receive a
                # stale candidate after a concurrent canonical insertion wins.
                connection.execute("BEGIN IMMEDIATE")
                projects = self.database.projects()
                existing = next((project for project in projects if project.root == root), None)
                if existing is not None:
                    connection.commit()
                    return existing
                aliases = {project.alias for project in projects}
                if explicit_alias and explicit_alias in aliases:
                    connection.rollback()
                    raise OrchestrationError(
                        "Project alias is already in use.",
                        code="alias_taken",
                        next_action="Pass a unique alias or omit alias to use an available default.",
                    )
                candidate = explicit_alias or base_alias
                suffix = 1
                while candidate in aliases:
                    suffix += 1
                    candidate = f"{base_alias}-{suffix}"
                project = self.database.upsert_project(
                    project_id=str(uuid.uuid4()),
                    alias=candidate,
                    root=root,
                )
                return project
            except sqlite3.IntegrityError:
                if connection.in_transaction:
                    connection.rollback()
                projects = self.database.projects()
                existing = next((project for project in projects if project.root == root), None)
                if existing is not None:
                    return existing
                if explicit_alias:
                    raise OrchestrationError(
                        "Project alias is already in use.",
                        code="alias_taken",
                        next_action="Pass a unique alias or omit alias to use an available default.",
                    ) from None
                suffix += 1
                candidate = f"{base_alias}-{suffix}"
            except BaseException:
                if connection.in_transaction:
                    connection.rollback()
                raise

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

    async def submit(self, project_id: str, workflow_name: str, prompt: str, *, context_key: str = "", profile: str = "", fresh_session: bool = False, depends_on: list[str] | tuple[str, ...] = ()) -> SubmissionResult:
        if self._closing:
            raise OrchestrationError(
                "The daemon is stopping.",
                code="daemon_stopping",
                next_action="Wait, then call project_resolve again.",
                retryable=True,
            )
        project = self.database.project(project_id)
        if project is None:
            raise OrchestrationError(
                "Project is not registered.",
                code="unknown_project",
                next_action="Call project_resolve with the Git root.",
            )
        try:
            workflow = get_workflow(workflow_name)
            resolved_prompt = validate_request(workflow, prompt)
        except ValueError as exc:
            raise OrchestrationError(
                str(exc),
                code="invalid_request",
                next_action="Correct the workflow or prompt and call job_submit again.",
            ) from exc
        try:
            with self.mutations.lock:
                catalog = load_project_config(Path(project.root), self._reload_catalog_locked())
                selected_profile = profile.strip() or catalog.default_profile
                plan = resolve_execution_plan(workflow, catalog, selected_profile)
        except ValueError as exc:
            code = "unknown_profile" if "Unknown profile" in str(exc) else "config_invalid"
            action = (
                "Call task_guide and choose an available profile."
                if code == "unknown_profile"
                else "Fix the project configuration in the dashboard."
            )
            raise OrchestrationError(
                sanitize_config_error(exc), code=code, next_action=action
            ) from exc
        job_id = str(uuid.uuid4())
        # The atomic creation API opens its own BEGIN IMMEDIATE transaction.
        # Preserve the former create_job connection-context behavior for any
        # already-open caller transaction before entering that API.
        if self.database._connection.in_transaction:
            self.database._connection.commit()
        try:
            self.database.create_job_with_dependencies(
                job_id=job_id,
                project_id=project.id,
                workflow=workflow,
                profile=selected_profile,
                prompt=resolved_prompt,
                execution_plan_json=json.dumps(execution_plan_data(plan), ensure_ascii=False),
                context_key=context_key.strip() or workflow,
                config_revision=catalog.config_revision,
                fresh_session=fresh_session,
                access_mode=derive_access_mode(plan),
                depends_on=depends_on,
            )
        except ValueError as exc:
            raise OrchestrationError(
                str(exc),
                code="invalid_dependency",
                next_action="Fix depends_on so every ID names an existing job in this project, then call job_submit again.",
            ) from exc
        if self._cancel_for_failed_parent(job_id):
            state = "cancelled"
        else:
            self._enqueue_record(job_id)
            state = "queued"
        await self._notify_job(job_id)
        log.info("Job queued", extra={"event": "job.queued", "project_id": project.id, "job_id": job_id, "workflow": workflow, "profile": selected_profile})
        return SubmissionResult(job_id=job_id, state=state)

    async def wait(self, job_id: str, timeout_s: int = 0) -> JobView:
        job = self.database.job(job_id)
        if job is None:
            raise OrchestrationError(
                "Job does not exist.",
                code="unknown_job",
                next_action="Call job_list for the project and use a listed job ID.",
            )
        if job.state in TERMINAL_STATES:
            await self.scheduler.wait(job_id, timeout_s)
            refreshed = self.database.job(job_id)
            if refreshed is None:
                raise OrchestrationError(f"Unknown job: {job_id}")
            return refreshed
        await self.scheduler.wait(job_id, timeout_s)
        refreshed = self.database.job(job_id)
        if refreshed is None:
            raise OrchestrationError(f"Unknown job: {job_id}")
        return refreshed

    async def cancel(self, job_id: str) -> ActionResult:
        job = self.database.job(job_id)
        if job is None:
            raise OrchestrationError(
                "Job does not exist.",
                code="unknown_job",
                next_action="Call job_list for the project and use a listed job ID.",
            )
        if job.state == "queued":
            location = self.scheduler.cancel(job_id)
            if location in {"queued", "missing"}:
                self.database.finish_job(job_id, "cancelled")
                cancelled = self._job_terminal(job_id, "cancelled")
                await self._notify_job(job_id)
                return ActionResult(
                    success=True,
                    job_id=job_id,
                    state="cancelled",
                    cancelled_dependents=cancelled,
                )
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
            raise OrchestrationError(
                "Job does not exist.",
                code="unknown_job",
                next_action="Call job_list for the project and use a listed job ID.",
            )
        if job.state not in {"failed", "cancelled", "interrupted"}:
            raise OrchestrationError(
                f"Job cannot be retried from state {job.state}.",
                code="invalid_state",
                next_action="Call job_wait or submit a new job.",
            )
        failed_dependency = self._failed_dependency(job_id)
        if failed_dependency is not None:
            dependency_id, dependency_state = failed_dependency
            raise OrchestrationError(
                f"Dependency {dependency_id} ended in state {dependency_state}.",
                code="dependency_failed",
                next_action=f"Retry dependency {dependency_id} first, then retry this job.",
            )
        self.database.reset_retry(job_id)
        self._enqueue_record(job_id)
        await self._notify_job(job_id)
        return SubmissionResult(job_id=job_id, state="queued")

    def status(self) -> DaemonStatusResult:
        return DaemonStatusResult(status="stopping" if self._closing else "running", workers=self.scheduler.workers, active_jobs=self.scheduler.active_jobs, queued_jobs=self.scheduler.queued_jobs)

    @property
    def catalog(self) -> DaemonConfig:
        return self._catalog

    def reload_configuration(self) -> None:
        """Reload the global catalog from disk inside the mutation lock.

        Job planning and configuration reloads must use the same
        synchronization boundary as configuration mutations so callers never
        observe disk-new with runtime-old state.
        """
        with self.mutations.lock:
            self._reload_catalog_locked()

    def publish_configuration(self) -> None:
        """Reload and publish the global runtime catalog from disk.

        A successful global mutation refreshes the runtime catalog, executor
        configuration, configuration health, and project resolution state.
        Reloading from the committed file keeps disk and memory consistent and
        reuses the exact byte buffer that was hashed for the revision.
        """
        with self.mutations.lock:
            self._publish_configuration_locked()

    def _publish_configuration_locked(self) -> None:
        """Publish a reloaded catalog; the caller holds the mutation lock."""
        catalog = self._reload_catalog_locked()
        self.target_executor.refresh_configuration(catalog)

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
            with self.mutations.lock:
                return load_project_config(Path(project.root), self._reload_catalog_locked())
        except ValueError as exc:
            raise OrchestrationError(sanitize_config_error(exc)) from exc

    def catalog_for_project_cached(self, project_id: str) -> DaemonConfig:
        """Resolve project configuration without attempting a global reload."""
        project = self.database.project(project_id)
        if project is None:
            raise OrchestrationError(f"Unknown project: {project_id}")
        try:
            return load_project_config(Path(project.root), self._catalog)
        except ValueError as exc:
            raise OrchestrationError(sanitize_config_error(exc)) from exc

    def publish_project_configuration(self, project_root: Path) -> None:
        """Invalidate and re-resolve one registered project's resolved catalog.

        Project resolution is derived from the live global catalog at read
        time, so no separate cache exists to invalidate; the method exists to
        (a) participate in the mutation synchronization boundary and (b) fail
        the transaction when the project file no longer resolves against the
        current runtime catalog.
        """
        with self.mutations.lock:
            self._publish_project_configuration_locked(project_root)

    def _publish_project_configuration_locked(self, project_root: Path) -> None:
        load_project_config(Path(project_root), self._catalog)

    def targets(self) -> list[TargetView]:
        views = self.target_executor.views(self._catalog.targets)
        target_by_id = {target.id: target for target in self._catalog.targets}
        return [
            view.model_copy(
                update={
                    "backend": target_by_id[view.id].backend,
                    "isolated": target_by_id[view.id].isolated,
                    "read_only": target_by_id[view.id].read_only,
                }
            )
            for view in views
        ]

    def _reload_catalog(self) -> DaemonConfig:
        """Reload the global configuration source inside the mutation lock.

        External callers (for example dashboard reads) use this helper so they
        share the mutation synchronization boundary; it is re-entrant.
        """
        with self.mutations.lock:
            return self._reload_catalog_locked()

    def _reload_catalog_locked(self) -> DaemonConfig:
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
                    "latest_error": bound_error(sanitize_config_error(exc)),
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
