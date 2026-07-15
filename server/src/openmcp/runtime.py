"""Durable project orchestration runtime."""

from __future__ import annotations

import asyncio
import json
import random
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from openmcp.config import DaemonConfig, RouteConfig, TargetConfig
from openmcp.database import Database, utc_now
from openmcp.drivers import DriverRegistry, DriverResult
from openmcp.logging_setup import get_logger
from openmcp.models import (
    ActionResult,
    JobView,
    ModelTargetView,
    ProjectView,
    SubmissionResult,
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
    "default": "forge",
    "coding": "forge",
    "backend": "forge",
    "frontend": "canvas",
    "review": "sentinel",
    "reasoning": "sage",
}


class RuntimeError(ValueError):
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
        self._target_semaphores = {
            target.id: asyncio.Semaphore(target.max_concurrency)
            for target in config.targets
        }
        self._target_active = {target.id: 0 for target in config.targets}
        self._targets = {target.id: target for target in config.targets}
        self._routes = {route.id: route for route in config.routes}
        self._routing_profiles = config.routing_profiles or {
            config.default_routing_profile: {
                route_id: route_id for route_id in self._routes
            }
        }
        self._logical_routes = {
            role
            for mapping in self._routing_profiles.values()
            for role in mapping
        }
        self._closing = False

    async def start(self) -> None:
        self._closing = False
        interrupted = self.database.interrupt_active_jobs()
        if interrupted:
            log.warning("Marked %d active records interrupted", interrupted)
        self._workers = [
            asyncio.create_task(self._worker(), name=f"openmcp-worker-{index}")
            for index in range(self.config.max_jobs)
        ]
        for job_id in self.database.queued_job_ids():
            self._completion_events[job_id] = asyncio.Event()
            await self._queue.put(job_id)

    async def close(self) -> None:
        self._closing = True
        for event in self._cancel_events.values():
            event.set()
        for _ in self._workers:
            await self._queue.put(None)
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self.database.close()

    def register_project(self, path: str, alias: str = "") -> ProjectView:
        try:
            state = inspect_repository(Path(path))
        except WorkspaceError as exc:
            raise RuntimeError(str(exc)) from exc
        if not state.clean:
            raise RuntimeError("Project worktree must be clean before registration")
        resolved_alias = alias.strip() or state.root.name
        if not resolved_alias:
            raise RuntimeError("Project alias cannot be empty")
        try:
            return self.database.upsert_project(
                project_id=str(uuid.uuid4()),
                alias=resolved_alias,
                root=state.root.as_posix(),
                head_commit=state.head,
                clean=state.clean,
            )
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                raise RuntimeError(f"Project alias already exists: {resolved_alias}") from exc
            raise

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
            raise RuntimeError(f"Unknown project: {project_id}")
        try:
            state = inspect_repository(Path(project.root))
        except WorkspaceError as exc:
            raise RuntimeError(str(exc)) from exc
        if not state.clean:
            raise RuntimeError("Project worktree must be clean before submission")
        self.database.upsert_project(
            project_id=project.id,
            alias=project.alias,
            root=state.root.as_posix(),
            head_commit=state.head,
            clean=True,
        )
        selected_profile = (
            routing_profile.strip() or self.config.default_routing_profile
        )
        profile_routes = self._routing_profiles.get(selected_profile)
        if profile_routes is None:
            raise RuntimeError(f"Unknown routing profile: {selected_profile}")
        workflow = load_workflow(
            Path(project.root),
            workflow_name,
            self._logical_routes,
        )
        missing_routes = {
            stage.route for stage in workflow.stages if stage.route not in profile_routes
        }
        if missing_routes:
            raise RuntimeError(
                f"Routing profile {selected_profile!r} does not map roles: "
                f"{sorted(missing_routes)}"
            )
        validate_inputs(workflow, inputs)
        base_commit = state.head
        integration_base = state.head
        if parent_job_id:
            parent = self.database.job(parent_job_id)
            if parent is None or parent.project_id != project.id:
                raise RuntimeError(f"Unknown parent job: {parent_job_id}")
            if parent.state != "succeeded" or not parent.result.commit:
                raise RuntimeError("Parent job must be successful")
            if state.head != parent.integration_base:
                raise RuntimeError("Project HEAD changed after the parent job started")
            base_commit = parent.result.commit
            integration_base = parent.integration_base
        job_id = str(uuid.uuid4())
        try:
            worktree, branch = self.workspaces.create_job(
                state.root,
                job_id,
                base_commit,
            )
            self.database.create_job(
                job_id=job_id,
                project_id=project.id,
                workflow=workflow.name,
                routing_profile=selected_profile,
                workflow_json=json.dumps(workflow_data(workflow), ensure_ascii=False),
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
        except Exception:
            candidate = self.config.worktrees_path / job_id / "primary"
            if candidate.exists():
                self.workspaces.remove(state.root, candidate)
            raise
        self._completion_events[job_id] = asyncio.Event()
        await self._queue.put(job_id)
        return SubmissionResult(job_id=job_id, state="queued")

    async def wait(self, job_id: str, timeout_s: int = 0) -> JobView:
        job = self.database.job(job_id)
        if job is None:
            raise RuntimeError(f"Unknown job: {job_id}")
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
            raise RuntimeError(f"Unknown job: {job_id}")
        return refreshed

    def cancel(self, job_id: str) -> ActionResult:
        job = self.database.job(job_id)
        if job is None:
            raise RuntimeError(f"Unknown job: {job_id}")
        if job.state == "queued":
            self.database.set_job_state(job_id, "cancelled")
            self._signal_completion(job_id)
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
        return ActionResult(success=True, job_id=job_id, state="running")

    async def retry(self, job_id: str, from_stage: str = "") -> SubmissionResult:
        job = self.database.job(job_id)
        record = self.database.job_record(job_id)
        if job is None or record is None:
            raise RuntimeError(f"Unknown job: {job_id}")
        if job.state not in {"failed", "cancelled", "interrupted"}:
            raise RuntimeError(f"Job cannot be retried from {job.state}")
        stages = self.database.stage_records(job_id)
        selected = None
        if from_stage:
            selected = next((stage for stage in stages if stage["id"] == from_stage), None)
            if selected is None:
                raise RuntimeError(f"Unknown stage: {from_stage}")
        else:
            selected = next((stage for stage in stages if stage["state"] != "succeeded"), None)
            selected = selected or stages[-1]
        project = self.database.project(job.project_id)
        if project is None:
            raise RuntimeError(f"Unknown project: {job.project_id}")
        worktree = Path(record["worktree"])
        try:
            self.workspaces.restore_job(Path(project.root), worktree, record["branch"])
            start_commit = selected["start_commit"] or record["base_commit"]
            patch_path = self.config.runs_path / job_id / f"retry-{utc_now().replace(':', '')}.patch"
            if self.workspaces.archive_patch(worktree, patch_path, start_commit):
                self.database.add_artifact(job_id, "retry_patch", patch_path.as_posix())
            self.workspaces.reset(worktree, start_commit)
        except WorkspaceError as exc:
            raise RuntimeError(str(exc)) from exc
        self.database.reset_retry(job_id, int(selected["ordinal"]))
        self._completion_events[job_id] = asyncio.Event()
        await self._queue.put(job_id)
        return SubmissionResult(job_id=job_id, state="queued")

    def integrate(self, job_id: str) -> ActionResult:
        job = self.database.job(job_id)
        record = self.database.job_record(job_id)
        if job is None or record is None:
            raise RuntimeError(f"Unknown job: {job_id}")
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
            raise RuntimeError(f"Unknown project: {job.project_id}")
        try:
            self.workspaces.integrate(
                Path(project.root),
                job.integration_base,
                job.result.commit,
            )
        except WorkspaceError as exc:
            self.database.set_job_state(job_id, "integration_conflict", error=str(exc))
            self._signal_completion(job_id)
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
        return ActionResult(success=True, job_id=job_id, state="integrated")

    def targets(self) -> list[ModelTargetView]:
        now = datetime.now(timezone.utc)
        views: list[ModelTargetView] = []
        for target in self.config.targets:
            health = self.database.target_health(target.id)
            open_until = str(health["circuit_open_until"])
            healthy = self.drivers.available(target) and not self._is_open(open_until, now)
            views.append(
                ModelTargetView(
                    id=target.id,
                    model=target.model,
                    capabilities=list(target.capabilities),
                    max_concurrency=target.max_concurrency,
                    active=self._target_active[target.id],
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
                    await self._run_job(job_id)
            except Exception as exc:
                log.exception("Unhandled scheduler failure for job %s", job_id)
                if job_id is not None:
                    self.database.set_job_state(job_id, "failed", error=f"scheduler: {exc}")
                    self._signal_completion(job_id)
            finally:
                self._queue.task_done()

    async def _run_job(self, job_id: str) -> None:
        record = self.database.job_record(job_id)
        if record is None:
            return
        if not record["routing_profile"]:
            record["routing_profile"] = self.config.default_routing_profile
            self.database.set_job_routing_profile(
                job_id,
                record["routing_profile"],
            )
        project = self.database.project(record["project_id"])
        if project is None:
            self.database.set_job_state(job_id, "failed", error="Project was removed")
            self._signal_completion(job_id)
            return
        workflow_document = json.loads(record["workflow_json"])
        for stage in workflow_document.get("stages", {}).values():
            if isinstance(stage, dict):
                stage["route"] = _LEGACY_ROLES.get(
                    stage.get("route"),
                    stage.get("route"),
                )
        workflow = parse_workflow(workflow_document, self._logical_routes)
        inputs = json.loads(record["inputs_json"])
        worktree = Path(record["worktree"])
        cancel_event = threading.Event()
        self._cancel_events[job_id] = cancel_event
        self.database.set_job_state(job_id, "running")
        try:
            while True:
                if cancel_event.is_set():
                    state = "interrupted" if self._closing else "cancelled"
                    self.database.set_job_state(job_id, state)
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
                    raise RuntimeError("Workflow has no runnable stages")
                readable = [stage for stage in ready if stage.mode == "read"]
                if readable:
                    results = await asyncio.gather(
                        *(
                            self._run_stage(
                                job_id,
                                project,
                                record,
                                workflow,
                                inputs,
                                stage,
                                cancel_event,
                            )
                            for stage in readable
                        )
                    )
                    if not all(results):
                        return
                    continue
                if not await self._run_stage(
                    job_id,
                    project,
                    record,
                    workflow,
                    inputs,
                    ready[0],
                    cancel_event,
                ):
                    return
            stages = self.database.stage_records(job_id)
            result_text = stages[-1]["text"] if stages else ""
            result_commit = self.workspaces.head(worktree)
            self.database.set_job_result(job_id, text=result_text, commit=result_commit)
            self.database.set_job_state(job_id, "succeeded")
            if all(stage.mode == "read" for stage in workflow.stages):
                self.workspaces.discard_job(
                    Path(project.root),
                    worktree,
                    record["branch"],
                )
        except WorkspaceError as exc:
            self.database.set_job_state(job_id, "failed", error=str(exc))
        finally:
            self._cancel_events.pop(job_id, None)
            self._signal_completion(job_id)

    async def _run_stage(
        self,
        job_id: str,
        project: ProjectView,
        job: dict[str, Any],
        workflow: WorkflowSpec,
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

        async def run_worker(worker: int) -> dict[str, Any]:
            reader: Path | None = None
            if stage.mode == "read":
                reader = self.workspaces.create_reader(
                    Path(project.root),
                    job_id,
                    stage.id,
                    worker,
                    start_commit,
                )
                cwd = reader
            else:
                cwd = primary
            try:
                result, target_id = await self._execute_with_route(
                    job_id=job_id,
                    project=project,
                    context_key=job["context_key"],
                    routing_profile=job["routing_profile"],
                    stage=stage,
                    prompt=prompt,
                    cwd=cwd,
                    cancel_event=cancel_event,
                )
                return {
                    "outcome": result.outcome,
                    "text": result.text,
                    "error": result.error,
                    "target_id": target_id,
                    "session_id": result.session_id,
                }
            finally:
                if reader is not None:
                    self.workspaces.remove(Path(project.root), reader)

        outputs = await asyncio.gather(*(run_worker(index) for index in range(stage.fanout)))
        target_ids = ",".join(output["target_id"] for output in outputs)
        errors = [output["error"] for output in outputs if output["outcome"] != "SUCCESS"]
        if errors:
            if stage.mode == "write":
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
            return False

        commit = start_commit
        if stage.mode == "write":
            message = str(inputs.get("commit_message", "")).strip()
            commit = self.workspaces.commit(
                primary,
                job_id,
                stage.id,
                message=message,
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
        return True

    async def _execute_with_route(
        self,
        *,
        job_id: str,
        project: ProjectView,
        context_key: str,
        routing_profile: str,
        stage: StageSpec,
        prompt: str,
        cwd: Path,
        cancel_event: threading.Event,
    ) -> tuple[DriverResult, str]:
        route_id = self._routing_profiles[routing_profile][stage.route]
        route = self._routes[route_id]
        attempted: set[str] = set()
        last_target_id = ""
        last = DriverResult("TARGET_FATAL", "", "", "No healthy target", "no_target")
        for attempt in range(route.max_attempts):
            target = self._select_target(route, attempted)
            if target is None:
                break
            attempted.add(target.id)
            last_target_id = target.id
            session_id = self.database.session(project.id, context_key, stage.context, target.id)
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
            semaphore = self._target_semaphores[target.id]
            async with semaphore:
                self._target_active[target.id] += 1
                try:
                    self.database.set_stage_state(
                        job_id,
                        stage.id,
                        "running",
                        target_id=target.id,
                        increment_attempts=True,
                    )
                    last = await self.drivers.execute(
                        target=target,
                        prompt=effective_prompt,
                        cwd=cwd,
                        session_id=session_id,
                        timeout_s=stage.timeout_s or route.timeout_s,
                        cancel_event=cancel_event,
                    )
                finally:
                    self._target_active[target.id] -= 1
            if last.outcome == "SUCCESS":
                self.database.record_target_success(target.id)
                self.database.append_turn(
                    project_id=project.id,
                    context_key=context_key,
                    role=stage.context,
                    target_id=target.id,
                    session_id=last.session_id,
                    prompt=prompt,
                    response=last.text,
                )
                return last, target.id
            if last.outcome in {"CANCELLED", "REQUEST_FATAL"}:
                return last, target.id
            health = self.database.target_health(target.id)
            circuit_open_until = ""
            if int(health["consecutive_failures"]) + 1 >= 3:
                circuit_open_until = (
                    datetime.now(timezone.utc) + timedelta(seconds=60)
                ).isoformat()
            self.database.record_target_failure(target.id, circuit_open_until)
            if attempt + 1 < route.max_attempts:
                delay = min(8.0, 2.0**attempt) * random.uniform(0.8, 1.2)
                await asyncio.sleep(delay)
        return last, last_target_id

    def _select_target(self, route: RouteConfig, attempted: set[str]) -> TargetConfig | None:
        now = datetime.now(timezone.utc)
        candidates: list[tuple[float, int, int, TargetConfig]] = []
        for order, target_id in enumerate(route.targets):
            target = self._targets[target_id]
            if target.id in attempted:
                continue
            if not set(route.requires).issubset(target.capabilities):
                continue
            health = self.database.target_health(target.id)
            if self._is_open(str(health["circuit_open_until"]), now):
                continue
            if not self.drivers.available(target):
                continue
            load = self._target_active[target.id] / target.max_concurrency
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


__all__ = ["Runtime", "RuntimeError"]
