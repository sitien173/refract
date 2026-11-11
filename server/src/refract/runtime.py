"""Public facade for durable direct-directory jobs."""

from __future__ import annotations

import asyncio
import json
import math
import os
import hashlib
import hmac
import secrets
import sqlite3
from contextlib import suppress
from dataclasses import replace
import subprocess
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
import threading
from collections.abc import Sequence
from typing import Any

from refract.ask import AskRegistry
from refract.config import DaemonConfig, load_config, load_project_config, resolve_target_environment
from refract.config_inspection import bound_error, sanitize_config_error, utc_now
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
from refract.planning import (ExecutionPlan, execution_plan_data, resolve_execution_plan, target_execution_key)
from refract import pricing
from refract.product_telemetry import (
    FEATURE_FLUSH_INTERVAL_S, build_features_event, build_heartbeat_event, build_job_event,
    SendStatus, install_id, purge, read_heartbeat_date, sender, telemetry_decision, telemetry_status,
    write_heartbeat_date,
)
from refract.processes import kill_stale_group
from refract.scheduler import ProjectScheduler
from refract.workflows import get_workflow, validate_request
from refract.workers import run_sync


log = get_logger("runtime")
RETENTION_INTERVAL_S = 3600
PRICING_REFRESH_INTERVAL_S = 24 * 3600
PRICING_RETRY_INTERVAL_S = 3600
DEFAULT_RETENTION_DAYS = 7
JOB_METRICS_RETENTION_DAYS = 365
MAX_ANSWER_LENGTH = 8192
MAX_FEATURE_NAMES = 200
UNKNOWN_JOB_MESSAGE = "Job does not exist."
_LIST_JOB_ID_ACTION = "Call list for the project and use a listed job ID."
_DESKTOP_NOTIFICATION_FAILED = "Desktop notification failed"
_DESKTOP_NOTIFICATION_FAILED_EVENT = "job.desktop_notification_failed"


class OrchestrationError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "internal_error",
        next_action: str = "Retry once, then report the request ID.",
        retry_after_s: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.next_action = next_action
        self.retry_after_s = retry_after_s


async def _noop_notifier(_: str) -> None:
    return None


class Runtime:
    def __init__(self, config: DaemonConfig, *, notifier: JobNotifier | None = None) -> None:
        self.config = config
        self.config.home.mkdir(parents=True, exist_ok=True)
        self.database = Database(config.database_path)
        self.ask_registry = AskRegistry()
        self._retention_task: asyncio.Task[None] | None = None
        self._telemetry_task: asyncio.Task[None] | None = None
        self._telemetry_enqueues: set[asyncio.Task[None]] = set()
        self._feature_counts: dict[str, int] = {}
        self._feature_lock = threading.Lock()
        self._feature_period_start = utc_now()
        self._feature_task: asyncio.Task[None] | None = None
        self._pricing_task: asyncio.Task[None] | None = None
        self.pricing = pricing.read_cache(config.home)
        # The purge lock. Consent changes, the sender, feature flushes and job enqueues each hold it in one worker thread.
        self._flush_lock = threading.RLock()
        self._flush_inflight: asyncio.Task[None] | None = None
        self._telemetry_send_status = SendStatus()
        # The one consent state. Only _set_telemetry_enabled changes it after construction.
        self._telemetry_enabled = telemetry_decision(config)[0]
        # File identity at the last publish, to tell whether the config changed since.
        self._consent_stat = _file_identity(config.config_path) if config.config_path else None
        self._catalog = config
        # A per-runtime secret makes revision contexts opaque and prevents
        # session keys from becoming fingerprints of secret-bearing config hashes.
        self._session_revision_secret = secrets.token_bytes(32)
        # Parsed configs keyed by file identity; parse again only on change.
        self._catalog_stat: tuple[int, int, int] | None = None
        self._project_catalogs: dict[
            Path, tuple[tuple[int, int, int] | None, DaemonConfig, DaemonConfig, str, str | None]
        ] = {}
        self._config_health = self._seed_config_health(config)
        self._closing = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self.notifier = notifier or _noop_notifier
        self.target_executor = TargetExecutor(
            config, self.database, DriverRegistry(),
            ask_registry=self.ask_registry,
            environment_resolver=self._resolve_target_environment,
        )
        self.runner = JobRunner(
            self.database,
            self.target_executor,
            is_closing=lambda: self._closing,
            notifier=self._notify_job,
            on_terminal=self._job_terminal,
        )
        self.scheduler = ProjectScheduler(config.max_jobs, self.runner.run)
        self._lock = threading.RLock()
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
                _DESKTOP_NOTIFICATION_FAILED,
                extra={"event": _DESKTOP_NOTIFICATION_FAILED_EVENT, "job_id": job_id},
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
            ok = await run_sync(send_job_notification, job, Path(project.root).name)
            if not ok:
                log.warning(
                    _DESKTOP_NOTIFICATION_FAILED,
                    extra={"event": _DESKTOP_NOTIFICATION_FAILED_EVENT, "job_id": job_id},
                )
        except Exception:
            log.warning(
                _DESKTOP_NOTIFICATION_FAILED,
                extra={"event": _DESKTOP_NOTIFICATION_FAILED_EVENT, "job_id": job_id},
                exc_info=True,
            )

    @property
    def drivers(self) -> DriverRegistry:
        return self.target_executor.drivers

    @drivers.setter
    def drivers(self, value: DriverRegistry) -> None:
        self.target_executor.drivers = value

    def prune_retained_transcripts(self, days: int = DEFAULT_RETENTION_DAYS) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        self.database.prune_history(cutoff)
        metrics_cutoff = (datetime.now(timezone.utc) - timedelta(days=JOB_METRICS_RETENTION_DAYS)).isoformat()
        self.database.prune_job_metrics(metrics_cutoff)

    async def _retain_history(self) -> None:
        while True:
            await asyncio.sleep(RETENTION_INTERVAL_S)
            try:
                await run_sync(self.prune_retained_transcripts)
            except Exception:
                log.warning("History retention failed", exc_info=True,
                            extra={"event": "history.retention_failed"})

    async def _refresh_pricing(self) -> None:
        # to_thread, not run_sync: run_sync shields cancellation, so close() would wait out the HTTP timeout.
        # asyncio.run joins the default executor at shutdown, so a fetch blocked in the thread can delay process exit by up to the fetch timeout.
        while True:
            delay = PRICING_RETRY_INTERVAL_S
            try:
                data = await asyncio.to_thread(pricing.fetch_pricing)
                parsed = pricing.parse_pricing_file(data)
                try:
                    await asyncio.to_thread(pricing.write_cache, self.config.home, data)
                except OSError:
                    log.warning("Pricing cache write failed", exc_info=True,
                                extra={"event": "pricing.cache_write_failed"})
                self.pricing = parsed
                delay = PRICING_REFRESH_INTERVAL_S
            except pricing.PricingError as err:
                log.warning("Pricing fetch failed", extra={"event": "pricing.fetch_failed", "reason": err.reason})
            except Exception:
                log.warning("Pricing refresh failed", exc_info=True,
                            extra={"event": "pricing.refresh_failed"})
            await asyncio.sleep(delay)

    def _warn_ignored_keys(self, config: DaemonConfig) -> None:
        if config.ignored_keys:
            log.warning(
                "Ignored configuration keys",
                extra={"event": "config.ignored_keys", "keys": config.ignored_keys},
            )

    async def start(self) -> None:
        self._warn_ignored_keys(self.config)
        self._loop = asyncio.get_running_loop()
        self._closing = False
        await run_sync(self.prune_retained_transcripts)
        await run_sync(self.database.reset_orphaned_target_probes)
        interrupted = await run_sync(self.database.interrupt_active_jobs)
        for job in interrupted:
            if job["pgid"]:
                killed = await run_sync(kill_stale_group, int(job["pgid"]), str(job["id"]))
                log.info("Stale worker group checked", extra={"event": "job.worker_group", "job_id": job["id"], "pgid": job["pgid"], "killed": killed})
        for job in interrupted:
            await self._job_terminal(str(job["id"]), "interrupted")
        for job in interrupted:
            await self._notify_job(str(job["id"]))
        for target in self._catalog.targets:
            await run_sync(self.drivers.supports_structured_streaming, target)
        await self.scheduler.start()
        self._retention_task = asyncio.create_task(self._retain_history(), name="refract-retention")
        self._telemetry_task = asyncio.create_task(
            sender(self.database, self._telemetry_config_check, self.config.home,
                   send_status=self._telemetry_send_status, purge_lock=self._flush_lock,
                   consent=lambda _config: self._telemetry_enabled),
            name="refract-telemetry-sender",
        )
        self._feature_task = asyncio.create_task(
            self._flush_features_hourly(), name="refract-telemetry-features",
        )
        if os.environ.get("REFRACT_PRICING_FETCH") != "0":
            self._pricing_task = asyncio.create_task(self._refresh_pricing(), name="refract-pricing")
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

    async def _job_terminal(self, job_id: str, _state: str, changed: bool = True) -> None:
        self.scheduler.complete(job_id, signal=False)
        run_secrets = self.target_executor.run_secrets.pop(job_id, None)
        # Only the call that moved the job to a terminal state reports it, so a repeat enqueues nothing.
        if not changed:
            return
        # A job that ended while consent was off stays unreported, unless the config changed since the last publish.
        if not self._telemetry_enabled and not self._consent_stale():
            return
        task = asyncio.create_task(self._enqueue_telemetry(job_id, run_secrets), name="refract-telemetry-enqueue")
        self._telemetry_enqueues.add(task)
        task.add_done_callback(self._telemetry_enqueues.discard)

    def _consent_stale(self) -> bool:
        """True when the config file or environment changed since consent was last published."""
        path = self.config.config_path
        if path is not None and _file_identity(path) != self._consent_stat:
            return True
        return telemetry_decision(self._catalog)[0] != self._telemetry_enabled

    def _telemetry_config_check(self) -> DaemonConfig:
        """Publish the current configuration and consent; an environment change needs no reload to count."""
        with self._lock:
            config = self._reload_catalog_locked()
            # Decide and apply under the catalog lock so a later publish cannot be overwritten by this decision.
            self._set_telemetry_enabled(telemetry_decision(config)[0])
        return config

    def _set_telemetry_enabled(self, enabled: bool) -> None:
        """The only writer of consent. A switch to off clears counts and purges queued state in the same locked section."""
        if enabled == self._telemetry_enabled:
            return
        with self._flush_lock:
            previous = self._telemetry_enabled
            with self._feature_lock:
                if enabled and not previous:
                    self._feature_period_start = utc_now()
                if not enabled:
                    self._feature_counts = {}
                self._telemetry_enabled = enabled
            if previous and not enabled:
                try:
                    purge(self.database, self.config.home)
                except Exception:
                    log.warning("Telemetry purge failed", extra={"event": "telemetry.purge_failed"}, exc_info=True)

    @property
    def telemetry_enabled(self) -> bool:
        return self._telemetry_enabled

    def telemetry_status(self) -> dict[str, Any]:
        """Report the consent decision and next batch without creating state while off."""
        try:
            config = self._telemetry_config_check()
        except ValueError:
            # A config that fails to load counts as off.
            return telemetry_status(self.database, self.config, False, "config", self._telemetry_send_status)
        enabled, source = telemetry_decision(config)
        return telemetry_status(self.database, config, enabled, source, self._telemetry_send_status)

    def count_feature(self, name: str) -> None:
        """Count one feature use in memory; a no-op while consent is off."""
        if not self._telemetry_enabled:
            return
        with self._feature_lock:
            if self._telemetry_enabled and (name in self._feature_counts
                                            or len(self._feature_counts) < MAX_FEATURE_NAMES):
                self._feature_counts[name] = self._feature_counts.get(name, 0) + 1

    async def _flush_features_hourly(self) -> None:
        while True:
            await asyncio.sleep(FEATURE_FLUSH_INTERVAL_S)
            # Shielded so a cancel from close() cannot drop counts the flush already detached.
            self._flush_inflight = asyncio.create_task(self._flush_telemetry())
            await asyncio.shield(self._flush_inflight)

    async def _flush_telemetry(self) -> None:
        counts: dict[str, int] = {}
        period_start = ""
        features_queued_flag: list[bool] = []
        try:
            try:
                config = await run_sync(self._telemetry_config_check)
            except ValueError:
                return
            if not self._telemetry_enabled:
                return
            now = utc_now()
            with self._feature_lock:
                # Coarse clocks such as Windows can repeat a timestamp; a repeated period start would reuse the outbox key and drop counts.
                start = datetime.fromisoformat(self._feature_period_start)
                if datetime.fromisoformat(now) <= start:
                    now = (start + timedelta(microseconds=1)).isoformat()
                counts, self._feature_counts = self._feature_counts, {}
                period_start, self._feature_period_start = self._feature_period_start, now
            events = [(f"features:{period_start}", build_features_event(period_start, now, counts))] if counts else []
            try:
                await run_sync(self._write_flush, config, events, now, features_queued_flag)
            except BaseException:
                if counts and not features_queued_flag:
                    self._restore_feature_counts(counts, period_start)
                raise
        except Exception:
            log.warning("Telemetry flush failed", extra={"event": "telemetry.flush_failed"}, exc_info=True)

    def _write_flush(self, config: DaemonConfig, events: list[tuple[str, dict[str, Any]]], now: str,
                     features_queued: list[bool]) -> None:
        """Write the heartbeat date and queue the events under the purge lock; run_sync joins this thread on cancel."""
        with self._flush_lock:
            if not self._telemetry_enabled:
                return
            previous = read_heartbeat_date(config.home)
            heartbeat_due = previous != now[:10]
            if heartbeat_due:
                events = [*events, (f"heartbeat:{now[:10]}", build_heartbeat_event(config))]
            if not events:
                return
            install_id(config.home)
            if not self._telemetry_enabled:
                return
            wrote_date = False
            try:
                if heartbeat_due:
                    # Persist the date first so a delivered heartbeat can never be re-queued after a restart.
                    wrote_date = True
                    write_heartbeat_date(config.home, now[:10])
                for key, event in events:
                    self._enqueue_marking(key, json.dumps(event), now, features_queued)
            except BaseException:
                if wrote_date:
                    self._restore_heartbeat_date(config.home, previous)
                raise

    def _enqueue_marking(self, key: str, payload: str, now: str, features_queued: list[bool]) -> None:
        """Enqueue, then record a committed features row; a failed call leaves the flag unset."""
        self.database.enqueue_telemetry(key, payload, now)
        if key.startswith("features:"):
            features_queued.append(True)

    def _restore_feature_counts(self, counts: dict[str, int], period_start: str) -> None:
        """Merge counts from a failed flush back in; consent off drops them."""
        with self._feature_lock:
            if not self._telemetry_enabled:
                return
            for name, value in counts.items():
                if name in self._feature_counts or len(self._feature_counts) < MAX_FEATURE_NAMES:
                    self._feature_counts[name] = self._feature_counts.get(name, 0) + value
            self._feature_period_start = period_start

    @staticmethod
    def _restore_heartbeat_date(home: Path, previous: str) -> None:
        if previous:
            write_heartbeat_date(home, previous)
        else:
            (home / "telemetry_heartbeat").unlink(missing_ok=True)

    async def _enqueue_telemetry(self, job_id: str, run_secrets: tuple[str, ...] | None = None) -> None:
        try:
            try:
                config = await run_sync(self._telemetry_config_check)
            except ValueError:
                return
            if not self._telemetry_enabled:
                return
            metrics = await run_sync(self.database.job_metrics_row, job_id)
            if metrics is None:
                return
            job = await run_sync(self.database.job_record, job_id)
            if not job:
                return
            project = await run_sync(self.database.project, job["project_id"])
            catalog = config
            if project is not None:
                catalog = await run_sync(self._project_catalog, Path(project.root), config)
            if run_secrets is None:
                run_secrets = tuple(value for target in catalog.targets for value in (*target.args, *target.env.values()))
            event = build_job_event(metrics, job, secrets=run_secrets,
                                    project=project.root if project else "", home=config.home)
            await run_sync(self._write_job_event, config.home, f"job:{job_id}", json.dumps(event, ensure_ascii=False))
        except Exception:
            log.warning("Telemetry enqueue failed", extra={"event": "telemetry.enqueue_failed", "job_id": job_id}, exc_info=True)

    def _write_job_event(self, home: Path, key: str, payload: str) -> None:
        """Queue the event exactly when consent is on, deciding under the purge lock."""
        with self._flush_lock:
            if not self._telemetry_enabled:
                return
            install_id(home)
            self.database.enqueue_telemetry(key, payload, utc_now())

    async def close(self) -> None:
        self._closing = True
        if self._retention_task is not None:
            self._retention_task.cancel()
            await asyncio.gather(self._retention_task, return_exceptions=True)
            self._retention_task = None
        if self._telemetry_task is not None:
            self._telemetry_task.cancel()
            await asyncio.gather(self._telemetry_task, return_exceptions=True)
            self._telemetry_task = None
        if self._feature_task is not None:
            self._feature_task.cancel()
            await asyncio.gather(self._feature_task, return_exceptions=True)
            self._feature_task = None
        if self._pricing_task is not None:
            self._pricing_task.cancel()
            await asyncio.gather(self._pricing_task, return_exceptions=True)
            self._pricing_task = None
        if self._flush_inflight is not None:
            await asyncio.gather(self._flush_inflight, return_exceptions=True)
            self._flush_inflight = None
        await self.scheduler.close()
        while self._telemetry_enqueues:
            await asyncio.gather(*tuple(self._telemetry_enqueues), return_exceptions=True)
        await self._flush_telemetry()
        self.target_executor.run_secrets.clear()
        await run_sync(self.database.close)
        log.info("Scheduler stopped", extra={"event": "scheduler.stopped"})

    def resolve_project(self, path: str) -> ProjectView:
        """Resolve the canonical Git root idempotently."""
        try:
            completed = subprocess.run(
                ["git", "-C", str(Path(path).expanduser()), "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, timeout=10, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            completed = None
        if completed is None or completed.returncode != 0 or not completed.stdout.strip():
            raise OrchestrationError(
                "Project path is not inside a Git repository.",
                code="invalid_path",
                next_action="Pass a path inside the project's Git repository.",
            )
        resolved = Path(completed.stdout.strip()).resolve()
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
        existing = next((project for project in self.database.projects() if project.root == root), None)
        if existing is not None:
            return existing
        try:
            return self.database.upsert_project(project_id=str(uuid.uuid4()), root=root)
        except sqlite3.IntegrityError:
            existing = next((project for project in self.database.projects() if project.root == root), None)
            if existing is None:
                raise
            return existing

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
                self._prepare_submission, job_id, project_id, workflow_name, prompt,
                session=session, profile=profile, fresh=fresh,
            )
        finally:
            # A cancelled request must not leave a committed job undispatched.
            await self._enqueue_record(job_id)
        await self._notify_job(job_id)
        log.info("Job queued", extra={"event": "job.queued", "project_id": project.id, "job_id": job_id, "workflow": workflow, "profile": selected_profile})
        return SubmissionResult(job_id=job_id, state="queued")

    def _prepare_submission(self, job_id: str, project_id: str, workflow_name: str, prompt: str, **options: Any) -> tuple[ProjectView, str, str]:
        # One critical section from the closing check to the job row, so that
        # shutdown_if_idle can never latch between admission and create_job.
        with self._lock:
            return self._admit_submission(job_id, project_id, workflow_name, prompt, **options)

    def _admit_submission(self, job_id: str, project_id: str, workflow_name: str, prompt: str, *, session: str = "", profile: str = "", fresh: bool = False, retry_of: str = "", target: str = "", after: str = "") -> tuple[ProjectView, str, str]:
        if self._closing:
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
        workflow, resolved_prompt = self._validate_request(workflow_name, prompt)
        try:
            with self._lock:
                catalog = self._project_catalog(Path(project.root), self._reload_catalog_locked())
                selected_profile = profile.strip() or catalog.default_profile
                plan = resolve_execution_plan(workflow, catalog, selected_profile)
                if retry_of:
                    plan = self._pin_retry_target(plan, selected_profile, target, after)
                self._ensure_candidates_available(plan)
        except OrchestrationError:
            raise
        except ValueError as exc:
            raise self._plan_error(exc) from exc
        self.database.create_job(
            job_id=job_id,
            project_id=project.id,
            workflow=workflow,
            profile=selected_profile,
            prompt=resolved_prompt,
            execution_plan_json=json.dumps(execution_plan_data(plan), ensure_ascii=False),
            session=session.strip() or workflow,
            fresh=fresh,
            retry_of=retry_of,
        )
        return project, workflow, selected_profile

    @staticmethod
    def _validate_request(workflow_name: str, prompt: str) -> tuple[str, str]:
        try:
            workflow = get_workflow(workflow_name)
            return workflow, validate_request(workflow, prompt)
        except ValueError as exc:
            raise OrchestrationError(
                str(exc),
                code="invalid_request",
                next_action="Correct the workflow or prompt and call submit again.",
            ) from exc

    def _pin_retry_target(self, plan: ExecutionPlan, selected_profile: str, target: str, after: str) -> ExecutionPlan:
        names = ", ".join(candidate.id for candidate in plan.targets)
        target_id = target
        if not target_id:
            ids = [candidate.id for candidate in plan.targets]
            following = plan.targets[ids.index(after) + 1:] if after in ids else plan.targets
            if not following:
                raise OrchestrationError(
                    "No target follows the job's target in profile order.",
                    code="targets_unavailable",
                    next_action=f"Call retry with target set to one of: {names}.",
                )
            self._ensure_candidates_available(replace(plan, targets=following))
            target_id = self._following_target(plan, after) or ""
        pinned = next((candidate for candidate in plan.targets if candidate.id == target_id), None)
        if pinned is None:
            raise OrchestrationError(
                f"Target {target_id!r} is not in profile {selected_profile}; profile targets: {names}.",
                code="invalid_request",
                next_action=f"Call retry with target set to one of: {names}.",
            )
        return replace(
            plan,
            selection=replace(plan.selection, targets=(pinned.id,)),
            targets=(pinned,),
            environment_targets=tuple(
                value for value in plan.environment_targets if value == pinned.id
            ),
        )

    @staticmethod
    def _plan_error(exc: ValueError) -> OrchestrationError:
        code = "unknown_profile" if "Unknown profile" in str(exc) else "config_invalid"
        action = (
            "Call list and choose an available profile."
            if code == "unknown_profile"
            else "Fix the project configuration in .refract/config.toml."
        )
        return OrchestrationError(sanitize_config_error(exc), code=code, next_action=action)

    def live_routing(self, job: JobView) -> dict[str, object]:
        kind = job.result.failure_kind
        if job.state == "succeeded":
            return {"failure_kind": kind, "retry": {"next_target": None}}
        retry: dict[str, object] = {"next_target": None}
        if kind in {"transient", "target_fatal", "circuit_open", "cancelled", "context_overflow"}:
            retry["next_target"] = self._next_target(job)
        return {"failure_kind": kind, "retry": retry}

    def _next_target(self, job: JobView) -> str | None:
        try:
            catalog = self.catalog_for_project(job.project_id)
            plan = resolve_execution_plan(job.workflow, catalog, job.profile)
        except (OrchestrationError, ValueError):
            return None
        return self._following_target(plan, job.target_id)

    def _following_target(self, plan: ExecutionPlan, after: str) -> str | None:
        """Return the next target after ``after`` in profile order whose circuit is closed."""
        ids = [target.id for target in plan.targets]
        start = ids.index(after) + 1 if after in ids else 0
        now = datetime.now(timezone.utc)
        for target in plan.targets[start:]:
            health = self.database.target_health(target_execution_key(target))
            if not self.target_executor.is_circuit_open(health.get("circuit_open_until", ""), now, health.get("probe_job_id", "")):
                return target.id
        return None

    async def wait(self, job_id: str, timeout_s: int = 0) -> JobView:
        job = await run_sync(self.database.job, job_id)
        if job is None:
            raise OrchestrationError(
                UNKNOWN_JOB_MESSAGE,
                code="unknown_job",
                next_action=_LIST_JOB_ID_ACTION,
            )
        if job.state in TERMINAL_STATES:
            await self.scheduler.wait(job_id, timeout_s)
            refreshed = await run_sync(self.database.job, job_id)
            if refreshed is None:
                raise OrchestrationError(f"Unknown job: {job_id}")
            return refreshed

        if self.ask_registry.has_pending(job_id):
            refreshed = await run_sync(self.database.job, job_id)
            if refreshed is None:
                raise OrchestrationError(f"Unknown job: {job_id}")
            return refreshed

        scheduler_task = asyncio.create_task(self.scheduler.wait(job_id, timeout_s))
        question_task = asyncio.create_task(self.ask_registry.wait_question(job_id, timeout_s))
        try:
            done, pending = await asyncio.wait(
                [scheduler_task, question_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                exc = task.exception()
                if exc is not None:
                    raise exc
        finally:
            for task in (scheduler_task, question_task):
                if not task.done():
                    task.cancel()
            for task in (scheduler_task, question_task):
                with suppress(asyncio.CancelledError, Exception):
                    await task

        refreshed = await run_sync(self.database.job, job_id)
        if refreshed is None:
            raise OrchestrationError(f"Unknown job: {job_id}")
        return refreshed

    async def job_answer(
        self, job_id: str, answer: str, expected_question_id: str | None = None
    ) -> ActionResult:
        job = await run_sync(self.database.job, job_id)
        if job is None:
            raise OrchestrationError(
                UNKNOWN_JOB_MESSAGE,
                code="unknown_job",
                next_action=_LIST_JOB_ID_ACTION,
            )
        if job.state in TERMINAL_STATES:
            raise OrchestrationError(
                f"Job {job_id} is in terminal state '{job.state}'.",
                code="invalid_state",
                next_action="Inspect using wait; use a new job if appropriate.",
            )
        cleaned_answer = answer if isinstance(answer, str) else ""
        if not cleaned_answer:
            raise OrchestrationError(
                "Answer must be a non-empty string.",
                code="invalid_request",
                next_action="Provide a non-empty answer string.",
            )
        if len(cleaned_answer) > MAX_ANSWER_LENGTH:
            raise OrchestrationError(
                f"Answer exceeds maximum length of {MAX_ANSWER_LENGTH} characters.",
                code="invalid_request",
                next_action=f"Provide an answer up to {MAX_ANSWER_LENGTH} characters.",
            )
        delivered = self.ask_registry.deliver_answer(
            job_id, cleaned_answer, expected_question_id=expected_question_id
        )
        if not delivered:
            raise OrchestrationError(
                f"No question is pending for job {job_id}, or it expired.",
                code="invalid_state",
                next_action="Inspect using wait; use a new job if appropriate.",
            )
        return ActionResult(success=True, job_id=job_id, state=job.state)

    async def cancel(self, job_id: str) -> ActionResult:
        self.ask_registry.revoke_token(job_id)
        # Reserve cancellation before yielding to a worker or starting dispatch.
        location = self.scheduler.cancel(job_id)
        job = await run_sync(self.database.job, job_id)
        if job is None:
            raise OrchestrationError(
                UNKNOWN_JOB_MESSAGE,
                code="unknown_job",
                next_action=_LIST_JOB_ID_ACTION,
            )
        if job.state == "queued":
            if location in {"queued", "missing"}:
                changed = await run_sync(self.database.finish_job, job_id, "cancelled")
                await self._job_terminal(job_id, "cancelled", changed)
                await self._notify_job(job_id)
                return ActionResult(success=True, job_id=job_id, state="cancelled")
            if location == "running":
                return ActionResult(success=True, job_id=job_id, state="running")
        if job.state == "cancelled" and location == "running":
            return ActionResult(success=True, job_id=job_id, state="cancelled")
        if job.state == "running" and location == "running":
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
        raise OrchestrationError("All candidate targets are temporarily unavailable.", code="targets_unavailable", next_action="Wait for a target to recover, then retry.", retry_after_s=min(delays))

    async def retry(self, job_id: str, target: str = "") -> SubmissionResult:
        new_id = str(uuid.uuid4())
        try:
            await run_sync(self._prepare_retry, new_id, job_id, target)
        finally:
            await self._enqueue_record(new_id)
        await self._notify_job(new_id)
        return SubmissionResult(job_id=new_id, state="queued")

    def _prepare_retry(self, new_id: str, job_id: str, target: str) -> None:
        job = self.database.job(job_id)
        if job is None:
            raise OrchestrationError(
                UNKNOWN_JOB_MESSAGE,
                code="unknown_job",
                next_action=_LIST_JOB_ID_ACTION,
            )
        if job.state not in {"succeeded", "failed", "cancelled", "interrupted"}:
            raise OrchestrationError(
                f"Job cannot be retried from state {job.state}.",
                code="invalid_state",
                next_action="Call wait or submit a new job.",
            )
        record = self.database.job_record(job_id) or {}
        self._prepare_submission(
            new_id, job.project_id, job.workflow, str(record.get("prompt", "")),
            session=job.session, profile=job.profile, fresh=bool(record.get("fresh", 0)),
            retry_of=job_id, target=target.strip(), after=job.target_id,
        )

    def status(self) -> DaemonStatusResult:
        return DaemonStatusResult(status="stopping" if self._closing else "running", workers=self.scheduler.workers, active_jobs=self.scheduler.active_jobs, queued_jobs=self.scheduler.queued_jobs)

    def shutdown_if_idle(self) -> dict[str, Any]:
        """Close admission and report ``stopping`` only when no job is queued or running."""
        with self._lock:
            counts = self.database.active_job_counts()
            running = max(counts["running"], self.scheduler.active_jobs)
            queued = max(counts["queued"], self.scheduler.queued_jobs)
            if running or queued:
                return {"stopping": False, "running": running, "queued": queued}
            self._closing = True
            return {"stopping": True, "running": 0, "queued": 0}

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
        with self._lock:
            self._publish_configuration_locked()

    def _publish_configuration_locked(self) -> None:
        """Publish off-loop; the caller holds the configuration lock."""
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
            with self._lock:
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

    def _project_catalog_snapshot(
        self, root: Path, base: DaemonConfig
    ) -> tuple[DaemonConfig, str]:
        config_path = root / ".refract" / "config.toml"
        for _ in range(3):
            before = _file_identity(config_path)
            before_digest = _file_digest(config_path)
            cached = self._project_catalogs.get(root)
            if cached is not None and cached[0] == before and cached[4] == before_digest and cached[1] is base:
                return cached[2], cached[3]
            catalog = load_project_config(root, base)
            after = _file_identity(config_path)
            if before != after or before_digest != _file_digest(config_path):
                continue
            # Bind sessions to environment configuration, not unrelated target
            # capacity. Environment values stay inside this keyed opaque digest.
            environment_config = {
                "targets": [
                    {"id": target.id, "env": target.env}
                    for target in sorted(catalog.targets, key=lambda item: item.id)
                ],
            }
            revision_payload = json.dumps(
                [environment_config, after], sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            revision = hmac.new(
                self._session_revision_secret, revision_payload, "sha256"
            ).hexdigest()
            self._project_catalogs[root] = (after, base, catalog, revision, before_digest)
            return catalog, revision
        raise ValueError("Project configuration changed during loading")

    def _project_catalog(self, root: Path, base: DaemonConfig) -> DaemonConfig:
        catalog, _ = self._project_catalog_snapshot(root, base)
        return catalog

    def _resolve_target_environment(self, project: ProjectView, target_id: str) -> tuple[dict[str, str], str]:
        """Resolve a marked target against the current project catalog off-loop."""
        with self._lock:
            catalog, revision = self._project_catalog_snapshot(
                Path(project.root), self._reload_catalog_locked()
            )
            target = next((item for item in catalog.targets if item.id == target_id), None)
            if target is None:
                raise ValueError("Unknown target")
            resolved = resolve_target_environment(catalog, target)
            return resolved, revision

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
            self._consent_stat = None
            # Invalid configuration counts as off.
            self._set_telemetry_enabled(False)
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
        self._catalog_stat = stat
        self._warn_ignored_keys(catalog)
        self._consent_stat = stat
        self._set_telemetry_enabled(telemetry_decision(catalog)[0])
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


def _file_digest(path: Path) -> str | None:
    """Hash the file so a same-size rewrite within one file-time tick still changes the cache key."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _file_identity(path: Path) -> tuple[int, int, int] | None:
    try:
        info = path.stat()
    except OSError:
        return None
    return (info.st_mtime_ns, info.st_size, info.st_ino)


__all__ = ["OrchestrationError", "Runtime"]
