"""Wiring for durable direct-directory jobs: construct the parts, start and stop them, delegate to them."""

from __future__ import annotations

import asyncio
import threading
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from refract.config import DaemonConfig, sanitize_config_error
from refract.config.catalog import Catalog
from refract.logging_setup import get_logger
from refract.models import (
    ActionResult,
    ConfigHealth,
    DaemonStatusResult,
    JobView,
    OrchestrationError,
    ProjectView,
    SubmissionResult,
    TargetView,
)
from refract.runner.attempts import TargetExecutor
from refract.runner.drivers import DriverRegistry
from refract.runner.jobs import JobNotifier, JobRunner, _noop_notifier
from refract.runner.notify import notify_job
from refract.runner.projects import resolve_project
from refract.runner.recovery import recover_interrupted
from refract.runner.submission import Admission
from refract.scheduling import retention
from refract.scheduling.asks import AskRegistry, answer_job
from refract.scheduling.cancellation import CancelStatus, Canceller
from refract.scheduling.hub import Hub
from refract.scheduling.scheduler import ProjectScheduler
from refract.scheduling.waiting import WaitResult, wait_jobs
from refract.store.database import Database
from refract.store.pool import run_db, run_on, run_sync

log = get_logger("runtime")


class Runtime:
    def __init__(self, config: DaemonConfig, *, notifier: JobNotifier | None = None) -> None:
        self.config = config
        self.config.home.mkdir(parents=True, exist_ok=True)
        self.database = Database(config.database_path)
        self.hub = Hub()
        self.ask_registry = AskRegistry(self.database, self.hub)
        self._closing = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.RLock()
        # Jobs whose terminal transition the runner reported; `_publish_terminal` publishes only for these.
        self._terminal_jobs: set[str] = set()
        self.notifier = notifier or _noop_notifier
        self.catalogs = Catalog(config, self._lock, self._refresh_executor)
        self.target_executor = TargetExecutor(
            config, self.database, DriverRegistry(),
            ask_registry=self.ask_registry,
            environment_resolver=self.catalogs.resolve_target_environment,
        )
        self.runner = JobRunner(
            self.database,
            self.target_executor,
            is_closing=lambda: self._closing,
            notifier=self._notify_job,
            on_terminal=self._job_terminal,
        )
        self.scheduler = ProjectScheduler(config.max_jobs, self.runner.run, self._publish_terminal)
        self.admission = Admission(self.database, self.catalogs, self.target_executor, self._lock, lambda: self._closing)
        self.canceller = Canceller(self.database, self.scheduler, self.hub, self.ask_registry, self._notify_job)
        self.retention = retention.RetentionSweep(self.database, lambda: self.prune_retained_transcripts())
        log.debug("Runtime initialized", extra={"event": "runtime.initialized", "database": config.database_path.as_posix(), "max_jobs": config.max_jobs})

    def _refresh_executor(self, catalog: DaemonConfig) -> None:
        """Apply a reloaded catalog on the loop that owns the executor, whichever thread reloaded it."""
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if self._loop is not None and self._loop is not running_loop:
            self._loop.call_soon_threadsafe(self.target_executor.refresh_configuration, catalog)
        else:
            self.target_executor.refresh_configuration(catalog)

    async def _notify_job(self, job_id: str) -> None:
        await notify_job(self.database, self.catalogs.current, self.notifier, job_id)

    @property
    def closing(self) -> bool:
        return self._closing

    @property
    def drivers(self) -> DriverRegistry:
        return self.target_executor.drivers

    @drivers.setter
    def drivers(self, value: DriverRegistry) -> None:
        self.target_executor.drivers = value

    @property
    def catalog(self) -> DaemonConfig:
        return self.catalogs.current

    @property
    def config_health(self) -> ConfigHealth:
        return self.catalogs.health.model_copy()

    def prune_retained_transcripts(self, days: int = retention.DEFAULT_RETENTION_DAYS) -> None:
        retention.prune(self.database, days)

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._closing = False
        await run_on(self.database.executor, self.prune_retained_transcripts)
        interrupted = await recover_interrupted(self.database, self.hub, self._notify_job)
        for target in self.catalog.targets:
            await self.drivers.supports_structured_streaming(target)
        await self.scheduler.start()
        self.retention.start()
        for job_id, _project_id in await run_db(self.database.queued_jobs):
            await self._enqueue_record(job_id)
        log.info("Scheduler started", extra={"event": "scheduler.started", "workers": self.scheduler.workers, "interrupted_jobs": interrupted, "queued_jobs": self.scheduler.queued_jobs})

    async def close(self) -> None:
        self._closing = True
        self.hub.wake()
        await self.retention.stop()
        await self.scheduler.close()
        await self.canceller.drain()
        await run_sync(self.database.close)
        log.info("Scheduler stopped", extra={"event": "scheduler.stopped"})

    async def _enqueue_record(self, job_id: str) -> None:
        record = await run_db(self.database.job_record, job_id)
        if record is None or record["state"] != "queued":
            return
        self.scheduler.enqueue(job_id, (str(record["project_id"]), str(record["session"]), str(record["workflow"])))
        self.hub.publish(job_id, "queued")

    async def _job_terminal(self, job_id: str, _state: str, changed: bool = True) -> None:
        # The runner has committed and left its session lock; free the slot now. `terminal` is published
        # by `_publish_terminal` once the run callback returns, after the notification.
        self._terminal_jobs.add(job_id)
        self.scheduler.complete(job_id)

    def _publish_terminal(self, job_id: str) -> None:
        """Scheduler callback: publish only when the runner reported a terminal transition for this job."""
        if job_id in self._terminal_jobs:
            self._terminal_jobs.discard(job_id)
            self.hub.publish(job_id, "terminal")

    def resolve_project(self, path: str) -> ProjectView:
        return resolve_project(self.database, self.config, path)

    def card_create(self, path: str, title: str, body: str, job_ids: Sequence[str]) -> dict[str, Any]:
        project = self.resolve_project(path)
        return self.database.create_card(
            card_id=str(uuid.uuid4()), project_id=project.id, title=title, body=body, job_ids=job_ids,
        )

    def card_move(self, card_id: str, state: str, job_ids: Sequence[str], note: str) -> dict[str, Any]:
        return self.database.move_card(card_id=card_id, state=state, job_ids=job_ids, note=note)

    def card_list(self, path: str) -> dict[str, Any]:
        project = self.resolve_project(path)
        return self.database.list_cards(project_id=project.id, limit=None)

    async def submit(self, project_id: str, workflow_name: str, prompt: str, *, session: str = "", profile: str = "", fresh: bool = False) -> SubmissionResult:
        job_id = str(uuid.uuid4())
        try:
            project, workflow, selected_profile = await run_sync(
                self.admission.prepare, job_id, project_id, workflow_name, prompt,
                session=session, profile=profile, fresh=fresh,
            )
        finally:
            # A cancelled request must not leave a committed job undispatched.
            await self._enqueue_record(job_id)
        await self._notify_job(job_id)
        log.info("Job queued", extra={"event": "job.queued", "project_id": project.id, "job_id": job_id, "workflow": workflow, "profile": selected_profile})
        return SubmissionResult(job_id=job_id, state="queued")

    async def submit_from_job(
        self, from_job: str, *, project_id: str = "", target: str = "", fresh: bool | None = None
    ) -> SubmissionResult:
        """Queue a new job that copies a terminal job; only `target` and `fresh` may differ from the source."""
        new_id = str(uuid.uuid4())
        try:
            await run_on(self.database.executor, self.admission.prepare_from_job, new_id, from_job, project_id, target, fresh)
        finally:
            await self._enqueue_record(new_id)
        await self._notify_job(new_id)
        return SubmissionResult(job_id=new_id, state="queued")

    def live_routing(self, job: JobView) -> dict[str, object]:
        kind = job.result.failure_kind
        if job.state == "succeeded":
            return {"failure_kind": kind, "retry": {"next_target": None}}
        return {"failure_kind": kind, "retry": {"next_target": self._next_target(job)}}

    @staticmethod
    def _next_target(job: JobView) -> str | None:
        """The next target the runner chose when the job finished; it never changes afterwards."""
        return job.result.next_target

    async def wait(self, job_id: str, timeout_s: int = 0) -> JobView:
        return (await self.wait_jobs([job_id], timeout_s)).job

    async def wait_jobs(self, job_ids: Sequence[str], timeout_s: float = 0) -> WaitResult:
        return await wait_jobs(self.database, self.hub, lambda: self._closing, job_ids, timeout_s)

    async def job_answer(self, job_id: str, answer: str, expected_question_id: str | None = None) -> ActionResult:
        return await answer_job(self.database, self.ask_registry, job_id, answer, expected_question_id)

    async def cancel_job(self, job_id: str) -> CancelStatus:
        return await self.canceller.cancel_job(job_id)

    async def cancel(self, job_id: str) -> ActionResult:
        status = await self.cancel_job(job_id)
        job = await run_db(self.database.job, job_id)
        state = job.state if job is not None else "cancelled"
        if status == "already_terminal":
            return ActionResult(success=False, job_id=job_id, state=state, error=f"Job cannot be cancelled from {state}")
        return ActionResult(success=True, job_id=job_id, state=state)

    def status(self) -> DaemonStatusResult:
        return DaemonStatusResult(status="stopping" if self._closing else "running", workers=self.scheduler.workers, active_jobs=self.scheduler.active_jobs, queued_jobs=self.scheduler.queued_jobs)

    def shutdown_if_idle(self, *, force: bool = False) -> dict[str, Any]:
        """Close admission and report ``stopping`` only when no job is queued or running, or when ``force`` is set."""
        with self._lock:
            counts = self.database.active_job_counts()
            running = max(counts["running"], self.scheduler.active_jobs)
            queued = max(counts["queued"], self.scheduler.queued_jobs)
            if (running or queued) and not force:
                return {"stopping": False, "running": running, "queued": queued}
            self._closing = True
            self.hub.wake()
            return {"stopping": True, "running": running, "queued": queued}

    def publish_configuration(self) -> None:
        """Reload and publish the global runtime catalog from disk after a global mutation."""
        self.catalogs.publish()

    def catalog_for_project(self, project_id: str) -> DaemonConfig:
        return self._project_catalog(project_id, self.catalogs.for_root)

    def catalog_for_project_cached(self, project_id: str) -> DaemonConfig:
        """Resolve project configuration without attempting a global reload."""
        return self._project_catalog(project_id, self.catalogs.for_root_cached)

    def _project_catalog(self, project_id: str, load: Any) -> DaemonConfig:
        project = self.database.project(project_id)
        if project is None:
            raise OrchestrationError(f"Unknown project: {project_id}")
        try:
            return load(Path(project.root))
        except ValueError as exc:
            raise OrchestrationError(sanitize_config_error(exc)) from exc

    def targets(self) -> list[TargetView]:
        views = self.target_executor.views(self.catalog.targets)
        target_by_id = {target.id: target for target in self.catalog.targets}
        return [
            view.model_copy(update={"backend": target_by_id[view.id].backend})
            for view in views
        ]


__all__ = ["OrchestrationError", "Runtime"]
