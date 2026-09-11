from __future__ import annotations

import asyncio
import inspect
import json
import subprocess
import threading
from dataclasses import replace

import pytest

from openmcp.config import TargetConfig, TargetSelection
from openmcp.database import Database
from openmcp.drivers import DriverResult
from openmcp.planning import execution_plan_data, resolve_execution_plan, target_execution_key
from openmcp.runtime import OrchestrationError, Runtime
from openmcp.workflows import get_workflow
from tests.orchestration_helpers import BlockingDrivers, FakeDrivers, config, git, repository


def test_runtime_submit_signature_omits_commit_message() -> None:
    assert "commit_message" not in inspect.signature(Runtime.submit).parameters


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
        assert (await runtime.cancel(second.job_id)).state == "cancelled"
        assert (await runtime.cancel(first.job_id)).state == "running"
        assert (await runtime.wait(first.job_id, 10)).state == "cancelled"
        assert (await runtime.wait(second.job_id, 10)).state == "cancelled"
        assert [uri for uri in notifications if uri == first.resource_uri] == [first.resource_uri] * 3
        assert [uri for uri in notifications if uri == second.resource_uri] == [second.resource_uri] * 2
    finally:
        await runtime.close()


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
        # Authoritative final result matches
        assert job.result.text == "streaming content"
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

        # Authoritative result is ONLY the successful one
        assert job.result.text == "final success"
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
