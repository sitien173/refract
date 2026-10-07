from __future__ import annotations

import asyncio
from collections.abc import Callable
import inspect
import json
import subprocess
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from openmcp.config import NotificationsConfig, TargetConfig, TargetSelection
from openmcp.database import Database
from openmcp.drivers import DriverResult
from openmcp.planning import execution_plan_data, resolve_execution_plan, target_execution_key
from openmcp.runtime import OrchestrationError, Runtime
from openmcp.workflows import get_workflow
from tests.orchestration_helpers import BlockingDrivers, FakeDrivers, config, git, repository


def test_runtime_submit_signature_omits_commit_message() -> None:
    assert "commit_message" not in inspect.signature(Runtime.submit).parameters
    assert "depends_on" in inspect.signature(Runtime.submit).parameters


@pytest.mark.asyncio
async def test_global_project_and_target_capacities_apply_together(tmp_path) -> None:
    (tmp_path / "project-a").mkdir()
    (tmp_path / "project-b").mkdir()
    root_a = repository(tmp_path / "project-a")
    root_b = repository(tmp_path / "project-b")
    first_driver_started = asyncio.Event()
    second_runner_started = asyncio.Event()
    release_drivers = asyncio.Event()
    second_job_id = ""

    class CapacityDrivers(FakeDrivers):
        def __init__(self) -> None:
            super().__init__()
            self.active = 0
            self.peak_active = 0
            self.calls = 0

        async def execute(self, **kwargs) -> DriverResult:
            self.calls += 1
            self.active += 1
            self.peak_active = max(self.peak_active, self.active)
            if self.calls == 1:
                first_driver_started.set()
            try:
                await release_drivers.wait()
                return DriverResult("SUCCESS", "", "done", "", "")
            finally:
                self.active -= 1

    runtime_holder: dict[str, Runtime] = {}
    running_job_ids: set[str] = set()

    async def notify(uri: str) -> None:
        runtime_value = runtime_holder.get("runtime")
        if runtime_value is None or not second_job_id:
            return
        job_id = uri.removeprefix("openmcp://jobs/")
        record = runtime_value.database.job_record(job_id)
        if record and record["state"] == "running":
            running_job_ids.add(job_id)
            if job_id == second_job_id:
                second_runner_started.set()

    target = TargetConfig(
        id="safe-reader", backend="pi", isolated=True, read_only=True, max_concurrency=1
    )
    catalog = replace(
        config(tmp_path / "home", (target,)), max_jobs=2, max_project_readers=2
    )
    runtime = Runtime(catalog, notifier=notify)
    runtime_holder["runtime"] = runtime
    drivers = CapacityDrivers()
    runtime.drivers = drivers
    await runtime.start()
    try:
        project_a = runtime.register_project(str(root_a), "a")
        project_b = runtime.register_project(str(root_b), "b")
        first = await runtime.submit(project_a.id, "consult", "first", context_key="first")
        await first_driver_started.wait()
        second = await runtime.submit(project_a.id, "consult", "second", context_key="second")
        second_job_id = second.job_id
        if second_job_id in running_job_ids:
            second_runner_started.set()
        await asyncio.wait_for(second_runner_started.wait(), 2)
        assert runtime.scheduler.active_jobs == 2
        assert drivers.calls == 1

        third = await runtime.submit(project_a.id, "consult", "third", context_key="third")
        fourth = await runtime.submit(project_b.id, "consult", "fourth", context_key="fourth")
        assert runtime.database.job(third.job_id).state == "queued"
        assert runtime.database.job(fourth.job_id).state == "queued"
        assert runtime.waiting_metadata(third.job_id)[1] == "waiting for project reader capacity"
        assert runtime.waiting_metadata(fourth.job_id)[1] == "waiting for global worker capacity"

        release_drivers.set()
        for submission in (first, second, third, fourth):
            assert (await runtime.wait(submission.job_id, 5)).state == "succeeded"
        assert drivers.peak_active == 1
    finally:
        release_drivers.set()
        await runtime.close()


@pytest.mark.asyncio
async def test_runtime_submit_persists_dependencies_and_plan_access_class(tmp_path) -> None:
    root = repository(tmp_path)
    target = TargetConfig(id="safe-reader", backend="pi", isolated=True, read_only=True)
    catalog = replace(config(tmp_path / "home", (target,)), max_project_readers=2)
    runtime = Runtime(catalog)
    runtime.drivers = FakeDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        parent_a = await runtime.submit(project.id, "consult", "parent a", context_key="a")
        parent_b = await runtime.submit(project.id, "consult", "parent b", context_key="b")
        child = await runtime.submit(
            project.id,
            "review",
            "child",
            context_key="child",
            depends_on=[parent_a.job_id, parent_b.job_id],
        )

        record = runtime.database.job_record(child.job_id)
        assert record is not None
        assert record["access_mode"] == "parallel_read"
        assert runtime.database.dependencies_for_job(child.job_id) == [parent_a.job_id, parent_b.job_id]
        assert (await runtime.wait(parent_a.job_id, 5)).state == "succeeded"
        assert (await runtime.wait(parent_b.job_id, 5)).state == "succeeded"
        assert (await runtime.wait(child.job_id, 5)).state == "succeeded"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_cancel_queued_parent_returns_transitive_dependents_and_releases_waiters(tmp_path) -> None:
    root = repository(tmp_path)
    blocker_started = asyncio.Event()
    release_blocker = asyncio.Event()

    class GatedDrivers(FakeDrivers):
        async def execute(self, *, prompt: str, **kwargs) -> DriverResult:
            if prompt == "blocker":
                blocker_started.set()
                await release_blocker.wait()
            return DriverResult("SUCCESS", "", prompt, "", "")

    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = GatedDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        blocker = await runtime.submit(project.id, "implement", "blocker")
        await blocker_started.wait()
        parent = await runtime.submit(project.id, "review", "parent")
        child = await runtime.submit(project.id, "review", "child", depends_on=[parent.job_id])
        sibling = await runtime.submit(project.id, "consult", "sibling", depends_on=[parent.job_id])
        grandchild = await runtime.submit(
            project.id, "review", "grandchild",
            depends_on=[child.job_id, sibling.job_id],
        )
        great_grandchild = await runtime.submit(
            project.id, "review", "great-grandchild", depends_on=[grandchild.job_id]
        )
        child_waiter = asyncio.create_task(runtime.wait(child.job_id, 5))
        sibling_waiter = asyncio.create_task(runtime.wait(sibling.job_id, 5))
        grandchild_waiter = asyncio.create_task(runtime.wait(grandchild.job_id, 5))
        great_grandchild_waiter = asyncio.create_task(runtime.wait(great_grandchild.job_id, 5))

        result = await runtime.cancel(parent.job_id)

        assert result.state == "cancelled"
        assert result.cancelled_dependents == [
            child.job_id,
            sibling.job_id,
            grandchild.job_id,
            great_grandchild.job_id,
        ]
        assert (await child_waiter).state == "cancelled"
        assert (await sibling_waiter).state == "cancelled"
        assert (await grandchild_waiter).state == "cancelled"
        assert (await great_grandchild_waiter).state == "cancelled"
        release_blocker.set()
        assert (await runtime.wait(blocker.job_id, 5)).state == "succeeded"
    finally:
        release_blocker.set()
        await runtime.close()


def test_runtime_reader_capacity_is_fixed_at_startup(tmp_path) -> None:
    catalog = replace(config(tmp_path / "home"), max_project_readers=1)
    runtime = Runtime(catalog)

    runtime._catalog = replace(catalog, max_project_readers=4)

    assert runtime.catalog.max_project_readers == 4
    assert runtime.scheduler.max_project_readers == 1
    runtime.database.close()


def test_action_result_cancellation_dependents_defaults_empty() -> None:
    from openmcp.models import ActionResult

    result = ActionResult(success=True, job_id="job", state="cancelled")

    assert result.cancelled_dependents == []


@pytest.mark.asyncio
async def test_runtime_submit_invalid_dependencies_leave_no_job(tmp_path) -> None:
    (tmp_path / "project-a").mkdir()
    (tmp_path / "project-b").mkdir()
    root_a = repository(tmp_path / "project-a")
    root_b = repository(tmp_path / "project-b")
    runtime = Runtime(config(tmp_path / "home"))
    try:
        project_a = runtime.register_project(str(root_a), "a")
        project_b = runtime.register_project(str(root_b), "b")
        valid_parent = runtime.database.create_job(
            job_id="valid-parent", project_id=project_a.id, workflow="consult",
            profile="balanced", prompt="parent", execution_plan_json="{}", context_key="parent",
        )
        foreign_parent = runtime.database.create_job(
            job_id="foreign-parent", project_id=project_b.id, workflow="consult",
            profile="balanced", prompt="parent", execution_plan_json="{}", context_key="parent",
        )
        original_count = runtime.database._connection.execute(
            "SELECT COUNT(*) FROM jobs"
        ).fetchone()[0]
        bad_cases = (
            (project_a.id, ["missing-parent"]),
            (project_a.id, ["valid-parent", "valid-parent"]),
            (project_a.id, ["foreign-parent"]),
        )
        for index, (project_id, depends_on) in enumerate(bad_cases):
            with pytest.raises(OrchestrationError, match="dependenc"):
                await runtime.submit(
                    project_id,
                    "review",
                    f"invalid-{index}",
                    context_key=f"invalid-{index}",
                    depends_on=depends_on,
                )
        assert runtime.database._connection.execute(
            "SELECT COUNT(*) FROM jobs"
        ).fetchone()[0] == original_count
        assert runtime.database._connection.execute(
            "SELECT COUNT(*) FROM job_dependencies"
        ).fetchone()[0] == 0
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_fresh_session_jobs_with_identical_scope_remain_serialized(tmp_path) -> None:
    root = repository(tmp_path)
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    second_started = asyncio.Event()

    class GatedFreshDrivers(FakeDrivers):
        async def execute(self, *, prompt: str, **kwargs) -> DriverResult:
            if prompt == "fresh-first":
                first_started.set()
                await release_first.wait()
            elif prompt == "fresh-second":
                second_started.set()
            return DriverResult("SUCCESS", "", prompt, "", "")

    target = TargetConfig(
        id="safe-reader", backend="pi", isolated=True, read_only=True, max_concurrency=2
    )
    catalog = replace(config(tmp_path / "home", (target,)), max_project_readers=2)
    runtime = Runtime(catalog)
    runtime.drivers = GatedFreshDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        first = await runtime.submit(
            project.id, "consult", "fresh-first", context_key="same", fresh_session=True
        )
        await first_started.wait()
        second = await runtime.submit(
            project.id, "consult", "fresh-second", context_key="same", fresh_session=True
        )
        assert not second_started.is_set()
        assert runtime.scheduler.waiting_reason(second.job_id) == "waiting for project session scope"
        release_first.set()
        await asyncio.wait_for(second_started.wait(), 2)
        assert (await runtime.wait(second.job_id, 5)).state == "succeeded"
    finally:
        release_first.set()
        await runtime.close()


@pytest.mark.asyncio
async def test_multiple_parents_must_all_succeed_before_child_runs(tmp_path) -> None:
    root = repository(tmp_path)
    parent_a_started = asyncio.Event()
    parent_b_started = asyncio.Event()
    release_a = asyncio.Event()
    release_b = asyncio.Event()
    child_started = asyncio.Event()

    class GatedParents(FakeDrivers):
        async def execute(self, *, prompt: str, **kwargs) -> DriverResult:
            if prompt == "parent-a":
                parent_a_started.set()
                await release_a.wait()
            elif prompt == "parent-b":
                parent_b_started.set()
                await release_b.wait()
            elif prompt == "child":
                child_started.set()
            return DriverResult("SUCCESS", "", prompt, "", "")

    target = TargetConfig(
        id="safe-reader", backend="pi", isolated=True, read_only=True, max_concurrency=2
    )
    catalog = replace(config(tmp_path / "home", (target,)), max_project_readers=2)
    runtime = Runtime(catalog)
    runtime.drivers = GatedParents()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        parent_a = await runtime.submit(project.id, "consult", "parent-a", context_key="a")
        parent_b = await runtime.submit(project.id, "consult", "parent-b", context_key="b")
        await asyncio.gather(parent_a_started.wait(), parent_b_started.wait())
        child = await runtime.submit(
            project.id, "review", "child", context_key="child",
            depends_on=[parent_a.job_id, parent_b.job_id],
        )
        release_a.set()
        assert (await runtime.wait(parent_a.job_id, 5)).state == "succeeded"
        assert not child_started.is_set()
        release_b.set()
        await asyncio.wait_for(child_started.wait(), 2)
        assert (await runtime.wait(child.job_id, 5)).state == "succeeded"
    finally:
        release_a.set()
        release_b.set()
        await runtime.close()


@pytest.mark.asyncio
async def test_submission_access_class_includes_unsafe_fallback_beyond_attempt_limit(tmp_path) -> None:
    root = repository(tmp_path)
    safe = TargetConfig(id="safe", backend="pi", isolated=True, read_only=True)
    unsafe_fallback = TargetConfig(
        id="fallback", backend="pi", isolated=True, read_only=True, args=("--export", "out.html")
    )
    selection = TargetSelection(("safe", "fallback"), max_attempts=1)
    catalog = replace(
        config(tmp_path / "home", (safe, unsafe_fallback)),
        profiles={"balanced": {workflow: selection for workflow in ("consult", "implement", "review", "other")}},
    )
    runtime = Runtime(catalog)
    try:
        project = runtime.register_project(str(root))
        submitted = await runtime.submit(project.id, "review", "inspect")
        record = runtime.database.job_record(submitted.job_id)
        assert record["access_mode"] == "exclusive"
        plan = json.loads(record["execution_plan_json"])
        assert plan["selection"]["max_attempts"] == 1
        assert [target["id"] for target in plan["targets"]] == ["safe", "fallback"]
        assert plan["targets"][1]["args"] == ["--export", "out.html"]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_submit_with_failed_parent_returns_cancelled_job_and_cause(tmp_path) -> None:
    root = repository(tmp_path)

    class FailedDrivers(FakeDrivers):
        async def execute(self, **kwargs) -> DriverResult:
            return DriverResult("TARGET_FATAL", "", "", "failed", "backend_failure")

    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = FailedDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        parent = await runtime.submit(project.id, "implement", "fails")
        assert (await runtime.wait(parent.job_id, 5)).state == "failed"

        child = await runtime.submit(
            project.id,
            "review",
            "must not execute",
            depends_on=[parent.job_id],
        )

        record = runtime.database.job_record(child.job_id)
        assert child.state == "cancelled"
        assert record is not None and record["state"] == "cancelled"
        assert parent.job_id in record["error"]
        assert any(
            event["kind"] == "job.dependency_cancelled"
            and event["data"]["dependency_job_id"] == parent.job_id
            for event in runtime.database.events(child.job_id)
        )
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_job_runner_task_cancellation_persists_terminal_state(tmp_path) -> None:
    from openmcp.execution import JobRunner

    root = repository(tmp_path)
    catalog = config(tmp_path / "home")
    runtime = Runtime(catalog)
    project = runtime.register_project(str(root))
    plan = resolve_execution_plan(get_workflow("consult"), catalog, "balanced")
    runtime.database.create_job(
        job_id="runner-cancel",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="cancel me",
        execution_plan_json=json.dumps(execution_plan_data(plan)),
        context_key="consult",
    )
    started = asyncio.Event()

    class WaitingDrivers(FakeDrivers):
        async def execute(self, **kwargs) -> DriverResult:
            started.set()
            await asyncio.Event().wait()

    runtime.drivers = WaitingDrivers()
    runner = JobRunner(
        runtime.database,
        runtime.target_executor,
        is_closing=lambda: False,
    )
    task = asyncio.create_task(runner.run("runner-cancel", threading.Event()))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert runtime.database.job("runner-cancel").state == "cancelled"
    runtime.database.close()


@pytest.mark.asyncio
async def test_retry_preserves_dependencies_and_waits_for_unfinished_parent(tmp_path) -> None:
    (tmp_path / "project").mkdir()
    root = repository(tmp_path / "project")
    parent_started = asyncio.Event()
    release_parent = asyncio.Event()
    child_started = asyncio.Event()

    class GatedDrivers(FakeDrivers):
        async def execute(self, *, prompt: str, **kwargs) -> DriverResult:
            if prompt == "parent":
                parent_started.set()
                await release_parent.wait()
            elif prompt == "child":
                child_started.set()
            return DriverResult("SUCCESS", "", prompt, "", "")

    target = TargetConfig(
        id="safe-reader", backend="pi", isolated=True, read_only=True, max_concurrency=2
    )
    catalog = replace(config(tmp_path / "home", (target,)), max_project_readers=2)
    runtime = Runtime(catalog)
    runtime.drivers = GatedDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        parent = await runtime.submit(project.id, "consult", "parent", context_key="parent")
        await parent_started.wait()
        child = await runtime.submit(
            project.id, "review", "child", context_key="child", depends_on=[parent.job_id]
        )
        await runtime.cancel(child.job_id)
        retried = await runtime.retry(child.job_id)

        record = runtime.database.job_record(child.job_id)
        assert retried.job_id == child.job_id
        assert record["access_mode"] == "parallel_read"
        assert runtime.database.dependencies_for_job(child.job_id) == [parent.job_id]
        assert record["state"] == "queued"
        assert runtime.scheduler.active_jobs == 1
        assert not child_started.is_set()

        release_parent.set()
        await asyncio.wait_for(child_started.wait(), 2)
        assert (await runtime.wait(child.job_id, 5)).state == "succeeded"
    finally:
        release_parent.set()
        await runtime.close()


@pytest.mark.asyncio
async def test_retry_rejects_dependent_with_unsuccessful_parent_without_reset(tmp_path) -> None:
    root = repository(tmp_path)

    class FailedDrivers(FakeDrivers):
        async def execute(self, **kwargs) -> DriverResult:
            return DriverResult("TARGET_FATAL", "", "", "failed", "backend_failure")

    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = FailedDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        parent = await runtime.submit(project.id, "implement", "parent")
        await runtime.wait(parent.job_id, 5)
        child = await runtime.submit(
            project.id, "review", "child", depends_on=[parent.job_id]
        )
        original_events = runtime.database.events(child.job_id)

        with pytest.raises(OrchestrationError, match="dependenc"):
            await runtime.retry(child.job_id)

        assert runtime.database.job(child.job_id).state == "cancelled"
        assert runtime.database.dependencies_for_job(child.job_id) == [parent.job_id]
        assert runtime.database.events(child.job_id) == original_events
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_retrying_parent_does_not_revive_cancelled_descendant(tmp_path) -> None:
    root = repository(tmp_path)

    class FailOnceDrivers(FakeDrivers):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        async def execute(self, **kwargs) -> DriverResult:
            self.calls += 1
            if self.calls == 1:
                return DriverResult("TARGET_FATAL", "", "", "failed", "backend_failure")
            return DriverResult("SUCCESS", "", "recovered", "", "")

    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = FailOnceDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        parent = await runtime.submit(project.id, "implement", "parent")
        await runtime.wait(parent.job_id, 5)
        child = await runtime.submit(project.id, "review", "child", depends_on=[parent.job_id])
        assert child.state == "cancelled"

        await runtime.retry(parent.job_id)
        assert (await runtime.wait(parent.job_id, 5)).state == "succeeded"
        assert runtime.database.job(child.job_id).state == "cancelled"
        assert runtime.database.dependencies_for_job(child.job_id) == [parent.job_id]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_cancel_reserved_unstarted_parent_cascades_and_retry_uses_new_dispatch(tmp_path) -> None:
    root = repository(tmp_path)
    runtime_holder: dict[str, Runtime] = {}
    blocker_notice_entered = asyncio.Event()
    release_blocker_notice = asyncio.Event()
    blocker_driver_started = asyncio.Event()
    release_blocker_driver = asyncio.Event()
    retry_driver_started = asyncio.Event()
    release_retry_driver = asyncio.Event()
    parent_id = ""
    blocker_job_id = ""
    dispatch_events: list[threading.Event] = []

    class RetryDriver(FakeDrivers):
        async def execute(self, *, prompt: str, **kwargs) -> DriverResult:
            if prompt == "blocker":
                blocker_driver_started.set()
                await release_blocker_driver.wait()
            if prompt == "retry-parent":
                retry_driver_started.set()
                await release_retry_driver.wait()
            return DriverResult("SUCCESS", "", prompt, "", "")

    async def notify(uri: str) -> None:
        runtime = runtime_holder.get("runtime")
        if runtime is None:
            return
        job_id = uri.removeprefix("openmcp://jobs/")
        record = runtime.database.job_record(job_id)
        if job_id == blocker_job_id and record and record["state"] == "succeeded":
            blocker_notice_entered.set()
            await release_blocker_notice.wait()

    runtime = Runtime(config(tmp_path / "home"), notifier=notify)
    runtime_holder["runtime"] = runtime
    runtime.drivers = RetryDriver()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        blocker = await runtime.submit(project.id, "implement", "blocker")
        blocker_job_id = blocker.job_id
        await blocker_driver_started.wait()
        release_blocker_driver.set()
        await asyncio.wait_for(blocker_notice_entered.wait(), 2)
        parent = await runtime.submit(project.id, "review", "retry-parent")
        parent_id = parent.job_id

        original_run = runtime.runner.run

        async def trace_dispatch(job_id: str, cancel_event: threading.Event) -> None:
            if job_id == parent_id:
                dispatch_events.append(cancel_event)
            await original_run(job_id, cancel_event)

        runtime.scheduler._run_job = trace_dispatch
        child = await runtime.submit(
            project.id, "consult", "child", depends_on=[parent.job_id]
        )
        assert runtime.database.job(parent.job_id).state == "queued"
        assert runtime.scheduler.active_jobs == 1

        cancelled = await runtime.cancel(parent.job_id)

        assert cancelled.state == "cancelled"
        assert cancelled.cancelled_dependents == [child.job_id]
        assert runtime.database.job(parent.job_id).state == "cancelled"
        assert runtime.database.job(child.job_id).state == "cancelled"
        assert runtime.scheduler.active_jobs == 0
        assert (await runtime.wait(child.job_id, 1)).state == "cancelled"

        retried = await runtime.retry(parent.job_id)
        assert retried.job_id == parent.job_id
        assert runtime.database.job(parent.job_id).state == "queued"
        assert runtime.database.job(child.job_id).state == "cancelled"
        assert runtime.scheduler.active_jobs == 1

        release_blocker_notice.set()
        await asyncio.wait_for(retry_driver_started.wait(), 2)
        assert len(dispatch_events) == 1
        assert not dispatch_events[0].is_set()
        release_retry_driver.set()
        assert (await runtime.wait(parent.job_id, 5)).state == "succeeded"
        assert runtime.database.job(child.job_id).state == "cancelled"
        assert len(dispatch_events) == 1
    finally:
        release_blocker_notice.set()
        release_blocker_driver.set()
        release_retry_driver.set()
        await runtime.close()


@pytest.mark.asyncio
async def test_retry_is_not_lost_while_terminal_notifier_is_paused(tmp_path) -> None:
    root = repository(tmp_path)
    runtime_holder: dict[str, Runtime] = {}
    driver_started = asyncio.Event()
    allow_first_failure = asyncio.Event()
    terminal_notice_entered = asyncio.Event()
    release_terminal_notice = asyncio.Event()

    class FailThenSucceedDrivers(FakeDrivers):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        async def execute(self, **kwargs) -> DriverResult:
            self.calls += 1
            if self.calls == 1:
                driver_started.set()
                await allow_first_failure.wait()
                return DriverResult("TARGET_FATAL", "", "", "failed", "backend_failure")
            return DriverResult("SUCCESS", "", "retried", "", "")

    async def notify(uri: str) -> None:
        runtime = runtime_holder.get("runtime")
        if runtime is None:
            return
        job_id = uri.removeprefix("openmcp://jobs/")
        record = runtime.database.job_record(job_id)
        if record and record["state"] == "failed" and not terminal_notice_entered.is_set():
            terminal_notice_entered.set()
            await release_terminal_notice.wait()

    runtime = Runtime(config(tmp_path / "home"), notifier=notify)
    runtime_holder["runtime"] = runtime
    drivers = FailThenSucceedDrivers()
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        submitted = await runtime.submit(project.id, "implement", "retry race")
        await driver_started.wait()
        child = await runtime.submit(
            project.id,
            "review",
            "dependent child",
            depends_on=[submitted.job_id],
        )
        allow_first_failure.set()
        await asyncio.wait_for(terminal_notice_entered.wait(), 2)
        assert runtime.database.job(child.job_id).state == "cancelled"

        retry_result = await runtime.retry(submitted.job_id)
        assert retry_result.job_id == submitted.job_id
        assert runtime.database.job(submitted.job_id).state == "queued"
        release_terminal_notice.set()
        assert (await runtime.wait(submitted.job_id, 5)).state == "succeeded"
        assert runtime.database.job(child.job_id).state == "cancelled"
        assert drivers.calls == 2
    finally:
        release_terminal_notice.set()
        await runtime.close()


@pytest.mark.asyncio
async def test_startup_cascades_interrupted_and_failed_parents_before_admission(tmp_path) -> None:
    root = repository(tmp_path)
    catalog = config(tmp_path / "home")
    database = Database(catalog.database_path)
    project = database.upsert_project(project_id="p", alias="p", root=root.as_posix())
    plan = execution_plan_data(resolve_execution_plan(get_workflow("consult"), catalog, "balanced"))
    serialized_plan = json.dumps(plan)
    database.create_job(
        job_id="interrupted-parent", project_id=project.id, workflow="consult", profile="balanced",
        prompt="parent", execution_plan_json=serialized_plan, context_key="parent",
    )
    database.start_job("interrupted-parent")
    database.create_job_with_dependencies(
        job_id="interrupted-child", project_id=project.id, workflow="review", profile="balanced",
        prompt="child", execution_plan_json=serialized_plan, context_key="child",
        access_mode="exclusive", depends_on=["interrupted-parent"],
    )
    database.create_job_with_dependencies(
        job_id="interrupted-grandchild", project_id=project.id, workflow="review", profile="balanced",
        prompt="grandchild", execution_plan_json=serialized_plan, context_key="grandchild",
        access_mode="exclusive", depends_on=["interrupted-child"],
    )
    database.create_job(
        job_id="failed-parent", project_id=project.id, workflow="consult", profile="balanced",
        prompt="failed", execution_plan_json=serialized_plan, context_key="failed",
    )
    database.finish_job("failed-parent", "failed", error="already failed")
    database.create_job_with_dependencies(
        job_id="failed-child", project_id=project.id, workflow="review", profile="balanced",
        prompt="failed child", execution_plan_json=serialized_plan, context_key="failed-child",
        access_mode="exclusive", depends_on=["failed-parent"],
    )
    database.close()

    runtime = Runtime(catalog)
    drivers = FakeDrivers()
    runtime.drivers = drivers
    await runtime.start()
    try:
        assert runtime.database.job("interrupted-parent").state == "interrupted"
        assert runtime.database.job("interrupted-child").state == "cancelled"
        assert runtime.database.job("interrupted-grandchild").state == "cancelled"
        assert runtime.database.job("failed-child").state == "cancelled"
        assert not drivers.sessions
    finally:
        await runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["attempt_persistence", "capability_probe", "recorder_setup", "recorder_close"])
async def test_target_semaphore_released_after_post_acquire_failures(tmp_path, monkeypatch, failure: str) -> None:
    from openmcp import execution as execution_module

    root = repository(tmp_path)
    catalog = config(tmp_path / "home")
    runtime = Runtime(catalog)
    project = runtime.register_project(str(root))
    plan = resolve_execution_plan(get_workflow("consult"), catalog, "balanced")
    target = plan.target("primary")
    runtime.database.create_job(
        job_id="target-lease",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="test target lease",
        execution_plan_json=json.dumps(execution_plan_data(plan)),
        context_key="consult",
    )

    class CapabilityFailureDrivers(FakeDrivers):
        def supports_structured_streaming(self, target):
            raise RuntimeError("capability setup failed")

    if failure == "attempt_persistence":
        monkeypatch.setattr(
            runtime.database,
            "record_job_attempt",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("attempt persistence failed")),
        )
    elif failure == "capability_probe":
        runtime.drivers = CapabilityFailureDrivers()
    elif failure == "recorder_setup":
        monkeypatch.setattr(
            execution_module,
            "StreamRecorder",
            lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("recorder setup failed")),
        )
    else:
        async def failing_close(_recorder):
            raise RuntimeError("recorder close failed")
        monkeypatch.setattr(execution_module.StreamRecorder, "close", failing_close)

    try:
        with pytest.raises(RuntimeError):
            await runtime.target_executor.execute(
                job_id="target-lease",
                project=project,
                workflow="consult",
                context_key="consult",
                plan=plan,
                prompt="test target lease",
                cwd=root,
                cancel_event=threading.Event(),
            )
        target_key = target_execution_key(target)
        assert runtime.target_executor._target_active[target_key] == 0
        assert runtime.target_executor._target_semaphores[target_key]._value == 1
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_dependency_waiting_consumes_no_worker_and_releases_after_all_parents(tmp_path) -> None:
    (tmp_path / "project-a").mkdir()
    (tmp_path / "project-b").mkdir()
    root_a = repository(tmp_path / "project-a")
    root_b = repository(tmp_path / "project-b")
    parent_started = asyncio.Event()
    release_parent = asyncio.Event()
    child_started = asyncio.Event()
    independent_started = asyncio.Event()

    class GatedDrivers(FakeDrivers):
        async def execute(self, *, prompt: str, **kwargs) -> DriverResult:
            if prompt == "parent":
                parent_started.set()
                await release_parent.wait()
            elif prompt == "child":
                child_started.set()
            else:
                independent_started.set()
            return DriverResult("SUCCESS", "", prompt, "", "")

    target = TargetConfig(
        id="safe-reader", backend="pi", isolated=True, read_only=True, max_concurrency=2
    )
    catalog = replace(config(tmp_path / "home", (target,)), max_jobs=2, max_project_readers=2)
    runtime = Runtime(catalog)
    runtime.drivers = GatedDrivers()
    await runtime.start()
    try:
        project_a = runtime.register_project(str(root_a), "a")
        project_b = runtime.register_project(str(root_b), "b")
        parent = await runtime.submit(project_a.id, "consult", "parent", context_key="parent")
        await parent_started.wait()
        child = await runtime.submit(
            project_a.id,
            "review",
            "child",
            context_key="child",
            depends_on=[parent.job_id],
        )
        assert runtime.database.job(child.job_id).state == "queued"
        assert runtime.scheduler.active_jobs == 1
        waiting_on, waiting_reason = runtime.waiting_metadata(child.job_id)
        assert waiting_on == [parent.job_id]
        assert waiting_reason == f"waiting on dependency {parent.job_id}"

        independent = await runtime.submit(project_b.id, "consult", "independent")
        await asyncio.wait_for(independent_started.wait(), 2)
        assert not child_started.is_set()
        release_parent.set()
        await asyncio.wait_for(child_started.wait(), 2)
        assert (await runtime.wait(child.job_id, 5)).state == "succeeded"
        assert (await runtime.wait(independent.job_id, 5)).state == "succeeded"
    finally:
        release_parent.set()
        await runtime.close()


@pytest.mark.asyncio
async def test_submission_result_includes_exact_job_resource_uri(tmp_path) -> None:
    root = repository(tmp_path)
    runtime = Runtime(config(tmp_path / "home"))
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        submission = await runtime.submit(project.id, "implement", "inspect")
        assert submission.resource_uri == f"openmcp://jobs/{submission.job_id}"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_job_state_transitions_notify_after_persistence(tmp_path) -> None:
    root = repository(tmp_path)
    notifications: list[str] = []

    async def notify(uri: str) -> None:
        notifications.append(uri)

    runtime = Runtime(config(tmp_path / "home"), notifier=notify)
    runtime.drivers = FakeDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        submission = await runtime.submit(project.id, "implement", "inspect")
        await runtime.wait(submission.job_id, 10)
        assert notifications == [submission.resource_uri] * 3
        assert runtime.database.job(submission.job_id).state == "succeeded"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_notification_failure_does_not_change_job_outcome(tmp_path) -> None:
    root = repository(tmp_path)

    async def notify(_: str) -> None:
        raise RuntimeError("subscription unavailable")

    runtime = Runtime(config(tmp_path / "home"), notifier=notify)
    runtime.drivers = FakeDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        submission = await runtime.submit(project.id, "implement", "inspect")
        assert (await runtime.wait(submission.job_id, 10)).state == "succeeded"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_implement_succeeds_with_dirty_worktree_and_leaves_changes(tmp_path) -> None:
    root = repository(tmp_path)
    baseline = git(root, "rev-parse", "HEAD")
    (root / "README.md").write_text("dirty\n", encoding="utf-8")
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = FakeDrivers(mutate=True)
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        submission = await runtime.submit(project.id, "implement", "create the result")
        job = await runtime.wait(submission.job_id, 10)
        assert job.state == "succeeded"
        assert (root / "result.txt").exists()
        assert (root / "README.md").read_text(encoding="utf-8") == "dirty\n"
        assert git(root, "rev-parse", "HEAD") == baseline
        assert "stages" not in job.model_dump()
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_implement_without_changes_uses_empty_result_placeholder(tmp_path) -> None:
    root = repository(tmp_path)
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = FakeDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        job = await runtime.wait((await runtime.submit(project.id, "implement", "inspect only")).job_id, 10)
        assert job.state == "succeeded"
    finally:
        await runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("workflow", ["review", "consult", "other"])
async def test_read_workflows_store_empty_commit_placeholder(tmp_path, workflow) -> None:
    root = repository(tmp_path)
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = FakeDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        job = await runtime.wait((await runtime.submit(project.id, workflow, "inspect")).job_id, 10)
        assert job.state == "succeeded"
        assert git(root, "status", "--porcelain") == ""
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_mutating_review_succeeds_and_leaves_changes(tmp_path) -> None:
    root = repository(tmp_path)
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = FakeDrivers(mutate=True)
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        job = await runtime.wait((await runtime.submit(project.id, "review", "review")).job_id, 10)
        assert job.state == "succeeded"
        assert (root / "result.txt").exists()
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_other_job_plan_and_context_retain_role(tmp_path) -> None:
    root = repository(tmp_path)
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = FakeDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        submitted = await runtime.submit(project.id, "other", "inspect", context_key="shared")
        job = await runtime.wait(submitted.job_id, 10)
        record = runtime.database.job_record(submitted.job_id)
        assert job.workflow == "other"
        assert job.context_key == "shared"
        assert record is not None
        assert json.loads(record["execution_plan_json"])["workflow"] == "other"
        context = runtime.database.context(project.id, "shared")
        assert [(stream.role, stream.turns) for stream in context] == [("other", 1)]
    finally:
        await runtime.close()


class MutatingFailureDrivers(FakeDrivers):
    async def execute(self, *, cwd, **kwargs) -> DriverResult:
        (cwd / "README.md").write_text("agent change\n", encoding="utf-8")
        (cwd / "partial.txt").write_text("partial\n", encoding="utf-8")
        return DriverResult("RETRYABLE", "", "", "target failed", "backend_failure")


class RetryDrivers(FakeDrivers):
    def __init__(self) -> None:
        super().__init__({"primary": "RETRYABLE"})
        self.started = asyncio.Event()
        self.calls = 0

    async def execute(self, **kwargs) -> DriverResult:
        self.calls += 1
        self.started.set()
        return DriverResult("RETRYABLE", "", "", "retry", "backend_failure")


class SaturatedTargetDrivers(FakeDrivers):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.calls = 0

    async def execute(self, *, cancel_event, **kwargs) -> DriverResult:
        self.calls += 1
        self.started.set()
        while not cancel_event.is_set():
            await asyncio.sleep(0.01)
        return DriverResult("CANCELLED", "", "", "cancelled", "cancelled")


@pytest.mark.asyncio
async def test_failed_execution_leaves_changes_and_preserves_dirty_preflight(tmp_path) -> None:
    root = repository(tmp_path)
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = MutatingFailureDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        job = await runtime.wait((await runtime.submit(project.id, "implement", "change")).job_id, 10)
        assert job.state == "failed"
        assert (root / "README.md").read_text(encoding="utf-8") == "agent change\n"
        assert (root / "partial.txt").exists()
        (root / "README.md").write_text("operator change\n", encoding="utf-8")
        job = await runtime.wait((await runtime.submit(project.id, "implement", "change")).job_id, 10)
        assert job.state == "failed"
        assert (root / "README.md").read_text(encoding="utf-8") == "agent change\n"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_retries_reuse_targets_after_each_failover_pass(tmp_path, monkeypatch) -> None:
    root = repository(tmp_path)
    selection = TargetSelection(("primary",), 2)
    catalog = replace(
        config(tmp_path / "home"),
        profiles={
            "balanced": {
                "implement": selection,
                "review": selection,
                "consult": selection,
            }
        },
    )
    runtime = Runtime(catalog)
    runtime.drivers = RetryDrivers()
    monkeypatch.setattr("openmcp.execution.random.uniform", lambda _a, _b: 0)
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        job = await runtime.wait(
            (await runtime.submit(project.id, "implement", "retry")).job_id,
            10,
        )
        assert job.state == "failed"
        assert job.attempts == 2
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_retry_transition_notifies_the_same_job_resource(tmp_path) -> None:
    root = repository(tmp_path)
    notifications: list[str] = []

    async def notify(uri: str) -> None:
        notifications.append(uri)

    runtime = Runtime(config(tmp_path / "home"), notifier=notify)
    runtime.drivers = RetryDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        submission = await runtime.submit(project.id, "implement", "retry")
        assert (await runtime.wait(submission.job_id, 10)).state == "failed"
        retried = await runtime.retry(submission.job_id)
        assert retried.resource_uri == submission.resource_uri
        assert (await runtime.wait(retried.job_id, 10)).state == "failed"
        assert notifications == [submission.resource_uri] * 6
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_cancellation_interrupts_retry_backoff(tmp_path) -> None:
    root = repository(tmp_path)
    selection = TargetSelection(("primary",), 2)
    catalog = replace(
        config(tmp_path / "home"),
        profiles={
            "balanced": {
                "implement": selection,
                "review": selection,
                "consult": selection,
            }
        },
    )
    drivers = RetryDrivers()
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        submitted = await runtime.submit(project.id, "implement", "retry")
        await drivers.started.wait()
        await runtime.cancel(submitted.job_id)
        assert (await runtime.wait(submitted.job_id, 0.5)).state == "cancelled"
        assert drivers.calls == 1
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_queued_and_running_cancellation(tmp_path) -> None:
    root = repository(tmp_path)
    drivers = BlockingDrivers()
    notifications: list[str] = []

    async def notify(uri: str) -> None:
        notifications.append(uri)

    runtime = Runtime(config(tmp_path / "home"), notifier=notify)
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        first = await runtime.submit(project.id, "implement", "block")
        second = await runtime.submit(project.id, "review", "never run")
        await drivers.started.wait()
        queued_cancel = await runtime.cancel(second.job_id)
        assert queued_cancel.state == "cancelled"
        assert queued_cancel.cancelled_dependents == []
        running_cancel = await runtime.cancel(first.job_id)
        assert running_cancel.state == "running"
        assert running_cancel.cancelled_dependents == []
        assert (await runtime.wait(first.job_id, 10)).state == "cancelled"
        assert (await runtime.wait(second.job_id, 10)).state == "cancelled"
        assert [uri for uri in notifications if uri == first.resource_uri] == [first.resource_uri] * 3
        assert [uri for uri in notifications if uri == second.resource_uri] == [second.resource_uri] * 2
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_shutdown_leaves_unstarted_queued_job_durable_for_restart(tmp_path) -> None:
    root = repository(tmp_path)
    catalog = config(tmp_path / "home")
    drivers = BlockingDrivers()
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    await runtime.start()
    project = runtime.register_project(str(root))
    active = await runtime.submit(project.id, "implement", "block active")
    queued = await runtime.submit(project.id, "review", "run after restart")
    await drivers.started.wait()

    await runtime.close()
    database = Database(catalog.database_path)
    assert database.job(active.job_id).state == "interrupted"
    assert database.job(queued.job_id).state == "queued"
    database.close()

    restarted = Runtime(catalog)
    restarted.drivers = FakeDrivers()
    await restarted.start()
    try:
        assert (await restarted.wait(queued.job_id, 5)).state == "succeeded"
    finally:
        await restarted.close()


@pytest.mark.asyncio
async def test_shutdown_interrupts_active_job(tmp_path) -> None:
    root = repository(tmp_path)
    catalog = config(tmp_path / "home")
    drivers = BlockingDrivers()
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    await runtime.start()
    project = runtime.register_project(str(root))
    submitted = await runtime.submit(project.id, "implement", "block")
    await drivers.started.wait()

    await runtime.close()

    database = Database(catalog.database_path)
    try:
        job = database.job(submitted.job_id)
        assert job and job.state == "interrupted"
    finally:
        database.close()


@pytest.mark.asyncio
async def test_cancel_interrupts_target_capacity_wait(tmp_path) -> None:
    (tmp_path / "first").mkdir()
    (tmp_path / "second").mkdir()
    first_root = repository(tmp_path / "first")
    second_root = repository(tmp_path / "second")
    drivers = SaturatedTargetDrivers()
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = drivers
    await runtime.start()
    try:
        first_project = runtime.register_project(str(first_root), "first")
        second_project = runtime.register_project(str(second_root), "second")
        first = await runtime.submit(first_project.id, "implement", "block")
        await drivers.started.wait()
        second = await runtime.submit(second_project.id, "implement", "wait")
        while runtime.database.job(second.job_id).state != "running":
            await asyncio.sleep(0)

        assert (await runtime.cancel(second.job_id)).state == "running"
        second_job = await runtime.wait(second.job_id, 1)
        assert second_job.state == "cancelled"
        assert second_job.attempts == 0
        assert drivers.calls == 1
        await runtime.cancel(first.job_id)
        await runtime.wait(first.job_id, 1)
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_shutdown_interrupts_target_capacity_wait(tmp_path) -> None:
    (tmp_path / "first").mkdir()
    (tmp_path / "second").mkdir()
    first_root = repository(tmp_path / "first")
    second_root = repository(tmp_path / "second")
    catalog = config(tmp_path / "home")
    drivers = SaturatedTargetDrivers()
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    await runtime.start()
    first_project = runtime.register_project(str(first_root), "first")
    second_project = runtime.register_project(str(second_root), "second")
    first = await runtime.submit(first_project.id, "implement", "block")
    await drivers.started.wait()
    second = await runtime.submit(second_project.id, "implement", "wait")
    while runtime.database.job(second.job_id).state != "running":
        await asyncio.sleep(0)

    await asyncio.wait_for(runtime.close(), 1)

    database = Database(catalog.database_path)
    try:
        assert database.job(first.job_id).state == "interrupted"
        assert database.job(second.job_id).state == "interrupted"
        assert drivers.calls == 1
    finally:
        database.close()


@pytest.mark.asyncio
async def test_startup_interrupts_persisted_running_job_without_reset(tmp_path) -> None:
    root = repository(tmp_path)
    home = tmp_path / "home"
    catalog = config(home)
    database = Database(catalog.database_path)
    project = database.upsert_project(project_id="project", alias="project", root=root.as_posix())
    plan = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")
    database.create_job(job_id="running", project_id=project.id, workflow="implement", profile="balanced", prompt="change", execution_plan_json=json.dumps(execution_plan_data(plan)), context_key="implement")
    database.start_job("running")
    (root / "partial.txt").write_text("partial\n", encoding="utf-8")
    database.close()
    notifications: list[str] = []

    async def notify(uri: str) -> None:
        notifications.append(uri)

    runtime = Runtime(catalog, notifier=notify)
    await runtime.start()
    try:
        interrupted = runtime.database.job("running")
        assert interrupted and interrupted.state == "interrupted"
        assert notifications == ["openmcp://jobs/running"]
        assert (root / "partial.txt").read_text(encoding="utf-8") == "partial\n"
    finally:
        await runtime.close()


def test_registration_accepts_plain_directory(tmp_path) -> None:
    root = tmp_path / "plain-project"
    root.mkdir()
    runtime = Runtime(config(tmp_path / "home"))
    try:
        project = runtime.register_project(str(root))
        assert project.root == root.resolve().as_posix()
    finally:
        runtime.database.close()


@pytest.mark.parametrize("path_kind", ["missing", "file"])
def test_registration_rejects_missing_or_file_paths(tmp_path, path_kind) -> None:
    path = tmp_path / "project"
    if path_kind == "file":
        path.write_text("not a directory\n", encoding="utf-8")
    runtime = Runtime(config(tmp_path / f"home-{path_kind}"))
    try:
        with pytest.raises(OrchestrationError):
            runtime.register_project(str(path))
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_plain_directory_execution_spawns_no_git(monkeypatch, tmp_path) -> None:
    root = tmp_path / "plain-project"
    root.mkdir()

    original_run = subprocess.run

    def fail_git_spawn(command, *args, **kwargs):
        if command and command[0] == "git":
            raise AssertionError("OpenMCP spawned Git")
        return original_run(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", fail_git_spawn)
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = FakeDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        job = await runtime.wait((await runtime.submit(project.id, "consult", "inspect")).job_id, 10)
        assert job.state == "succeeded"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_retry_attempts_recompile_argv_per_backend(tmp_path) -> None:
    root = repository(tmp_path)
    selection = TargetSelection(("claude-target", "pi-target"), 2)
    catalog = replace(
        config(tmp_path / "home"),
        targets=(
            TargetConfig(id="claude-target", backend="claude"),
            TargetConfig(id="pi-target", backend="pi"),
        ),
        profiles={
            "balanced": {
                "implement": selection,
                "review": selection,
                "consult": selection,
            }
        },
    )
    compiled: list[str] = []

    class RetryingDrivers(FakeDrivers):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        async def execute(self, *, target: TargetConfig, **kwargs) -> DriverResult:
            self.calls += 1
            compiled.append(target.id)
            return DriverResult("RETRYABLE", "", "", "retry", "backend_failure")

    runtime = Runtime(catalog)
    runtime.drivers = RetryingDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        job = await runtime.wait((await runtime.submit(project.id, "implement", "retry")).job_id, 10)
        assert job.state == "failed"
        assert job.attempts == 2
        assert compiled == ["claude-target", "pi-target"]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_new_submissions_use_refreshed_catalog_while_existing_plan_stable(tmp_path) -> None:
    """A published target change affects only new submissions.

    Existing submitted execution-plan snapshots retain their original target
    configuration even after the runtime catalog is refreshed.
    """
    root = repository(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    path = home / "config.toml"
    path.write_text(
        """[daemon]
default_profile = "balanced"

[[targets]]
id = "primary"
backend = "codex"
model = "old-model"

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
""",
        encoding="utf-8",
    )
    from openmcp.config import load_config
    runtime = Runtime(load_config(path))
    runtime.drivers = FakeDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        submitted = await runtime.submit(project.id, "implement", "first task")
        plan_before = json.loads(runtime.database.job_record(submitted.job_id)["execution_plan_json"])
        assert plan_before["targets"][0]["model"] == "old-model"

        # Publish a refreshed catalog that changes the target model.
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                'model = "old-model"', 'model = "new-model"'
            ),
            encoding="utf-8",
        )
        runtime.publish_configuration()
        assert runtime.catalog.targets[0].model == "new-model"

        # A new submission resolves against the refreshed catalog.
        fresh = await runtime.submit(project.id, "implement", "second task")
        plan_after = json.loads(runtime.database.job_record(fresh.job_id)["execution_plan_json"])
        assert plan_after["targets"][0]["model"] == "new-model"

        # The earlier submission's plan is unchanged.
        plan_still = json.loads(runtime.database.job_record(submitted.job_id)["execution_plan_json"])
        assert plan_still["targets"][0]["model"] == "old-model"
        assert runtime.database.job_record(submitted.job_id)["config_revision"] != \
            runtime.database.job_record(fresh.job_id)["config_revision"]
    finally:
        await runtime.close()


class RecordingSessionDrivers(FakeDrivers):
    def __init__(self) -> None:
        super().__init__()
        self.recorded_sessions: list[str] = []
        self.recorded_prompts: list[str] = []

    async def execute(self, *, target: TargetConfig, cwd: Path, session_id: str, prompt: str = "", **kwargs) -> DriverResult:
        self.recorded_sessions.append(session_id)
        self.recorded_prompts.append(prompt)
        assigned = f"new-session-{len(self.recorded_sessions)}"
        return DriverResult("SUCCESS", assigned, f"response-{len(self.recorded_sessions)}", "", "")


@pytest.mark.asyncio
async def test_fresh_job_bypasses_session_and_history_and_clears_prior_sessions(tmp_path) -> None:
    root = repository(tmp_path)
    drivers = RecordingSessionDrivers()
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = drivers
    target = runtime.catalog.targets[0]
    tkey = target_execution_key(target)
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        # Seed prior turns and sessions
        runtime.database.append_turn(
            project_id=project.id,
            context_key="feature",
            role="implement",
            target_id=target.id,
            target_key=tkey,
            session_id="old-session-1",
            prompt="turn 1",
            response="response 1",
        )
        runtime.database.append_turn(
            project_id=project.id,
            context_key="feature",
            role="implement",
            target_id="secondary",
            target_key="secondary-key",
            session_id="old-session-2",
            prompt="turn 2",
            response="response 2",
        )
        runtime.database.append_turn(
            project_id=project.id,
            context_key="unrelated",
            role="implement",
            target_id=target.id,
            target_key=tkey,
            session_id="unrelated-session",
            prompt="unrelated turn",
            response="unrelated response",
        )

        assert runtime.database.session(project.id, "feature", "implement", tkey) == "old-session-1"
        assert runtime.database.session(project.id, "feature", "implement", "secondary-key") == "old-session-2"

        # Submit fresh job
        submitted = await runtime.submit(
            project.id,
            "implement",
            "fresh request prompt",
            context_key="feature",
            fresh_session=True,
        )
        job = await runtime.wait(submitted.job_id, 10)
        assert job.state == "succeeded"

        # Every fresh attempt supplies empty session ID and exact validated prompt
        assert drivers.recorded_sessions[0] == ""
        assert drivers.recorded_prompts[0] == "fresh request prompt"

        # Old sessions for this project, context_key, workflow are cleared
        assert runtime.database.session(project.id, "feature", "implement", "secondary-key") == ""
        # The new session is the only resumable session
        assert runtime.database.session(project.id, "feature", "implement", tkey) == "new-session-1"
        # Unrelated stream is unaffected
        assert runtime.database.session(project.id, "unrelated", "implement", tkey) == "unrelated-session"

        # Next standard job resumes only the newly returned session
        standard_sub = await runtime.submit(
            project.id,
            "implement",
            "next standard prompt",
            context_key="feature",
            fresh_session=False,
        )
        standard_job = await runtime.wait(standard_sub.job_id, 10)
        assert standard_job.state == "succeeded"

        assert drivers.recorded_sessions[1] == "new-session-1"
        assert drivers.recorded_prompts[1] == "next standard prompt"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_fresh_job_failover_preserves_freshness(tmp_path) -> None:
    root = repository(tmp_path)
    catalog = config(
        tmp_path / "home",
        (TargetConfig(id="primary", backend="codex"), TargetConfig(id="secondary", backend="codex")),
    )

    class FailoverDrivers(FakeDrivers):
        def __init__(self) -> None:
            super().__init__()
            self.attempts: list[tuple[str, str, str]] = []

        async def execute(
            self,
            *,
            target: TargetConfig,
            session_id: str,
            prompt: str = "",
            **kwargs,
        ) -> DriverResult:
            self.attempts.append((target.id, session_id, prompt))
            if target.id == "primary":
                return DriverResult("RETRYABLE", "", "", "transient error", "backend_failure")
            return DriverResult("SUCCESS", "secondary-session", "success", "", "")

    drivers = FailoverDrivers()
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    primary_key = target_execution_key(catalog.targets[0])
    secondary_key = target_execution_key(catalog.targets[1])
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        for target, target_key in zip(catalog.targets, (primary_key, secondary_key), strict=True):
            runtime.database.append_turn(
                project_id=project.id,
                context_key="stream",
                role="implement",
                target_id=target.id,
                target_key=target_key,
                session_id=f"old-{target.id}-session",
                prompt=f"{target.id} turn",
                response=f"{target.id} response",
            )

        submitted = await runtime.submit(
            project.id,
            "implement",
            "failover prompt",
            context_key="stream",
            fresh_session=True,
        )
        job = await runtime.wait(submitted.job_id, 10)
        assert job.state == "succeeded"
        assert job.attempts == 2

        assert drivers.attempts == [
            ("primary", "", "failover prompt"),
            ("secondary", "", "failover prompt"),
        ]
        assert runtime.database.session(project.id, "stream", "implement", primary_key) == ""
        assert runtime.database.session(project.id, "stream", "implement", secondary_key) == "secondary-session"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_fresh_job_retry_survives_and_runs_fresh(tmp_path) -> None:
    root = repository(tmp_path)
    catalog = config(tmp_path / "home")

    class OnceFailingDrivers(FakeDrivers):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0
            self.recorded_sessions: list[str] = []
            self.recorded_prompts: list[str] = []

        async def execute(self, *, session_id: str, prompt: str = "", **kwargs) -> DriverResult:
            self.calls += 1
            self.recorded_sessions.append(session_id)
            self.recorded_prompts.append(prompt)
            if self.calls == 1:
                return DriverResult("TARGET_FATAL", "", "", "fatal error", "backend_failure")
            return DriverResult("SUCCESS", "retry-session", "ok", "", "")

    drivers = OnceFailingDrivers()
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    tkey = target_execution_key(catalog.targets[0])
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        runtime.database.append_turn(
            project_id=project.id,
            context_key="stream",
            role="implement",
            target_id=catalog.targets[0].id,
            target_key=tkey,
            session_id="old-session",
            prompt="turn 1",
            response="response 1",
        )

        submitted = await runtime.submit(
            project.id,
            "implement",
            "retry prompt",
            context_key="stream",
            fresh_session=True,
        )
        failed_job = await runtime.wait(submitted.job_id, 10)
        assert failed_job.state == "failed"

        # Failed fresh job does not clear preexisting sessions
        assert runtime.database.session(project.id, "stream", "implement", tkey) == "old-session"

        # Retry the job
        retried = await runtime.retry(submitted.job_id)
        assert retried.job_id == submitted.job_id
        record = runtime.database.job_record(submitted.job_id)
        assert record and record["fresh_session"] == 1

        succeeded_job = await runtime.wait(submitted.job_id, 10)
        assert succeeded_job.state == "succeeded"

        # Both attempts (initial and retry) received empty session and exact prompt
        assert drivers.recorded_sessions == ["", ""]
        assert drivers.recorded_prompts == ["retry prompt", "retry prompt"]
        assert runtime.database.session(project.id, "stream", "implement", tkey) == "retry-session"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_fresh_job_without_returned_session_clears_old_session(tmp_path) -> None:
    root = repository(tmp_path)
    catalog = config(tmp_path / "home")

    class NoSessionDrivers(FakeDrivers):
        async def execute(self, **kwargs) -> DriverResult:
            return DriverResult("SUCCESS", "", "success without session", "", "")

    runtime = Runtime(catalog)
    runtime.drivers = NoSessionDrivers()
    tkey = target_execution_key(catalog.targets[0])
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        runtime.database.append_turn(
            project_id=project.id,
            context_key="stream",
            role="implement",
            target_id=catalog.targets[0].id,
            target_key=tkey,
            session_id="old-session",
            prompt="turn 1",
            response="response 1",
        )
        assert runtime.database.session(project.id, "stream", "implement", tkey) == "old-session"

        submitted = await runtime.submit(
            project.id,
            "implement",
            "stateless prompt",
            context_key="stream",
            fresh_session=True,
        )
        job = await runtime.wait(submitted.job_id, 10)
        assert job.state == "succeeded"

        # Old session removed, no new session stored
        assert runtime.database.session(project.id, "stream", "implement", tkey) == ""
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_standard_sessionless_reconstructs_history_while_fresh_bypasses(tmp_path) -> None:
    root = repository(tmp_path)
    catalog = config(tmp_path / "home")

    class CaptureDrivers(FakeDrivers):
        def __init__(self) -> None:
            super().__init__()
            self.prompts: list[str] = []

        async def execute(self, *, prompt: str = "", **kwargs) -> DriverResult:
            self.prompts.append(prompt)
            return DriverResult("SUCCESS", "", "ok", "", "")

    drivers = CaptureDrivers()
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    tkey = target_execution_key(catalog.targets[0])
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        # Turn with no session
        runtime.database.append_turn(
            project_id=project.id,
            context_key="history-stream",
            role="implement",
            target_id=catalog.targets[0].id,
            target_key=tkey,
            session_id="",
            prompt="prior question",
            response="prior answer",
        )

        # Standard job injects history
        sub_standard = await runtime.submit(
            project.id,
            "implement",
            "current task",
            context_key="history-stream",
            fresh_session=False,
        )
        await runtime.wait(sub_standard.job_id, 10)
        assert "Previous context:" in drivers.prompts[0]
        assert "prior question" in drivers.prompts[0]
        assert "current task" in drivers.prompts[0]

        # Fresh job bypasses history
        sub_fresh = await runtime.submit(
            project.id,
            "implement",
            "current task",
            context_key="history-stream",
            fresh_session=True,
        )
        await runtime.wait(sub_fresh.job_id, 10)
        assert drivers.prompts[1] == "current task"
        assert "Previous context:" not in drivers.prompts[1]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_fresh_session_flag_survives_daemon_restart(tmp_path) -> None:
    root = repository(tmp_path)
    home = tmp_path / "home"
    catalog = config(home)
    database = Database(catalog.database_path)
    project = database.upsert_project(project_id="project", alias="project", root=root.as_posix())
    plan = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")
    database.create_job(
        job_id="queued-fresh",
        project_id=project.id,
        workflow="implement",
        profile="balanced",
        prompt="fresh restart prompt",
        execution_plan_json=json.dumps(execution_plan_data(plan)),
        context_key="implement",
        fresh_session=True,
    )
    database.close()

    class CaptureDrivers(FakeDrivers):
        def __init__(self) -> None:
            super().__init__()
            self.sessions: list[str] = []
            self.prompts: list[str] = []

        async def execute(self, *, session_id: str, prompt: str = "", **kwargs) -> DriverResult:
            self.sessions.append(session_id)
            self.prompts.append(prompt)
            return DriverResult("SUCCESS", "restarted-session", "done", "", "")

    drivers = CaptureDrivers()
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    await runtime.start()
    try:
        job = await runtime.wait("queued-fresh", 10)
        assert job.state == "succeeded"
        assert drivers.sessions == [""]
        assert drivers.prompts == ["fresh restart prompt"]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_cancelled_fresh_job_preserves_old_sessions_when_backend_reports_success(tmp_path) -> None:
    root = repository(tmp_path)
    catalog = config(tmp_path / "home")

    class RaceCancellingDrivers(FakeDrivers):
        async def execute(self, *, cancel_event, **kwargs) -> DriverResult:
            # Simulate cancellation arriving right as backend produces SUCCESS
            cancel_event.set()
            return DriverResult("SUCCESS", "unwanted-fresh-session", "success text", "", "")

    drivers = RaceCancellingDrivers()
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    tkey = target_execution_key(catalog.targets[0])
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        runtime.database.append_turn(
            project_id=project.id,
            context_key="stream",
            role="implement",
            target_id=catalog.targets[0].id,
            target_key=tkey,
            session_id="old-session",
            prompt="turn 1",
            response="response 1",
        )
        assert runtime.database.session(project.id, "stream", "implement", tkey) == "old-session"

        submitted = await runtime.submit(
            project.id,
            "implement",
            "cancelled prompt",
            context_key="stream",
            fresh_session=True,
        )
        job = await runtime.wait(submitted.job_id, 10)
        assert job.state in {"cancelled", "interrupted"}

        # Preserves old context sessions on cancellation race
        assert runtime.database.session(project.id, "stream", "implement", tkey) == "old-session"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_fresh_job_persistence_failure_rolls_back_and_preserves_old_sessions(tmp_path) -> None:
    root = repository(tmp_path)
    catalog = config(tmp_path / "home")

    class SuccessDrivers(FakeDrivers):
        async def execute(self, **kwargs) -> DriverResult:
            return DriverResult("SUCCESS", "new-session", "success text", "", "")

    runtime = Runtime(catalog)
    runtime.drivers = SuccessDrivers()
    tkey = target_execution_key(catalog.targets[0])
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        runtime.database.append_turn(
            project_id=project.id,
            context_key="stream",
            role="implement",
            target_id=catalog.targets[0].id,
            target_key=tkey,
            session_id="old-session",
            prompt="turn 1",
            response="response 1",
        )
        assert runtime.database.session(project.id, "stream", "implement", tkey) == "old-session"

        runtime.database._connection.execute("""
            CREATE TRIGGER fail_fresh_turn BEFORE INSERT ON context_turns
            BEGIN
                SELECT RAISE(FAIL, 'turn insert failed');
            END;
        """)

        submitted = await runtime.submit(
            project.id,
            "implement",
            "failing persistence prompt",
            context_key="stream",
            fresh_session=True,
        )
        job = await runtime.wait(submitted.job_id, 10)
        assert job.state == "failed"

        runtime.database._connection.execute("DROP TRIGGER fail_fresh_turn")

        # Atomic rollback preserves old session on persistence failure
        assert runtime.database.session(project.id, "stream", "implement", tkey) == "old-session"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_fresh_job_failure_updating_state_to_succeeded_preserves_old_session_and_turn_count(tmp_path) -> None:
    root = repository(tmp_path)
    catalog = config(tmp_path / "home")

    class SuccessDrivers(FakeDrivers):
        async def execute(self, **kwargs) -> DriverResult:
            return DriverResult("SUCCESS", "new-session", "success text", "", "")

    runtime = Runtime(catalog)
    runtime.drivers = SuccessDrivers()
    tkey = target_execution_key(catalog.targets[0])
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        runtime.database.append_turn(
            project_id=project.id,
            context_key="stream",
            role="implement",
            target_id=catalog.targets[0].id,
            target_key=tkey,
            session_id="old-session",
            prompt="turn 1",
            response="response 1",
        )
        assert runtime.database.session(project.id, "stream", "implement", tkey) == "old-session"
        initial_turns = len(runtime.database.recent_turns(project.id, "stream", "implement", 100))
        assert initial_turns == 1

        # Reject only state='succeeded'
        runtime.database._connection.execute("""
            CREATE TRIGGER reject_succeeded BEFORE UPDATE OF state ON jobs
            FOR EACH ROW
            WHEN NEW.state = 'succeeded'
            BEGIN
                SELECT RAISE(FAIL, 'reject succeeded state');
            END;
        """)

        submitted = await runtime.submit(
            project.id,
            "implement",
            "failing state update prompt",
            context_key="stream",
            fresh_session=True,
        )
        job = await runtime.wait(submitted.job_id, 10)
        assert job.state == "failed"

        runtime.database._connection.execute("DROP TRIGGER reject_succeeded")

        # Preserves old session and previous turn count
        assert runtime.database.session(project.id, "stream", "implement", tkey) == "old-session"
        assert len(runtime.database.recent_turns(project.id, "stream", "implement", 100)) == initial_turns
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_stream_bridge_blocking_backpressure_and_sentinel_drain(tmp_path) -> None:
    """Queue capacity of 256 blocks producer until consumer drains."""
    from openmcp.drivers import StreamBridge

    bridge = StreamBridge(queue_capacity=256)
    producer_threads: set[int] = set()

    # In a worker thread, emit 300 events
    def worker():
        import threading
        producer_threads.add(threading.get_ident())
        for i in range(300):
            bridge.emit({"kind": "assistant.text.delta", "entity_id": "msg-1", "data": {"text": f"{i} "}})
        bridge.close_producer()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    consumed = []
    async for evt in bridge.consumer():
        consumed.append(evt)

    thread.join(timeout=2.0)
    assert len(consumed) == 300
    assert len(producer_threads) == 1
    assert producer_threads != {threading.get_ident()}


@pytest.mark.asyncio
async def test_stream_bridge_event_loop_close_drains_accepted_events() -> None:
    from openmcp.drivers import StreamBridge

    bridge = StreamBridge(queue_capacity=256)
    await bridge.queue.put({
        "kind": "assistant.text.delta",
        "entity_id": "msg-1",
        "data": {"text": "accepted"},
    })
    await bridge.close()

    assert [event async for event in bridge.consumer()] == [{
        "kind": "assistant.text.delta",
        "entity_id": "msg-1",
        "data": {"text": "accepted"},
    }]


@pytest.mark.asyncio
async def test_stream_bridge_cancellation_drains_accepted_events(tmp_path) -> None:
    from openmcp.drivers import StreamBridge

    bridge = StreamBridge(queue_capacity=256)

    def worker():
        for i in range(10):
            bridge.emit({"kind": "assistant.text.delta", "entity_id": "msg-1", "data": {"text": f"item-{i}"}})
        bridge.close_producer()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    consumed = []
    async for evt in bridge.consumer():
        consumed.append(evt)

    thread.join(timeout=2.0)
    assert len(consumed) == 10


@pytest.mark.asyncio
async def test_stream_bridge_tool_activity_tracking() -> None:
    from openmcp.drivers import StreamBridge

    bridge = StreamBridge(queue_capacity=256)
    # 1. New bridge reports no activity
    assert bridge.has_tool_activity is False

    def emit_worker(events: list[dict[str, Any]]) -> None:
        for evt in events:
            bridge.emit(evt)

    # 2. Assistant deltas do not mark activity
    await asyncio.to_thread(emit_worker, [{"kind": "assistant.text.delta", "entity_id": "msg-1", "data": {"text": "hello"}}])
    assert bridge.has_tool_activity is False

    # 3. tool.completed alone does not mark activity
    await asyncio.to_thread(emit_worker, [{"kind": "tool.completed", "entity_id": "tool-1", "data": {"status": "completed"}}])
    assert bridge.has_tool_activity is False

    # 4. tool.started permanently marks activity
    await asyncio.to_thread(emit_worker, [{"kind": "tool.started", "entity_id": "tool-1", "data": {"tool": "grep"}}])
    assert bridge.has_tool_activity is True

    # Repeated tool.started retains signal
    await asyncio.to_thread(emit_worker, [{"kind": "tool.started", "entity_id": "tool-2", "data": {"tool": "read"}}])
    assert bridge.has_tool_activity is True

    # 5. Closing and draining preserve the signal
    await asyncio.to_thread(bridge.close_producer)
    assert bridge.has_tool_activity is True

    consumed = []
    async for event in bridge.consumer():
        consumed.append(event)
    assert len(consumed) == 4
    assert bridge.has_tool_activity is True


@pytest.mark.asyncio
async def test_stream_bridge_thread_ownership_no_sqlite_on_provider_thread(tmp_path) -> None:
    """Assert provider threads never touch the SQLite database."""
    from openmcp.drivers import StreamBridge
    root = repository(tmp_path)
    cat = config(tmp_path / "home")
    runtime = Runtime(cat)
    await runtime.start()

    accessed_threads: set[int] = set()
    orig_append = runtime.database.append_stream_events

    def tracking_append(*args, **kwargs):
        accessed_threads.add(threading.get_ident())
        return orig_append(*args, **kwargs)

    runtime.database.append_stream_events = tracking_append

    bridge = StreamBridge(queue_capacity=256)
    worker_tid = None

    def worker():
        nonlocal worker_tid
        worker_tid = threading.get_ident()
        bridge.emit({"kind": "assistant.text.delta", "entity_id": "msg-1", "data": {"text": "hello"}})
        bridge.close_producer()

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    async for _ in bridge.consumer():
        pass
    t.join(timeout=2.0)

    try:
        assert worker_tid is not None
        assert worker_tid not in accessed_threads
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_accepted_events_flush_before_lifecycle_completion(tmp_path) -> None:
    """Accepted stream events must be durably flushed before attempt.finished and job terminal state."""
    root = repository(tmp_path)
    cat = config(tmp_path / "home")

    class StreamingDrivers(FakeDrivers):
        async def execute(self, *, emitter=None, **kwargs) -> DriverResult:
            if emitter:
                def worker():
                    emitter({"kind": "assistant.text.delta", "entity_id": "msg-1", "data": {"text": "streaming content"}})
                await asyncio.to_thread(worker)
            return DriverResult("SUCCESS", "sess-1", "streaming content", "", "")

    runtime = Runtime(cat)
    runtime.drivers = StreamingDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        sub = await runtime.submit(project.id, "implement", "do streaming")
        job = await runtime.wait(sub.job_id, 5)
        assert job.state == "succeeded"

        events = runtime.database.stream_events(sub.job_id, after=0)
        assert any(e.kind == "assistant.text.delta" and e.data.get("text") == "streaming content" for e in events)
        finished = [e for e in events if e.kind == "attempt.finished"]
        assert len(finished) == 1
        assert finished[0].attempt == 1
        assert finished[0].data["status"] == "succeeded"
        assert finished[0].data["outcome"] == "SUCCESS"
        assert finished[0].data["error_code"] == ""
        delta_idx = next(i for i, e in enumerate(events) if e.kind == "assistant.text.delta")
        finished_idx = next(i for i, e in enumerate(events) if e.kind == "attempt.finished")
        assert delta_idx < finished_idx
        # Authoritative final result matches
        assert job.result.text == "streaming content"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_attempt_finished_cancelled_status_on_job_cancellation(tmp_path) -> None:
    root = repository(tmp_path)
    cat = config(tmp_path / "home")

    class CancellingStreamingDrivers(FakeDrivers):
        def __init__(self):
            super().__init__()
            self.started = asyncio.Event()

        async def execute(self, *, emitter=None, cancel_event=None, **kwargs) -> DriverResult:
            if emitter:
                def worker():
                    emitter({"kind": "assistant.text.delta", "entity_id": "msg-1", "data": {"text": "stream before cancel"}})
                await asyncio.to_thread(worker)
            self.started.set()
            while cancel_event and not cancel_event.is_set():
                await asyncio.sleep(0.01)
            return DriverResult("CANCELLED", "", "", "cancelled", "cancelled")

    drivers = CancellingStreamingDrivers()
    runtime = Runtime(cat)
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        sub = await runtime.submit(project.id, "implement", "cancel test")
        await drivers.started.wait()
        await runtime.cancel(sub.job_id)
        job = await runtime.wait(sub.job_id, 5)
        assert job.state == "cancelled"

        events = runtime.database.stream_events(sub.job_id, after=0)
        assert any(e.kind == "assistant.text.delta" for e in events)
        finished = [e for e in events if e.kind == "attempt.finished"]
        assert len(finished) == 1
        assert finished[0].attempt == 1
        assert finished[0].data["status"] == "cancelled"
        assert finished[0].data["outcome"] == "CANCELLED"
        assert finished[0].data["error_code"] == "cancelled"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_attempt_finished_records_cancelled_status_when_cancel_event_set(tmp_path) -> None:
    root = repository(tmp_path)
    cat = config(tmp_path / "home")

    class RaceCancellingDrivers(FakeDrivers):
        async def execute(self, *, emitter=None, cancel_event=None, **kwargs) -> DriverResult:
            if emitter:
                def worker():
                    emitter({"kind": "assistant.text.delta", "entity_id": "msg-1", "data": {"text": "streaming content"}})
                await asyncio.to_thread(worker)
            if cancel_event:
                cancel_event.set()
            return DriverResult("SUCCESS", "sess-1", "streaming content", "", "")

    runtime = Runtime(cat)
    runtime.drivers = RaceCancellingDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        sub = await runtime.submit(project.id, "implement", "test cancel race")
        job = await runtime.wait(sub.job_id, 5)
        assert job.state in {"cancelled", "interrupted"}

        events = runtime.database.stream_events(sub.job_id, after=0)
        finished = [e for e in events if e.kind == "attempt.finished"]
        assert len(finished) == 1
        assert finished[0].data["status"] == "cancelled"
        assert finished[0].data["outcome"] == "CANCELLED"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_execution_exact_quota_boundary_retains_finish_marker(tmp_path, monkeypatch) -> None:
    from openmcp.streaming import StreamRecorder

    orig_init = StreamRecorder.__init__
    def custom_init(self, *args, **kwargs):
        kwargs.setdefault("max_job_events", 2)
        orig_init(self, *args, **kwargs)
    monkeypatch.setattr(StreamRecorder, "__init__", custom_init)

    root = repository(tmp_path)
    cfg = config(tmp_path / "home")

    class ExactBoundaryDrivers(FakeDrivers):
        async def execute(self, *, emitter=None, **kwargs) -> DriverResult:
            if emitter:
                def worker():
                    emitter({"kind": "assistant.text.delta", "entity_id": "m1", "data": {"text": "first"}})
                    emitter({"kind": "assistant.text.delta", "entity_id": "m2", "data": {"text": "second"}})
                await asyncio.to_thread(worker)
            return DriverResult("SUCCESS", "sess-1", "all good", "", "")

    runtime = Runtime(cfg)
    runtime.drivers = ExactBoundaryDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        sub = await runtime.submit(project.id, "implement", "exact quota test")
        job = await runtime.wait(sub.job_id, 5)
        assert job.state == "succeeded"
        assert runtime.database.stream_is_truncated(sub.job_id) is False

        events = runtime.database.stream_events(sub.job_id, after=0)
        assert not any(e.kind == "stream.truncated" for e in events)
        finished = [e for e in events if e.kind == "attempt.finished"]
        assert len(finished) == 1
        assert finished[0].data["status"] == "succeeded"
        assert finished[0].data["outcome"] == "SUCCESS"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_failed_attempts_retain_attempt_labels(tmp_path) -> None:
    """Failed attempt transcripts must retain their attempt number and separate from successful attempts."""
    root = repository(tmp_path)
    selection = TargetSelection(("primary",), 2)
    cat = replace(
        config(tmp_path / "home"),
        profiles={"balanced": {"implement": selection, "review": selection, "consult": selection}},
    )

    class MultiAttemptDrivers(FakeDrivers):
        def __init__(self):
            super().__init__()
            self.call_count = 0

        async def execute(self, *, emitter=None, **kwargs) -> DriverResult:
            self.call_count += 1
            if emitter:
                def worker(c):
                    emitter({"kind": "assistant.text.delta", "entity_id": "msg-1", "data": {"text": f"attempt-{c}"}})
                await asyncio.to_thread(worker, self.call_count)
            if self.call_count == 1:
                return DriverResult("RETRYABLE", "", "", "first attempt failed", "backend_failure")
            return DriverResult("SUCCESS", "sess-2", "final success", "", "")

    runtime = Runtime(cat)
    runtime.drivers = MultiAttemptDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        sub = await runtime.submit(project.id, "implement", "do attempts")
        job = await runtime.wait(sub.job_id, 5)
        assert job.state == "succeeded"
        assert job.attempts == 2

        events = runtime.database.stream_events(sub.job_id, after=0)
        attempt_1_events = [e for e in events if e.attempt == 1 and e.kind == "assistant.text.delta"]
        attempt_2_events = [e for e in events if e.attempt == 2 and e.kind == "assistant.text.delta"]
        assert len(attempt_1_events) == 1
        assert attempt_1_events[0].data["text"] == "attempt-1"
        assert len(attempt_2_events) == 1
        assert attempt_2_events[0].data["text"] == "attempt-2"

        a1_all = [e for e in events if e.attempt == 1]
        a2_all = [e for e in events if e.attempt == 2]
        assert [e.kind for e in a1_all] == ["assistant.text.delta", "attempt.finished"]
        assert a1_all[1].data["status"] == "failed"
        assert a1_all[1].data["outcome"] == "RETRYABLE"
        assert a1_all[1].data["error_code"] == "backend_failure"

        assert [e.kind for e in a2_all] == ["assistant.text.delta", "attempt.finished"]
        assert a2_all[1].data["status"] == "succeeded"
        assert a2_all[1].data["outcome"] == "SUCCESS"
        assert a2_all[1].data["error_code"] == ""

        # Authoritative result is ONLY the successful one
        assert job.result.text == "final success"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_attempt_finished_does_not_reuse_prior_attempt_on_exception(tmp_path) -> None:
    """If drivers.execute raises an exception, the recorder must not reuse the prior attempt's DriverResult."""
    root = repository(tmp_path)
    selection = TargetSelection(("primary",), 2)
    cat = replace(
        config(tmp_path / "home"),
        profiles={"balanced": {"implement": selection, "review": selection, "consult": selection}},
    )

    class CrashingDrivers(FakeDrivers):
        def __init__(self):
            super().__init__()
            self.call_count = 0

        async def execute(self, *, emitter=None, **kwargs) -> DriverResult:
            self.call_count += 1
            if emitter:
                def worker(c):
                    emitter({"kind": "assistant.text.delta", "entity_id": "msg-1", "data": {"text": f"attempt-{c}"}})
                await asyncio.to_thread(worker, self.call_count)
            if self.call_count == 1:
                return DriverResult("RETRYABLE", "", "", "first attempt failed", "backend_failure")
            raise RuntimeError("driver crash on attempt 2")

    runtime = Runtime(cat)
    runtime.drivers = CrashingDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        sub = await runtime.submit(project.id, "implement", "do crashing attempt")
        job = await runtime.wait(sub.job_id, 5)
        assert job.state == "failed"

        events = runtime.database.stream_events(sub.job_id, after=0)
        a1_finished = [e for e in events if e.attempt == 1 and e.kind == "attempt.finished"]
        a2_finished = [e for e in events if e.attempt == 2 and e.kind == "attempt.finished"]
        assert len(a1_finished) == 1
        assert a1_finished[0].data["status"] == "failed"
        assert a1_finished[0].data["outcome"] == "RETRYABLE"
        assert a1_finished[0].data["error_code"] == "backend_failure"

        assert len(a2_finished) == 1
        assert a2_finished[0].data["status"] == "failed"
        assert a2_finished[0].data["outcome"] != "RETRYABLE"
        assert a2_finished[0].data["error_code"] == "execution_error"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_agy_continuations_stay_one_openmcp_attempt(tmp_path) -> None:
    """Agy continuations within one attempt must remain attempt=1."""
    root = repository(tmp_path)
    cat = config(
        tmp_path / "home",
        (TargetConfig(id="primary", backend="agy"),),
    )

    class AgyContinuationDrivers(FakeDrivers):
        async def execute(self, *, emitter=None, **kwargs) -> DriverResult:
            if emitter:
                def worker():
                    # Continuation 1
                    emitter({"kind": "assistant.text.delta", "entity_id": "msg-1", "data": {"text": "part 1"}})
                    # Continuation 2
                    emitter({"kind": "assistant.text.delta", "entity_id": "msg-2", "data": {"text": "part 2"}})
                await asyncio.to_thread(worker)
            return DriverResult("SUCCESS", "agy-sess", "part 1\n\npart 2", "", "")

    runtime = Runtime(cat)
    runtime.drivers = AgyContinuationDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        sub = await runtime.submit(project.id, "implement", "do agy")
        job = await runtime.wait(sub.job_id, 5)
        assert job.state == "succeeded"
        assert job.attempts == 1

        events = runtime.database.stream_events(sub.job_id, after=0)
        deltas = [e for e in events if e.kind == "assistant.text.delta"]
        assert len(deltas) == 2
        assert all(e.attempt == 1 for e in deltas)
        assert {e.entity_id for e in deltas} == {"msg-1", "msg-2"}
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_capability_check_before_submission_with_final_only_fallback(tmp_path, monkeypatch) -> None:
    """Structured mode capability check happens before prompt submission with final-only fallback."""
    from openmcp.drivers import DriverRegistry

    registry = DriverRegistry()
    target_old = TargetConfig(id="target-old", backend="claude-old")
    target_new = TargetConfig(id="target-new", backend="claude-new")

    fake_bins = {
        "claude-old": "/bin/claude-old",
        "claude-new": "/bin/claude-new",
    }
    monkeypatch.setattr("shutil.which", lambda name: fake_bins.get(name))

    # Assert capability check method exists and caches per resolved executable
    assert hasattr(registry, "supports_structured_streaming")
    checks = []

    def fake_version_check(exe_path: str) -> bool:
        checks.append(exe_path)
        return "new" in exe_path

    # Check for target_old -> False, cached per resolved executable /bin/claude-old
    assert registry.supports_structured_streaming(target_old, version_check=fake_version_check) is False
    assert len(checks) == 1
    # Repeated call uses cache without calling check again
    assert registry.supports_structured_streaming(target_old, version_check=fake_version_check) is False
    assert len(checks) == 1

    # Check for target_new -> True, cached per resolved executable /bin/claude-new
    assert registry.supports_structured_streaming(target_new, version_check=fake_version_check) is True
    assert len(checks) == 2
    assert registry.supports_structured_streaming(target_new, version_check=fake_version_check) is True
    assert len(checks) == 2

    # In execution, when capability is unsupported, TargetExecutor falls back to final-only invocation (emitter=None)
    root = repository(tmp_path)
    target_exec = TargetConfig(id="target-exec", backend="claude")
    cat = config(tmp_path / "home", (target_exec,))
    runtime = Runtime(cat)

    received_emitters = []

    class MockExecutorDrivers(FakeDrivers):
        def supports_structured_streaming(self, target, **kwargs):
            return False

        async def execute(self, *, emitter=None, **kwargs) -> DriverResult:
            received_emitters.append(emitter)
            return DriverResult("SUCCESS", "sess-old", "fallback output", "", "")

    runtime.drivers = MockExecutorDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        sub = await runtime.submit(project.id, "implement", "test fallback")
        job = await runtime.wait(sub.job_id, 5)
        assert job.state == "succeeded"
        assert job.result.text == "fallback output"
        # Emitter passed to driver must be None for final-only fallback
        assert received_emitters == [None]
        # No stream events recorded
        events = runtime.database.stream_events(sub.job_id, after=0)
        assert len(events) == 0
    finally:
        await runtime.close()


def test_detect_structured_mode_invokes_help_probe_and_detects_support(tmp_path, monkeypatch) -> None:
    """Default capability probe invokes configured --help command and detects supported structured mode."""
    from openmcp.drivers import DriverRegistry

    marker = tmp_path / "probe_invoked.txt"
    fake_cli = tmp_path / "fake-claude"
    fake_cli.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "--help" ]; then\n'
        f"  echo called >> {marker}\n"
        '  echo "options: stream-json --include-partial-messages"\n'
        "fi\n",
        encoding="utf-8",
    )
    fake_cli.chmod(0o755)

    registry = DriverRegistry()
    target = TargetConfig(id="target-claude", backend="claude")
    monkeypatch.setattr("shutil.which", lambda name: str(fake_cli) if name == "claude" else None)

    # Reach default capability probe without version_check override
    assert registry.supports_structured_streaming(target) is True
    assert marker.read_text(encoding="utf-8").strip() == "called"

    # Cached per resolved executable: second call should not re-invoke probe
    assert registry.supports_structured_streaming(target) is True
    assert marker.read_text(encoding="utf-8").splitlines() == ["called"]


def test_codex_capability_probes_exec_subcommand(tmp_path, monkeypatch) -> None:
    """Codex capability probe must run 'codex exec --help' rather than top-level 'codex --help'."""
    from openmcp.drivers import DriverRegistry

    invocations: list[str] = []
    fake_codex = tmp_path / "fake-codex"
    fake_codex.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "exec" ] && [ "$2" = "--help" ]; then\n'
        '  echo "exec-probe" >> ' + str(tmp_path / "codex_log.txt") + '\n'
        '  echo "Usage: codex exec [OPTIONS] [PROMPT]"\n'
        '  echo "Options:"\n'
        '  echo "  --json  Output structured JSONL events"\n'
        'elif [ "$1" = "--help" ]; then\n'
        '  echo "toplevel-probe" >> ' + str(tmp_path / "codex_log.txt") + '\n'
        '  echo "Usage: codex [OPTIONS] COMMAND [ARGS]..."\n'
        '  echo "Commands:"\n'
        '  echo "  exec    Execute prompt"\n'
        '  echo "  review  Review workspace"\n'
        "fi\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)

    registry = DriverRegistry()
    target = TargetConfig(id="target-codex", backend="codex")
    monkeypatch.setattr("shutil.which", lambda name: str(fake_codex) if name == "codex" else None)

    # Must probe 'exec --help' and detect structured streaming support
    assert registry.supports_structured_streaming(target) is True
    log_content = (tmp_path / "codex_log.txt").read_text(encoding="utf-8").strip()
    assert log_content == "exec-probe"

    # Also test representative older codex where exec --help lacks --json
    fake_old_codex = tmp_path / "fake-old-codex"
    fake_old_codex.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "exec" ] && [ "$2" = "--help" ]; then\n'
        '  echo "Usage: codex exec [OPTIONS] [PROMPT]"\n'
        '  echo "Options: --help Show this message"\n'
        "fi\n",
        encoding="utf-8",
    )
    fake_old_codex.chmod(0o755)
    target_old = TargetConfig(id="target-old-codex", backend="codex-old")
    monkeypatch.setattr("shutil.which", lambda name: str(fake_old_codex) if name == "codex-old" else (str(fake_codex) if name == "codex" else None))
    assert registry.supports_structured_streaming(target_old) is False


@pytest.mark.asyncio
async def test_execution_durable_reload_preserves_streaming_and_authoritative_result(tmp_path) -> None:
    """Complete job streaming execution, restart runtime, and assert durable reconstruction."""
    root = repository(tmp_path)
    cfg = config(tmp_path / "home")

    class SampleDrivers(FakeDrivers):
        async def execute(self, *, emitter=None, **kwargs) -> DriverResult:
            if emitter:
                def worker():
                    emitter({"kind": "assistant.message.started", "entity_id": "m1", "data": {}})
                    emitter({"kind": "assistant.text.delta", "entity_id": "m1", "data": {"text": "live tokens"}})
                    emitter({"kind": "assistant.message.completed", "entity_id": "m1", "data": {}})
                await asyncio.to_thread(worker)
            return DriverResult("SUCCESS", "sess-1", "live tokens", "", "")

    runtime1 = Runtime(cfg)
    runtime1.drivers = SampleDrivers()
    await runtime1.start()
    try:
        project = runtime1.register_project(str(root))
        sub = await runtime1.submit(project.id, "implement", "test reload")
        job = await runtime1.wait(sub.job_id, 5)
        assert job.state == "succeeded"
        hw1 = runtime1.database.stream_high_water(sub.job_id)
        assert hw1 > 0
    finally:
        await runtime1.close()

    runtime2 = Runtime(cfg)
    try:
        hw2 = runtime2.database.stream_high_water(sub.job_id)
        assert hw2 == hw1
        events = runtime2.database.stream_events(sub.job_id, after=0)
        assert len(events) >= 3
        assert any(e.kind == "assistant.text.delta" and e.data.get("text") == "live tokens" for e in events)
        job2 = runtime2.database.job(sub.job_id)
        assert job2 is not None
        assert job2.result.text == "live tokens"
    finally:
        await runtime2.close()


@pytest.mark.asyncio
async def test_execution_retries_across_runtime_reload(tmp_path) -> None:
    """Failed attempt transcripts and retry attempts survive daemon restart with correct labels."""
    root = repository(tmp_path)
    selection = TargetSelection(("primary",), 2)
    cfg = replace(
        config(tmp_path / "home"),
        profiles={"balanced": {"implement": selection, "review": selection, "consult": selection}},
    )

    class RetryDrivers(FakeDrivers):
        def __init__(self):
            super().__init__()
            self.count = 0

        async def execute(self, *, emitter=None, **kwargs) -> DriverResult:
            self.count += 1
            if emitter:
                def worker(c):
                    emitter({"kind": "assistant.text.delta", "entity_id": f"msg-{c}", "data": {"text": f"attempt-{c}-text"}})
                await asyncio.to_thread(worker, self.count)
            if self.count == 1:
                return DriverResult("RETRYABLE", "", "", "transient error", "network_err")
            return DriverResult("SUCCESS", "sess-retry", "successful second attempt", "", "")

    runtime1 = Runtime(cfg)
    runtime1.drivers = RetryDrivers()
    await runtime1.start()
    try:
        project = runtime1.register_project(str(root))
        sub = await runtime1.submit(project.id, "implement", "retry test")
        job = await runtime1.wait(sub.job_id, 5)
        assert job.state == "succeeded"
        assert job.attempts == 2
    finally:
        await runtime1.close()

    runtime2 = Runtime(cfg)
    try:
        events = runtime2.database.stream_events(sub.job_id, after=0)
        a1 = [e for e in events if e.attempt == 1 and e.kind == "assistant.text.delta"]
        a2 = [e for e in events if e.attempt == 2 and e.kind == "assistant.text.delta"]
        assert len(a1) == 1
        assert a1[0].data["text"] == "attempt-1-text"
        assert len(a2) == 1
        assert a2[0].data["text"] == "attempt-2-text"
        reloaded_job = runtime2.database.job(sub.job_id)
        assert reloaded_job.result.text == "successful second attempt"
    finally:
        await runtime2.close()


@pytest.mark.asyncio
async def test_execution_truncation_limits_preserve_final_result(tmp_path, monkeypatch) -> None:
    """Stream truncation marks stream.truncated while keeping job.result.text authoritative."""
    from openmcp.streaming import StreamRecorder

    orig_init = StreamRecorder.__init__
    def custom_init(self, *args, **kwargs):
        kwargs.setdefault("max_job_bytes", 500)
        orig_init(self, *args, **kwargs)
    monkeypatch.setattr(StreamRecorder, "__init__", custom_init)

    root = repository(tmp_path)
    cfg = config(tmp_path / "home")

    class VoluminousDrivers(FakeDrivers):
        async def execute(self, *, emitter=None, **kwargs) -> DriverResult:
            if emitter:
                def worker():
                    for i in range(10):
                        emitter({"kind": "assistant.text.delta", "entity_id": f"m{i}", "data": {"text": "A" * 100}})
                await asyncio.to_thread(worker)
            return DriverResult("SUCCESS", "sess-vol", "Full authoritative final text exceeding quota.", "", "")

    runtime = Runtime(cfg)
    runtime.drivers = VoluminousDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        sub = await runtime.submit(project.id, "implement", "voluminous test")
        job = await runtime.wait(sub.job_id, 5)
        assert job.state == "succeeded"
        assert job.result.text == "Full authoritative final text exceeding quota."

        assert runtime.database.stream_is_truncated(sub.job_id) is True
        events = runtime.database.stream_events(sub.job_id, after=0)
        assert any(e.kind == "stream.truncated" for e in events)
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_execution_persistence_failure_does_not_corrupt_stream_or_fail_job(tmp_path) -> None:
    """Persistence failure logs warning and records event without aborting terminal job state."""
    root = repository(tmp_path)
    cfg = config(tmp_path / "home")

    class FailingStreamDrivers(FakeDrivers):
        async def execute(self, *, emitter=None, **kwargs) -> DriverResult:
            if emitter:
                def worker():
                    emitter({"kind": "assistant.text.delta", "entity_id": "m1", "data": {"text": "first event"}})
                await asyncio.to_thread(worker)
            return DriverResult("SUCCESS", "sess-fail", "terminal result text", "", "")

    runtime = Runtime(cfg)
    runtime.drivers = FailingStreamDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        orig_append = runtime.database.append_stream_events

        call_count = 0
        def fragile_append(job_id, events):
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                raise RuntimeError("simulated disk write failure")
            return orig_append(job_id, events)

        runtime.database.append_stream_events = fragile_append
        sub = await runtime.submit(project.id, "implement", "persistence fail test")
        job = await runtime.wait(sub.job_id, 5)
        assert job.state == "succeeded"
        assert job.result.text == "terminal result text"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_execution_security_regression_fixtures_strip_forbidden_content(tmp_path) -> None:
    """Security regression asserting forbidden content never reaches database rows across execution."""
    root = repository(tmp_path)
    cfg = config(tmp_path / "home")

    forbidden_secrets = [
        "FORBIDDEN_PROMPT_SECRET_ABC123",
        "FORBIDDEN_THINKING_DELTA_XYZ789",
        "FORBIDDEN_TOOL_ARG_SSH_KEY_999",
        "FORBIDDEN_TOOL_RESULT_HASH_555",
        "FORBIDDEN_BASH_CMD_LINE_777",
        "FORBIDDEN_DIAGNOSTIC_TRACE_333",
        "FORBIDDEN_ENV_VARIABLE_222",
        "FORBIDDEN_SUBAGENT_TRANSCRIPT_111",
    ]

    class DirtyNormalizedDrivers(FakeDrivers):
        async def execute(self, *, emitter=None, **kwargs) -> DriverResult:
            if emitter:
                def worker():
                    emitter({"kind": "assistant.text.delta", "entity_id": "safe-msg", "data": {"text": "Safe verified response."}})
                    emitter({"kind": "tool.started", "entity_id": "tool-1", "data": {"tool": "read"}})
                    emitter({"kind": "tool.completed", "entity_id": "tool-1", "data": {"status": "completed"}})
                await asyncio.to_thread(worker)
            return DriverResult("SUCCESS", "sess-clean", "Safe verified response.", "", "")

    runtime = Runtime(cfg)
    runtime.drivers = DirtyNormalizedDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        sub = await runtime.submit(project.id, "implement", f"run with {forbidden_secrets[0]}")
        job = await runtime.wait(sub.job_id, 5)
        assert job.state == "succeeded"
        assert job.result.text == "Safe verified response."

        cursor = runtime.database._connection.execute(
            "SELECT id, kind, entity_id, parent_entity_id, data_json FROM job_stream_events WHERE job_id=?",
            (sub.job_id,),
        )
        stream_rows_raw = str(cursor.fetchall())
        for secret in forbidden_secrets:
            assert secret not in stream_rows_raw
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_agy_never_promotes_log_text_to_agent_messages_on_empty_stdout(tmp_path, monkeypatch) -> None:
    """Empty stdout with diagnostic/secret log text extracts session ID but never promotes log text."""
    from openmcp.backends import agy as agy_backend
    from openmcp.backends.agy import AgyParams

    secret_diagnostic = "DIAGNOSTIC_SECRET_TRACE_TOKEN_NEVER_PROMOTE_777"
    session_id = "11111111-2222-3333-4444-555555555555"

    def fake_run_shell(cmd, cwd=None, **kwargs):
        log_idx = cmd.index("--log-file") + 1
        log_path = Path(cmd[log_idx])
        log_path.write_text(
            f"Created conversation {session_id}\n[diag] {secret_diagnostic}\nserver internal dump",
            encoding="utf-8",
        )
        yield ""

    monkeypatch.setattr(agy_backend.shutil, "which", lambda _: "/bin/agy")
    monkeypatch.setattr(agy_backend, "run_shell_command", fake_run_shell)

    res = await agy_backend.execute(AgyParams(PROMPT="test", cd=tmp_path))
    assert res.SESSION_ID == session_id
    assert secret_diagnostic not in res.agent_messages
    assert "server internal dump" not in res.agent_messages
    assert res.agent_messages == ""
    assert res.outcome == "FATAL"
    assert res.error_class == "no_agent_messages"


def test_agy_execute_sync_post_submission_type_error_single_invocation(tmp_path, monkeypatch) -> None:
    """Post-submission TypeError in _execute_once raises immediately with exactly one invocation."""
    from openmcp.backends import agy as agy_backend
    from openmcp.backends.agy import AgyParams

    call_count = 0

    def fail_with_type_error(params, entity_state=None):
        nonlocal call_count
        call_count += 1
        raise TypeError("post-submission internal failure")

    monkeypatch.setattr(agy_backend, "_execute_once", fail_with_type_error)

    with pytest.raises(TypeError, match="post-submission internal failure"):
        agy_backend._execute_sync(AgyParams(PROMPT="test", cd=tmp_path))

    assert call_count == 1


def test_agy_continuation_post_submission_type_error_single_invocation(tmp_path, monkeypatch) -> None:
    """Post-submission TypeError during continuation raises immediately with exactly one continuation invocation."""
    from openmcp.backends import agy as agy_backend
    from openmcp.backends.agy import AgyParams, BackendResult

    initial_called = 0
    continuation_called = 0

    def step_execute_once(params, entity_state=None):
        nonlocal initial_called, continuation_called
        if params.PROMPT == "test":
            initial_called += 1
            return BackendResult("OK", "sess-cont-123", "first reply", "", "")
        continuation_called += 1
        raise TypeError("post-submission continuation failure")

    monkeypatch.setattr(agy_backend, "_execute_once", step_execute_once)
    monkeypatch.setattr(agy_backend, "_agy_has_pending_tasks", lambda *args: True)

    with pytest.raises(TypeError, match="post-submission continuation failure"):
        agy_backend._execute_sync(AgyParams(PROMPT="test", cd=tmp_path))

    assert initial_called == 1
    assert continuation_called == 1


@pytest.mark.asyncio
async def test_execution_all_provider_fixtures_persistence_and_authoritative_results(tmp_path, monkeypatch) -> None:
    """Exercise sanitized Claude, Codex, Pi, and Agy fixtures through execution flow."""
    from openmcp.backends.claude import ClaudeParams, _execute_sync as claude_sync
    from openmcp.backends.codex import CodexParams, _execute_sync as codex_sync
    from openmcp.backends.pi import PiParams, _execute_sync as pi_sync
    from openmcp.backends.agy import AgyParams, _execute_once as agy_execute_once

    root = repository(tmp_path)
    cfg = config(tmp_path / "home")

    secrets = [
        "SECRET_CLAUDE_PROMPT_999",
        "SECRET_CODEX_CMD_888",
        "SECRET_PI_PATTERN_777",
        "SECRET_AGY_DIAG_666",
        "SECRET_REASONING_555",
        "SECRET_TOOL_RESULT_444",
    ]

    dirty_streams = {
        "claude": [
            json.dumps({"type": "system", "content": f"system {secrets[0]}"}),
            json.dumps({"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "thinking_delta", "thinking": secrets[4]}, "index": 0}}),
            json.dumps({"type": "stream_event", "event": {"type": "content_block_start", "content_block": {"type": "tool_use", "id": "t1", "name": "read", "input": {"secret": secrets[1]}}}}),
            json.dumps({"type": "stream_event", "event": {"type": "content_block_stop", "index": 1}}),
            json.dumps({"type": "stream_event", "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Claude verified clean."}, "index": 2}}),
            json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "Claude verified clean.", "session_id": "c-sess"}),
        ],
        "codex": [
            json.dumps({"type": "thread.started", "thread_id": "thread-1"}),
            json.dumps({"type": "item.started", "item": {"type": "tool_call", "id": "tc1", "name": "bash", "input": secrets[1]}}),
            json.dumps({"type": "item.completed", "item": {"type": "tool_call", "id": "tc1", "name": "bash", "output": secrets[5], "status": "completed"}}),
            json.dumps({"type": "item.completed", "item": {"type": "reasoning", "text": secrets[4]}}),
            json.dumps({"type": "item.completed", "item": {"type": "agent_message", "id": "m1", "text": "Codex verified clean."}}),
        ],
        "pi": [
            json.dumps({"type": "session", "id": "pi-sess"}),
            json.dumps({"type": "message_update", "assistantMessageEvent": {"type": "thinking_delta", "delta": secrets[4]}}),
            json.dumps({"type": "message_update", "assistantMessageEvent": {"type": "text_delta", "delta": "Pi verified clean."}}),
            json.dumps({"type": "tool_execution_start", "toolCallId": "pt1", "toolName": "grep", "args": {"pattern": secrets[2]}}),
            json.dumps({"type": "tool_execution_end", "toolCallId": "pt1", "isError": False, "result": secrets[5]}),
            json.dumps({"type": "message_end", "message": {"role": "assistant", "content": [{"type": "text", "text": "Pi verified clean."}]}}),
        ],
        "agy": [
            "Created conversation 12345678-1234-1234-1234-123456789abc",
            f"[diagnostic] {secrets[3]} and server trace",
            json.dumps({"type": "assistant.text.delta", "text": "Agy verified clean."}),
            json.dumps({"type": "tool.started", "tool_name": "exec", "arguments": {"token": secrets[1]}}),
            json.dumps({"type": "tool.completed", "status": "completed", "result": secrets[5]}),
            json.dumps({"type": "result", "result": "Agy verified clean."}),
        ],
    }
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/mock")

    class RealAdapterDrivers(FakeDrivers):
        def __init__(self, backend_name):
            super().__init__()
            self.backend_name = backend_name

        async def execute(self, *, emitter=None, **kwargs) -> DriverResult:
            lines = dirty_streams[self.backend_name]
            def run_adapter():
                if self.backend_name == "claude":
                    monkeypatch.setattr("openmcp.backends.claude.run_shell_command", lambda *args, **kw: (l for l in lines))
                    return claude_sync(ClaudeParams(PROMPT="p", cd=tmp_path, emitter=emitter))
                elif self.backend_name == "codex":
                    monkeypatch.setattr("openmcp.backends.codex.run_shell_command", lambda *args, **kw: (l for l in lines))
                    return codex_sync(CodexParams(PROMPT="p", cd=tmp_path, emitter=emitter))
                elif self.backend_name == "pi":
                    monkeypatch.setattr("openmcp.backends.pi.run_shell_command", lambda *args, **kw: (l for l in lines))
                    return pi_sync(PiParams(PROMPT="p", cd=tmp_path, emitter=emitter))
                else:
                    monkeypatch.setattr("openmcp.backends.agy.run_shell_command", lambda *args, **kw: (l for l in lines))
                    return agy_execute_once(AgyParams(PROMPT="p", cd=tmp_path, emitter=emitter))

            res = await asyncio.to_thread(run_adapter)
            return DriverResult(
                outcome="SUCCESS" if res.outcome == "OK" else "FATAL",
                session_id=res.SESSION_ID,
                text=res.agent_messages,
                error=res.error,
                error_code=res.error_class,
            )

    for backend_name in ("claude", "codex", "pi", "agy"):
        runtime = Runtime(cfg)
        runtime.drivers = RealAdapterDrivers(backend_name)
        await runtime.start()
        try:
            project = runtime.register_project(str(root))
            sub = await runtime.submit(project.id, "implement", f"run {backend_name}")
            job = await runtime.wait(sub.job_id, 5)
            assert job.state == "succeeded"
            assert "verified clean." in job.result.text

            for s in secrets:
                assert s not in job.result.text

            cursor = runtime.database._connection.execute(
                "SELECT id, kind, entity_id, parent_entity_id, data_json FROM job_stream_events WHERE job_id=?",
                (sub.job_id,),
            )
            rows = cursor.fetchall()
            rows_data_text = " ".join(r["data_json"] for r in rows)

            # Prompts (secrets[0]), diagnostic traces (secrets[3]), and reasoning (secrets[4]) must never persist
            for s in [secrets[0], secrets[3], secrets[4]]:
                assert s not in rows_data_text, f"{backend_name} leaked non-tool secret {s} in stream event data"

            # Approved tool payloads must persist in the stream event data
            if backend_name in {"claude", "codex", "agy"}:
                assert secrets[1] in rows_data_text, f"{backend_name} missing persisted tool input {secrets[1]}"
            if backend_name == "pi":
                assert secrets[2] in rows_data_text, f"{backend_name} missing persisted tool input {secrets[2]}"
            if backend_name in {"codex", "pi", "agy"}:
                assert secrets[5] in rows_data_text, f"{backend_name} missing persisted tool output {secrets[5]}"

            # Activity classification in persisted stream events
            tool_start_rows = [r for r in rows if r["kind"] == "tool.started"]
            assert len(tool_start_rows) >= 1
            for r in tool_start_rows:
                data = json.loads(r["data_json"])
                assert "activity" in data, f"{backend_name} missing activity in persisted tool.started"
                if backend_name == "codex":
                    assert data["activity"] == "command"
                else:
                    assert data["activity"] == "tool_call"

            tool_completed_rows = [r for r in rows if r["kind"] == "tool.completed"]
            for r in tool_completed_rows:
                data = json.loads(r["data_json"])
                assert "activity" not in data, f"{backend_name} leaked activity to tool.completed"
        finally:
            await runtime.close()


@dataclass(frozen=True)
class RecordedInvocation:
    target_id: str
    session_id: str
    prompt: str
    emitted_tool_activity: bool


class ScriptedRecoveryDrivers(FakeDrivers):
    def __init__(self, script: list[tuple[DriverResult, bool]]) -> None:
        super().__init__()
        self.script = list(script)
        self.calls: list[RecordedInvocation] = []
        self.on_call: Callable[[int, TargetConfig, str, threading.Event | None], None] | None = None

    async def execute(
        self,
        *,
        target: TargetConfig,
        cwd: Path,
        session_id: str,
        prompt: str = "",
        emitter=None,
        cancel_event=None,
        **kwargs,
    ) -> DriverResult:
        call_idx = len(self.calls)
        if self.on_call:
            self.on_call(call_idx, target, session_id, cancel_event)
        if self.script:
            result, emit_tool = self.script.pop(0)
        else:
            result, emit_tool = (
                DriverResult("SUCCESS", f"session-{target.id}", "default text", "", ""),
                False,
            )

        if emit_tool and emitter:
            await asyncio.to_thread(emitter, {"kind": "tool.started", "tool_name": "bash"})

        self.calls.append(
            RecordedInvocation(
                target_id=target.id,
                session_id=session_id,
                prompt=prompt,
                emitted_tool_activity=emit_tool,
            )
        )
        return result


@pytest.mark.asyncio
async def test_recovery_resumed_overflow_followed_by_successful_reconstruction(tmp_path) -> None:
    root = repository(tmp_path)
    script = [
        (DriverResult("RETRYABLE", "old-sess-1", "", "context length exceeded", "context_overflow"), False),
        (DriverResult("SUCCESS", "reconstructed-sess-2", "reconstructed answer", "", ""), False),
    ]
    drivers = ScriptedRecoveryDrivers(script)
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = drivers
    target = runtime.catalog.targets[0]
    tkey = target_execution_key(target)
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        runtime.database.append_turn(
            project_id=project.id,
            context_key="feature",
            role="implement",
            target_id=target.id,
            target_key=tkey,
            session_id="old-sess-1",
            prompt="turn 1 prompt",
            response="turn 1 response",
        )
        sub = await runtime.submit(project.id, "implement", "turn 2 prompt", context_key="feature")
        job = await runtime.wait(sub.job_id, 5)
        assert job.state == "succeeded"

        assert len(drivers.calls) == 2
        # Exact invocation order and arguments
        assert drivers.calls[0].target_id == target.id
        assert drivers.calls[0].session_id == "old-sess-1"
        assert drivers.calls[0].prompt == "turn 2 prompt"
        assert drivers.calls[0].emitted_tool_activity is False

        assert drivers.calls[1].target_id == target.id
        assert drivers.calls[1].session_id == ""
        assert "Previous context:\n\nUser:\nturn 1 prompt\n\nAssistant:\nturn 1 response" in drivers.calls[1].prompt
        assert "Current request:\n\nturn 2 prompt" in drivers.calls[1].prompt
        assert drivers.calls[1].emitted_tool_activity is False

        # Database session replaced
        assert runtime.database.session(project.id, "feature", "implement", tkey) == "reconstructed-sess-2"

        # Events emitted
        events = runtime.database.events(sub.job_id)
        kinds = [e["kind"] for e in events]
        assert "target.context_overflow" in kinds
        assert "target.session_recovery_started" in kinds
        assert "target.session_recovery_finished" in kinds
        assert "target.session_replaced" in kinds

        # Event payload checks
        overflow_events = [e for e in events if e["kind"] == "target.context_overflow"]
        assert overflow_events[0]["data"]["error_code"] == "context_overflow"
        rec_started = [e for e in events if e["kind"] == "target.session_recovery_started"]
        assert rec_started[0]["data"]["phase"] == "reconstruct"
        rec_finished = [e for e in events if e["kind"] == "target.session_recovery_finished"]
        assert rec_finished[0]["data"]["phase"] == "reconstruct"
        assert rec_finished[0]["data"]["outcome"] == "SUCCESS"
        sess_rep = [e for e in events if e["kind"] == "target.session_replaced"]
        assert sess_rep[0]["data"]["phase"] == "reconstruct"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_recovery_reconstruction_overflow_followed_by_prompt_only_success(tmp_path) -> None:
    root = repository(tmp_path)
    script = [
        (DriverResult("RETRYABLE", "old-sess-1", "", "context length exceeded", "context_overflow"), False),
        (DriverResult("RETRYABLE", "", "", "context length exceeded", "context_overflow"), False),
        (DriverResult("SUCCESS", "prompt-only-sess-3", "prompt-only answer", "", ""), False),
    ]
    drivers = ScriptedRecoveryDrivers(script)
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = drivers
    target = runtime.catalog.targets[0]
    tkey = target_execution_key(target)
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        runtime.database.append_turn(
            project_id=project.id,
            context_key="feature",
            role="implement",
            target_id=target.id,
            target_key=tkey,
            session_id="old-sess-1",
            prompt="turn 1 prompt",
            response="turn 1 response",
        )
        sub = await runtime.submit(project.id, "implement", "turn 2 prompt", context_key="feature")
        job = await runtime.wait(sub.job_id, 5)
        assert job.state == "succeeded"

        assert len(drivers.calls) == 3
        # Exact invocation order and arguments
        assert drivers.calls[0].target_id == target.id
        assert drivers.calls[0].session_id == "old-sess-1"
        assert drivers.calls[0].prompt == "turn 2 prompt"

        assert drivers.calls[1].target_id == target.id
        assert drivers.calls[1].session_id == ""
        assert "Previous context:" in drivers.calls[1].prompt

        assert drivers.calls[2].target_id == target.id
        assert drivers.calls[2].session_id == ""
        assert drivers.calls[2].prompt == "turn 2 prompt"

        assert runtime.database.session(project.id, "feature", "implement", tkey) == "prompt-only-sess-3"

        events = runtime.database.events(sub.job_id)
        phases = [e["data"].get("phase") for e in events if e["kind"] == "target.session_recovery_started"]
        assert phases == ["reconstruct", "fresh"]
        rep = [e for e in events if e["kind"] == "target.session_replaced"]
        assert rep[0]["data"]["phase"] == "fresh"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_recovery_duplicate_prompt_only_suppression_when_history_adds_nothing(tmp_path) -> None:
    root = repository(tmp_path)
    script = [
        (DriverResult("RETRYABLE", "old-sess-1", "", "context length exceeded", "context_overflow"), False),
        (DriverResult("RETRYABLE", "", "", "context length exceeded", "context_overflow"), False),
        (DriverResult("RETRYABLE", "", "", "unexpected third call", "context_overflow"), False),
    ]
    drivers = ScriptedRecoveryDrivers(script)
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = drivers
    target = runtime.catalog.targets[0]
    tkey = target_execution_key(target)
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        # Seed session directly without any turns in context_turns
        runtime.database._connection.execute(
            """INSERT INTO context_sessions(project_id, context_key, role, target_id, target_key, lane, session_id, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, '2026-01-01T00:00:00Z')""",
            (project.id, "feature", "implement", target.id, tkey, "", "old-sess-1"),
        )
        assert runtime.database.session(project.id, "feature", "implement", tkey) == "old-sess-1"

        sub = await runtime.submit(project.id, "implement", "turn 1 prompt", context_key="feature")
        job = await runtime.wait(sub.job_id, 5)
        assert job.state == "failed"

        # Exactly 2 invocations: resumed call and one empty-session prompt call
        assert len(drivers.calls) == 2
        assert drivers.calls[0].session_id == "old-sess-1"
        assert drivers.calls[0].prompt == "turn 1 prompt"
        assert drivers.calls[1].session_id == ""
        assert drivers.calls[1].prompt == "turn 1 prompt"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_recovery_tool_activity_during_resumed_call(tmp_path) -> None:
    root = repository(tmp_path)
    catalog = config(
        tmp_path / "home",
        (TargetConfig(id="primary", backend="codex"), TargetConfig(id="secondary", backend="codex")),
    )
    script = [
        (DriverResult("RETRYABLE", "old-sess-1", "", "context length exceeded", "context_overflow"), True),
        (DriverResult("SUCCESS", "should-not-run", "should not run", "", ""), False),
    ]
    drivers = ScriptedRecoveryDrivers(script)
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    tkey = target_execution_key(catalog.targets[0])
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        runtime.database.append_turn(
            project_id=project.id,
            context_key="feature",
            role="implement",
            target_id="primary",
            target_key=tkey,
            session_id="old-sess-1",
            prompt="t1",
            response="r1",
        )
        sub = await runtime.submit(project.id, "implement", "turn 2 prompt", context_key="feature")
        job = await runtime.wait(sub.job_id, 5)
        assert job.state == "failed"

        # Tool activity on resumed call blocks both same-target recovery and cross-target failover
        assert len(drivers.calls) == 1
        assert drivers.calls[0].target_id == "primary"
        assert drivers.calls[0].emitted_tool_activity is True

        # Old session preserved
        assert runtime.database.session(project.id, "feature", "implement", tkey) == "old-sess-1"

        # Overflow does not penalize health
        assert runtime.database.target_health(tkey)["consecutive_failures"] == 0
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_recovery_tool_activity_during_reconstruction(tmp_path) -> None:
    root = repository(tmp_path)
    catalog = config(
        tmp_path / "home",
        (TargetConfig(id="primary", backend="codex"), TargetConfig(id="secondary", backend="codex")),
    )
    script = [
        (DriverResult("RETRYABLE", "old-sess-1", "", "context length exceeded", "context_overflow"), False),
        (DriverResult("RETRYABLE", "", "", "context length exceeded", "context_overflow"), True),
        (DriverResult("SUCCESS", "should-not-run", "should not run", "", ""), False),
    ]
    drivers = ScriptedRecoveryDrivers(script)
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    tkey = target_execution_key(catalog.targets[0])
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        runtime.database.append_turn(
            project_id=project.id,
            context_key="feature",
            role="implement",
            target_id="primary",
            target_key=tkey,
            session_id="old-sess-1",
            prompt="t1",
            response="r1",
        )
        sub = await runtime.submit(project.id, "implement", "turn 2 prompt", context_key="feature")
        job = await runtime.wait(sub.job_id, 5)
        assert job.state == "failed"

        # Reconstruction emitted tool activity: blocks prompt-only call and cross-target failover
        assert len(drivers.calls) == 2
        assert drivers.calls[0].target_id == "primary"
        assert drivers.calls[1].target_id == "primary"
        assert drivers.calls[1].emitted_tool_activity is True

        # Old session preserved and health not penalized
        assert runtime.database.session(project.id, "feature", "implement", tkey) == "old-sess-1"
        assert runtime.database.target_health(tkey)["consecutive_failures"] == 0
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_recovery_ordinary_failure_followed_by_normal_failover(tmp_path) -> None:
    root = repository(tmp_path)
    catalog = config(
        tmp_path / "home",
        (TargetConfig(id="primary", backend="codex"), TargetConfig(id="secondary", backend="codex")),
    )
    script = [
        (DriverResult("RETRYABLE", "old-sess-1", "", "context length exceeded", "context_overflow"), False),
        (DriverResult("RETRYABLE", "", "", "ordinary backend failure", "execution_error"), False),
        (DriverResult("SUCCESS", "sec-sess", "secondary response", "", ""), False),
    ]
    drivers = ScriptedRecoveryDrivers(script)
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    tkey_primary = target_execution_key(catalog.targets[0])
    tkey_sec = target_execution_key(catalog.targets[1])
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        runtime.database.append_turn(
            project_id=project.id,
            context_key="feature",
            role="implement",
            target_id="primary",
            target_key=tkey_primary,
            session_id="old-sess-1",
            prompt="t1",
            response="r1",
        )
        sub = await runtime.submit(project.id, "implement", "turn 2 prompt", context_key="feature")
        job = await runtime.wait(sub.job_id, 5)
        assert job.state == "succeeded"

        assert len(drivers.calls) == 3
        assert drivers.calls[0].target_id == "primary"
        assert drivers.calls[1].target_id == "primary"
        assert drivers.calls[2].target_id == "secondary"

        # Ordinary failure increments consecutive_failures for primary
        assert runtime.database.target_health(tkey_primary)["consecutive_failures"] == 1
        assert runtime.database.session(project.id, "feature", "implement", tkey_sec) == "sec-sess"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_recovery_all_bounded_calls_overflowing_before_normal_failover(tmp_path) -> None:
    root = repository(tmp_path)
    catalog = config(
        tmp_path / "home",
        (TargetConfig(id="primary", backend="codex"), TargetConfig(id="secondary", backend="codex")),
    )
    script = [
        (DriverResult("RETRYABLE", "old-sess-1", "", "context length exceeded", "context_overflow"), False),
        (DriverResult("RETRYABLE", "", "", "context length exceeded", "context_overflow"), False),
        (DriverResult("RETRYABLE", "", "", "context length exceeded", "context_overflow"), False),
        (DriverResult("SUCCESS", "sec-sess", "secondary response", "", ""), False),
    ]
    drivers = ScriptedRecoveryDrivers(script)
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    tkey_primary = target_execution_key(catalog.targets[0])
    tkey_sec = target_execution_key(catalog.targets[1])
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        runtime.database.append_turn(
            project_id=project.id,
            context_key="feature",
            role="implement",
            target_id="primary",
            target_key=tkey_primary,
            session_id="old-sess-1",
            prompt="t1",
            response="r1",
        )
        sub = await runtime.submit(project.id, "implement", "turn 2 prompt", context_key="feature")
        job = await runtime.wait(sub.job_id, 5)
        assert job.state == "succeeded"

        assert len(drivers.calls) == 4
        assert [c.target_id for c in drivers.calls] == ["primary", "primary", "primary", "secondary"]

        # Overflow is health-neutral: primary failures remain 0
        assert runtime.database.target_health(tkey_primary)["consecutive_failures"] == 0
        assert runtime.database.session(project.id, "feature", "implement", tkey_sec) == "sec-sess"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_recovery_cancellation_during_recovery(tmp_path) -> None:
    root = repository(tmp_path)
    script = [
        (DriverResult("RETRYABLE", "old-sess-1", "", "context length exceeded", "context_overflow"), False),
        (DriverResult("CANCELLED", "", "", "cancelled", "cancelled"), False),
    ]
    drivers = ScriptedRecoveryDrivers(script)
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = drivers
    target = runtime.catalog.targets[0]
    tkey = target_execution_key(target)

    def trigger_cancel(call_idx: int, _target, _sess, cancel_event: threading.Event | None) -> None:
        if call_idx == 1 and cancel_event:
            cancel_event.set()

    drivers.on_call = trigger_cancel

    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        runtime.database.append_turn(
            project_id=project.id,
            context_key="feature",
            role="implement",
            target_id=target.id,
            target_key=tkey,
            session_id="old-sess-1",
            prompt="t1",
            response="r1",
        )
        sub = await runtime.submit(project.id, "implement", "turn 2 prompt", context_key="feature")
        job = await runtime.wait(sub.job_id, 5)
        assert job.state == "cancelled"

        assert len(drivers.calls) == 2
        # Old session preserved on cancellation
        assert runtime.database.session(project.id, "feature", "implement", tkey) == "old-sess-1"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_recovery_successful_replacement_resumed_by_next_job(tmp_path) -> None:
    root = repository(tmp_path)
    script = [
        (DriverResult("RETRYABLE", "old-sess-1", "", "context length exceeded", "context_overflow"), False),
        (DriverResult("SUCCESS", "replacement-sess-2", "recovered response", "", ""), False),
        (DriverResult("SUCCESS", "next-sess-3", "next response", "", ""), False),
    ]
    drivers = ScriptedRecoveryDrivers(script)
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = drivers
    target = runtime.catalog.targets[0]
    tkey = target_execution_key(target)
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        runtime.database.append_turn(
            project_id=project.id,
            context_key="feature",
            role="implement",
            target_id=target.id,
            target_key=tkey,
            session_id="old-sess-1",
            prompt="turn 1 prompt",
            response="turn 1 response",
        )
        sub1 = await runtime.submit(project.id, "implement", "turn 2 prompt", context_key="feature")
        job1 = await runtime.wait(sub1.job_id, 5)
        assert job1.state == "succeeded"
        assert runtime.database.session(project.id, "feature", "implement", tkey) == "replacement-sess-2"

        # Submit next job with same context key and workflow
        sub2 = await runtime.submit(project.id, "implement", "turn 3 prompt", context_key="feature")
        job2 = await runtime.wait(sub2.job_id, 5)
        assert job2.state == "succeeded"

        assert len(drivers.calls) == 3
        assert drivers.calls[2].session_id == "replacement-sess-2"
        assert drivers.calls[2].prompt == "turn 3 prompt"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_recovery_original_prompt_and_completed_turn_stored_exactly_once(tmp_path) -> None:
    root = repository(tmp_path)
    script = [
        (DriverResult("RETRYABLE", "old-sess-1", "", "context length exceeded", "context_overflow"), False),
        (DriverResult("RETRYABLE", "", "", "context length exceeded", "context_overflow"), False),
        (DriverResult("SUCCESS", "final-sess-3", "final answer text", "", ""), False),
    ]
    drivers = ScriptedRecoveryDrivers(script)
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = drivers
    target = runtime.catalog.targets[0]
    tkey = target_execution_key(target)
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        runtime.database.append_turn(
            project_id=project.id,
            context_key="feature",
            role="implement",
            target_id=target.id,
            target_key=tkey,
            session_id="old-sess-1",
            prompt="seed prompt",
            response="seed response",
        )
        sub = await runtime.submit(project.id, "implement", "unmodified original prompt 42", context_key="feature")
        job = await runtime.wait(sub.job_id, 5)
        assert job.state == "succeeded"

        # Check stored turns: exactly 2 turns
        turns = runtime.database.recent_turns(project.id, "feature", "implement", 10)
        assert len(turns) == 2
        assert turns[0]["prompt"] == "seed prompt"
        assert turns[0]["response"] == "seed response"
        assert turns[1]["prompt"] == "unmodified original prompt 42"
        assert turns[1]["response"] == "final answer text"
        assert "Previous context:" not in turns[1]["prompt"]
        assert "seed prompt" not in turns[1]["prompt"]
    finally:
        await runtime.close()


def test_with_history_returns_original_prompt_when_all_turns_exceed_history_bytes(tmp_path) -> None:
    """Bounded history must not fabricate an empty wrapper when every turn is excluded."""
    from openmcp.execution import TargetExecutor

    catalog = replace(config(tmp_path / "home"), history_bytes=1)
    database = Database(catalog.database_path)
    project = database.upsert_project(project_id="project", alias="project", root="/project")
    database.append_turn(
        project_id=project.id,
        context_key="feature",
        role="implement",
        target_id="primary",
        target_key="primary",
        session_id="old-sess",
        prompt="seed prompt",
        response="seed response",
    )
    executor = TargetExecutor(catalog, database, FakeDrivers())
    try:
        assert executor._with_history(project.id, "feature", "implement", "current task") == "current task"
    finally:
        database.close()


@pytest.mark.asyncio
async def test_recovery_all_history_excluded_by_bytes_avoids_duplicate_prompt_only(tmp_path) -> None:
    """When bounds exclude every stored turn, reconstruction equals the prompt and must not repeat it."""
    root = repository(tmp_path)
    catalog = replace(config(tmp_path / "home"), history_bytes=1)
    script = [
        (DriverResult("RETRYABLE", "old-sess-1", "", "context length exceeded", "context_overflow"), False),
        (DriverResult("SUCCESS", "prompt-only-sess-2", "prompt-only answer", "", ""), False),
        (DriverResult("RETRYABLE", "", "", "unexpected duplicate call", "context_overflow"), False),
    ]
    drivers = ScriptedRecoveryDrivers(script)
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    target = catalog.targets[0]
    tkey = target_execution_key(target)
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        runtime.database.append_turn(
            project_id=project.id,
            context_key="feature",
            role="implement",
            target_id=target.id,
            target_key=tkey,
            session_id="old-sess-1",
            prompt="seed prompt",
            response="seed response",
        )
        sub = await runtime.submit(project.id, "implement", "turn 2 prompt", context_key="feature")
        job = await runtime.wait(sub.job_id, 5)
        assert job.state == "succeeded"

        # Exactly two invocations: resumed overflow, then prompt-only with the untouched prompt.
        assert len(drivers.calls) == 2
        assert drivers.calls[0].session_id == "old-sess-1"
        assert drivers.calls[0].prompt == "turn 2 prompt"
        assert drivers.calls[1].session_id == ""
        assert drivers.calls[1].prompt == "turn 2 prompt"

        events = runtime.database.events(sub.job_id)
        phases = [e["data"].get("phase") for e in events if e["kind"] == "target.session_recovery_started"]
        assert phases == ["reconstruct"]
        assert runtime.database.session(project.id, "feature", "implement", tkey) == "prompt-only-sess-2"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_recovery_success_with_empty_session_clears_stale_without_replacement(tmp_path) -> None:
    root = repository(tmp_path)
    script = [
        (DriverResult("RETRYABLE", "old-sess-1", "", "context length exceeded", "context_overflow"), False),
        (DriverResult("SUCCESS", "", "recovered without session", "", ""), False),
    ]
    drivers = ScriptedRecoveryDrivers(script)
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = drivers
    target = runtime.catalog.targets[0]
    tkey = target_execution_key(target)
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        runtime.database.append_turn(
            project_id=project.id,
            context_key="feature",
            role="implement",
            target_id=target.id,
            target_key=tkey,
            session_id="old-sess-1",
            prompt="seed prompt",
            response="seed response",
        )
        sub = await runtime.submit(project.id, "implement", "turn 2 prompt", context_key="feature")
        job = await runtime.wait(sub.job_id, 5)
        assert job.state == "succeeded"

        # Successfully recovered but no replacement session: stale session is cleared.
        assert runtime.database.session(project.id, "feature", "implement", tkey) == ""
        turns = runtime.database.recent_turns(project.id, "feature", "implement", 10)
        assert len(turns) == 2
        assert turns[1]["prompt"] == "turn 2 prompt"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_recovery_persistence_rollback_preserves_stale_session(tmp_path) -> None:
    root = repository(tmp_path)
    script = [
        (DriverResult("RETRYABLE", "old-sess-1", "", "context length exceeded", "context_overflow"), False),
        (DriverResult("SUCCESS", "replacement-sess-2", "recovered text", "", ""), False),
    ]
    drivers = ScriptedRecoveryDrivers(script)
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = drivers
    target = runtime.catalog.targets[0]
    tkey = target_execution_key(target)
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        runtime.database.append_turn(
            project_id=project.id,
            context_key="feature",
            role="implement",
            target_id=target.id,
            target_key=tkey,
            session_id="old-sess-1",
            prompt="seed prompt",
            response="seed response",
        )
        initial_turns = len(runtime.database.recent_turns(project.id, "feature", "implement", 100))

        runtime.database._connection.execute("""
            CREATE TRIGGER fail_recovery_turn BEFORE INSERT ON context_turns
            BEGIN
                SELECT RAISE(FAIL, 'simulated turn failure');
            END;
        """)

        sub = await runtime.submit(project.id, "implement", "turn 2 prompt", context_key="feature")
        job = await runtime.wait(sub.job_id, 5)
        assert job.state == "failed"

        runtime.database._connection.execute("DROP TRIGGER fail_recovery_turn")

        # Atomic rollback preserves prior session and turn count on persistence failure.
        assert runtime.database.session(project.id, "feature", "implement", tkey) == "old-sess-1"
        assert len(runtime.database.recent_turns(project.id, "feature", "implement", 100)) == initial_turns
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_recovery_max_attempts_one_stays_on_selected_target(tmp_path) -> None:
    root = repository(tmp_path)
    selection = TargetSelection(("primary",), 1)
    catalog = replace(
        config(tmp_path / "home"),
        profiles={
            "balanced": {
                "implement": selection,
                "review": selection,
                "consult": selection,
                "other": selection,
            }
        },
    )
    script = [
        (DriverResult("RETRYABLE", "old-sess-1", "", "context length exceeded", "context_overflow"), False),
        (DriverResult("RETRYABLE", "", "", "context length exceeded", "context_overflow"), False),
        (DriverResult("RETRYABLE", "", "", "context length exceeded", "context_overflow"), False),
    ]
    drivers = ScriptedRecoveryDrivers(script)
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    target = catalog.targets[0]
    tkey = target_execution_key(target)
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        runtime.database.append_turn(
            project_id=project.id,
            context_key="feature",
            role="implement",
            target_id=target.id,
            target_key=tkey,
            session_id="old-sess-1",
            prompt="seed prompt",
            response="seed response",
        )
        sub = await runtime.submit(project.id, "implement", "turn 2 prompt", context_key="feature")
        job = await runtime.wait(sub.job_id, 5)
        assert job.state == "failed"

        # Exactly one selected target and one recorded job attempt despite three internal calls.
        assert job.attempts == 1
        assert [c.target_id for c in drivers.calls] == ["primary", "primary", "primary"]
        assert runtime.database.target_health(tkey)["consecutive_failures"] == 0
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_recovery_target_fatal_uses_normal_health_and_failover(tmp_path) -> None:
    root = repository(tmp_path)
    catalog = config(
        tmp_path / "home",
        (TargetConfig(id="primary", backend="codex"), TargetConfig(id="secondary", backend="codex")),
    )
    script = [
        (DriverResult("RETRYABLE", "old-sess-1", "", "context length exceeded", "context_overflow"), False),
        (DriverResult("TARGET_FATAL", "", "", "target fatal during recovery", "backend_failure"), False),
        (DriverResult("SUCCESS", "sec-sess", "secondary response", "", ""), False),
    ]
    drivers = ScriptedRecoveryDrivers(script)
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    tkey_primary = target_execution_key(catalog.targets[0])
    tkey_sec = target_execution_key(catalog.targets[1])
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        runtime.database.append_turn(
            project_id=project.id,
            context_key="feature",
            role="implement",
            target_id="primary",
            target_key=tkey_primary,
            session_id="old-sess-1",
            prompt="seed prompt",
            response="seed response",
        )
        sub = await runtime.submit(project.id, "implement", "turn 2 prompt", context_key="feature")
        job = await runtime.wait(sub.job_id, 5)
        assert job.state == "succeeded"

        assert [c.target_id for c in drivers.calls] == ["primary", "primary", "secondary"]
        # Genuine recovery failure retains normal health accounting and failover.
        assert runtime.database.target_health(tkey_primary)["consecutive_failures"] == 1
        assert runtime.database.session(project.id, "feature", "implement", tkey_sec) == "sec-sess"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_recovery_request_fatal_stops_recovery_and_failover(tmp_path) -> None:
    root = repository(tmp_path)
    catalog = config(
        tmp_path / "home",
        (TargetConfig(id="primary", backend="codex"), TargetConfig(id="secondary", backend="codex")),
    )
    script = [
        (DriverResult("RETRYABLE", "old-sess-1", "", "context length exceeded", "context_overflow"), False),
        (DriverResult("REQUEST_FATAL", "", "", "request fatal during recovery", "execution_error"), False),
        (DriverResult("SUCCESS", "should-not-run", "should not run", "", ""), False),
    ]
    drivers = ScriptedRecoveryDrivers(script)
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    tkey_primary = target_execution_key(catalog.targets[0])
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        runtime.database.append_turn(
            project_id=project.id,
            context_key="feature",
            role="implement",
            target_id="primary",
            target_key=tkey_primary,
            session_id="old-sess-1",
            prompt="seed prompt",
            response="seed response",
        )
        sub = await runtime.submit(project.id, "implement", "turn 2 prompt", context_key="feature")
        job = await runtime.wait(sub.job_id, 5)
        assert job.state == "failed"

        # Request-fatal recovery stops immediately: no prompt-only and no cross-target failover.
        assert [c.target_id for c in drivers.calls] == ["primary", "primary"]
        assert runtime.database.target_health(tkey_primary)["consecutive_failures"] == 0
        assert runtime.database.session(project.id, "feature", "implement", tkey_primary) == "old-sess-1"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_recovery_internal_calls_count_one_selected_target_attempt(tmp_path) -> None:
    root = repository(tmp_path)
    catalog = config(
        tmp_path / "home",
        (TargetConfig(id="primary", backend="codex"), TargetConfig(id="secondary", backend="codex")),
    )
    script = [
        (DriverResult("RETRYABLE", "old-sess-1", "", "context length exceeded", "context_overflow"), False),
        (DriverResult("RETRYABLE", "", "", "context length exceeded", "context_overflow"), False),
        (DriverResult("RETRYABLE", "", "", "context length exceeded", "context_overflow"), False),
        (DriverResult("SUCCESS", "sec-sess", "secondary response", "", ""), False),
    ]
    drivers = ScriptedRecoveryDrivers(script)
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    tkey_primary = target_execution_key(catalog.targets[0])
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        runtime.database.append_turn(
            project_id=project.id,
            context_key="feature",
            role="implement",
            target_id="primary",
            target_key=tkey_primary,
            session_id="old-sess-1",
            prompt="seed prompt",
            response="seed response",
        )
        sub = await runtime.submit(project.id, "implement", "turn 2 prompt", context_key="feature")
        job = await runtime.wait(sub.job_id, 5)
        assert job.state == "succeeded"

        # Three internal calls on primary plus one failover to secondary count as two selected targets.
        assert job.attempts == 2
        assert [c.target_id for c in drivers.calls] == ["primary", "primary", "primary", "secondary"]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_terminal_desktop_notifications_succeeded_and_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repository(tmp_path)
    catalog = replace(config(tmp_path / "home"), notifications=NotificationsConfig(enabled=True))
    mock_send = MagicMock(return_value=True)
    monkeypatch.setattr("openmcp.runtime.send_job_notification", mock_send)

    runtime = Runtime(catalog)
    runtime.drivers = FakeDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        submission = await runtime.submit(project.id, "implement", "inspect")
        job = await runtime.wait(submission.job_id, 10)
        assert job.state == "succeeded"
        assert mock_send.call_count == 1
        called_job, called_alias = mock_send.call_args[0]
        assert called_job.id == submission.job_id
        assert called_job.state == "succeeded"
        assert called_alias == project.alias

        mock_send.reset_mock()
        runtime.drivers = MutatingFailureDrivers()
        fail_sub = await runtime.submit(project.id, "implement", "fail")
        fail_job = await runtime.wait(fail_sub.job_id, 10)
        assert fail_job.state == "failed"
        assert mock_send.call_count == 1
        called_job2, called_alias2 = mock_send.call_args[0]
        assert called_job2.id == fail_sub.job_id
        assert called_job2.state == "failed"
        assert called_alias2 == project.alias
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_terminal_desktop_notifications_queued_cancel_and_startup_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repository(tmp_path)
    catalog = replace(config(tmp_path / "home"), notifications=NotificationsConfig(enabled=True))
    mock_send = MagicMock(return_value=True)
    monkeypatch.setattr("openmcp.runtime.send_job_notification", mock_send)

    drivers = BlockingDrivers()
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        first = await runtime.submit(project.id, "implement", "block")
        second = await runtime.submit(project.id, "review", "never run")
        await drivers.started.wait()
        cancelled_action = await runtime.cancel(second.job_id)
        assert cancelled_action.state == "cancelled"
        assert (await runtime.wait(second.job_id, 10)).state == "cancelled"
        assert mock_send.call_count == 1
        called_job, called_alias = mock_send.call_args[0]
        assert called_job.id == second.job_id
        assert called_job.state == "cancelled"
        assert called_alias == project.alias

        await runtime.cancel(first.job_id)
        await runtime.wait(first.job_id, 10)
    finally:
        await runtime.close()

    mock_send.reset_mock()
    rec_home = tmp_path / "home_recovery"
    rec_catalog = replace(config(rec_home), notifications=NotificationsConfig(enabled=True))
    database = Database(rec_catalog.database_path)
    rec_proj = database.upsert_project(project_id="rec-proj", alias="recovery-project", root=root.as_posix())
    plan = resolve_execution_plan(get_workflow("implement"), rec_catalog, "balanced")
    database.create_job(
        job_id="interrupted-job",
        project_id=rec_proj.id,
        workflow="implement",
        profile="balanced",
        prompt="interrupted",
        execution_plan_json=json.dumps(execution_plan_data(plan)),
        context_key="recovery",
    )
    database.start_job("interrupted-job")
    database.close()

    runtime_rec = Runtime(rec_catalog)
    await runtime_rec.start()
    try:
        interrupted_job = runtime_rec.database.job("interrupted-job")
        assert interrupted_job and interrupted_job.state == "interrupted"
        assert mock_send.call_count == 1
        called_job3, called_alias3 = mock_send.call_args[0]
        assert called_job3.id == "interrupted-job"
        assert called_job3.state == "interrupted"
        assert called_alias3 == "recovery-project"
    finally:
        await runtime_rec.close()


@pytest.mark.asyncio
async def test_terminal_desktop_notifications_disabled_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repository(tmp_path)
    mock_send = MagicMock(return_value=True)
    monkeypatch.setattr("openmcp.runtime.send_job_notification", mock_send)

    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = FakeDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        submission = await runtime.submit(project.id, "implement", "inspect")
        await runtime.wait(submission.job_id, 10)
        assert mock_send.call_count == 0
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_terminal_desktop_notifications_no_call_on_queued_running_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repository(tmp_path)
    catalog = replace(config(tmp_path / "home"), notifications=NotificationsConfig(enabled=True))
    mock_send = MagicMock(return_value=True)
    monkeypatch.setattr("openmcp.runtime.send_job_notification", mock_send)

    runtime = Runtime(catalog)
    runtime.drivers = RetryDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        submission = await runtime.submit(project.id, "implement", "retry")
        assert (await runtime.wait(submission.job_id, 10)).state == "failed"
        assert mock_send.call_count == 1

        retried = await runtime.retry(submission.job_id)
        assert retried.job_id == submission.job_id
        assert mock_send.call_count == 1
        assert (await runtime.wait(retried.job_id, 10)).state == "failed"
        assert mock_send.call_count == 2
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_terminal_desktop_notifications_failure_isolation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    root = repository(tmp_path)
    catalog = replace(config(tmp_path / "home"), notifications=NotificationsConfig(enabled=True))
    notifications: list[str] = []

    async def notify(uri: str) -> None:
        notifications.append(uri)

    mock_send_false = MagicMock(return_value=False)
    monkeypatch.setattr("openmcp.runtime.send_job_notification", mock_send_false)

    runtime = Runtime(catalog, notifier=notify)
    runtime.drivers = FakeDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        caplog.clear()
        sub1 = await runtime.submit(project.id, "implement", "inspect")
        job1 = await runtime.wait(sub1.job_id, 10)
        assert job1.state == "succeeded"
        assert notifications == [sub1.resource_uri] * 3
        failed_records = [
            r for r in caplog.records
            if getattr(r, "event", None) == "job.desktop_notification_failed"
        ]
        assert len(failed_records) == 1
        assert failed_records[0].job_id == sub1.job_id

        mock_send_raise = MagicMock(side_effect=RuntimeError("notification daemon down"))
        monkeypatch.setattr("openmcp.runtime.send_job_notification", mock_send_raise)
        notifications.clear()
        caplog.clear()

        sub2 = await runtime.submit(project.id, "implement", "inspect2")
        job2 = await runtime.wait(sub2.job_id, 10)
        assert job2.state == "succeeded"
        assert notifications == [sub2.resource_uri] * 3
        failed_records2 = [
            r for r in caplog.records
            if getattr(r, "event", None) == "job.desktop_notification_failed"
        ]
        assert len(failed_records2) == 1
        assert failed_records2[0].job_id == sub2.job_id
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_terminal_desktop_notifications_live_catalog_toggle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repository(tmp_path)
    mock_send = MagicMock(return_value=True)
    monkeypatch.setattr("openmcp.runtime.send_job_notification", mock_send)

    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = FakeDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        sub1 = await runtime.submit(project.id, "implement", "inspect1")
        await runtime.wait(sub1.job_id, 10)
        assert mock_send.call_count == 0

        runtime._catalog = replace(runtime._catalog, notifications=NotificationsConfig(enabled=True))
        sub2 = await runtime.submit(project.id, "implement", "inspect2")
        await runtime.wait(sub2.job_id, 10)
        assert mock_send.call_count == 1

        runtime._catalog = replace(runtime._catalog, notifications=NotificationsConfig(enabled=False))
        sub3 = await runtime.submit(project.id, "implement", "inspect3")
        await runtime.wait(sub3.job_id, 10)
        assert mock_send.call_count == 1
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_concurrent_retry_preserves_terminal_notification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repository(tmp_path)
    catalog = replace(config(tmp_path / "home"), notifications=NotificationsConfig(enabled=True))
    mock_send = MagicMock(return_value=True)
    monkeypatch.setattr("openmcp.runtime.send_job_notification", mock_send)

    database = Database(catalog.database_path)
    project = database.upsert_project(project_id="proj-1", alias="retry-project", root=root.as_posix())
    plan = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")
    database.create_job(
        job_id="failed-1",
        project_id=project.id,
        workflow="implement",
        profile="balanced",
        prompt="fail",
        execution_plan_json=json.dumps(execution_plan_data(plan)),
        context_key="retry-ctx",
    )
    database.finish_job("failed-1", "failed")
    database.close()

    first_publish_entered = asyncio.Event()
    release_first_publish = asyncio.Event()
    paused_once = False

    async def pausing_notifier(uri: str) -> None:
        nonlocal paused_once
        if not paused_once:
            paused_once = True
            first_publish_entered.set()
            await release_first_publish.wait()

    runtime = Runtime(catalog, notifier=pausing_notifier)
    try:
        publish_task = asyncio.create_task(
            runtime._notify_job_resource("openmcp://jobs/failed-1")
        )
        await first_publish_entered.wait()

        retry_result = await runtime.retry("failed-1")
        assert retry_result.state == "queued"
        assert runtime.database.job("failed-1").state == "queued"

        release_first_publish.set()
        await publish_task

        assert mock_send.call_count == 1
        called_job, called_alias = mock_send.call_args[0]
        assert called_job.id == "failed-1"
        assert called_job.state == "failed"
        assert called_alias == "retry-project"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_terminal_desktop_notifications_snapshot_lookup_failure_warning_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    catalog = replace(config(tmp_path / "home"), notifications=NotificationsConfig(enabled=True))
    notifications: list[str] = []

    async def notify(uri: str) -> None:
        notifications.append(uri)

    runtime = Runtime(catalog, notifier=notify)
    try:
        lookup_exc = RuntimeError("database locked")
        monkeypatch.setattr(
            runtime.database,
            "job",
            MagicMock(side_effect=lookup_exc),
        )

        caplog.clear()
        await runtime._notify_job_resource("openmcp://jobs/job-snapshot-err")

        assert notifications == ["openmcp://jobs/job-snapshot-err"]
        failed_records = [
            r for r in caplog.records
            if getattr(r, "event", None) == "job.desktop_notification_failed"
        ]
        assert len(failed_records) == 1
        assert failed_records[0].job_id == "job-snapshot-err"
        assert failed_records[0].exc_info is not None
        exc_type, exc_val, exc_tb = failed_records[0].exc_info
        assert exc_type is RuntimeError
        assert exc_val is lookup_exc
        assert exc_tb is not None
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_terminal_desktop_notifications_disabled_does_not_lookup_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = config(tmp_path / "home")
    notifications: list[str] = []

    async def notify(uri: str) -> None:
        notifications.append(uri)

    runtime = Runtime(catalog, notifier=notify)
    try:
        mock_job = MagicMock(side_effect=AssertionError("database.job should not be called when disabled"))
        monkeypatch.setattr(runtime.database, "job", mock_job)

        await runtime._notify_job_resource("openmcp://jobs/job-disabled")
        assert notifications == ["openmcp://jobs/job-disabled"]
        mock_job.assert_not_called()
    finally:
        await runtime.close()
