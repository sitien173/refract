"""Public facade for durable direct-directory jobs."""

from __future__ import annotations

import asyncio
import json
import math
import sqlite3
from dataclasses import replace
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from refract.config import DaemonConfig, load_config, load_project_config
from refract.config_inspection import bound_error, sanitize_config_error, utc_now
from refract.config_mutation import ConfigurationMutationService
from refract.database import Database
from refract.drivers import DriverRegistry
from refract.execution import JobNotifier, JobRunner, TargetExecutor
from refract.logging_setup import get_logger
from refract.models import (
    ActionResult,
    ConfigHealth,
    DaemonStatusResult,
    JobView,
    ProjectView,
    SubmissionResult,
    TERMINAL_STATES,
    TargetView,
)
from refract.notifications import send_job_notification
from refract.planning import (ExecutionPlan, execution_plan_data, parse_execution_plan, resolve_execution_plan, target_execution_key, next_target_token, resolve_next_target)
from refract.scheduler import ProjectScheduler
from refract.streaming import DEFAULT_RETENTION_DAYS, JobStreamHub
from refract.workflows import get_workflow, validate_request
from refract.workers import run_sync


log = get_logger("runtime")
RETENTION_INTERVAL_S = 3600


class OrchestrationError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "internal_error",
        next_action: str = "Retry once, then report the request ID.",
        retryable: bool = False,
        retry_after_s: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.next_action = next_action
        self.retryable = retryable
        self.retry_after_s = retry_after_s


async def _noop_notifier(_: str) -> None:
    return None


class Runtime:
    def __init__(self, config: DaemonConfig, *, notifier: JobNotifier | None = None) -> None:
        self.config = config
        self.config.home.mkdir(parents=True, exist_ok=True)
        self.database = Database(config.database_path, history_turns=config.history_turns)
        self._retention_task: asyncio.Task[None] | None = None
        self.stream_hub = JobStreamHub()
        self._catalog = config
        # Parsed configs keyed by file identity; parse again only on change.
        self._catalog_stat: tuple[int, int, int] | None = None
        self._project_catalogs: dict[Path, tuple[tuple[int, int, int] | None, DaemonConfig, DaemonConfig]] = {}
        self._config_health = self._seed_config_health(config)
        self._closing = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self.notifier = notifier or _noop_notifier
        self.target_executor = TargetExecutor(
            config, self.database, DriverRegistry(), on_stream_commit=self.stream_hub.publish
        )
        self.runner = JobRunner(
            self.database,
            self.target_executor,
            is_closing=lambda: self._closing,
            notifier=self._notify_job,
            on_terminal=self._job_terminal,
        )
        self.scheduler = ProjectScheduler(config.max_jobs, self.runner.run)
        self.mutations = ConfigurationMutationService(self)
        log.debug("Runtime initialized", extra={"event": "runtime.initialized", "database": config.database_path.as_posix(), "max_jobs": config.max_jobs})

    async def _notify_job(self, job_id: str) -> None:
        job: JobView | None = None
        lookup_error: Exception | None = None
        if self._catalog.notifications.enabled:
            try:
                job = await run_sync(self.database.job, job_id)
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
            project = await run_sync(self.database.project, job.project_id)
            if project is None:
                return
            ok = await run_sync(send_job_notification, job, project.alias)
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
        self.database.prune_history(cutoff)
        if pruned > 0:
            log.info(
                "Pruned expired stream transcripts",
                extra={"event": "stream.retention_pruned", "deleted_events": pruned},
            )
        return pruned

    async def _retain_history(self) -> None:
        while True:
            await asyncio.sleep(RETENTION_INTERVAL_S)
            try:
                await run_sync(self.prune_retained_transcripts)
            except Exception:
                log.warning("History retention failed", exc_info=True,
                            extra={"event": "history.retention_failed"})

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._closing = False
        await run_sync(self.prune_retained_transcripts)
        await run_sync(self.database.reset_orphaned_target_probes)
        interrupted = await run_sync(self.database.interrupt_active_jobs)
        for job in interrupted:
            await self._job_terminal(str(job["id"]), "interrupted")
        for job in interrupted:
            await self._notify_job(str(job["id"]))
        for target in self._catalog.targets:
            await run_sync(self.drivers.supports_structured_streaming, target)
        await self.scheduler.start()
        self._retention_task = asyncio.create_task(self._retain_history(), name="refract-retention")
        for job_id, _project_id in await run_sync(self.database.queued_jobs):
            await self._enqueue_record(job_id)
        log.info("Scheduler started", extra={"event": "scheduler.started", "workers": self.scheduler.workers, "interrupted_jobs": len(interrupted), "queued_jobs": self.scheduler.queued_jobs})


    async def _enqueue_record(self, job_id: str) -> None:
        record = await run_sync(self.database.job_record, job_id)
        if record is None or record["state"] != "queued":
            return
        self.scheduler.enqueue(
            job_id,
            str(record["project_id"]),
        )

    async def _job_terminal(self, job_id: str, _state: str) -> None:
        self.stream_hub.publish(job_id, await run_sync(self.database.stream_high_water, job_id))
        self.scheduler.complete(job_id, signal=False)

    async def close(self) -> None:
        self._closing = True
        if self._retention_task is not None:
            self._retention_task.cancel()
            await asyncio.gather(self._retention_task, return_exceptions=True)
            self._retention_task = None
        await self.scheduler.close()
        await run_sync(self.database.close)
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
        config_path = getattr(self.config, "config_path", None)
        if config_path is not None and (
            resolved / ".refract" / "config.toml"
        ).resolve() == Path(config_path).resolve():
            raise OrchestrationError(
                "Project path holds the global Refract configuration.",
                code="invalid_path",
                next_action="Register the project's own directory instead.",
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
        return self._register_project(root, base_alias, explicit_alias)

    def _upsert_project_alias(self, root: str, base_alias: str, explicit_alias: str) -> ProjectView:
        with self.database.transaction():
            projects = self.database.projects()
            existing = next((project for project in projects if project.root == root), None)
            if existing is not None:
                return existing
            aliases = {project.alias for project in projects}
            if explicit_alias and explicit_alias in aliases:
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
            return self.database.upsert_project(
                project_id=str(uuid.uuid4()), alias=candidate, root=root,
            )

    def _register_project(self, root: str, base_alias: str, explicit_alias: str) -> ProjectView:
        while True:
            try:
                return self._upsert_project_alias(root, base_alias, explicit_alias)
            except sqlite3.IntegrityError:
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

    async def submit(self, project_id: str, workflow_name: str, prompt: str, *, context_key: str = "", profile: str = "", fresh_session: bool = False, next_target: str = "") -> SubmissionResult:
        job_id = str(uuid.uuid4())
        try:
            project, workflow, selected_profile = await run_sync(
                self._prepare_submission, job_id, project_id, workflow_name, prompt,
                context_key=context_key, profile=profile,
                fresh_session=fresh_session, next_target=next_target,
            )
        finally:
            # A cancelled request must not leave a committed job undispatched.
            await self._enqueue_record(job_id)
        await self._notify_job(job_id)
        log.info("Job queued", extra={"event": "job.queued", "project_id": project.id, "job_id": job_id, "workflow": workflow, "profile": selected_profile})
        return SubmissionResult(job_id=job_id, state="queued")

    def _prepare_submission(self, job_id: str, project_id: str, workflow_name: str, prompt: str, *, context_key: str = "", profile: str = "", fresh_session: bool = False, next_target: str = "") -> tuple[ProjectView, str, str]:
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
                catalog = self._project_catalog(Path(project.root), self._reload_catalog_locked())
                selected_profile = profile.strip() or catalog.default_profile
                plan = resolve_execution_plan(workflow, catalog, selected_profile)
                if next_target:
                    target = resolve_next_target(next_target, catalog.config_revision, project.id, plan)
                    if target is None:
                        raise OrchestrationError("The next_target token is invalid or stale.", code="invalid_request", next_action="Resubmit without next_target.")
                    plan = replace(plan, selection=replace(plan.selection, targets=(target.id,)), targets=(target,))
                self._ensure_candidates_available(plan)
        except OrchestrationError:
            raise
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
        self.database.create_job(
            job_id=job_id,
            project_id=project.id,
            workflow=workflow,
            profile=selected_profile,
            prompt=resolved_prompt,
            execution_plan_json=json.dumps(execution_plan_data(plan), ensure_ascii=False),
            context_key=context_key.strip() or workflow,
            config_revision=catalog.config_revision,
            fresh_session=fresh_session,
        )
        return project, workflow, selected_profile

    def live_result_metadata(self, job: JobView) -> dict[str, object]:
        keys = ("model_name", "context_window_max", "context_window_used", "input_tokens", "output_tokens", "cached_input_tokens", "duration_ms", "failure_kind", "retryable", "next_target")
        stored = job.result.metadata
        if not stored:
            return dict.fromkeys(keys)
        metadata = {key: stored.get(key) for key in keys}
        if job.state == "succeeded":
            metadata["next_target"] = metadata["retryable"] = None
            return metadata
        if metadata.get("failure_kind") in {"retryable", "target_fatal", "circuit_open", "cancelled"}:
            next_token = self._next_target_token(job)
            metadata["next_target"] = next_token
            metadata["retryable"] = next_token is not None
        return metadata

    def _next_target_token(self, job: JobView) -> str | None:
        try:
            project = self.database.project(job.project_id)
            if not project:
                return None
            catalog = self.catalog_for_project(job.project_id)
            plan = resolve_execution_plan(job.workflow, catalog, job.profile)
            ids = [target.id for target in plan.targets]
            start = ids.index(job.target_id) + 1 if job.target_id in ids else 0
            now = datetime.now(timezone.utc)
            for target in plan.targets[start:]:
                health = self.database.target_health(target_execution_key(target))
                if not self.target_executor.is_circuit_open(health.get("circuit_open_until", ""), now, health.get("probe_job_id", "")):
                    return next_target_token(catalog.config_revision, project.id, job.profile, job.workflow, target)
        except (OrchestrationError, ValueError):
            return None
        return None

    async def wait(self, job_id: str, timeout_s: int = 0) -> JobView:
        job = await run_sync(self.database.job, job_id)
        if job is None:
            raise OrchestrationError(
                "Job does not exist.",
                code="unknown_job",
                next_action="Call job_list for the project and use a listed job ID.",
            )
        if job.state in TERMINAL_STATES:
            await self.scheduler.wait(job_id, timeout_s)
            refreshed = await run_sync(self.database.job, job_id)
            if refreshed is None:
                raise OrchestrationError(f"Unknown job: {job_id}")
            return refreshed
        await self.scheduler.wait(job_id, timeout_s)
        refreshed = await run_sync(self.database.job, job_id)
        if refreshed is None:
            raise OrchestrationError(f"Unknown job: {job_id}")
        return refreshed

    async def cancel(self, job_id: str) -> ActionResult:
        # Reserve cancellation before yielding to a worker or starting dispatch.
        location = self.scheduler.cancel(job_id)
        job = await run_sync(self.database.job, job_id)
        if job is None:
            raise OrchestrationError(
                "Job does not exist.",
                code="unknown_job",
                next_action="Call job_list for the project and use a listed job ID.",
            )
        if job.state == "queued":
            if location in {"queued", "missing"}:
                await run_sync(self.database.finish_job, job_id, "cancelled")
                await self._job_terminal(job_id, "cancelled")
                await self._notify_job(job_id)
                return ActionResult(success=True, job_id=job_id, state="cancelled")
            if location == "running":
                await run_sync(self.database.event, job_id, "job.cancellation_requested", {})
                return ActionResult(success=True, job_id=job_id, state="running")
        if job.state == "cancelled" and location == "running":
            return ActionResult(success=True, job_id=job_id, state="cancelled")
        if job.state == "running" and location == "running":
            await run_sync(self.database.event, job_id, "job.cancellation_requested", {})
            return ActionResult(success=True, job_id=job_id, state="running")
        return ActionResult(success=False, job_id=job_id, state=job.state, error=f"Job cannot be cancelled from {job.state}")

    def _ensure_candidates_available(self, plan: ExecutionPlan) -> None:
        now = datetime.now(timezone.utc)
        opened = []
        for target in plan.targets:
            health = self.database.target_health(target_execution_key(target))
            if self.target_executor.is_circuit_open(health.get("circuit_open_until", ""), now, health.get("probe_job_id", "")):
                opened.append(health)
        if len(opened) != len(plan.targets):
            return
        delays = []
        for health in opened:
            until = health.get("circuit_open_until", "")
            try:
                delay = max(1, math.ceil((datetime.fromisoformat(until) - now).total_seconds())) if until and datetime.fromisoformat(until) > now else self._catalog.breaker_base_cooldown_s
            except ValueError:
                delay = self._catalog.breaker_base_cooldown_s
            delays.append(delay)
        raise OrchestrationError("All candidate targets are temporarily unavailable.", code="targets_unavailable", next_action="Wait for a target to recover, then retry.", retryable=True, retry_after_s=min(delays))

    async def retry(self, job_id: str) -> SubmissionResult:
        try:
            await run_sync(self._prepare_retry, job_id)
        finally:
            await self._enqueue_record(job_id)
        await self._notify_job(job_id)
        return SubmissionResult(job_id=job_id, state="queued")

    def _prepare_retry(self, job_id: str) -> None:
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
        record = self.database.job_record(job_id)
        if record is not None:
            try:
                stored_plan = parse_execution_plan(json.loads(record["execution_plan_json"]))
            except (ValueError, TypeError, json.JSONDecodeError):
                stored_plan = None
            if stored_plan is not None:
                self._ensure_candidates_available(stored_plan)
        self.database.reset_retry(job_id)

    def status(self) -> DaemonStatusResult:
        return DaemonStatusResult(status="stopping" if self._closing else "running", workers=self.scheduler.workers, active_jobs=self.scheduler.active_jobs, queued_jobs=self.scheduler.queued_jobs)

    @property
    def catalog(self) -> DaemonConfig:
        return self._catalog

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
        self._catalog_stat = None
        self._reload_catalog_locked()

    @property
    def config_health(self) -> ConfigHealth:
        return self._config_health.model_copy()

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
                return self._project_catalog(Path(project.root), self._reload_catalog_locked())
        except ValueError as exc:
            raise OrchestrationError(sanitize_config_error(exc)) from exc

    def catalog_for_project_cached(self, project_id: str) -> DaemonConfig:
        """Resolve project configuration without attempting a global reload."""
        project = self.database.project(project_id)
        if project is None:
            raise OrchestrationError(f"Unknown project: {project_id}")
        try:
            return self._project_catalog(Path(project.root), self._catalog)
        except ValueError as exc:
            raise OrchestrationError(sanitize_config_error(exc)) from exc

    def _project_catalog(self, root: Path, base: DaemonConfig) -> DaemonConfig:
        stat = _file_identity(root / ".refract" / "config.toml")
        cached = self._project_catalogs.get(root)
        if cached is not None and cached[0] == stat and cached[1] is base:
            return cached[2]
        catalog = load_project_config(root, base)
        self._project_catalogs[root] = (stat, base, catalog)
        return catalog

    def _publish_project_configuration_locked(self, project_root: Path) -> None:
        self._project_catalogs.pop(Path(project_root), None)
        self._project_catalog(Path(project_root), self._catalog)

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

    def _reload_catalog_locked(self) -> DaemonConfig:
        if self.config.config_path is None:
            return self._catalog
        stat = _file_identity(self.config.config_path)
        if stat is not None and stat == self._catalog_stat:
            return self._catalog
        try:
            catalog = load_config(self.config.config_path)
        except ValueError as exc:
            self._catalog_stat = None
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
        self.database.history_turns = catalog.history_turns
        self._catalog_stat = stat
        # Planning and execution must read the same settings after any reload.
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if self._loop is not None and self._loop is not running_loop:
            self._loop.call_soon_threadsafe(self.target_executor.refresh_configuration, catalog)
        else:
            self.target_executor.refresh_configuration(catalog)
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


def _file_identity(path: Path) -> tuple[int, int, int] | None:
    try:
        info = path.stat()
    except OSError:
        return None
    return (info.st_mtime_ns, info.st_size, info.st_ino)


__all__ = ["OrchestrationError", "Runtime"]
