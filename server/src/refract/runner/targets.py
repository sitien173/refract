"""Target capacity, session locks, selection, and the circuit breaker."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from refract.config import DaemonConfig, TargetConfig
from refract.store.database import Database
from refract.logging_setup import get_logger
from refract.models import TargetView
from refract.runner.drivers import DriverRegistry, DriverResult
from refract.runner.planning import ExecutionPlan, target_execution_key
from refract.scheduling.cancel import CancelEvent
from refract.store.pool import run_db, run_on

log = get_logger("targets")


class TargetPool:
    def __init__(self, config: DaemonConfig, database: Database, drivers: DriverRegistry) -> None:
        self.config = config
        self.database = database
        self.drivers = drivers
        self._target_semaphores: dict[str, asyncio.Semaphore] = {}
        self._target_active: dict[str, int] = {}
        self._target_users: dict[str, int] = {}
        # Jobs of one (project, session, workflow) run one at a time, across all attempts and targets.
        self._session_locks: dict[tuple[str, str, str], asyncio.Semaphore] = {}
        self._session_users: dict[tuple[str, str, str], int] = {}

    def refresh_configuration(self, config: DaemonConfig) -> None:
        """Adopt settings; occupied capacity drains before replacing its limit."""
        self.config = config
        self._target_semaphores = {
            key: semaphore for key, semaphore in self._target_semaphores.items()
            if self._target_users.get(key, 0)
        }

    async def _release_probe(self, target_key: str, job_id: str) -> None:
        try:
            await run_db(self.database.release_target_probe, target_key, job_id)
        except Exception:
            log.warning("Failed to release target probe", exc_info=True)

    async def _update_target_health(
        self, result: DriverResult, target_key: str, held_probe: bool, job_id: str,
    ) -> None:
        if result.outcome in {"CANCELLED", "REQUEST_FATAL"}:
            return
        if result.error_code == "context_overflow":
            return
        elif result.outcome == "TARGET_FATAL":
            await run_on(self.database.executor, self._record_failure, target_key, job_id,
                           immediate=True, failed_probe=False)
        elif result.outcome == "RETRYABLE":
            await run_on(self.database.executor, self._record_failure, target_key, job_id, failed_probe=held_probe)
        elif held_probe:
            return

    def eligible_targets(self, target_ids: tuple[str, ...], plan: ExecutionPlan) -> list[str]:
        """Targets of `target_ids`, in order, that are available and have a closed circuit; claims nothing."""
        now = datetime.now(timezone.utc)
        eligible = []
        for target_id in target_ids:
            target = plan.target(target_id)
            health = self.database.target_health(target_execution_key(target))
            open_until, probe_job = str(health["circuit_open_until"]), str(health.get("probe_job_id", ""))
            if self.drivers.available(target) and not self.is_circuit_open(open_until, now, probe_job):
                eligible.append(target_id)
        return eligible

    def readmit_target(self, target: TargetConfig, plan: ExecutionPlan, job_id: str) -> tuple[bool, bool]:
        """Admit a target the job already ran on for another attempt: (admitted, holds the half-open probe)."""
        claimed: list[str] = []
        key = target_execution_key(target)
        admitted = self._admit_target(target, key, datetime.now(timezone.utc), job_id, claimed)
        return admitted, bool(claimed)

    def _release_capacity(self, target_id: str) -> None:
        self._target_users[target_id] -= 1
        if not self._target_users[target_id]:
            self._target_users.pop(target_id)
            self._target_semaphores.pop(target_id, None)
            self._target_active.pop(target_id, None)

    @asynccontextmanager
    async def hold_session(
        self, project_id: str, session: str, workflow: str, cancel_event: CancelEvent,
    ) -> AsyncIterator[bool]:
        """Hold the session lock for a whole job; yields False when cancelled before it was taken."""
        key = (project_id, session, workflow)
        lock = self._session_locks.setdefault(key, asyncio.Semaphore(1))
        self._session_users[key] = self._session_users.get(key, 0) + 1
        locked = False
        try:
            locked = await self._acquire_target(lock, cancel_event)
            yield locked
        finally:
            if locked:
                lock.release()
            self._session_users[key] -= 1
            if not self._session_users[key]:
                self._session_users.pop(key)
                self._session_locks.pop(key, None)

    @staticmethod
    async def _acquire_target(semaphore: asyncio.Semaphore, cancel_event: CancelEvent) -> bool:
        if cancel_event.is_set():
            return False
        acquire = asyncio.create_task(semaphore.acquire())
        cancelled = asyncio.create_task(cancel_event.wait_async())
        accepted = False
        try:
            await asyncio.wait((acquire, cancelled), return_when=asyncio.FIRST_COMPLETED)
            accepted = acquire.done() and not cancel_event.is_set()
            return accepted
        finally:
            acquire.cancel()
            cancelled.cancel()
            await asyncio.gather(acquire, cancelled, return_exceptions=True)
            if not accepted and not acquire.cancelled() and acquire.exception() is None:
                semaphore.release()


    def _select_target(self, target_ids: tuple[str, ...], plan: ExecutionPlan, job_id: str = "") -> tuple[TargetConfig | None, int]:
        now = datetime.now(timezone.utc)
        healthy: list[TargetConfig] = []
        claimed_probes: list[str] = []
        rejected = 0
        for target_id in target_ids:
            target = plan.target(target_id)
            target_key = target_execution_key(target)
            if not self._admit_target(target, target_key, now, job_id, claimed_probes):
                rejected += 1
                continue
            healthy.append(target)
            if self._target_active.get(target.id, 0) < target.max_concurrency:
                self._release_unselected_probes(claimed_probes, target_key, job_id)
                return target, rejected
        if not healthy:
            return None, rejected
        selected = healthy[0]
        self._release_unselected_probes(claimed_probes, target_execution_key(selected), job_id)
        return selected, rejected

    def _admit_target(
        self, target: TargetConfig, target_key: str, now: datetime,
        job_id: str, claimed_probes: list[str],
    ) -> bool:
        health = self.database.target_health(target_key)
        open_until = str(health["circuit_open_until"])
        probe_job = str(health.get("probe_job_id", ""))
        try:
            half_open = bool(open_until) and datetime.fromisoformat(open_until) <= now and not probe_job
        except ValueError:
            half_open = False
        if self.is_circuit_open(open_until, now, probe_job) or not self.drivers.available(target):
            return False
        if half_open:
            if not job_id or not self.database.claim_target_probe(target_key, job_id, now.isoformat()):
                return False
            claimed_probes.append(target_key)
        return True

    def _release_unselected_probes(self, claimed_probes: list[str], selected_key: str, job_id: str) -> None:
        for claimed_key in claimed_probes:
            if claimed_key != selected_key:
                self.database.release_target_probe(claimed_key, job_id)

    def _record_failure(self, target_key: str, job_id: str, *, immediate: bool = False, failed_probe: bool = False) -> None:
        self.database.record_target_failure(
            target_key,
            threshold=self.config.breaker_failure_threshold,
            base_cooldown_s=self.config.breaker_base_cooldown_s,
            max_cooldown_s=self.config.breaker_max_cooldown_s,
            failed_probe=failed_probe,
            immediate=immediate,
            job_id=job_id,
        )

    @staticmethod
    def is_circuit_open(value: str, now: datetime, probe_job_id: str = "") -> bool:
        if probe_job_id:
            return True
        if not value:
            return False
        try:
            return datetime.fromisoformat(value) > now
        except ValueError:
            return False

    def views(self, targets: tuple[TargetConfig, ...]) -> list[TargetView]:
        now = datetime.now(timezone.utc)
        result: list[TargetView] = []
        for target in targets:
            target_key = target_execution_key(target)
            health = self.database.target_health(target_key)
            open_until = str(health["circuit_open_until"])
            probe_job_id = str(health["probe_job_id"])
            probing = bool(probe_job_id)
            if probing:
                breaker_state = "half_open"
            elif not open_until:
                breaker_state = "closed"
            elif self.is_circuit_open(open_until, now):
                breaker_state = "open"
            else:
                breaker_state = "half_open"
            result.append(TargetView(id=target.id, model=target.model, max_concurrency=target.max_concurrency, active=self._target_active.get(target.id, 0), healthy=self.drivers.available(target) and not self.is_circuit_open(open_until, now), circuit_open_until=open_until, breaker_state=breaker_state, cooldown_s=int(health["cooldown_s"]), probing=probing))
        return result


