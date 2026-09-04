from __future__ import annotations

import asyncio
import inspect
import json
import subprocess
import threading
from dataclasses import replace

import pytest

from openmcp.backends import BackendResult
from openmcp.config import TargetConfig, TargetSelection
from openmcp.context_files import MANAGED_MARKER, materialize_context_file
from openmcp.database import Database
from openmcp.drivers import DriverRegistry, DriverResult, _target_args
from openmcp.planning import execution_plan_data, resolve_execution_plan
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


@pytest.mark.parametrize("backend", ["claude", "pi"])
@pytest.mark.asyncio
async def test_driver_appends_system_prompt_for_instructed_backend(monkeypatch, tmp_path, backend) -> None:
    import openmcp.drivers as drivers_module

    captured = {}

    async def fake_execute(params):
        captured["args"] = params.args
        return BackendResult(outcome="OK", SESSION_ID="session", agent_messages="reviewed", error="", error_class="")

    monkeypatch.setattr(drivers_module, f"{backend}_execute", fake_execute)
    await drivers_module.DriverRegistry().execute(
        target=TargetConfig(id=f"{backend}-target", backend=backend, args=("--verbose",)),
        prompt="review",
        cwd=tmp_path,
        session_id="",
        timeout_s=0,
        cancel_event=threading.Event(),
        instruction="follow the plan",
    )

    assert captured["args"][-2:] == ("--append-system-prompt", "follow the plan")
    assert captured["args"][0] == "--verbose"


@pytest.mark.parametrize("backend", ["claude", "pi"])
@pytest.mark.asyncio
async def test_driver_appends_system_prompt_for_isolated_backend(monkeypatch, tmp_path, backend) -> None:
    import openmcp.drivers as drivers_module

    captured = {}

    async def fake_execute(params):
        captured["args"] = params.args
        return BackendResult(outcome="OK", SESSION_ID="session", agent_messages="reviewed", error="", error_class="")

    monkeypatch.setattr(drivers_module, f"{backend}_execute", fake_execute)
    await drivers_module.DriverRegistry().execute(
        target=TargetConfig(id=f"{backend}-isolated", backend=backend, isolated=True),
        prompt="review",
        cwd=tmp_path,
        session_id="",
        timeout_s=0,
        cancel_event=threading.Event(),
        instruction="follow the plan",
    )

    assert "--append-system-prompt" in captured["args"]
    assert captured["args"][-2:] == ("--append-system-prompt", "follow the plan")
    if backend == "claude":
        assert "--safe-mode" in captured["args"]
    else:
        assert "--no-context-files" in captured["args"]


@pytest.mark.parametrize("backend", ["agy", "codex"])
@pytest.mark.asyncio
async def test_driver_ignores_instruction_for_other_backends(monkeypatch, tmp_path, backend) -> None:
    import openmcp.drivers as drivers_module

    captured = {}

    async def fake_execute(params):
        captured["args"] = params.args
        return BackendResult(outcome="OK", SESSION_ID="session", agent_messages="reviewed", error="", error_class="")

    monkeypatch.setattr(drivers_module, f"{backend}_execute", fake_execute)
    await drivers_module.DriverRegistry().execute(
        target=TargetConfig(id=f"{backend}-target", backend=backend),
        prompt="review",
        cwd=tmp_path,
        session_id="",
        timeout_s=0,
        cancel_event=threading.Event(),
        instruction="follow the plan",
    )

    assert "--append-system-prompt" not in captured["args"]


@pytest.mark.parametrize(
    "backend",
    ["claude", "pi", "agy", "codex"],
)
@pytest.mark.asyncio
async def test_driver_empty_instruction_preserves_argv(monkeypatch, tmp_path, backend) -> None:
    import openmcp.drivers as drivers_module

    plain_captured = {}
    instructed_captured = {}

    async def plain_execute(params):
        plain_captured["args"] = params.args
        return BackendResult(outcome="OK", SESSION_ID="", agent_messages="", error="", error_class="")

    async def instructed_execute(params):
        instructed_captured["args"] = params.args
        return BackendResult(outcome="OK", SESSION_ID="", agent_messages="", error="", error_class="")

    monkeypatch.setattr(drivers_module, f"{backend}_execute", plain_execute)
    await drivers_module.DriverRegistry().execute(
        target=TargetConfig(id=f"{backend}-plain", backend=backend),
        prompt="review",
        cwd=tmp_path,
        session_id="",
        timeout_s=0,
        cancel_event=threading.Event(),
    )
    monkeypatch.setattr(drivers_module, f"{backend}_execute", instructed_execute)
    await drivers_module.DriverRegistry().execute(
        target=TargetConfig(id=f"{backend}-plain", backend=backend),
        prompt="review",
        cwd=tmp_path,
        session_id="",
        timeout_s=0,
        cancel_event=threading.Event(),
        instruction="",
    )

    assert instructed_captured["args"] == plain_captured["args"]


@pytest.mark.asyncio
async def test_target_args_appends_instruction_after_operator_args(monkeypatch) -> None:
    target = TargetConfig(id="pi-target", backend="pi", args=("--verbose",))
    assert _target_args(target, instruction="follow the plan") == (
        "--verbose",
        "--approve",
        "--append-system-prompt",
        "follow the plan",
    )


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
    compiled: list[tuple[str, tuple[str, ...]]] = []

    class RetryingDrivers(FakeDrivers):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        async def execute(self, *, target: TargetConfig, **kwargs) -> DriverResult:
            self.calls += 1
            compiled.append((target.id, kwargs.get("instruction", "")))
            return DriverResult("RETRYABLE", "", "", "retry", "backend_failure")

    runtime = Runtime(catalog)
    runtime.drivers = RetryingDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        await context_init_instruction(runtime, project.id, "implement", "follow the plan")
        job = await runtime.wait((await runtime.submit(project.id, "implement", "retry")).job_id, 10)
        assert job.state == "failed"
        assert job.attempts == 2
        assert compiled == [
            ("claude-target", "follow the plan"),
            ("pi-target", "follow the plan"),
        ]
    finally:
        await runtime.close()


async def context_init_instruction(runtime, project_id: str, workflow: str, instruction: str) -> None:
    runtime.database.set_context_instruction(project_id, workflow, instruction)


class CodexDrivers(FakeDrivers):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0
        self.last_cwd: Path | None = None

    async def execute(self, *, cwd: Path, **kwargs) -> DriverResult:
        self.calls += 1
        self.last_cwd = cwd
        return DriverResult("SUCCESS", "", f"response {self.calls}", "", "")


def codex_catalog(tmp_path, root: Path, *, targets: tuple[TargetConfig, ...] | None = None) -> object:
    resolved_targets = targets or (TargetConfig(id="codex-target", backend="codex"),)
    from tests.orchestration_helpers import config as make_config

    return make_config(tmp_path / "home", targets=resolved_targets)


def agy_catalog(tmp_path, root: Path) -> object:
    from tests.orchestration_helpers import config as make_config

    return make_config(tmp_path / "home", targets=(TargetConfig(id="agy-target", backend="agy"),))


class AgyDrivers(FakeDrivers):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def execute(self, *, cwd: Path, **kwargs) -> DriverResult:
        self.calls += 1
        return DriverResult("SUCCESS", "", f"response {self.calls}", "", "")


@pytest.mark.asyncio
async def test_agy_attempt_materializes_instruction_only_gemini(tmp_path) -> None:
    root = repository(tmp_path)
    (root / "AGENTS.md").write_text("root guidance\n", encoding="utf-8")
    git(root, "add", "AGENTS.md")
    git(root, "commit", "-m", "add agents")
    captured: dict[str, bytes] = {}

    class CapturingAgyDrivers(FakeDrivers):
        async def execute(self, *, cwd: Path, **kwargs) -> DriverResult:
            captured["gemini"] = (cwd / "GEMINI.md").read_bytes()
            captured["agents"] = (cwd / "AGENTS.md").read_bytes()
            return DriverResult("SUCCESS", "", "ok", "", "")

    runtime = Runtime(agy_catalog(tmp_path, root))
    runtime.drivers = CapturingAgyDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        await context_init_instruction(runtime, project.id, "implement", "follow the plan")
        job = await runtime.wait((await runtime.submit(project.id, "implement", "inspect")).job_id, 10)
        assert job.state == "succeeded"
    finally:
        await runtime.close()

    assert MANAGED_MARKER.encode() in captured["gemini"]
    assert b"follow the plan" in captured["gemini"]
    assert b"root guidance" not in captured["gemini"]
    assert captured["agents"] == b"root guidance\n"
    assert not (root / "GEMINI.md").exists()
    assert git(root, "status", "--porcelain") == ""


@pytest.mark.asyncio
async def test_agy_tracked_gemini_fails_request_fatal(tmp_path) -> None:
    root = repository(tmp_path)
    original = b"tracked gemini\n"
    (root / "GEMINI.md").write_bytes(original)
    git(root, "add", "-f", "GEMINI.md")
    git(root, "commit", "-m", "track gemini")

    runtime = Runtime(agy_catalog(tmp_path, root))
    runtime.drivers = AgyDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        await context_init_instruction(runtime, project.id, "implement", "follow the plan")
        job = await runtime.wait((await runtime.submit(project.id, "implement", "inspect")).job_id, 10)
        assert job.state == "failed"
        assert (root / "GEMINI.md").read_bytes() == original
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_agy_foreign_gemini_fails_request_fatal(tmp_path) -> None:
    root = repository(tmp_path)
    (root / "GEMINI.md").write_text("foreign\n", encoding="utf-8")

    runtime = Runtime(agy_catalog(tmp_path, root))
    runtime.drivers = AgyDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        await context_init_instruction(runtime, project.id, "implement", "follow the plan")
        job = await runtime.wait((await runtime.submit(project.id, "implement", "inspect")).job_id, 10)
        assert job.state == "failed"
        assert (root / "GEMINI.md").read_text(encoding="utf-8") == "foreign\n"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_startup_sweep_removes_agy_gemini_leftover(tmp_path) -> None:
    root = repository(tmp_path)
    (root / "GEMINI.md").write_text(MANAGED_MARKER + "\nmanaged\n", encoding="utf-8")
    (root / "keep.txt").write_text("keep\n", encoding="utf-8")
    catalog = agy_catalog(tmp_path, root)
    database = Database(catalog.database_path)
    database.upsert_project(project_id="project", alias="project", root=root.as_posix())
    database.close()

    runtime = Runtime(catalog)
    await runtime.start()
    try:
        assert not (root / "GEMINI.md").exists()
        assert (root / "keep.txt").exists()
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_codex_attempt_materializes_and_cleans_up_context_file(tmp_path) -> None:
    root = repository(tmp_path)
    (root / "AGENTS.md").write_text("root guidance\n", encoding="utf-8")
    git(root, "add", "AGENTS.md")
    git(root, "commit", "-m", "add agents")
    drivers = CodexDrivers()
    catalog = codex_catalog(tmp_path, root)
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        await context_init_instruction(runtime, project.id, "implement", "follow the plan")
        job = await runtime.wait((await runtime.submit(project.id, "implement", "inspect")).job_id, 10)
        assert job.state == "succeeded"
        assert drivers.calls == 1
        assert not (root / "AGENTS.override.md").exists()
        assert git(root, "status", "--porcelain") == ""
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_codex_composed_file_preserves_root_guidance_during_attempt(tmp_path) -> None:
    root = repository(tmp_path)
    (root / "AGENTS.md").write_text("root guidance\n", encoding="utf-8")
    git(root, "add", "AGENTS.md")
    git(root, "commit", "-m", "add agents")
    captured: dict[str, bytes] = {}

    class CapturingCodexDrivers(FakeDrivers):
        async def execute(self, *, cwd: Path, **kwargs) -> DriverResult:
            captured["content"] = (cwd / "AGENTS.override.md").read_bytes()
            return DriverResult("SUCCESS", "", "ok", "", "")

    catalog = codex_catalog(tmp_path, root)
    runtime = Runtime(catalog)
    runtime.drivers = CapturingCodexDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        await context_init_instruction(runtime, project.id, "implement", "follow the plan")
        await runtime.wait((await runtime.submit(project.id, "implement", "inspect")).job_id, 10)
    finally:
        await runtime.close()

    assert MANAGED_MARKER.encode() in captured["content"]
    assert b"follow the plan" in captured["content"]
    assert b"root guidance" in captured["content"]
    assert not (root / "AGENTS.override.md").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("outcome", "error_code"),
    [
        ("RETRYABLE", "backend_failure"),
        ("TARGET_FATAL", "fatal_backend"),
    ],
)
async def test_codex_cleanup_after_failed_attempt(tmp_path, outcome, error_code) -> None:
    root = repository(tmp_path)

    class FailingCodexDrivers(FakeDrivers):
        async def execute(self, *, cwd: Path, **kwargs) -> DriverResult:
            assert (cwd / "AGENTS.override.md").exists()
            return DriverResult(outcome, "", "", "failed", error_code)

    catalog = codex_catalog(tmp_path, root)
    runtime = Runtime(catalog)
    runtime.drivers = FailingCodexDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        await context_init_instruction(runtime, project.id, "implement", "follow the plan")
        job = await runtime.wait((await runtime.submit(project.id, "implement", "inspect")).job_id, 10)
        assert job.state in {"failed", "cancelled"}
        assert not (root / "AGENTS.override.md").exists()
        assert git(root, "status", "--porcelain") == ""
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_codex_cleanup_after_driver_exception(tmp_path) -> None:
    root = repository(tmp_path)

    class ExplodingCodexDrivers(FakeDrivers):
        async def execute(self, *, cwd: Path, **kwargs) -> DriverResult:
            assert (cwd / "AGENTS.override.md").exists()
            raise RuntimeError("driver exploded")

    catalog = codex_catalog(tmp_path, root)
    runtime = Runtime(catalog)
    runtime.drivers = ExplodingCodexDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        await context_init_instruction(runtime, project.id, "implement", "follow the plan")
        job = await runtime.wait((await runtime.submit(project.id, "implement", "inspect")).job_id, 10)
        assert job.state == "failed"
        assert not (root / "AGENTS.override.md").exists()
        assert git(root, "status", "--porcelain") == ""
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_codex_cleanup_after_cancellation(tmp_path) -> None:
    root = repository(tmp_path)

    class CancellingCodexDrivers(FakeDrivers):
        def __init__(self) -> None:
            super().__init__()
            self.started = asyncio.Event()

        async def execute(self, *, cwd: Path, cancel_event, **kwargs) -> DriverResult:
            self.started.set()
            while not cancel_event.is_set():
                await asyncio.sleep(0.01)
            return DriverResult("CANCELLED", "", "", "cancelled", "cancelled")

    drivers = CancellingCodexDrivers()
    catalog = codex_catalog(tmp_path, root)
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        await context_init_instruction(runtime, project.id, "implement", "follow the plan")
        submitted = await runtime.submit(project.id, "implement", "block")
        await drivers.started.wait()
        await runtime.cancel(submitted.job_id)
        assert (await runtime.wait(submitted.job_id, 1)).state == "cancelled"
        assert not (root / "AGENTS.override.md").exists()
        assert git(root, "status", "--porcelain") == ""
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_codex_cleanup_after_timeout(tmp_path) -> None:
    root = repository(tmp_path)

    class TimingOutCodexDrivers(FakeDrivers):
        async def execute(self, *, cwd: Path, **kwargs) -> DriverResult:
            assert (cwd / "AGENTS.override.md").exists()
            return DriverResult("TARGET_FATAL", "", "", "timed out", "timeout")

    selection = TargetSelection(("codex-target",), 1)
    from openmcp.config import DaemonConfig

    catalog = codex_catalog(tmp_path, root)
    catalog = DaemonConfig(
        home=catalog.home,
        max_jobs=catalog.max_jobs,
        default_profile="balanced",
        targets=catalog.targets,
        profiles={"balanced": {"implement": selection, "review": selection, "consult": selection, "other": selection}},
        profile_declarations=catalog.profile_declarations,
    )
    runtime = Runtime(catalog)
    runtime.drivers = TimingOutCodexDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        await context_init_instruction(runtime, project.id, "implement", "follow the plan")
        job = await runtime.wait((await runtime.submit(project.id, "implement", "inspect")).job_id, 10)
        assert job.state == "failed"
        assert not (root / "AGENTS.override.md").exists()
        assert git(root, "status", "--porcelain") == ""
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_codex_tracked_target_path_fails_request_fatal(tmp_path) -> None:
    root = repository(tmp_path)
    original = b"tracked content\n"
    (root / "AGENTS.override.md").write_bytes(original)
    git(root, "add", "AGENTS.override.md")
    git(root, "commit", "-m", "track override")

    catalog = codex_catalog(tmp_path, root)
    runtime = Runtime(catalog)
    runtime.drivers = CodexDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        await context_init_instruction(runtime, project.id, "implement", "follow the plan")
        job = await runtime.wait((await runtime.submit(project.id, "implement", "inspect")).job_id, 10)
        assert job.state == "failed"
        assert (root / "AGENTS.override.md").read_bytes() == original
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_codex_untracked_foreign_target_path_fails_request_fatal(tmp_path) -> None:
    root = repository(tmp_path)
    (root / "AGENTS.override.md").write_text("foreign content\n", encoding="utf-8")

    catalog = codex_catalog(tmp_path, root)
    runtime = Runtime(catalog)
    runtime.drivers = CodexDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        await context_init_instruction(runtime, project.id, "implement", "follow the plan")
        job = await runtime.wait((await runtime.submit(project.id, "implement", "inspect")).job_id, 10)
        assert job.state == "failed"
        assert (root / "AGENTS.override.md").read_text(encoding="utf-8") == "foreign content\n"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_codex_leftover_marker_file_is_overwritten(tmp_path) -> None:
    root = repository(tmp_path)
    (root / "AGENTS.override.md").write_text(MANAGED_MARKER + "\nstale\n", encoding="utf-8")

    catalog = codex_catalog(tmp_path, root)
    runtime = Runtime(catalog)
    runtime.drivers = CodexDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        await context_init_instruction(runtime, project.id, "implement", "follow the plan")
        job = await runtime.wait((await runtime.submit(project.id, "implement", "inspect")).job_id, 10)
        assert job.state == "succeeded"
        assert not (root / "AGENTS.override.md").exists()
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_non_git_project_materializes_and_logs_warning(tmp_path, caplog) -> None:
    root = tmp_path / "plain-project"
    root.mkdir()

    catalog = codex_catalog(tmp_path, root)
    runtime = Runtime(catalog)
    runtime.drivers = CodexDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        await context_init_instruction(runtime, project.id, "implement", "follow the plan")
        job = await runtime.wait((await runtime.submit(project.id, "implement", "inspect")).job_id, 10)
        assert job.state == "succeeded"
        assert not (root / "AGENTS.override.md").exists()
    finally:
        await runtime.close()
    assert any("not a git repository" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_startup_sweep_removes_managed_leftovers(tmp_path) -> None:
    root = repository(tmp_path)
    (root / "AGENTS.override.md").write_text(MANAGED_MARKER + "\nmanaged\n", encoding="utf-8")
    (root / "keep.txt").write_text("keep\n", encoding="utf-8")
    catalog = codex_catalog(tmp_path, root)
    database = Database(catalog.database_path)
    database.upsert_project(project_id="project", alias="project", root=root.as_posix())
    database.close()
    runtime = Runtime(catalog)
    await runtime.start()
    try:
        assert not (root / "AGENTS.override.md").exists()
        assert (root / "keep.txt").exists()
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_startup_sweep_leaves_tracked_foreign_alone(tmp_path) -> None:
    root = repository(tmp_path)
    (root / "AGENTS.override.md").write_text(MANAGED_MARKER + "\ntracked\n", encoding="utf-8")
    git(root, "add", "AGENTS.override.md")
    git(root, "commit", "-m", "track override")
    catalog = codex_catalog(tmp_path, root)
    database = Database(catalog.database_path)
    database.upsert_project(project_id="project", alias="project", root=root.as_posix())
    database.close()
    runtime = Runtime(catalog)
    await runtime.start()
    try:
        assert (root / "AGENTS.override.md").exists()
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
