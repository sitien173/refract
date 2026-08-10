"""Direct job lifecycle and target execution."""

from __future__ import annotations

import asyncio
import json
import random
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from openmcp.config import DaemonConfig, TargetConfig
from openmcp.database import Database
from openmcp.drivers import DriverRegistry, DriverResult
from openmcp.logging_setup import get_logger, log_context
from openmcp.models import ProjectView, TargetView, job_resource_uri
from openmcp.planning import ExecutionPlan, parse_execution_plan, target_execution_key


log = get_logger("execution")


@dataclass(slots=True, frozen=True)
class TargetExecutionResult:
    result: DriverResult
    target_id: str


class TargetExecutor:
    def __init__(self, config: DaemonConfig, database: Database, drivers: DriverRegistry) -> None:
        self.config = config
        self.database = database
        self.drivers = drivers
        self._target_semaphores: dict[str, asyncio.Semaphore] = {}
        self._target_active: dict[str, int] = {}

    async def execute(self, *, job_id: str, project: ProjectView, workflow: str, context_key: str, plan: ExecutionPlan, prompt: str, cwd: Path, cancel_event: threading.Event) -> TargetExecutionResult:
        attempted: set[str] = set()
        last_target_id = ""
        last = DriverResult("TARGET_FATAL", "", "", "No healthy target", "no_target")
        for attempt in range(plan.selection.max_attempts):
            if cancel_event.is_set():
                return TargetExecutionResult(
                    DriverResult("CANCELLED", "", "", "cancelled", "cancelled"),
                    last_target_id,
                )
            target = self._select_target(plan.selection.targets, plan, attempted)
            if target is None and attempted:
                attempted.clear()
                target = self._select_target(plan.selection.targets, plan, attempted)
            if target is None:
                break
            attempted.add(target.id)
            last_target_id = target.id
            target_key = target_execution_key(target)
            session_id = self.database.session(project.id, context_key, workflow, target_key)
            effective_prompt = prompt if session_id else self._with_history(project.id, context_key, workflow, prompt)
            self.database.event(job_id, "target.selected", {"workflow": workflow, "target": target.id, "attempt": attempt + 1})
            semaphore = self._target_semaphores.setdefault(target_key, asyncio.Semaphore(target.max_concurrency))
            self._target_active.setdefault(target_key, 0)
            if not await self._acquire_target(semaphore, cancel_event):
                return TargetExecutionResult(
                    DriverResult("CANCELLED", "", "", "cancelled", "cancelled"),
                    target.id,
                )
            self.database.record_job_attempt(job_id, target.id)
            started_at = time.monotonic()
            log.info("Target attempt started", extra={"event": "target.attempt_started", "job_id": job_id, "target_id": target.id, "profile": plan.profile, "workflow": workflow, "attempt": attempt + 1, "timeout_s": plan.selection.timeout_s, "resumed_session": bool(session_id)})
            self._target_active[target_key] += 1
            try:
                with log_context(target_id=target.id):
                    last = await self.drivers.execute(target=target, prompt=effective_prompt, cwd=cwd, session_id=session_id, timeout_s=plan.selection.timeout_s, cancel_event=cancel_event)
            finally:
                self._target_active[target_key] -= 1
                semaphore.release()
            self.database.event(job_id, "target.attempt_finished", {"workflow": workflow, "target": target.id, "attempt": attempt + 1, "outcome": last.outcome, "error_code": last.error_code})
            log.info("Target attempt finished", extra={"event": "target.attempt_finished", "job_id": job_id, "target_id": target.id, "workflow": workflow, "attempt": attempt + 1, "outcome": last.outcome, "error_code": last.error_code, "duration_ms": round((time.monotonic() - started_at) * 1000, 2)})
            if last.outcome == "SUCCESS":
                self.database.record_target_success(target_key)
                self.database.append_turn(project_id=project.id, context_key=context_key, role=workflow, target_id=target.id, target_key=target_key, session_id=last.session_id, prompt=prompt, response=last.text)
                return TargetExecutionResult(last, target.id)
            if last.outcome in {"CANCELLED", "REQUEST_FATAL"}:
                return TargetExecutionResult(last, target.id)
            self._record_failure(target_key)
            if attempt + 1 < plan.selection.max_attempts:
                delay = min(8.0, 2.0**attempt) * random.uniform(0.8, 1.2)
                self.database.event(job_id, "target.retry_scheduled", {"workflow": workflow, "target": target.id, "attempt": attempt + 1, "delay_s": round(delay, 3)})
                log.info("Retrying target", extra={"event": "target.retry_scheduled", "job_id": job_id, "target_id": target.id, "workflow": workflow, "delay_s": round(delay, 3)})
                if await asyncio.to_thread(cancel_event.wait, delay):
                    break
        return TargetExecutionResult(last, last_target_id)

    @staticmethod
    async def _acquire_target(semaphore: asyncio.Semaphore, cancel_event: threading.Event) -> bool:
        while not cancel_event.is_set():
            try:
                await asyncio.wait_for(semaphore.acquire(), 0.1)
            except TimeoutError:
                continue
            if cancel_event.is_set():
                semaphore.release()
                return False
            return True
        return False

    def _select_target(self, target_ids: tuple[str, ...], plan: ExecutionPlan, attempted: set[str]) -> TargetConfig | None:
        now = datetime.now(timezone.utc)
        healthy: list[TargetConfig] = []
        for target_id in target_ids:
            target = plan.target(target_id)
            if target.id in attempted:
                continue
            target_key = target_execution_key(target)
            health = self.database.target_health(target_key)
            if self._is_open(str(health["circuit_open_until"]), now) or not self.drivers.available(target):
                continue
            healthy.append(target)
            if self._target_active.get(target_key, 0) < target.max_concurrency:
                return target
        return healthy[0] if healthy else None

    def _record_failure(self, target_key: str) -> None:
        health = self.database.target_health(target_key)
        circuit_open_until = ""
        if int(health["consecutive_failures"]) + 1 >= 3:
            circuit_open_until = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()
        self.database.record_target_failure(target_key, circuit_open_until)

    @staticmethod
    def _is_open(value: str, now: datetime) -> bool:
        if not value:
            return False
        try:
            return datetime.fromisoformat(value) > now
        except ValueError:
            return False

    def _with_history(self, project_id: str, context_key: str, role: str, prompt: str) -> str:
        turns = self.database.recent_turns(project_id, context_key, role, self.config.history_turns)
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
        return f"Previous context:\n\n{'\n\n---\n\n'.join(blocks)}\n\nCurrent request:\n\n{prompt}"

    def views(self, targets: tuple[TargetConfig, ...]) -> list[TargetView]:
        now = datetime.now(timezone.utc)
        result: list[TargetView] = []
        for target in targets:
            target_key = target_execution_key(target)
            health = self.database.target_health(target_key)
            open_until = str(health["circuit_open_until"])
            result.append(TargetView(id=target.id, model=target.model, max_concurrency=target.max_concurrency, active=self._target_active.get(target_key, 0), healthy=self.drivers.available(target) and not self._is_open(open_until, now), circuit_open_until=open_until))
        return result


JobNotifier = Callable[[str], Awaitable[None]]


async def _noop_notifier(_: str) -> None:
    return None


class JobRunner:
    def __init__(
        self,
        database: Database,
        targets: TargetExecutor,
        *,
        is_closing: Callable[[], bool],
        notifier: JobNotifier | None = None,
    ) -> None:
        self.database = database
        self.targets = targets
        self.is_closing = is_closing
        self.notifier = notifier or _noop_notifier

    async def _notify(self, job_id: str) -> None:
        try:
            await self.notifier(job_resource_uri(job_id))
        except Exception:
            log.warning(
                "Job resource notification failed",
                extra={"event": "job.resource_notification_failed", "job_id": job_id},
                exc_info=True,
            )

    async def run(self, job_id: str, cancel_event: threading.Event) -> None:
        started_at = time.monotonic()
        record = self.database.job_record(job_id)
        if record is None or record["state"] != "queued":
            return
        project_id = str(record["project_id"])
        project = self.database.project(project_id)
        if project is None:
            self.database.finish_job(job_id, "failed", error="Project was removed")
            await self._notify(job_id)
            return
        root = Path(project.root)
        log.info("Job started", extra={"event": "job.started", "job_id": job_id, "project_id": project.id, "workflow": record["workflow"]})
        final_state = "failed"
        try:
            self.database.start_job(job_id)
            await self._notify(job_id)
            plan = parse_execution_plan(json.loads(record["execution_plan_json"]))
            execution = await self.targets.execute(job_id=job_id, project=project, workflow=record["workflow"], context_key=record["context_key"], plan=plan, prompt=record["prompt"], cwd=root, cancel_event=cancel_event)
            if execution.result.outcome != "SUCCESS" or cancel_event.is_set():
                final_state = "interrupted" if cancel_event.is_set() and self.is_closing() else "cancelled" if cancel_event.is_set() else "failed"
                raise RuntimeError(execution.result.error or execution.result.outcome)
            self.database.finish_job(job_id, "succeeded", text=execution.result.text, target_id=execution.target_id)
            await self._notify(job_id)
        except Exception as exc:
            if not isinstance(exc, RuntimeError):
                log.exception(
                    "Unexpected job failure",
                    extra={"event": "job.exception", "job_id": job_id},
                )
            error = str(exc)
            self.database.finish_job(job_id, final_state, error=error)
            await self._notify(job_id)
        finally:
            completed = self.database.job(job_id)
            log.info("Job finished", extra={"event": "job.finished", "job_id": job_id, "project_id": project_id, "state": completed.state if completed else "unknown", "duration_ms": round((time.monotonic() - started_at) * 1000, 2)})


__all__ = ["JobNotifier", "JobRunner", "TargetExecutor", "TargetExecutionResult"]
