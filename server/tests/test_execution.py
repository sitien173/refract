from __future__ import annotations

import asyncio
from collections.abc import Callable
import inspect
import json
import os
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timezone
from dataclasses import dataclass, replace
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from refract.config import NotificationsConfig, RetryPolicy, TargetConfig, TargetSelection
from refract.database import Database
from refract.drivers import DriverResult
from refract.backends import BackendParams
from refract.planning import execution_plan_data, resolve_execution_plan, target_execution_key
from refract.runtime import OrchestrationError, Runtime
from refract.execution import TargetExecutor
from refract.scheduler import CancelEvent
from refract.workflows import get_workflow
from tests.claude_cli import stub_claude
from tests.cli_stub import execute_sync, fake_run_process, shell_fake_as_process
from tests.launchers import install_launcher
from tests.orchestration_helpers import BlockingDrivers, FakeDrivers, config, git, repository
from tests.orchestration_helpers import register_project


def _stream_events(database: Database, job_id: str) -> list[dict]:
    path = database.stream_path(job_id)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]










@pytest.mark.asyncio
async def test_legacy_snapshot_ignores_current_target_environment(tmp_path: Path) -> None:
    root = repository(tmp_path)
    base = config(tmp_path / "home")
    target = replace(base.targets[0], env={"CURRENT_ONLY": "SYNTHETIC_CURRENT_VALUE"})
    catalog = replace(base, targets=(target,))
    runtime = Runtime(catalog)
    project = register_project(runtime, str(root))
    plan_data = execution_plan_data(resolve_execution_plan(get_workflow("implement"), catalog, "balanced"))
    plan_data.pop("environment_targets")
    calls = []
    resolver = runtime.target_executor.environment_resolver
    def tracking_resolver(*args):
        calls.append(True)
        return resolver(*args)
    runtime.target_executor.environment_resolver = tracking_resolver
    runtime.database.create_job(
        job_id="legacy-env-snapshot", project_id=project.id, workflow="implement",
        profile="balanced", prompt="legacy", execution_plan_json=json.dumps(plan_data),
        session="legacy",
    )
    received: list[dict[str, str]] = []
    class LegacyDrivers(FakeDrivers):
        async def execute(self, *, env=None, **kwargs):
            received.append(dict(env or {}))
            return await super().execute(**kwargs)
    runtime.drivers = LegacyDrivers()
    await runtime.start()
    try:
        assert (await runtime.wait("legacy-env-snapshot", 10)).state == "succeeded"
        assert calls == []
        assert all("CURRENT_ONLY" not in env for env in received)
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_concurrent_projects_keep_environment_bindings_isolated(tmp_path: Path) -> None:
    base = config(tmp_path / "home")
    target = replace(base.targets[0], env={"PROJECT_BINDING": "global"}, max_concurrency=1)
    catalog = replace(base, targets=(target,))
    roots = [tmp_path / "project-a", tmp_path / "project-b"]
    projects_config = ("project-a-secret", "project-b-secret")
    runtime = Runtime(catalog)
    received: list[str] = []
    active = 0
    maximum_active = 0
    class ConcurrentDrivers(FakeDrivers):
        async def execute(self, *, env=None, **kwargs):
            nonlocal active, maximum_active
            received.append((env or {}).get("PROJECT_BINDING", ""))
            active += 1
            maximum_active = max(maximum_active, active)
            try:
                await asyncio.sleep(0.05)
                return await super().execute(**kwargs)
            finally:
                active -= 1
    runtime.drivers = ConcurrentDrivers()
    await runtime.start()
    try:
        projects = []
        for root, value in zip(roots, projects_config, strict=True):
            root.mkdir()
            config_path = root / ".refract" / "config.toml"
            config_path.parent.mkdir()
            config_path.write_text(f'[[targets]]\nid = "primary"\nenv = {{ PROJECT_BINDING = "{value}" }}\n', encoding="utf-8")
            projects.append(register_project(runtime, str(root)))
        submissions = await asyncio.gather(*(
            runtime.submit(project.id, "implement", "isolated") for project in projects
        ))
        jobs = await asyncio.gather(*(runtime.wait(sub.job_id, 10) for sub in submissions))
        assert all(job.state == "succeeded" for job in jobs)
        assert set(received) == set(projects_config)
        assert maximum_active == 1
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_queued_restart_binds_current_project_environment(tmp_path: Path) -> None:
    root = repository(tmp_path)
    project_config = root / ".refract" / "config.toml"
    project_config.parent.mkdir()
    project_config.write_text('[[targets]]\nid = "primary"\nenv = { RESTART_VALUE = "before" }\n', encoding="utf-8")
    base = config(tmp_path / "home")
    target = replace(base.targets[0], env={"RESTART_VALUE": "global"})
    catalog = replace(base, targets=(target,))
    runtime = Runtime(catalog)
    project = register_project(runtime, str(root))
    plan = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")
    runtime.database.create_job(
        job_id="queued-env-restart", project_id=project.id, workflow="implement",
        profile="balanced", prompt="restart", execution_plan_json=json.dumps(execution_plan_data(plan)),
        session="restart",
    )
    runtime.database.close()
    project_config.write_text('[[targets]]\nid = "primary"\nenv = { RESTART_VALUE = "after" }\n', encoding="utf-8")
    received: list[str] = []
    class RestartDrivers(FakeDrivers):
        async def execute(self, *, env=None, **kwargs):
            received.append((env or {}).get("RESTART_VALUE", ""))
            return await super().execute(**kwargs)
    restarted = Runtime(catalog)
    restarted.drivers = RestartDrivers()
    await restarted.start()
    try:
        assert (await restarted.wait("queued-env-restart", 10)).state == "succeeded"
        assert received == ["after"]
    finally:
        await restarted.close()




@pytest.mark.asyncio
async def test_explicit_retry_rebinds_rotated_project_environment(tmp_path: Path) -> None:
    root = repository(tmp_path)
    base = config(tmp_path / "home")
    target = replace(base.targets[0], env={"ROTATION": "global"})
    catalog = replace(base, targets=(target,))
    project_config = root / ".refract" / "config.toml"
    project_config.parent.mkdir()
    project_config.write_text('[[targets]]\nid = "primary"\nenv = { ROTATION = "first" }\n', encoding="utf-8")
    received: list[str] = []
    class RotatingDrivers(FakeDrivers):
        async def execute(self, *, env=None, **kwargs):
            received.append((env or {}).get("ROTATION", ""))
            if len(received) == 1:
                return DriverResult("REQUEST_FATAL", "", "", "first failure", "execution_error")
            return await super().execute(**kwargs)
    runtime = Runtime(catalog)
    runtime.drivers = RotatingDrivers()
    session_keys: list[str] = []
    original_session = runtime.database.session
    def capture_session(project_id, session, role, target_key):
        session_keys.append(target_key)
        return original_session(project_id, session, role, target_key)
    runtime.database.session = capture_session
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        submitted = await runtime.submit(project.id, "implement", "rotate")
        assert (await runtime.wait(submitted.job_id, 10)).state == "failed"
        project_config.write_text('[[targets]]\nid = "primary"\nenv = { ROTATION = "second" }\n', encoding="utf-8")
        retried = await runtime.retry(submitted.job_id, target="primary")
        assert (await runtime.wait(retried.job_id, 10)).state == "succeeded"
        assert runtime.database.job(submitted.job_id).state == "failed"
        assert received == ["first", "second"]
        assert len(session_keys) == 2
        assert session_keys[0] != session_keys[1]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_cancellation_during_environment_resolution_releases_probe(tmp_path: Path) -> None:
    root = repository(tmp_path)
    base = config(tmp_path / "home")
    target = replace(base.targets[0], env={"LOCAL": "synthetic"})
    catalog = replace(base, targets=(target,))
    runtime = Runtime(catalog)
    runtime.drivers = FakeDrivers()
    project = register_project(runtime, str(root))
    plan = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")
    runtime.database.create_job(
        job_id="cancel-env-resolution", project_id=project.id, workflow="implement",
        profile="balanced", prompt="cancel", execution_plan_json=json.dumps(execution_plan_data(plan)),
        session="cancel",
    )
    key = target_execution_key(target)
    with runtime.database._connection:
        runtime.database._connection.execute(
            "INSERT INTO target_health(target_id, circuit_open_until, cooldown_s, probe_job_id) VALUES (?, '2000-01-01T00:00:00+00:00', 60, '')",
            (key,),
        )
    def cancel_resolution(*_args):
        raise asyncio.CancelledError
    runtime.target_executor.environment_resolver = cancel_resolution
    cancel_event = CancelEvent()
    try:
        with pytest.raises(asyncio.CancelledError):
            await runtime.target_executor.execute(
                job_id="cancel-env-resolution", project=project, workflow="implement",
                session="cancel", plan=plan, prompt="cancel", cwd=root,
                cancel_event=cancel_event,
            )
        assert runtime.database.target_health(key)["probe_job_id"] == ""
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_environment_binding_uses_real_driver_backend_shell_transport(
    tmp_path: Path, caplog, monkeypatch
) -> None:
    root = repository(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    captured_path = tmp_path / "child-environment.json"
    fake_codex = tmp_path / "fake_codex.py"
    fake_codex.write_text(
        f'''import json, os, pathlib, sys
if '--help' in sys.argv:
    print('--json')
    raise SystemExit(0)
capture = pathlib.Path({str(captured_path)!r})
keys = ('SYNTHETIC_INHERITED_VALUE', 'SHARED_ONLY', 'PROJECT_ONLY', 'LOCAL_ONLY', 'LAYERED', 'REFRACT_ASK_URL', 'REFRACT_ASK_TOKEN')
capture.write_text(json.dumps({{key: os.environ.get(key) for key in keys}}))
if '-o' in sys.argv:
    pathlib.Path(sys.argv[sys.argv.index('-o') + 1]).write_text('fake provider response')
print(json.dumps({{'type': 'thread.started', 'thread_id': '00000000-0000-4000-8000-000000000001'}}))
print(json.dumps({{'type': 'item.completed', 'item': {{'type': 'agent_message', 'text': 'synthetic success'}}}}))
''',
        encoding="utf-8",
    )
    install_launcher(bin_dir, "codex", fake_codex)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    fake_codex_home = tmp_path / "codex-home"
    (fake_codex_home / "sessions").mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(fake_codex_home))
    monkeypatch.setenv("SYNTHETIC_INHERITED_VALUE", "inherited-marker")

    base = config(tmp_path / "home")
    target = replace(
        base.targets[0],
        env={"SHARED_ONLY": "global-value", "LOCAL_ONLY": "local-value", "LAYERED": "target-local"},
    )
    catalog = replace(base, targets=(target,))
    project_config = root / ".refract" / "config.toml"
    project_config.parent.mkdir()
    project_config.write_text(
        '''[[targets]]
id = "primary"
env = { SHARED_ONLY = "project-value", PROJECT_ONLY = "project-only", LAYERED = "project-layer" }
''',
        encoding="utf-8",
    )
    before_environment = dict(os.environ)
    runtime = Runtime(catalog)
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        submitted = await runtime.submit(project.id, "implement", "exercise fake codex")
        job = await runtime.wait(submitted.job_id, 15)
        assert job.state == "succeeded"
        child_environment = json.loads(captured_path.read_text(encoding="utf-8"))
        assert child_environment == {
            "SYNTHETIC_INHERITED_VALUE": "inherited-marker",
            "SHARED_ONLY": "project-value",
            "PROJECT_ONLY": "project-only",
            "LOCAL_ONLY": "local-value",
            "LAYERED": "project-layer",
            "REFRACT_ASK_URL": f"http://{runtime.config.host}:{runtime.config.port}/ask",
            "REFRACT_ASK_TOKEN": child_environment["REFRACT_ASK_TOKEN"],
        }
        assert child_environment["REFRACT_ASK_TOKEN"]
        record = runtime.database.job_record(submitted.job_id)
        assert "SYNTHETIC_" not in record["execution_plan_json"]
        assert "SYNTHETIC_" not in json.dumps(record)
        assert "SYNTHETIC_" not in caplog.text
        assert dict(os.environ) == before_environment
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_environment_configuration_failure_is_sanitized_and_not_provider_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = repository(tmp_path)
    base = config(tmp_path / "home")
    target = replace(base.targets[0], env={"BROKEN": "value"}, retry=RetryPolicy(3, (), ()))
    runtime = Runtime(replace(base, targets=(target,)))
    def broken_environment(_catalog, _target):
        raise ValueError("Environment value MISSING_SYNTHETIC_SECRET is invalid")
    monkeypatch.setattr("refract.runtime.resolve_target_environment", broken_environment)
    calls = []
    class CountingDrivers(FakeDrivers):
        async def execute(self, **kwargs):
            calls.append(True)
            return await super().execute(**kwargs)
    runtime.drivers = CountingDrivers()
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        submitted = await runtime.submit(project.id, "implement", "bad config")
        job = await runtime.wait(submitted.job_id, 10)
        assert job.state == "failed"
        assert calls == []
        assert job.result.failure_kind == "request_fatal"
        assert "MISSING_SYNTHETIC_SECRET" not in str(job.result)
        health = runtime.database.target_health(target_execution_key(target))
        assert health["consecutive_failures"] == 0
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_environment_binding_reaches_driver_without_persisting_values(tmp_path: Path, caplog, monkeypatch) -> None:
    root = repository(tmp_path)
    base = config(tmp_path / "home")
    target = replace(
        base.targets[0],
        env={"SHARED_ONLY": "SYNTHETIC_GLOBAL_VALUE", "LOCAL_ONLY": "SYNTHETIC_LOCAL_VALUE"},
        retry=RetryPolicy(1, ("temporary",), ()),
    )
    catalog = replace(base, targets=(target,))
    project_config = root / ".refract" / "config.toml"
    project_config.parent.mkdir()
    project_config.write_text('[[targets]]\nid = "primary"\nenv = { SHARED_ONLY = "SYNTHETIC_PROJECT_VALUE", PROJECT_ONLY = "SYNTHETIC_PROJECT_ONLY" }\n', encoding="utf-8")
    monkeypatch.setenv("SYNTHETIC_INHERITED_VALUE", "SYNTHETIC_INHERITED_MARKER")
    received: list[dict[str, str]] = []

    class CapturingDrivers(FakeDrivers):
        async def execute(self, *, env=None, **kwargs):
            received.append(dict(env or {}))
            child_env = {**os.environ, **(env or {})}
            child = subprocess.run(
                [sys.executable, "-c", "import os; print(os.environ.get('SYNTHETIC_INHERITED_VALUE', '')); print(os.environ.get('SHARED_ONLY', '')); print(os.environ.get('LOCAL_ONLY', '')); print(os.environ.get('PROJECT_ONLY', ''))"],
                env=child_env, capture_output=True, text=True, check=True,
            )
            assert child.stdout.splitlines() == ["SYNTHETIC_INHERITED_MARKER", "SYNTHETIC_PROJECT_VALUE", "SYNTHETIC_LOCAL_VALUE", "SYNTHETIC_PROJECT_ONLY"]
            if len(received) == 1:
                return DriverResult("RETRYABLE", "", "", "retry", "temporary")
            return await super().execute(**kwargs)

    before_environment = dict(os.environ)
    runtime = Runtime(catalog)
    runtime.drivers = CapturingDrivers()
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        submitted = await runtime.submit(project.id, "implement", "bind env")
        job = await runtime.wait(submitted.job_id, 10)
        assert job.state == "succeeded"
        assert received[0]["SHARED_ONLY"] == received[1]["SHARED_ONLY"] == "SYNTHETIC_PROJECT_VALUE"
        assert received[0]["LOCAL_ONLY"] == received[1]["LOCAL_ONLY"] == "SYNTHETIC_LOCAL_VALUE"
        assert received[-1]["SHARED_ONLY"] == "SYNTHETIC_PROJECT_VALUE"
        assert received[-1]["LOCAL_ONLY"] == "SYNTHETIC_LOCAL_VALUE"
        assert "REFRACT_ASK_TOKEN" in received[-1]
        record = runtime.database.job_record(submitted.job_id)
        assert "SYNTHETIC_" not in record["execution_plan_json"]
        assert "SYNTHETIC_" not in json.dumps(record)
        assert "SYNTHETIC_" not in caplog.text
        assert dict(os.environ) == before_environment
    finally:
        await runtime.close()


async def _dispatch_claimed_probe(tmp_path, drivers, runtime_holder=None):
    root = repository(tmp_path)
    catalog = config(tmp_path / "home")
    runtime = Runtime(catalog)
    if runtime_holder is not None:
        runtime_holder["runtime"] = runtime
    runtime.drivers = drivers
    target = catalog.targets[0]
    key = target_execution_key(target)
    project = register_project(runtime, str(root))
    plan = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")
    job_id = "probe-job"
    runtime.database.create_job(job_id=job_id, project_id=project.id, workflow="implement", profile="balanced", prompt="probe", execution_plan_json="{}", session="probe")
    with runtime.database._connection:
        runtime.database._connection.execute(
            "INSERT INTO target_health(target_id, consecutive_failures, circuit_open_until, cooldown_s) VALUES (?, 1, '2000-01-01T00:00:00+00:00', 77)",
            (key,),
        )
    result = await runtime.target_executor.execute(
        job_id=job_id, project=project, workflow="implement", session="probe", plan=plan,
        prompt="probe", cwd=root, cancel_event=CancelEvent(),
    )
    return runtime, key, result


@pytest.mark.asyncio
async def test_driver_exception_releases_claimed_probe(tmp_path):
    class Exploding(FakeDrivers):
        async def execute(self, **kwargs):
            raise RuntimeError("backend exploded")

    runtime = Runtime(config(tmp_path / "home"))
    root = repository(tmp_path)
    project = register_project(runtime, str(root))
    catalog = runtime.config
    key = target_execution_key(catalog.targets[0])
    plan = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")
    runtime.database.create_job(job_id="probe-job", project_id=project.id, workflow="implement", profile="balanced", prompt="probe", execution_plan_json="{}", session="probe")
    with runtime.database._connection:
        runtime.database._connection.execute("INSERT INTO target_health(target_id,circuit_open_until,cooldown_s) VALUES (?, '2000-01-01T00:00:00+00:00', 77)", (key,))
    runtime.drivers = Exploding()
    cancel_event = CancelEvent()
    with pytest.raises(RuntimeError, match="backend exploded"):
        await runtime.target_executor.execute(job_id="probe-job", project=project, workflow="implement", session="probe", plan=plan, prompt="probe", cwd=root, cancel_event=cancel_event)
    assert runtime.database.target_health(key)["probe_job_id"] == ""
    runtime.database.close()


@pytest.mark.asyncio
async def test_capacity_acquire_cancellation_releases_claimed_probe(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda cmd: f"/usr/bin/{cmd}")
    runtime = Runtime(config(tmp_path / "home"))
    root = repository(tmp_path)
    project = register_project(runtime, str(root))
    key = target_execution_key(runtime.config.targets[0])
    plan = resolve_execution_plan(get_workflow("implement"), runtime.config, "balanced")
    runtime.database.create_job(job_id="probe-job", project_id=project.id, workflow="implement", profile="balanced", prompt="probe", execution_plan_json="{}", session="probe")
    with runtime.database._connection:
        runtime.database._connection.execute("INSERT INTO target_health(target_id,circuit_open_until,cooldown_s) VALUES (?, '2000-01-01T00:00:00+00:00', 77)", (key,))

    async def cancelled_acquire(*args):
        raise asyncio.CancelledError()

    runtime.target_executor._acquire_target = cancelled_acquire
    cancel_event = CancelEvent()
    with pytest.raises(asyncio.CancelledError):
        await runtime.target_executor.execute(job_id="probe-job", project=project, workflow="implement", session="probe", plan=plan, prompt="probe", cwd=root, cancel_event=cancel_event)
    assert runtime.database.target_health(key)["probe_job_id"] == ""
    runtime.database.close()


@pytest.mark.asyncio
async def test_target_fatal_probe_does_not_double_cooldown(tmp_path):
    runtime, key, result = await _dispatch_claimed_probe(tmp_path, FakeDrivers({"primary": "TARGET_FATAL"}))
    health = runtime.database.target_health(key)
    assert result.result.outcome == "TARGET_FATAL"
    assert health["circuit_open_until"]
    assert health["cooldown_s"] == 77
    assert health["probe_job_id"] == ""
    runtime.database.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [
    DriverResult("RETRYABLE", "", "", "overflow", "context_overflow"),
    DriverResult("CANCELLED", "", "", "cancelled", "cancelled"),
    DriverResult("REQUEST_FATAL", "", "", "request failure", "request_error"),
])
async def test_noncounted_probe_outcomes_release_probe(tmp_path, result) -> None:
    root = repository(tmp_path)
    catalog = config(tmp_path / "home")

    class OneResultDrivers(FakeDrivers):
        async def execute(self, **kwargs) -> DriverResult:
            return result

    runtime = Runtime(catalog)
    runtime.drivers = OneResultDrivers()
    target_key = target_execution_key(catalog.targets[0])
    await runtime.start()
    try:
        with runtime.database._connection:
            runtime.database._connection.execute(
                "INSERT INTO target_health(target_id, consecutive_failures, circuit_open_until, cooldown_s) VALUES (?, 2, '2000-01-01T00:00:00+00:00', 60)",
                (target_key,),
            )
        project = register_project(runtime, str(root))
        submitted = await runtime.submit(project.id, "implement", "probe")
        await runtime.wait(submitted.job_id, 5)
        health = runtime.database.target_health(target_key)
        assert health["consecutive_failures"] == 2
        assert health["probe_job_id"] == ""
        assert health["circuit_open_until"] == "2000-01-01T00:00:00+00:00"
    finally:
        await runtime.close()


def test_half_open_probe_claim_is_not_leaked_when_target_at_capacity(tmp_path) -> None:
    targets = (TargetConfig(id="probe", backend="codex"), TargetConfig(id="closed", backend="codex"))
    catalog = config(tmp_path / "home", targets)
    database = Database(catalog.database_path)
    executor = TargetExecutor(catalog, database, FakeDrivers())
    probe_key = target_execution_key(targets[0])
    with database._connection:
        database._connection.execute(
            "INSERT INTO target_health(target_id, circuit_open_until, cooldown_s) VALUES (?, '2000-01-01T00:00:00+00:00', 60)",
            (probe_key,),
        )
    executor._target_active[targets[0].id] = targets[0].max_concurrency
    plan = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")

    selected = executor._select_target(plan.selection.targets, plan, "probe-job")

    assert selected is targets[1]
    assert database.target_health(probe_key)["probe_job_id"] == ""
    database.close()


@pytest.mark.asyncio
async def test_transient_failure_runs_one_target_and_persists_result_metadata(tmp_path) -> None:
    root = repository(tmp_path)
    targets = (TargetConfig(id="one", backend="codex", model="public-model-a"), TargetConfig(id="two", backend="codex", model="public-model-b"))
    catalog = config(tmp_path / "home", targets)

    class RetryDrivers(FakeDrivers):
        def __init__(self):
            super().__init__()
            self.called = []

        async def execute(self, *, target, **kwargs):
            self.called.append(target.id)
            return DriverResult("RETRYABLE", "", "", "transient", "backend_failure")

    drivers = RetryDrivers()
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        job = await runtime.wait((await runtime.submit(project.id, "implement", "fail once")).job_id, 5)
        job_result = job.result
        assert drivers.called == ["one"]
        assert job.state == "failed"
        assert job_result.failure_kind == "transient"
        assert job_result.model == "public-model-a"
        assert isinstance(job_result.duration_ms, int)
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_retry_overwrites_previous_run_metadata_after_driver_exception(tmp_path) -> None:
    root = repository(tmp_path)
    catalog = config(tmp_path / "home", (TargetConfig(id="primary", backend="codex", model="configured-model"),))

    class FailThenRaise(FakeDrivers):
        def __init__(self):
            super().__init__()
            self.calls = 0
        async def execute(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return DriverResult("RETRYABLE", "", "", "transient", "backend_failure", model="old-model")
            raise RuntimeError("retry backend failure")

    runtime = Runtime(catalog)
    drivers = FailThenRaise()
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        submission = await runtime.submit(project.id, "implement", "retry")
        first = await runtime.wait(submission.job_id, 5)
        assert first.result.model == "old-model"
        retried = await runtime.retry(submission.job_id, target="primary")
        second = await runtime.wait(retried.job_id, 5)
        assert second.state == "failed"
        assert runtime.database.job(submission.job_id).result.model == "old-model"
        assert second.result.failure_kind == "request_fatal"
        assert second.result.model == "configured-model"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_all_open_targets_fail_dispatch_without_counting_or_invoking_driver(tmp_path) -> None:
    root = repository(tmp_path)
    targets = (TargetConfig(id="one", backend="codex"), TargetConfig(id="two", backend="codex"))
    catalog = config(tmp_path / "home", targets)

    class CountingDrivers(FakeDrivers):
        def __init__(self):
            super().__init__()
            self.calls = 0
        async def execute(self, **kwargs):
            self.calls += 1
            return DriverResult("SUCCESS", "", "unexpected", "", "")

    drivers = CountingDrivers()
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        for target in targets:
            key = target_execution_key(target)
            with runtime.database._connection:
                runtime.database._connection.execute(
                    "INSERT INTO target_health(target_id, consecutive_failures, circuit_open_until, cooldown_s) VALUES (?, 2, '2999-01-01T00:00:00+00:00', 60)",
                    (key,),
                )
        plan = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")
        job_id = "dispatch-all-open"
        runtime.database.create_job(
            job_id=job_id, project_id=project.id, workflow="implement", profile="balanced",
            prompt="blocked", execution_plan_json=json.dumps(execution_plan_data(plan)),
            session="implement",
        )
        outcome = await runtime.target_executor.execute(
            job_id=job_id, project=project, workflow="implement", session="implement",
            plan=plan, prompt="blocked", cwd=root, cancel_event=CancelEvent(),
        )
        runtime.database.finish_job(
            job_id, "failed", error="circuit_open", failure_kind=outcome.outcome["failure_kind"],
            model=outcome.outcome["model"], duration_ms=outcome.outcome["duration_ms"],
        )
        job = runtime.database.job(job_id)
        assert drivers.calls == 0
        assert job.state == "failed"
        assert job.result.failure_kind == "circuit_open"
        assert job.result.duration_ms is None
        assert all(runtime.database.target_health(target_execution_key(target))["consecutive_failures"] == 2 for target in targets)
    finally:
        await runtime.close()


def test_runtime_submit_signature_omits_commit_message() -> None:
    assert "commit_message" not in inspect.signature(Runtime.submit).parameters
    assert "depends_on" not in inspect.signature(Runtime.submit).parameters


@pytest.mark.asyncio
async def test_global_project_and_target_capacities_apply_together(tmp_path) -> None:
    (tmp_path / "project-a").mkdir()
    (tmp_path / "project-b").mkdir()
    (tmp_path / "project-c").mkdir()
    root_a = repository(tmp_path / "project-a")
    root_b = repository(tmp_path / "project-b")
    root_c = repository(tmp_path / "project-c")
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
        job_id = uri.removeprefix("refract://jobs/")
        record = runtime_value.database.job_record(job_id)
        if record and record["state"] == "running":
            running_job_ids.add(job_id)
            if job_id == second_job_id:
                second_runner_started.set()

    target = TargetConfig(
        id="safe-reader", backend="pi", isolated=True, read_only=True, max_concurrency=1
    )
    catalog = replace(
        config(tmp_path / "home", (target,)), max_jobs=2
    )
    runtime = Runtime(catalog, notifier=notify)
    runtime_holder["runtime"] = runtime
    drivers = CapacityDrivers()
    runtime.drivers = drivers
    await runtime.start()
    try:
        project_a = register_project(runtime, str(root_a))
        project_b = register_project(runtime, str(root_b))
        project_c = register_project(runtime, str(root_c))
        first = await runtime.submit(project_a.id, "consult", "first", session="first")
        await first_driver_started.wait()
        second = await runtime.submit(project_b.id, "consult", "second", session="second")
        second_job_id = second.job_id
        if second_job_id in running_job_ids:
            second_runner_started.set()
        await asyncio.wait_for(second_runner_started.wait(), 2)
        assert runtime.scheduler.active_jobs == 2
        assert drivers.calls == 1

        third = await runtime.submit(project_c.id, "consult", "third", session="third")
        fourth = await runtime.submit(project_a.id, "consult", "fourth", session="fourth")
        assert runtime.database.job(third.job_id).state == "queued"
        assert runtime.database.job(fourth.job_id).state == "queued"

        release_drivers.set()
        for submission in (first, second, third, fourth):
            assert (await runtime.wait(submission.job_id, 5)).state == "succeeded"
        assert drivers.peak_active == 1
    finally:
        release_drivers.set()
        await runtime.close()












@pytest.mark.asyncio




@pytest.mark.asyncio
async def test_submission_preserves_fallback_targets_beyond_attempt_limit(tmp_path) -> None:
    root = repository(tmp_path)
    safe = TargetConfig(id="safe", backend="pi", isolated=True, read_only=True)
    fallback = TargetConfig(
        id="fallback", backend="pi", isolated=True, read_only=True,
        args=("--export", "out.html"),
    )
    selection = TargetSelection(("safe", "fallback"))
    catalog = replace(
        config(tmp_path / "home", (safe, fallback)),
        profiles={"balanced": {workflow: selection for workflow in ("consult", "implement", "review", "other")}},
    )
    runtime = Runtime(catalog)
    try:
        project = register_project(runtime, str(root))
        submitted = await runtime.submit(project.id, "review", "inspect")
        record = runtime.database.job_record(submitted.job_id)
        assert record is not None
        plan = json.loads(record["execution_plan_json"])
        assert "max_attempts" not in plan["selection"]
        assert [target["id"] for target in plan["targets"]] == ["safe", "fallback"]
        assert plan["targets"][1]["args"] == ["--export", "out.html"]
    finally:
        runtime.database.close()




@pytest.mark.asyncio
async def test_job_runner_task_cancellation_persists_terminal_state(tmp_path) -> None:
    from refract.execution import JobRunner

    root = repository(tmp_path)
    catalog = config(tmp_path / "home", (TargetConfig(id="primary", backend="codex", model="cancel-model"),))
    runtime = Runtime(catalog)
    project = register_project(runtime, str(root))
    plan = resolve_execution_plan(get_workflow("consult"), catalog, "balanced")
    runtime.database.create_job(
        job_id="runner-cancel",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="cancel me",
        execution_plan_json=json.dumps(execution_plan_data(plan)),
        session="consult",
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
    task = asyncio.create_task(runner.run("runner-cancel", CancelEvent()))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    cancelled_job = runtime.database.job("runner-cancel")
    assert cancelled_job.state == "cancelled"
    assert cancelled_job.result.failure_kind == "cancelled"
    assert cancelled_job.result.model == "cancel-model"
    assert isinstance(cancelled_job.result.duration_ms, int)
    runtime.database.close()










@pytest.mark.asyncio
async def test_cancel_reserved_unstarted_dispatch_then_retry_uses_fresh_event_once(tmp_path) -> None:
    root = repository(tmp_path)
    runtime_holder: dict[str, Runtime] = {}
    blocker_notice_entered = asyncio.Event()
    release_blocker_notice = asyncio.Event()
    blocker_driver_started = asyncio.Event()
    release_blocker_driver = asyncio.Event()
    retry_driver_started = asyncio.Event()
    release_retry_driver = asyncio.Event()
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
        job_id = uri.removeprefix("refract://jobs/")
        record = runtime.database.job_record(job_id)
        if job_id == blocker_job_id and record and record["state"] == "succeeded":
            blocker_notice_entered.set()
            await release_blocker_notice.wait()

    runtime = Runtime(config(tmp_path / "home"), notifier=notify)
    runtime_holder["runtime"] = runtime
    runtime.drivers = RetryDriver()
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        blocker = await runtime.submit(project.id, "implement", "blocker")
        blocker_job_id = blocker.job_id
        await blocker_driver_started.wait()
        release_blocker_driver.set()
        await asyncio.wait_for(blocker_notice_entered.wait(), 2)
        parent = await runtime.submit(project.id, "review", "retry-parent")

        original_run = runtime.runner.run

        async def trace_dispatch(job_id: str, cancel_event: threading.Event) -> None:
            if job_id != blocker_job_id:
                dispatch_events.append(cancel_event)
            await original_run(job_id, cancel_event)

        runtime.scheduler._run_job = trace_dispatch
        assert runtime.database.job(parent.job_id).state == "queued"
        assert runtime.scheduler.active_jobs == 1

        cancelled = await runtime.cancel(parent.job_id)
        assert cancelled.state == "cancelled"
        assert runtime.database.job(parent.job_id).state == "cancelled"
        assert runtime.scheduler.active_jobs == 0

        retried = await runtime.retry(parent.job_id, target="primary")
        assert retried.job_id != parent.job_id
        assert runtime.database.job(parent.job_id).state == "cancelled"
        assert runtime.database.job(retried.job_id).state == "queued"
        assert runtime.scheduler.active_jobs == 1

        release_blocker_notice.set()
        await asyncio.wait_for(retry_driver_started.wait(), 2)
        assert len(dispatch_events) == 1
        assert not dispatch_events[0].is_set()
        release_retry_driver.set()
        assert (await runtime.wait(retried.job_id, 5)).state == "succeeded"
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
                return DriverResult("REQUEST_FATAL", "", "", "failed", "request_error")
            return DriverResult("SUCCESS", "", "retried", "", "")

    async def notify(uri: str) -> None:
        runtime = runtime_holder.get("runtime")
        if runtime is None:
            return
        job_id = uri.removeprefix("refract://jobs/")
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
        project = register_project(runtime, str(root))
        submitted = await runtime.submit(project.id, "implement", "retry race")
        await driver_started.wait()
        allow_first_failure.set()
        await asyncio.wait_for(terminal_notice_entered.wait(), 2)

        retry_result = await runtime.retry(submitted.job_id, target="primary")
        assert runtime.database.job(retry_result.job_id).state in {"queued", "running", "succeeded"}
        release_terminal_notice.set()
        assert (await runtime.wait(retry_result.job_id, 5)).state == "succeeded"
        assert runtime.database.job(submitted.job_id).state == "failed"
        assert drivers.calls == 2
    finally:
        release_terminal_notice.set()
        await runtime.close()


@pytest.mark.asyncio
async def test_startup_recovers_interrupted_jobs_before_admission(tmp_path) -> None:
    root = repository(tmp_path)
    catalog = config(tmp_path / "home")
    database = Database(catalog.database_path)
    project = database.upsert_project(project_id="p", root=root.as_posix())
    plan = execution_plan_data(resolve_execution_plan(get_workflow("consult"), catalog, "balanced"))
    database.create_job(
        job_id="interrupted-job", project_id=project.id, workflow="consult", profile="balanced",
        prompt="interrupted", execution_plan_json=json.dumps(plan), session="consult",
    )
    database.start_job("interrupted-job")
    database.close()

    runtime = Runtime(catalog)
    drivers = FakeDrivers()
    runtime.drivers = drivers
    await runtime.start()
    try:
        assert runtime.database.job("interrupted-job").state == "interrupted"
        assert not drivers.sessions
    finally:
        await runtime.close()




@pytest.mark.asyncio
async def test_target_semaphore_released_after_post_acquire_failures(tmp_path, monkeypatch) -> None:

    root = repository(tmp_path)
    catalog = config(tmp_path / "home")
    runtime = Runtime(catalog)
    project = register_project(runtime, str(root))
    plan = resolve_execution_plan(get_workflow("consult"), catalog, "balanced")
    target = plan.target("primary")
    runtime.database.create_job(
        job_id="target-lease",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="test target lease",
        execution_plan_json=json.dumps(execution_plan_data(plan)),
        session="consult",
    )

    class CapabilityFailureDrivers(FakeDrivers):
        def supports_structured_streaming(self, target):
            raise RuntimeError("capability setup failed")

    runtime.drivers = CapabilityFailureDrivers()

    cancel_event = CancelEvent()
    try:
        with pytest.raises(RuntimeError):
            await runtime.target_executor.execute(
                job_id="target-lease",
                project=project,
                workflow="consult",
                session="consult",
                plan=plan,
                prompt="test target lease",
                cwd=root,
                cancel_event=cancel_event,
            )
        target_key = target_execution_key(target)
        assert not runtime.target_executor._target_active
        assert not runtime.target_executor._target_semaphores
    finally:
        runtime.database.close()




@pytest.mark.asyncio
async def test_submission_result_has_no_resource_uri(tmp_path) -> None:
    root = repository(tmp_path)
    runtime = Runtime(config(tmp_path / "home"))
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        submission = await runtime.submit(project.id, "implement", "inspect")
        assert submission.job_id
        assert "resource_uri" not in submission.model_dump()
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
        project = register_project(runtime, str(root))
        submission = await runtime.submit(project.id, "implement", "inspect")
        await runtime.wait(submission.job_id, 10)
        assert notifications == [submission.job_id] * 3
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
        project = register_project(runtime, str(root))
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
        project = register_project(runtime, str(root))
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
        project = register_project(runtime, str(root))
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
        project = register_project(runtime, str(root))
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
        project = register_project(runtime, str(root))
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
        project = register_project(runtime, str(root))
        submitted = await runtime.submit(project.id, "other", "inspect", session="shared")
        job = await runtime.wait(submitted.job_id, 10)
        record = runtime.database.job_record(submitted.job_id)
        assert job.workflow == "other"
        assert job.session == "shared"
        assert record is not None
        assert json.loads(record["execution_plan_json"])["workflow"] == "other"
        workflows = runtime.database._connection.execute(
            "SELECT workflow FROM target_sessions WHERE project_id=? AND session='shared'", (project.id,)
        ).fetchall()
        assert [row[0] for row in workflows] == ["other"]
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
        project = register_project(runtime, str(root))
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
async def test_transient_failure_does_not_schedule_another_attempt(tmp_path) -> None:
    root = repository(tmp_path)
    selection = TargetSelection(("primary",))
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
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        job = await runtime.wait(
            (await runtime.submit(project.id, "implement", "retry")).job_id,
            10,
        )
        assert job.state == "failed"
        assert runtime.drivers.calls == 1
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_retry_transition_notifies_each_job_resource(tmp_path) -> None:
    root = repository(tmp_path)
    notifications: list[str] = []

    async def notify(uri: str) -> None:
        notifications.append(uri)

    runtime = Runtime(config(tmp_path / "home"), notifier=notify)
    runtime.drivers = RetryDrivers()
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        submission = await runtime.submit(project.id, "implement", "retry")
        assert (await runtime.wait(submission.job_id, 10)).state == "failed"
        retried = await runtime.retry(submission.job_id, target="primary")
        assert (await runtime.wait(retried.job_id, 10)).state == "failed"
        assert notifications == [submission.job_id] * 3 + [retried.job_id] * 3
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_transient_failure_returns_without_retry_backoff(tmp_path) -> None:
    root = repository(tmp_path)
    selection = TargetSelection(("primary",))
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
        project = register_project(runtime, str(root))
        submitted = await runtime.submit(project.id, "implement", "retry")
        assert (await runtime.wait(submitted.job_id, 5)).state == "failed"
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
        project = register_project(runtime, str(root))
        first = await runtime.submit(project.id, "implement", "block")
        second = await runtime.submit(project.id, "review", "never run")
        await drivers.started.wait()
        queued_cancel = await runtime.cancel(second.job_id)
        assert queued_cancel.state == "cancelled"
        running_cancel = await runtime.cancel(first.job_id)
        assert running_cancel.state == "running"
        assert (await runtime.wait(first.job_id, 10)).state == "cancelled"
        assert (await runtime.wait(second.job_id, 10)).state == "cancelled"
        assert [job_id for job_id in notifications if job_id == first.job_id] == [first.job_id] * 3
        assert [job_id for job_id in notifications if job_id == second.job_id] == [second.job_id] * 2
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_restart_releases_orphaned_probe_to_half_open(tmp_path) -> None:
    catalog = config(tmp_path / "home")
    key = target_execution_key(catalog.targets[0])
    runtime = Runtime(catalog)
    await runtime.start()
    with runtime.database._connection:
        runtime.database._connection.execute(
            "INSERT INTO target_health(target_id, consecutive_failures, circuit_open_until, cooldown_s, probe_job_id) VALUES (?, 1, '2000-01-01T00:00:00+00:00', 60, 'dead-job')",
            (key,),
        )
    await runtime.close()

    restarted = Runtime(catalog)
    await restarted.start()
    try:
        health = restarted.database.target_health(key)
        assert health["probe_job_id"] == ""
        assert not restarted.target_executor.is_circuit_open(
            health["circuit_open_until"], datetime.now(timezone.utc)
        )
    finally:
        await restarted.close()


@pytest.mark.asyncio
async def test_shutdown_leaves_unstarted_queued_job_durable_for_restart(tmp_path) -> None:
    root = repository(tmp_path)
    catalog = config(tmp_path / "home")
    drivers = BlockingDrivers()
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    await runtime.start()
    project = register_project(runtime, str(root))
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
    project = register_project(runtime, str(root))
    submitted = await runtime.submit(project.id, "implement", "block")
    await drivers.started.wait()

    await runtime.close()

    database = Database(catalog.database_path)
    try:
        job = database.job(submitted.job_id)
        assert job
        assert job.state == "interrupted"
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
        first_project = register_project(runtime, str(first_root))
        second_project = register_project(runtime, str(second_root))
        first = await runtime.submit(first_project.id, "implement", "block")
        await drivers.started.wait()
        second = await runtime.submit(second_project.id, "implement", "wait")
        while runtime.database.job(second.job_id).state != "running":
            await asyncio.sleep(0)

        assert (await runtime.cancel(second.job_id)).state in {"running", "cancelled"}
        second_job = await runtime.wait(second.job_id, 1)
        assert second_job.state == "cancelled"
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
    first_project = register_project(runtime, str(first_root))
    second_project = register_project(runtime, str(second_root))
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
    project = database.upsert_project(project_id="project", root=root.as_posix())
    plan = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")
    database.create_job(job_id="running", project_id=project.id, workflow="implement", profile="balanced", prompt="change", execution_plan_json=json.dumps(execution_plan_data(plan)), session="implement")
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
        assert interrupted
        assert interrupted.state == "interrupted"
        assert notifications == ["running"]
        assert (root / "partial.txt").read_text(encoding="utf-8") == "partial\n"
    finally:
        await runtime.close()


def test_registration_accepts_plain_directory(tmp_path) -> None:
    root = tmp_path / "plain-project"
    root.mkdir()
    runtime = Runtime(config(tmp_path / "home"))
    try:
        project = register_project(runtime, str(root))
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
            runtime.resolve_project(str(path))
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_plain_directory_execution_spawns_no_git(monkeypatch, tmp_path) -> None:
    root = tmp_path / "plain-project"
    root.mkdir()

    original_run = subprocess.run

    def fail_git_spawn(command, *args, **kwargs):
        if command and command[0] == "git":
            raise AssertionError("Refract spawned Git")
        return original_run(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", fail_git_spawn)
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = FakeDrivers()
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        job = await runtime.wait((await runtime.submit(project.id, "consult", "inspect")).job_id, 10)
        assert job.state == "succeeded"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_retry_attempts_recompile_argv_per_backend(tmp_path) -> None:
    root = repository(tmp_path)
    selection = TargetSelection(("claude-target", "pi-target"))
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
        project = register_project(runtime, str(root))
        job = await runtime.wait((await runtime.submit(project.id, "implement", "retry")).job_id, 10)
        assert job.state == "failed"
        assert compiled == ["claude-target"]
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
    from refract.config import load_config
    runtime = Runtime(load_config(path))
    runtime.drivers = FakeDrivers()
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
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
        project = register_project(runtime, str(root))
        # Seed prior turns and sessions
        runtime.database.store_session(
            project_id=project.id,
            session="feature",
            workflow="implement",
                        target_key=tkey,
            backend_session_id="old-session-1",
        )
        runtime.database.store_session(
            project_id=project.id,
            session="feature",
            workflow="implement",
            target_key="secondary-key",
            backend_session_id="old-session-2",
        )
        runtime.database.store_session(
            project_id=project.id,
            session="unrelated",
            workflow="implement",
                        target_key=tkey,
            backend_session_id="unrelated-session",
        )

        assert runtime.database.session(project.id, "feature", "implement", tkey) == "old-session-1"
        assert runtime.database.session(project.id, "feature", "implement", "secondary-key") == "old-session-2"

        # Submit fresh job
        submitted = await runtime.submit(
            project.id,
            "implement",
            "fresh request prompt",
            session="feature",
            fresh=True,
        )
        job = await runtime.wait(submitted.job_id, 10)
        assert job.state == "succeeded"

        # Every fresh attempt supplies empty session ID and exact validated prompt
        assert drivers.recorded_sessions[0] == ""
        assert drivers.recorded_prompts[0] == "fresh request prompt"

        # Old sessions for this project, session, workflow are cleared
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
            session="feature",
            fresh=False,
        )
        standard_job = await runtime.wait(standard_sub.job_id, 10)
        assert standard_job.state == "succeeded"

        assert drivers.recorded_sessions[1] == "new-session-1"
        assert drivers.recorded_prompts[1] == "next standard prompt"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_fresh_job_failure_preserves_freshness_without_fallback(tmp_path) -> None:
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
        project = register_project(runtime, str(root))
        for target, target_key in zip(catalog.targets, (primary_key, secondary_key), strict=True):
            runtime.database.store_session(
                project_id=project.id,
                session="stream",
                workflow="implement",
                                target_key=target_key,
                backend_session_id=f"old-{target.id}-session",
            )

        submitted = await runtime.submit(
            project.id,
            "implement",
            "failover prompt",
            session="stream",
            fresh=True,
        )
        job = await runtime.wait(submitted.job_id, 10)
        assert job.state == "failed"

        assert drivers.attempts == [("primary", "", "failover prompt")]
        assert runtime.database.session(project.id, "stream", "implement", primary_key) == "old-primary-session"
        assert runtime.database.session(project.id, "stream", "implement", secondary_key) == "old-secondary-session"
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
                return DriverResult("REQUEST_FATAL", "", "", "fatal error", "request_error")
            return DriverResult("SUCCESS", "retry-session", "ok", "", "")

    drivers = OnceFailingDrivers()
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    tkey = target_execution_key(catalog.targets[0])
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        runtime.database.store_session(
            project_id=project.id,
            session="stream",
            workflow="implement",
            target_key=tkey,
            backend_session_id="old-session",
        )

        submitted = await runtime.submit(
            project.id,
            "implement",
            "retry prompt",
            session="stream",
            fresh=True,
        )
        failed_job = await runtime.wait(submitted.job_id, 10)
        assert failed_job.state == "failed"

        # Failed fresh job does not clear preexisting sessions
        assert runtime.database.session(project.id, "stream", "implement", tkey) == "old-session"

        # Retry the job
        retried = await runtime.retry(submitted.job_id, target="primary")
        record = runtime.database.job_record(retried.job_id)
        assert record
        assert record["fresh"] == 1
        assert record["retry_of"] == submitted.job_id

        succeeded_job = await runtime.wait(retried.job_id, 10)
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
        project = register_project(runtime, str(root))
        runtime.database.store_session(
            project_id=project.id,
            session="stream",
            workflow="implement",
            target_key=tkey,
            backend_session_id="old-session",
        )
        assert runtime.database.session(project.id, "stream", "implement", tkey) == "old-session"

        submitted = await runtime.submit(
            project.id,
            "implement",
            "stateless prompt",
            session="stream",
            fresh=True,
        )
        job = await runtime.wait(submitted.job_id, 10)
        assert job.state == "succeeded"

        # Old session removed, no new session stored
        assert runtime.database.session(project.id, "stream", "implement", tkey) == ""
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_fresh_flag_survives_daemon_restart(tmp_path) -> None:
    root = repository(tmp_path)
    home = tmp_path / "home"
    catalog = config(home)
    database = Database(catalog.database_path)
    project = database.upsert_project(project_id="project", root=root.as_posix())
    plan = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")
    database.create_job(
        job_id="queued-fresh",
        project_id=project.id,
        workflow="implement",
        profile="balanced",
        prompt="fresh restart prompt",
        execution_plan_json=json.dumps(execution_plan_data(plan)),
        session="implement",
        fresh=True,
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
        project = register_project(runtime, str(root))
        runtime.database.store_session(
            project_id=project.id,
            session="stream",
            workflow="implement",
            target_key=tkey,
            backend_session_id="old-session",
        )
        assert runtime.database.session(project.id, "stream", "implement", tkey) == "old-session"

        submitted = await runtime.submit(
            project.id,
            "implement",
            "cancelled prompt",
            session="stream",
            fresh=True,
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
        project = register_project(runtime, str(root))
        runtime.database.store_session(
            project_id=project.id,
            session="stream",
            workflow="implement",
            target_key=tkey,
            backend_session_id="old-session",
        )
        assert runtime.database.session(project.id, "stream", "implement", tkey) == "old-session"

        runtime.database._connection.execute("""
            CREATE TRIGGER fail_fresh BEFORE INSERT ON target_sessions
            BEGIN
                SELECT RAISE(FAIL, 'session insert failed');
            END;
        """)

        submitted = await runtime.submit(
            project.id,
            "implement",
            "failing persistence prompt",
            session="stream",
            fresh=True,
        )
        job = await runtime.wait(submitted.job_id, 10)
        assert job.state == "failed"

        runtime.database._connection.execute("DROP TRIGGER fail_fresh")

        # Atomic rollback preserves old session on persistence failure
        assert runtime.database.session(project.id, "stream", "implement", tkey) == "old-session"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_fresh_job_failure_updating_state_to_succeeded_preserves_old_session(tmp_path) -> None:
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
        project = register_project(runtime, str(root))
        runtime.database.store_session(
            project_id=project.id,
            session="stream",
            workflow="implement",
            target_key=tkey,
            backend_session_id="old-session",
        )
        assert runtime.database.session(project.id, "stream", "implement", tkey) == "old-session"

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
            session="stream",
            fresh=True,
        )
        job = await runtime.wait(submitted.job_id, 10)
        assert job.state == "failed"

        runtime.database._connection.execute("DROP TRIGGER reject_succeeded")

        # Preserves old session
        assert runtime.database.session(project.id, "stream", "implement", tkey) == "old-session"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_accepted_events_flush_before_lifecycle_completion(tmp_path) -> None:
    """Accepted stream events must be durably flushed before attempt.finished and job terminal state."""
    root = repository(tmp_path)
    cat = config(tmp_path / "home")

    class StreamingDrivers(FakeDrivers):
        async def execute(self, *, on_event=None, **kwargs) -> DriverResult:
            if on_event:
                async def worker():
                    await on_event({"kind": "assistant.text.delta", "entity_id": "msg-1", "data": {"text": "streaming content"}})
                await worker()
            return DriverResult("SUCCESS", "sess-1", "streaming content", "", "")

    runtime = Runtime(cat)
    runtime.drivers = StreamingDrivers()
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        sub = await runtime.submit(project.id, "implement", "do streaming")
        job = await runtime.wait(sub.job_id, 5)
        assert job.state == "succeeded"

        events = _stream_events(runtime.database, sub.job_id)
        assert any(e["kind"] == "assistant.text.delta" and e["data"].get("text") == "streaming content" for e in events)
        finished = [e for e in events if e["kind"] == "attempt.finished"]
        assert len(finished) == 1
        assert finished[0]["attempt"] == 1
        assert finished[0]["data"]["status"] == "succeeded"
        assert finished[0]["data"]["outcome"] == "SUCCESS"
        assert finished[0]["data"]["error_code"] == ""
        delta_idx = next(i for i, e in enumerate(events) if e["kind"] == "assistant.text.delta")
        finished_idx = next(i for i, e in enumerate(events) if e["kind"] == "attempt.finished")
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

        async def execute(self, *, on_event=None, cancel_event=None, **kwargs) -> DriverResult:
            if on_event:
                async def worker():
                    await on_event({"kind": "assistant.text.delta", "entity_id": "msg-1", "data": {"text": "stream before cancel"}})
                await worker()
            self.started.set()
            while cancel_event and not cancel_event.is_set():
                await asyncio.sleep(0.01)
            return DriverResult("CANCELLED", "", "", "cancelled", "cancelled")

    drivers = CancellingStreamingDrivers()
    runtime = Runtime(cat)
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        sub = await runtime.submit(project.id, "implement", "cancel test")
        await drivers.started.wait()
        await runtime.cancel(sub.job_id)
        job = await runtime.wait(sub.job_id, 5)
        assert job.state == "cancelled"

        events = _stream_events(runtime.database, sub.job_id)
        assert any(e["kind"] == "assistant.text.delta" for e in events)
        finished = [e for e in events if e["kind"] == "attempt.finished"]
        assert len(finished) == 1
        assert finished[0]["attempt"] == 1
        assert finished[0]["data"]["status"] == "cancelled"
        assert finished[0]["data"]["outcome"] == "CANCELLED"
        assert finished[0]["data"]["error_code"] == "cancelled"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_attempt_finished_records_cancelled_status_when_cancel_event_set(tmp_path) -> None:
    root = repository(tmp_path)
    cat = config(tmp_path / "home")

    class RaceCancellingDrivers(FakeDrivers):
        async def execute(self, *, on_event=None, cancel_event=None, **kwargs) -> DriverResult:
            if on_event:
                async def worker():
                    await on_event({"kind": "assistant.text.delta", "entity_id": "msg-1", "data": {"text": "streaming content"}})
                await worker()
            if cancel_event:
                cancel_event.set()
            return DriverResult("SUCCESS", "sess-1", "streaming content", "", "")

    runtime = Runtime(cat)
    runtime.drivers = RaceCancellingDrivers()
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        sub = await runtime.submit(project.id, "implement", "test cancel race")
        job = await runtime.wait(sub.job_id, 5)
        assert job.state in {"cancelled", "interrupted"}

        events = _stream_events(runtime.database, sub.job_id)
        finished = [e for e in events if e["kind"] == "attempt.finished"]
        assert len(finished) == 1
        assert finished[0]["data"]["status"] == "cancelled"
        assert finished[0]["data"]["outcome"] == "CANCELLED"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_single_failed_attempt_transcript_uses_attempt_one(tmp_path) -> None:
    """A single failed target run records its transcript under attempt one."""
    root = repository(tmp_path)
    selection = TargetSelection(("primary",))
    cat = replace(
        config(tmp_path / "home"),
        profiles={"balanced": {"implement": selection, "review": selection, "consult": selection}},
    )

    class MultiAttemptDrivers(FakeDrivers):
        def __init__(self):
            super().__init__()
            self.call_count = 0

        async def execute(self, *, on_event=None, **kwargs) -> DriverResult:
            self.call_count += 1
            if on_event:
                async def worker(c):
                    await on_event({"kind": "assistant.text.delta", "entity_id": "msg-1", "data": {"text": f"attempt-{c}"}})
                await worker(self.call_count)
            if self.call_count == 1:
                return DriverResult("RETRYABLE", "", "", "first attempt failed", "backend_failure")
            return DriverResult("SUCCESS", "sess-2", "final success", "", "")

    runtime = Runtime(cat)
    runtime.drivers = MultiAttemptDrivers()
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        sub = await runtime.submit(project.id, "implement", "do attempts")
        job = await runtime.wait(sub.job_id, 5)
        assert job.state == "failed"
        events = _stream_events(runtime.database, sub.job_id)
        deltas = [e for e in events if e["attempt"] == 1 and e["kind"] == "assistant.text.delta"]
        assert len(deltas) == 1
        assert deltas[0]["data"]["text"] == "attempt-1"
        finished = [e for e in events if e["kind"] == "attempt.finished"]
        assert len(finished) == 1
        assert finished[0]["attempt"] == 1
        assert finished[0]["data"]["status"] == "failed"
        assert finished[0]["data"]["outcome"] == "RETRYABLE"
        assert finished[0]["data"]["error_code"] == "backend_failure"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_attempt_finished_records_driver_exception_as_request_failure(tmp_path) -> None:
    """A driver exception produces one failed recorder event rather than retrying."""
    root = repository(tmp_path)
    selection = TargetSelection(("primary",))
    cat = config(tmp_path / "home", (TargetConfig(id="primary", backend="codex", model="configured-model"),))

    class CrashingDrivers(FakeDrivers):
        def __init__(self):
            super().__init__()
            self.call_count = 0

        async def execute(self, *, on_event=None, **kwargs) -> DriverResult:
            self.call_count += 1
            if on_event:
                async def worker(c):
                    await on_event({"kind": "assistant.text.delta", "entity_id": "msg-1", "data": {"text": f"attempt-{c}"}})
                await worker(self.call_count)
            raise RuntimeError("driver crash")

    runtime = Runtime(cat)
    runtime.drivers = CrashingDrivers()
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        sub = await runtime.submit(project.id, "implement", "do crashing attempt")
        job = await runtime.wait(sub.job_id, 5)
        assert job.state == "failed"
        job_result = job.result
        assert job_result.failure_kind == "request_fatal"
        assert job_result.model == "configured-model"
        assert isinstance(job_result.duration_ms, int)

        events = _stream_events(runtime.database, sub.job_id)
        finished = [e for e in events if e["attempt"] == 1 and e["kind"] == "attempt.finished"]
        assert len(finished) == 1
        assert finished[0]["data"]["status"] == "failed"
        assert finished[0]["data"]["outcome"] == "REQUEST_FATAL"
        assert finished[0]["data"]["error_code"] == "execution_error"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_capability_check_before_submission_with_final_only_fallback(tmp_path, monkeypatch) -> None:
    """Structured mode capability check happens before prompt submission with final-only fallback."""
    from refract.drivers import DriverRegistry

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

    # In execution, when capability is unsupported, TargetExecutor falls back to final-only invocation (on_event=None)
    root = repository(tmp_path)
    target_exec = TargetConfig(id="target-exec", backend="claude")
    cat = config(tmp_path / "home", (target_exec,))
    runtime = Runtime(cat)

    received_emitters = []

    class MockExecutorDrivers(FakeDrivers):
        def supports_structured_streaming(self, target, **kwargs):
            return False

        async def execute(self, *, on_event=None, **kwargs) -> DriverResult:
            received_emitters.append(on_event)
            return DriverResult("SUCCESS", "sess-old", "fallback output", "", "")

    runtime.drivers = MockExecutorDrivers()
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        sub = await runtime.submit(project.id, "implement", "test fallback")
        job = await runtime.wait(sub.job_id, 5)
        assert job.state == "succeeded"
        assert job.result.text == "fallback output"
        # Emitter passed to driver must be None for final-only fallback
        assert received_emitters == [None]
        # No stream events recorded
        events = _stream_events(runtime.database, sub.job_id)
        assert len(events) == 0
    finally:
        await runtime.close()


def test_detect_structured_mode_invokes_help_probe_and_detects_support(tmp_path, monkeypatch) -> None:
    """Default capability probe invokes configured --help command and detects supported structured mode."""
    from refract.drivers import DriverRegistry
    from tests.launchers import install_launcher

    marker = tmp_path / "probe_invoked.txt"
    script = tmp_path / "fake_claude.py"
    script.write_text(
        "import sys\n"
        'if sys.argv[1:2] == ["--help"]:\n'
        f"    with open({str(marker)!r}, 'a', encoding='utf-8') as log:\n"
        "        log.write('called\\n')\n"
        "    print('options: stream-json --include-partial-messages')\n",
        encoding="utf-8",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_cli = install_launcher(bin_dir, "claude", script)

    registry = DriverRegistry()
    target = TargetConfig(id="target-claude", backend="claude")
    previous = shutil.which
    monkeypatch.setattr(
        "shutil.which",
        lambda name, *args, **kwargs: str(fake_cli) if name == "claude" else previous(name, *args, **kwargs),
    )

    # Reach default capability probe without version_check override
    assert registry.supports_structured_streaming(target) is True
    assert marker.read_text(encoding="utf-8").strip() == "called"

    # Cached per resolved executable: second call should not re-invoke probe
    assert registry.supports_structured_streaming(target) is True
    assert marker.read_text(encoding="utf-8").splitlines() == ["called"]


def test_detect_structured_mode_launches_windows_shim_through_prepare_command(tmp_path) -> None:
    """The help probe must use the .ps1 shim, never run the .cmd through cmd.exe."""
    from refract.drivers import DriverRegistry

    script = tmp_path / "fake_claude.py"
    script.write_text("print('options: stream-json --include-partial-messages')\n", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_cli = install_launcher(bin_dir, "claude", script)
    if fake_cli.suffix == ".cmd":
        # Only the PowerShell shim works, so a probe that executes the .cmd directly fails.
        fake_cli.write_text("@exit /b 9\r\n", encoding="utf-8")

    assert DriverRegistry._detect_structured_mode("claude", str(fake_cli)) is True


def test_codex_capability_probes_exec_subcommand(tmp_path, monkeypatch) -> None:
    """Codex capability probe must run 'codex exec --help' rather than top-level 'codex --help'."""
    from refract.drivers import DriverRegistry
    from tests.launchers import install_launcher

    log = tmp_path / "codex_log.txt"
    script = tmp_path / "fake_codex.py"
    script.write_text(
        "import sys\n"
        "def record(line):\n"
        f"    with open({str(log)!r}, 'a', encoding='utf-8') as handle:\n"
        "        handle.write(line + '\\n')\n"
        "if sys.argv[1:3] == ['exec', '--help']:\n"
        "    record('exec-probe')\n"
        "    print('Usage: codex exec [OPTIONS] [PROMPT]')\n"
        "    print('Options:')\n"
        "    print('  --json  Output structured JSONL events')\n"
        "elif sys.argv[1:2] == ['--help']:\n"
        "    record('toplevel-probe')\n"
        "    print('Usage: codex [OPTIONS] COMMAND [ARGS]...')\n"
        "    print('Commands:')\n"
        "    print('  exec    Execute prompt')\n"
        "    print('  review  Review workspace')\n",
        encoding="utf-8",
    )
    old_script = tmp_path / "fake_old_codex.py"
    old_script.write_text(
        "import sys\n"
        "if sys.argv[1:3] == ['exec', '--help']:\n"
        "    print('Usage: codex exec [OPTIONS] [PROMPT]')\n"
        "    print('Options: --help Show this message')\n",
        encoding="utf-8",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_codex = install_launcher(bin_dir, "codex", script)
    old_bin_dir = tmp_path / "old-bin"
    old_bin_dir.mkdir()
    fake_old_codex = install_launcher(old_bin_dir, "codex-old", old_script)

    registry = DriverRegistry()
    target = TargetConfig(id="target-codex", backend="codex")
    previous = shutil.which
    monkeypatch.setattr(
        "shutil.which",
        lambda name, *args, **kwargs: str(fake_codex) if name == "codex" else previous(name, *args, **kwargs),
    )

    # Must probe 'exec --help' and detect structured streaming support
    assert registry.supports_structured_streaming(target) is True
    log_content = log.read_text(encoding="utf-8").strip()
    assert log_content == "exec-probe"

    # Also test representative older codex where exec --help lacks --json
    target_old = TargetConfig(id="target-old-codex", backend="codex-old")
    monkeypatch.setattr(
        "shutil.which",
        lambda name, *args, **kwargs: str(fake_old_codex)
        if name == "codex-old"
        else (str(fake_codex) if name == "codex" else previous(name, *args, **kwargs)),
    )
    assert registry.supports_structured_streaming(target_old) is False


@pytest.mark.asyncio
async def test_single_failed_execution_metadata_survives_runtime_reload(tmp_path) -> None:
    """The single failed target's transcript and metadata survive daemon restart."""
    root = repository(tmp_path)
    selection = TargetSelection(("primary",))
    cfg = replace(
        config(tmp_path / "home"),
        profiles={"balanced": {"implement": selection, "review": selection, "consult": selection}},
    )

    class RetryDrivers(FakeDrivers):
        def __init__(self):
            super().__init__()
            self.count = 0

        async def execute(self, *, on_event=None, **kwargs) -> DriverResult:
            self.count += 1
            if on_event:
                async def worker(c):
                    await on_event({"kind": "assistant.text.delta", "entity_id": f"msg-{c}", "data": {"text": f"attempt-{c}-text"}})
                await worker(self.count)
            if self.count == 1:
                return DriverResult("RETRYABLE", "", "", "transient error", "network_err")
            return DriverResult("SUCCESS", "sess-retry", "successful second attempt", "", "")

    runtime1 = Runtime(cfg)
    runtime1.drivers = RetryDrivers()
    await runtime1.start()
    try:
        project = register_project(runtime1, str(root))
        sub = await runtime1.submit(project.id, "implement", "retry test")
        job = await runtime1.wait(sub.job_id, 5)
        assert job.state == "failed"
        assert job.result.failure_kind == "transient"
    finally:
        await runtime1.close()

    runtime2 = Runtime(cfg)
    try:
        events = _stream_events(runtime2.database, sub.job_id)
        deltas = [e for e in events if e["attempt"] == 1 and e["kind"] == "assistant.text.delta"]
        assert len(deltas) == 1
        assert deltas[0]["data"]["text"] == "attempt-1-text"
        reloaded_job = runtime2.database.job(sub.job_id)
        assert reloaded_job.result.failure_kind == "transient"
    finally:
        await runtime2.close()


@pytest.mark.asyncio
async def test_execution_persistence_failure_does_not_corrupt_stream_or_fail_job(tmp_path) -> None:
    """Persistence failure logs warning and records event without aborting terminal job state."""
    root = repository(tmp_path)
    cfg = config(tmp_path / "home")

    class FailingStreamDrivers(FakeDrivers):
        async def execute(self, *, on_event=None, **kwargs) -> DriverResult:
            if on_event:
                async def worker():
                    await on_event({"kind": "assistant.text.delta", "entity_id": "m1", "data": {"text": "first event"}})
                await worker()
            return DriverResult("SUCCESS", "sess-fail", "terminal result text", "", "")

    runtime = Runtime(cfg)
    runtime.drivers = FailingStreamDrivers()
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        orig_append = runtime.database.append_stream

        call_count = 0
        def fragile_append(job_id, events):
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                raise RuntimeError("simulated disk write failure")
            return orig_append(job_id, events)

        runtime.database.append_stream = fragile_append
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
        async def execute(self, *, on_event=None, **kwargs) -> DriverResult:
            if on_event:
                async def worker():
                    await on_event({"kind": "assistant.text.delta", "entity_id": "safe-msg", "data": {"text": "Safe verified response."}})
                    await on_event({"kind": "tool.started", "entity_id": "tool-1", "data": {"tool": "read"}})
                    await on_event({"kind": "tool.completed", "entity_id": "tool-1", "data": {"status": "completed"}})
                await worker()
            return DriverResult("SUCCESS", "sess-clean", "Safe verified response.", "", "")

    runtime = Runtime(cfg)
    runtime.drivers = DirtyNormalizedDrivers()
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        sub = await runtime.submit(project.id, "implement", f"run with {forbidden_secrets[0]}")
        job = await runtime.wait(sub.job_id, 5)
        assert job.state == "succeeded"
        assert job.result.text == "Safe verified response."

        stream_rows_raw = json.dumps(_stream_events(runtime.database, sub.job_id))
        for secret in forbidden_secrets:
            assert secret not in stream_rows_raw
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_agy_never_promotes_log_text_to_agent_messages_on_empty_stdout(tmp_path, monkeypatch) -> None:
    """Empty stdout with diagnostic/secret log text extracts session ID but never promotes log text."""
    from refract.backends import agy as agy_backend

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

    monkeypatch.setattr("refract.backends.shutil.which", lambda _: "/bin/agy")
    monkeypatch.setattr(agy_backend, "run_process", shell_fake_as_process(fake_run_shell))

    res = await agy_backend.execute(BackendParams(PROMPT="test", cd=tmp_path))
    assert res.SESSION_ID == session_id
    assert secret_diagnostic not in res.agent_messages
    assert "server internal dump" not in res.agent_messages
    assert res.agent_messages == ""
    assert res.outcome == "FATAL"
    assert res.error_class == "no_agent_messages"


def test_agy_execute_sync_post_submission_type_error_single_invocation(tmp_path, monkeypatch) -> None:
    """Post-submission TypeError in execute raises immediately with exactly one invocation."""
    from refract.backends import agy as agy_backend

    call_count = 0

    def fail_with_type_error(params, *, cancel=None, on_event=None, entity_state=None):
        nonlocal call_count
        call_count += 1
        raise TypeError("post-submission internal failure")

    monkeypatch.setattr(agy_backend, "execute", fail_with_type_error)

    params = BackendParams(PROMPT="test", cd=tmp_path)
    with pytest.raises(TypeError, match="post-submission internal failure"):
        execute_sync(agy_backend.execute, params)

    assert call_count == 1


@pytest.mark.asyncio
async def test_execution_all_provider_fixtures_persistence_and_authoritative_results(tmp_path, monkeypatch) -> None:
    """Exercise sanitized Claude, Codex, Pi, and Agy fixtures through execution flow."""
    from refract.backends.claude import execute as claude_execute
    from refract.backends.codex import execute as codex_execute
    from refract.backends.pi import execute as pi_execute_once
    from refract.backends.agy import execute as agy_execute_once

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
    previous_which = shutil.which
    monkeypatch.setattr(
        "shutil.which",
        lambda cmd, *args, **kwargs: "/usr/bin/mock"
        if cmd in ("claude", "codex", "pi", "agy")
        else previous_which(cmd, *args, **kwargs),
    )

    class RealAdapterDrivers(FakeDrivers):
        def __init__(self, backend_name):
            super().__init__()
            self.backend_name = backend_name

        async def execute(self, *, on_event=None, **kwargs) -> DriverResult:
            lines = dirty_streams[self.backend_name]
            if self.backend_name == "claude":
                stub_claude(monkeypatch, tmp_path, lines)
                res = await claude_execute(BackendParams(PROMPT="p", cd=tmp_path), on_event=on_event)
                return DriverResult(
                    outcome="SUCCESS" if res.outcome == "OK" else "FATAL",
                    session_id=res.SESSION_ID,
                    text=res.agent_messages,
                    error=res.error,
                    error_code=res.error_class,
                )

            if self.backend_name == "codex":
                monkeypatch.setattr("refract.backends.codex.run_process", shell_fake_as_process(lambda *args, **kw: (l for l in lines)))
                res = await codex_execute(BackendParams(PROMPT="p", cd=tmp_path), on_event=on_event)
            elif self.backend_name == "pi":
                monkeypatch.setattr("refract.backends.pi.run_process", fake_run_process(lines))
                res = await pi_execute_once(BackendParams(PROMPT="p", cd=tmp_path), on_event=on_event)
            else:
                monkeypatch.setattr("refract.backends.agy.run_process", fake_run_process(lines))
                res = await agy_execute_once(BackendParams(PROMPT="p", cd=tmp_path), on_event=on_event)
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
            project = register_project(runtime, str(root))
            sub = await runtime.submit(project.id, "implement", f"run {backend_name}")
            job = await runtime.wait(sub.job_id, 5)
            assert job.state == "succeeded"
            assert "verified clean." in job.result.text

            for s in secrets:
                assert s not in job.result.text

            rows = _stream_events(runtime.database, sub.job_id)
            rows_data_text = " ".join(json.dumps(r["data"]) for r in rows)

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
                data = r["data"]
                assert "activity" in data, f"{backend_name} missing activity in persisted tool.started"
                if backend_name == "codex":
                    assert data["activity"] == "command"
                else:
                    assert data["activity"] == "tool_call"

            tool_completed_rows = [r for r in rows if r["kind"] == "tool.completed"]
            for r in tool_completed_rows:
                data = r["data"]
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
        on_event=None,
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

        if emit_tool and on_event:
            await on_event({"kind": "tool.started", "tool_name": "bash"})

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
async def test_resumed_context_overflow_fails_without_in_run_recovery(tmp_path) -> None:
    root = repository(tmp_path)
    script = [
        (DriverResult("RETRYABLE", "old-sess-1", "", "context length exceeded", "context_overflow"), False),
        (DriverResult("SUCCESS", "should-not-run", "should not run", "", ""), False),
    ]
    drivers = ScriptedRecoveryDrivers(script)
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = drivers
    target = runtime.catalog.targets[0]
    tkey = target_execution_key(target)
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        runtime.database.store_session(
            project_id=project.id, session="feature", workflow="implement",
            target_key=tkey, backend_session_id="old-sess-1",
        )
        sub = await runtime.submit(project.id, "implement", "turn 2 prompt", session="feature")
        job = await runtime.wait(sub.job_id, 5)

        assert job.state == "failed"
        assert job.result.failure_kind == "context_overflow"
        assert [(c.session_id, c.prompt) for c in drivers.calls] == [("old-sess-1", "turn 2 prompt")]
        assert runtime.database.session(project.id, "feature", "implement", tkey) == "old-sess-1"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_resumed_failure_after_tool_activity_is_replay_blocked(tmp_path) -> None:
    root = repository(tmp_path)
    script = [
        (DriverResult("RETRYABLE", "old-sess-1", "", "context length exceeded", "context_overflow"), True),
        (DriverResult("SUCCESS", "should-not-run", "should not run", "", ""), False),
    ]
    drivers = ScriptedRecoveryDrivers(script)
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = drivers
    target = runtime.catalog.targets[0]
    tkey = target_execution_key(target)
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        runtime.database.store_session(
            project_id=project.id, session="feature", workflow="implement",
            target_key=tkey, backend_session_id="old-sess-1",
        )
        sub = await runtime.submit(project.id, "implement", "turn 2 prompt", session="feature")
        job = await runtime.wait(sub.job_id, 5)

        assert job.state == "failed"
        assert job.result.failure_kind == "replay_blocked"
        assert len(drivers.calls) == 1
        assert runtime.database.session(project.id, "feature", "implement", tkey) == "old-sess-1"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_sessionless_job_sends_prompt_without_history(tmp_path) -> None:
    root = repository(tmp_path)
    script = [
        (DriverResult("SUCCESS", "", "first answer", "", ""), False),
        (DriverResult("SUCCESS", "", "second answer", "", ""), False),
    ]
    drivers = ScriptedRecoveryDrivers(script)
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        for prompt in ("first prompt", "second prompt"):
            sub = await runtime.submit(project.id, "implement", prompt, session="feature")
            assert (await runtime.wait(sub.job_id, 5)).state == "succeeded"

        assert [(c.session_id, c.prompt) for c in drivers.calls] == [("", "first prompt"), ("", "second prompt")]
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
        project = register_project(runtime, str(root))
        runtime.database.store_session(
            project_id=project.id,
            session="feature",
            workflow="implement",
            target_key=tkey,
            backend_session_id="old-sess-1",
        )
        sub = await runtime.submit(project.id, "implement", "turn 2 prompt", session="feature")
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
async def test_terminal_desktop_notifications_succeeded_and_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repository(tmp_path)
    catalog = replace(config(tmp_path / "home"), notifications=NotificationsConfig(enabled=True))
    mock_send = MagicMock(return_value=True)
    monkeypatch.setattr("refract.runtime.send_job_notification", mock_send)

    runtime = Runtime(catalog)
    runtime.drivers = FakeDrivers()
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        submission = await runtime.submit(project.id, "implement", "inspect")
        job = await runtime.wait(submission.job_id, 10)
        assert job.state == "succeeded"
        assert mock_send.call_count == 1
        called_job, called_alias = mock_send.call_args[0]
        assert called_job.id == submission.job_id
        assert called_job.state == "succeeded"
        assert called_alias == Path(project.root).name

        mock_send.reset_mock()
        runtime.drivers = MutatingFailureDrivers()
        fail_sub = await runtime.submit(project.id, "implement", "fail")
        fail_job = await runtime.wait(fail_sub.job_id, 10)
        assert fail_job.state == "failed"
        assert mock_send.call_count == 1
        called_job2, called_alias2 = mock_send.call_args[0]
        assert called_job2.id == fail_sub.job_id
        assert called_job2.state == "failed"
        assert called_alias2 == Path(project.root).name
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_terminal_desktop_notifications_queued_cancel_and_startup_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repository(tmp_path)
    catalog = replace(config(tmp_path / "home"), notifications=NotificationsConfig(enabled=True))
    mock_send = MagicMock(return_value=True)
    monkeypatch.setattr("refract.runtime.send_job_notification", mock_send)

    drivers = BlockingDrivers()
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
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
        assert called_alias == Path(project.root).name

        await runtime.cancel(first.job_id)
        await runtime.wait(first.job_id, 10)
    finally:
        await runtime.close()

    mock_send.reset_mock()
    rec_home = tmp_path / "home_recovery"
    rec_catalog = replace(config(rec_home), notifications=NotificationsConfig(enabled=True))
    database = Database(rec_catalog.database_path)
    rec_proj = database.upsert_project(project_id="rec-proj", root=root.as_posix())
    plan = resolve_execution_plan(get_workflow("implement"), rec_catalog, "balanced")
    database.create_job(
        job_id="interrupted-job",
        project_id=rec_proj.id,
        workflow="implement",
        profile="balanced",
        prompt="interrupted",
        execution_plan_json=json.dumps(execution_plan_data(plan)),
        session="recovery",
    )
    database.start_job("interrupted-job")
    database.close()

    runtime_rec = Runtime(rec_catalog)
    await runtime_rec.start()
    try:
        interrupted_job = runtime_rec.database.job("interrupted-job")
        assert interrupted_job
        assert interrupted_job.state == "interrupted"
        assert mock_send.call_count == 1
        called_job3, called_alias3 = mock_send.call_args[0]
        assert called_job3.id == "interrupted-job"
        assert called_job3.state == "interrupted"
        assert called_alias3 == root.name
    finally:
        await runtime_rec.close()


@pytest.mark.asyncio
async def test_terminal_desktop_notifications_disabled_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repository(tmp_path)
    mock_send = MagicMock(return_value=True)
    monkeypatch.setattr("refract.runtime.send_job_notification", mock_send)

    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = FakeDrivers()
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
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
    monkeypatch.setattr("refract.runtime.send_job_notification", mock_send)

    runtime = Runtime(catalog)
    runtime.drivers = RetryDrivers()
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        submission = await runtime.submit(project.id, "implement", "retry")
        assert (await runtime.wait(submission.job_id, 10)).state == "failed"
        assert mock_send.call_count == 1

        retried = await runtime.retry(submission.job_id, target="primary")
        assert retried.job_id != submission.job_id
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

    async def notify(job_id: str) -> None:
        notifications.append(job_id)

    mock_send_false = MagicMock(return_value=False)
    monkeypatch.setattr("refract.runtime.send_job_notification", mock_send_false)

    runtime = Runtime(catalog, notifier=notify)
    runtime.drivers = FakeDrivers()
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        caplog.clear()
        sub1 = await runtime.submit(project.id, "implement", "inspect")
        job1 = await runtime.wait(sub1.job_id, 10)
        assert job1.state == "succeeded"
        assert notifications == [sub1.job_id] * 3
        failed_records = [
            r for r in caplog.records
            if getattr(r, "event", None) == "job.desktop_notification_failed"
        ]
        assert len(failed_records) == 1
        assert failed_records[0].job_id == sub1.job_id

        mock_send_raise = MagicMock(side_effect=RuntimeError("notification daemon down"))
        monkeypatch.setattr("refract.runtime.send_job_notification", mock_send_raise)
        notifications.clear()
        caplog.clear()

        sub2 = await runtime.submit(project.id, "implement", "inspect2")
        job2 = await runtime.wait(sub2.job_id, 10)
        assert job2.state == "succeeded"
        assert notifications == [sub2.job_id] * 3
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
    monkeypatch.setattr("refract.runtime.send_job_notification", mock_send)

    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = FakeDrivers()
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
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
    monkeypatch.setattr("refract.runtime.send_job_notification", mock_send)

    database = Database(catalog.database_path)
    project = database.upsert_project(project_id="proj-1", root=root.as_posix())
    plan = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")
    database.create_job(
        job_id="failed-1",
        project_id=project.id,
        workflow="implement",
        profile="balanced",
        prompt="fail",
        execution_plan_json=json.dumps(execution_plan_data(plan)),
        session="retry-ctx",
    )
    database.finish_job("failed-1", "failed")
    database.close()

    first_publish_entered = asyncio.Event()
    release_first_publish = asyncio.Event()
    paused_once = False

    async def pausing_notifier(job_id: str) -> None:
        nonlocal paused_once
        if not paused_once:
            paused_once = True
            first_publish_entered.set()
            await release_first_publish.wait()

    runtime = Runtime(catalog, notifier=pausing_notifier)
    try:
        publish_task = asyncio.create_task(
            runtime._notify_job("failed-1")
        )
        await first_publish_entered.wait()

        retry_result = await runtime.retry("failed-1", target="primary")
        assert retry_result.state == "queued"
        assert runtime.database.job("failed-1").state == "failed"

        release_first_publish.set()
        await publish_task

        assert mock_send.call_count == 1
        called_job, called_alias = mock_send.call_args[0]
        assert called_job.id == "failed-1"
        assert called_job.state == "failed"
        assert called_alias == root.name
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_terminal_desktop_notifications_snapshot_lookup_failure_warning_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    catalog = replace(config(tmp_path / "home"), notifications=NotificationsConfig(enabled=True))
    notifications: list[str] = []

    async def notify(job_id: str) -> None:
        notifications.append(job_id)

    runtime = Runtime(catalog, notifier=notify)
    try:
        lookup_exc = RuntimeError("database locked")
        monkeypatch.setattr(
            runtime.database,
            "job",
            MagicMock(side_effect=lookup_exc),
        )

        caplog.clear()
        await runtime._notify_job("job-snapshot-err")

        assert notifications == ["job-snapshot-err"]
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

    async def notify(job_id: str) -> None:
        notifications.append(job_id)

    runtime = Runtime(catalog, notifier=notify)
    try:
        mock_job = MagicMock(side_effect=AssertionError("database.job should not be called when disabled"))
        monkeypatch.setattr(runtime.database, "job", mock_job)

        await runtime._notify_job("job-disabled")
        assert notifications == ["job-disabled"]
        mock_job.assert_not_called()
    finally:
        await runtime.close()


def test_configuration_failure_metadata_retains_selected_capacity():
    target = TargetConfig(id="bad-environment", backend="codex", context_window=2048)
    result = TargetExecutor._configuration_failure(
        target, "target-key", "invalid environment", [],
    )
    tokens = result.outcome["tokens"]
    assert tokens["context_window"] == 2048


@pytest.mark.asyncio
async def test_telemetry_updated_routes_through_execution_before_stream_recording(tmp_path: Path) -> None:
    root = repository(tmp_path)
    catalog = config(tmp_path / "home")

    class TelemetryDriver(FakeDrivers):
        async def execute(self, **kwargs):
            on_event = kwargs.get("on_event")
            if on_event:
                await on_event({
                    "kind": "telemetry.updated",
                    "data": {
                        "context_used": 1200,
                        "context_window": 8000,
                        "input": 100,
                        "output": 40,
                    },
                })
            return DriverResult("SUCCESS", "", "done", "", "")

    runtime = Runtime(catalog)
    runtime.drivers = TelemetryDriver()
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        submission = await runtime.submit(project.id, "implement", "test")
        job = await runtime.wait(submission.job_id, 5)
        assert job.state == "succeeded"
        telemetry = job.result.tokens
        assert telemetry is not None
        assert telemetry["context_used"] == 1200
        assert telemetry["context_window"] == 8000
        assert telemetry["input"] == 100
        assert telemetry["output"] == 40
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_context_invalidation_persists_nulls_without_clearing_consumption(tmp_path: Path) -> None:
    root = repository(tmp_path)
    runtime = Runtime(config(tmp_path / "home"))

    class InvalidateContextDriver(FakeDrivers):
        async def execute(self, **kwargs):
            emit = kwargs.get("on_event")
            await emit({"kind": "telemetry.updated", "data": {
                "context_used": 1060, "context_window": 64000, "input": 100, "output": 20,
            }})
            await emit({"kind": "telemetry.updated", "data": {
                "context_used": None, "context_window": 64000, "input": 100, "output": 20,
            }})
            return DriverResult("SUCCESS", "", "done", "", "")

    runtime.drivers = InvalidateContextDriver()
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        submission = await runtime.submit(project.id, "implement", "test")
        job = await runtime.wait(submission.job_id, 5)
        telemetry = job.result.tokens
        assert telemetry["context_used"] == 120
        assert telemetry["context_window"] == 64000
        assert telemetry["input"] == 100
        assert telemetry["output"] == 20
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_codex_budget_exhaustion_keeps_context_unknown_through_persistence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from refract.backends.codex import CodexRun

    root = repository(tmp_path)
    codex_home = tmp_path / "codex-home"
    sessions = codex_home / "sessions"
    sessions.mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    sid = "00000000-0000-0000-0000-aaaaaaaaaaaa"

    class RolloutDriver(FakeDrivers):
        async def execute(self, *, cwd, **kwargs):
            rollout = sessions / f"rollout_{sid}.jsonl"
            header = json.dumps({"type": "session_meta", "payload": {"id": sid, "cwd": str(cwd)}})
            usage = {"input_tokens": 100, "cached_input_tokens": 0, "output_tokens": 10, "reasoning_output_tokens": 0, "total_tokens": 110}
            token_count = json.dumps({"type": "event_msg", "payload": {"type": "token_count", "info": {
                "total_token_usage": usage, "last_token_usage": usage, "model_context_window": 64000,
            }}})
            rollout.write_text(header + "\n" + token_count + "\n" + (" " * 5000) + "\n")
            run = CodexRun(BackendParams(PROMPT="test", cd=cwd), cwd, tmp_path / "last-message.txt", kwargs.get("on_event"))
            run.collector.max_bytes_per_poll = 4096
            run.collector.max_total_bytes = 4096
            await run.feed(json.dumps({"type": "thread.started", "thread_id": sid}))
            await run.feed(json.dumps({"type": "turn.completed", "usage": {
                "input_tokens": 5000, "output_tokens": 700, "reasoning_output_tokens": 100,
            }}))
            return DriverResult("SUCCESS", sid, "done", "", "")

    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = RolloutDriver()
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        submission = await runtime.submit(project.id, "implement", "test")
        job = await runtime.wait(submission.job_id, 5)
        telemetry = job.result.tokens
        assert telemetry["context_used"] == 5700
        assert telemetry["context_window"] is None
        assert telemetry["input"] == 5000
        assert telemetry["output"] == 700
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_telemetry_survives_transcript_quota_exhaustion_in_execution(tmp_path: Path) -> None:
    root = repository(tmp_path)
    catalog = config(tmp_path / "home")

    class QuotaExhaustionDriver(FakeDrivers):
        async def execute(self, **kwargs):
            on_event = kwargs.get("on_event")
            if on_event:
                # Fill quota with lots of text deltas
                large_chunk = "x" * 20000
                for i in range(100):
                    await on_event({
                        "kind": "assistant.text.delta",
                        "data": {"text": large_chunk},
                        "entity_id": f"msg-{i}",
                    })
                # Now emit telemetry after stream truncation
                await on_event({
                    "kind": "telemetry.updated",
                    "data": {
                        "context_used": 4000,
                        "context_window": 8000,
                        "input": 250,
                        "output": 80,
                    },
                })
            return DriverResult("SUCCESS", "", "done", "", "")

    runtime = Runtime(catalog)
    runtime.drivers = QuotaExhaustionDriver()
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        submission = await runtime.submit(project.id, "implement", "test")
        job = await runtime.wait(submission.job_id, 5)
        assert job.state == "succeeded"
        telemetry = job.result.tokens
        assert telemetry is not None
        assert telemetry["context_used"] == 4000
        assert telemetry["input"] == 250
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_cancellation_and_failure_retain_partial_telemetry(tmp_path: Path) -> None:
    root = repository(tmp_path)
    catalog = config(tmp_path / "home")

    class FailingDriverWithTelemetry(FakeDrivers):
        async def execute(self, **kwargs):
            on_event = kwargs.get("on_event")
            if on_event:
                await on_event({
                    "kind": "telemetry.updated",
                    "data": {
                        "context_used": 3000,
                        "context_window": 8000,
                        "input": 180,
                        "output": 50,
                    },
                })
            return DriverResult("TARGET_FATAL", "", "", "target crashed", "crashed")

    runtime = Runtime(catalog)
    runtime.drivers = FailingDriverWithTelemetry()
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        submission = await runtime.submit(project.id, "implement", "test")
        job = await runtime.wait(submission.job_id, 5)
        assert job.state == "failed"
        telemetry = job.result.tokens
        assert telemetry is not None
        assert telemetry["context_used"] == 3000
        assert telemetry["input"] == 180
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_telemetry_updated_dispatches_cumulative_totals_before_cache_fields(tmp_path: Path) -> None:
    root = repository(tmp_path)
    catalog = config(tmp_path / "home")

    class CumulativeDriver(FakeDrivers):
        async def execute(self, **kwargs):
            on_event = kwargs.get("on_event")
            if on_event:
                await on_event({
                    "kind": "telemetry.updated",
                    "data": {
                        "input": 500,
                        "output": 200,
                        "cache_read": 50,
                    },
                })
            return DriverResult("SUCCESS", "", "done", "", "")

    runtime = Runtime(catalog)
    runtime.drivers = CumulativeDriver()
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        submission = await runtime.submit(project.id, "implement", "test")
        job = await runtime.wait(submission.job_id, 5)
        assert job.state == "succeeded"
        telemetry = job.result.tokens
        assert telemetry is not None
        assert telemetry["input"] == 500
        assert telemetry["output"] == 200
        assert telemetry["cache_read"] == 50
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_resumed_session_history_is_not_counted_as_subsequent_job_consumption(tmp_path: Path) -> None:
    root = repository(tmp_path)
    catalog = config(tmp_path / "home")

    class ResumedSessionDriver(FakeDrivers):
        def __init__(self):
            super().__init__()
            self.calls = 0

        async def execute(self, **kwargs):
            self.calls += 1
            on_event = kwargs.get("on_event")
            if self.calls == 1:
                if on_event:
                    await on_event({
                        "kind": "telemetry.updated",
                        "data": {
                            "input": 500,
                            "output": 200,
                        },
                    })
                return DriverResult("SUCCESS", "shared-session-123", "job 1 ok", "", "")
            else:
                if on_event:
                    await on_event({
                        "kind": "telemetry.updated",
                        "data": {
                            "input": 150,
                            "output": 60,
                        },
                    })
                return DriverResult("SUCCESS", "shared-session-123", "job 2 ok", "", "")

    runtime = Runtime(catalog)
    runtime.drivers = ResumedSessionDriver()
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        sub1 = await runtime.submit(project.id, "implement", "turn 1", session="feature")
        job1 = await runtime.wait(sub1.job_id, 5)
        assert job1.state == "succeeded"
        tel1 = job1.result.tokens
        assert tel1 is not None
        assert tel1["input"] == 500
        assert tel1["output"] == 200

        sub2 = await runtime.submit(project.id, "implement", "turn 2", session="feature")
        job2 = await runtime.wait(sub2.job_id, 5)
        assert job2.state == "succeeded"
        tel2 = job2.result.tokens
        assert tel2 is not None
        assert tel2["input"] == 150
        assert tel2["output"] == 60
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_telemetry_streaming_enabled_does_not_double_count_returned_telemetry(tmp_path: Path) -> None:
    root = repository(tmp_path)
    base = config(tmp_path / "home")
    target = TargetConfig(id="t_stream", backend="codex")
    catalog = replace(
        base,
        targets=(target,),
        profiles={"balanced": {"implement": TargetSelection((target.id,)), "review": TargetSelection((target.id,)), "consult": TargetSelection((target.id,))}},
    )

    backend_tokens = {
        "context_used": 125,
        "context_window": 128000,
        "input": 100,
        "output": 25,
        "cache_read": 10,
        "cache_write": None,
    }

    class StreamingDriver(FakeDrivers):
        def supports_structured_streaming(self, target: Any) -> bool:
            return True

        async def execute(self, *, on_event: Any = None, **kwargs: Any) -> DriverResult:
            if on_event:
                await on_event({
                    "kind": "telemetry.updated",
                    "data": {"input": 100, "output": 25, "cache_read": 10},
                })
                await on_event({
                    "kind": "telemetry.updated",
                    "data": {"context_used": 125, "context_window": 128000, "input": 100, "output": 25, "cache_read": 10},
                })
            return DriverResult("SUCCESS", "sess-1", "done", "", "", tokens=backend_tokens)

    runtime = Runtime(catalog)
    runtime.drivers = StreamingDriver()
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        sub = await runtime.submit(project.id, "implement", "test streaming double count")
        job = await runtime.wait(sub.job_id, 10)
        assert job.state == "succeeded"
        tel = job.result.tokens
        assert tel["input"] == 100
        assert tel["output"] == 25
        assert tel["context_used"] == 125
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_telemetry_fallback_preserves_cumulative_totals_across_retries(tmp_path: Path) -> None:
    root = repository(tmp_path)
    base = config(tmp_path / "home")
    policy = RetryPolicy(1, ("rate_limit",), ())
    target = TargetConfig(id="t_retry", backend="codex", retry=policy)
    catalog = replace(
        base,
        targets=(target,),
        profiles={"balanced": {"implement": TargetSelection(("t_retry",)), "review": TargetSelection(("t_retry",)), "consult": TargetSelection(("t_retry",))}},
    )

    attempt_1_tokens = {
        "context_used": 120,
        "context_window": 128000,
        "input": 100,
        "output": 20,
        "cache_read": 5,
        "cache_write": None,
    }
    attempt_2_tokens = {
        "context_used": 180,
        "context_window": 128000,
        "input": 150,
        "output": 30,
        "cache_read": 10,
        "cache_write": None,
    }

    class RetryFallbackDrivers(StreamingSequenceDrivers):
        def __init__(self):
            super().__init__([
                DriverResult("RETRYABLE", "", "", "rate limit", "rate_limit", tokens=attempt_1_tokens),
                DriverResult("SUCCESS", "sess-ok", "done", "", "", tokens=attempt_2_tokens),
            ])

    runtime = Runtime(catalog)
    runtime.drivers = RetryFallbackDrivers()
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        sub = await runtime.submit(project.id, "implement", "test retry fallback")
        job = await runtime.wait(sub.job_id, 10)
        assert job.state == "succeeded"
        tel = job.result.tokens
        assert tel["input"] == 250
        assert tel["output"] == 50
        assert tel["cache_read"] == 15
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_telemetry_malformed_fallback_does_not_change_outcome(tmp_path: Path) -> None:
    root = repository(tmp_path)
    base = config(tmp_path / "home")
    target = TargetConfig(id="t_malformed", backend="codex")
    catalog = replace(
        base,
        targets=(target,),
        profiles={"balanced": {"implement": TargetSelection((target.id,)), "review": TargetSelection((target.id,)), "consult": TargetSelection((target.id,))}},
    )

    class MalformedDriver(FakeDrivers):
        def supports_structured_streaming(self, target: Any) -> bool:
            return False

        async def execute(self, **kwargs: Any) -> DriverResult:
            return DriverResult("SUCCESS", "sess-ok", "done", "", "", tokens={"corrupt": "data", "input": "invalid"})

    runtime = Runtime(catalog)
    runtime.drivers = MalformedDriver()
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        sub = await runtime.submit(project.id, "implement", "test malformed telemetry")
        job = await runtime.wait(sub.job_id, 10)
        assert job.state == "succeeded"
        tel = job.result.tokens
        assert tel["input"] is None
    finally:
        await runtime.close()


class StreamingSequenceDrivers(FakeDrivers):
    def __init__(self, sequence):
        super().__init__()
        self.sequence = list(sequence)
        self.invocations = []

    def supports_structured_streaming(self, target):
        return True

    async def execute(self, *, target, **kwargs):
        self.invocations.append(target.id)
        if self.sequence:
            item = self.sequence.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        return DriverResult("SUCCESS", "ok", "", "", "")




@pytest.mark.asyncio
async def test_retry_policy_matching_code_or_pattern_and_empty_rules(tmp_path: Path) -> None:
    root = repository(tmp_path)
    base = config(tmp_path / "home")

    # Policy matches rate_limit code OR overloaded pattern
    policy = RetryPolicy(2, ("rate_limit",), ("overloaded",))
    catalog = replace(
        base,
        targets=(
            TargetConfig(id="t_match", backend="codex", retry=policy),
            TargetConfig(id="t_all", backend="codex", retry=RetryPolicy(1, (), ())),
        ),
        profiles={
            "p_match": {"implement": TargetSelection(("t_match",)), "review": TargetSelection(("t_match",)), "consult": TargetSelection(("t_match",))},
            "p_all": {"implement": TargetSelection(("t_all",)), "review": TargetSelection(("t_all",)), "consult": TargetSelection(("t_all",))},
        },
    )

    # 1. Exact code match retries and succeeds
    drivers = StreamingSequenceDrivers([
        DriverResult("RETRYABLE", "", "", "something went wrong", "rate_limit"),
        DriverResult("SUCCESS", "success on retry", "", "", ""),
    ])
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        sub = await runtime.submit(project.id, "implement", "test code match", profile="p_match")
        job = await runtime.wait(sub.job_id, 10)
        assert job.state == "succeeded"
        assert len(drivers.invocations) == 2
    finally:
        await runtime.close()

    # 2. Case-insensitive pattern match retries and succeeds
    drivers2 = StreamingSequenceDrivers([
        DriverResult("RETRYABLE", "", "", "Server is OverLoaded right now", "other_code"),
        DriverResult("SUCCESS", "success on retry 2", "", "", ""),
    ])
    runtime2 = Runtime(catalog)
    runtime2.drivers = drivers2
    await runtime2.start()
    try:
        project2 = register_project(runtime2, str(root))
        sub2 = await runtime2.submit(project2.id, "implement", "test pattern match", profile="p_match")
        job2 = await runtime2.wait(sub2.job_id, 10)
        assert job2.state == "succeeded"
        assert len(drivers2.invocations) == 2
    finally:
        await runtime2.close()

    # 3. Both lists empty allows all eligible transient failures
    drivers3 = StreamingSequenceDrivers([
        DriverResult("RETRYABLE", "", "", "unspecified temporary glitch", "arbitrary_transient"),
        DriverResult("SUCCESS", "catchall success", "", "", ""),
    ])
    runtime3 = Runtime(catalog)
    runtime3.drivers = drivers3
    await runtime3.start()
    try:
        project3 = register_project(runtime3, str(root))
        sub3 = await runtime3.submit(project3.id, "implement", "test catchall", profile="p_all")
        job3 = await runtime3.wait(sub3.job_id, 10)
        assert job3.state == "succeeded"
        assert len(drivers3.invocations) == 2
    finally:
        await runtime3.close()

    # 4. Unmatched error code and pattern invokes once without retrying
    drivers4 = StreamingSequenceDrivers([
        DriverResult("RETRYABLE", "", "", "unmatched message", "unmatched_code"),
        DriverResult("SUCCESS", "should not run", "", "", ""),
    ])
    runtime4 = Runtime(catalog)
    runtime4.drivers = drivers4
    await runtime4.start()
    try:
        project4 = register_project(runtime4, str(root))
        sub4 = await runtime4.submit(project4.id, "implement", "test unmatched", profile="p_match")
        job4 = await runtime4.wait(sub4.job_id, 10)
        assert job4.state == "failed"
        assert len(drivers4.invocations) == 1
    finally:
        await runtime4.close()


@pytest.mark.asyncio
async def test_retry_policy_bounded_attempts_and_budget_exhaustion(tmp_path: Path) -> None:
    root = repository(tmp_path)
    base = config(tmp_path / "home")

    policy = RetryPolicy(2, ("rate_limit",), ())
    catalog = replace(
        base,
        targets=(TargetConfig(id="primary", backend="codex", retry=policy),),
        profiles={"balanced": {"implement": TargetSelection(("primary",)), "review": TargetSelection(("primary",)), "consult": TargetSelection(("primary",))}},
    )

    # retryAttempt = 2 permits at most 3 attempts (1 initial + 2 retries)
    drivers = StreamingSequenceDrivers([
        DriverResult("RETRYABLE", "", "", "transient 1", "rate_limit"),
        DriverResult("RETRYABLE", "", "", "transient 2", "rate_limit"),
        DriverResult("RETRYABLE", "", "", "transient 3 final", "rate_limit"),
        DriverResult("SUCCESS", "should not reach attempt 4", "", "", ""),
    ])
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        sub = await runtime.submit(project.id, "implement", "exhaustion test")
        job = await runtime.wait(sub.job_id, 10)
        assert job.state == "failed"
        assert len(drivers.invocations) == 3
        assert job.result.failure_kind == "transient"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_retry_policy_exclusions_fatal_and_cancellation(tmp_path: Path) -> None:
    root = repository(tmp_path)
    base = config(tmp_path / "home")

    policy = RetryPolicy(2, ("rate_limit",), ())
    catalog = replace(
        base,
        targets=(TargetConfig(id="primary", backend="codex", retry=policy),),
        profiles={"balanced": {"implement": TargetSelection(("primary",)), "review": TargetSelection(("primary",)), "consult": TargetSelection(("primary",))}},
    )

    # REQUEST_FATAL does not retry even if error_code matches
    drivers = StreamingSequenceDrivers([
        DriverResult("REQUEST_FATAL", "", "", "bad request", "rate_limit"),
        DriverResult("SUCCESS", "should not run", "", "", ""),
    ])
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        sub = await runtime.submit(project.id, "implement", "fatal test")
        job = await runtime.wait(sub.job_id, 10)
        assert job.state == "failed"
        assert len(drivers.invocations) == 1
    finally:
        await runtime.close()

    # TARGET_FATAL does not retry even if error_code matches
    drivers2 = StreamingSequenceDrivers([
        DriverResult("TARGET_FATAL", "", "", "backend dead", "rate_limit"),
        DriverResult("SUCCESS", "should not run", "", "", ""),
    ])
    runtime2 = Runtime(catalog)
    runtime2.drivers = drivers2
    await runtime2.start()
    try:
        project2 = register_project(runtime2, str(root))
        sub2 = await runtime2.submit(project2.id, "implement", "target fatal test")
        job2 = await runtime2.wait(sub2.job_id, 10)
        assert job2.state == "failed"
        assert len(drivers2.invocations) == 1
    finally:
        await runtime2.close()




@pytest.mark.asyncio
async def test_retry_probe_and_capacity_held_and_final_only_health(tmp_path: Path) -> None:
    root = repository(tmp_path)
    base = config(tmp_path / "home")

    policy = RetryPolicy(1, ("rate_limit",), ())
    catalog = replace(
        base,
        breaker_failure_threshold=1,
        targets=(TargetConfig(id="primary", backend="codex", retry=policy),),
        profiles={"balanced": {"implement": TargetSelection(("primary",)), "review": TargetSelection(("primary",)), "consult": TargetSelection(("primary",))}},
    )

    probe_during_retry = []
    active_during_retry = []

    class ProbeTrackingDrivers(FakeDrivers):
        def __init__(self, target_key):
            super().__init__()
            self.target_key = target_key
            self.attempt = 0

        def supports_structured_streaming(self, target):
            return True

        async def execute(self, *, target, **kwargs):
            self.attempt += 1
            health = runtime.database.target_health(self.target_key)
            probe_during_retry.append((self.attempt, health.get("probe_job_id")))
            active_during_retry.append((self.attempt, runtime.target_executor._target_active.get(target.id)))
            if self.attempt == 1:
                return DriverResult("RETRYABLE", "", "", "transient error", "rate_limit")
            return DriverResult("SUCCESS", "recovered", "", "", "")

    runtime = Runtime(catalog)
    target = catalog.targets[0]
    target_key = target_execution_key(target)
    drivers = ProbeTrackingDrivers(target_key)
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = register_project(runtime, str(root))

        with runtime.database._connection:
            runtime.database._connection.execute(
                "INSERT INTO target_health(target_id, consecutive_failures, circuit_open_until, cooldown_s, probe_job_id) VALUES (?, 1, '2000-01-01T00:00:00+00:00', 60, '')",
                (target_key,),
            )

        sub = await runtime.submit(project.id, "implement", "probe held test")
        job = await runtime.wait(sub.job_id, 10)
        assert job.state == "succeeded"

        # Probe was held continuously by job across both attempt 1 and attempt 2
        assert len(probe_during_retry) == 2
        assert probe_during_retry[0] == (1, sub.job_id)
        assert probe_during_retry[1] == (2, sub.job_id)

        # Capacity permit was held continuously across attempts
        assert active_during_retry[0] == (1, 1)
        assert active_during_retry[1] == (2, 1)

        # Final target health: success reset circuit and cleared probe
        final_health = runtime.database.target_health(target_key)
        assert final_health["probe_job_id"] == ""
        assert final_health["consecutive_failures"] == 0
        assert final_health["circuit_open_until"] == ""
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_retry_telemetry_rollover_cumulative_consumption(tmp_path: Path) -> None:
    root = repository(tmp_path)
    base = config(tmp_path / "home")

    policy = RetryPolicy(2, ("rate_limit",), ())
    catalog = replace(
        base,
        targets=(TargetConfig(id="primary", backend="codex", retry=policy),),
        profiles={"balanced": {"implement": TargetSelection(("primary",)), "review": TargetSelection(("primary",)), "consult": TargetSelection(("primary",))}},
    )

    class TelemetryStreamingDrivers(FakeDrivers):
        def __init__(self):
            super().__init__()
            self.attempt = 0

        def supports_structured_streaming(self, target):
            return True

        async def execute(self, *, target, on_event=None, **kwargs):
            self.attempt += 1
            if on_event:
                if self.attempt == 1:
                    await on_event({
                        "kind": "telemetry.updated",
                        "data": {"input": 100, "output": 20},
                    })
                elif self.attempt == 2:
                    await on_event({
                        "kind": "telemetry.updated",
                        "data": {"input": 150, "output": 30},
                    })
            if self.attempt == 1:
                return DriverResult("RETRYABLE", "", "", "rate limit", "rate_limit")
            return DriverResult("SUCCESS", "done", "", "", "")

    drivers = TelemetryStreamingDrivers()
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        sub = await runtime.submit(project.id, "implement", "telemetry rollover test")
        job = await runtime.wait(sub.job_id, 10)
        assert job.state == "succeeded"

        telemetry = job.result.tokens
        assert telemetry is not None
        assert telemetry["input"] == 250
        assert telemetry["output"] == 50
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_retry_ten_attempts_budget_bound(tmp_path: Path) -> None:
    root = repository(tmp_path)
    base = config(tmp_path / "home")

    policy = RetryPolicy(9, ("rate_limit",), ())
    catalog = replace(
        base,
        targets=(TargetConfig(id="primary", backend="codex", retry=policy),),
        profiles={"balanced": {"implement": TargetSelection(("primary",)), "review": TargetSelection(("primary",)), "consult": TargetSelection(("primary",))}},
    )

    drivers = StreamingSequenceDrivers([
        DriverResult("RETRYABLE", "", "", "transient error", "rate_limit")
        for _ in range(12)
    ])
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        sub = await runtime.submit(project.id, "implement", "max budget test")
        job = await runtime.wait(sub.job_id, 15)
        assert job.state == "failed"
        assert len(drivers.invocations) == 10
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_retry_tool_activity_after_truncation_blocks_replay(tmp_path: Path) -> None:
    root = repository(tmp_path)
    base = config(tmp_path / "home")

    policy = RetryPolicy(2, ("rate_limit",), ())
    catalog = replace(
        base,
        targets=(TargetConfig(id="primary", backend="codex", retry=policy),),
        profiles={"balanced": {"implement": TargetSelection(("primary",)), "review": TargetSelection(("primary",)), "consult": TargetSelection(("primary",))}},
    )

    class TruncatedToolDriver(FakeDrivers):
        def __init__(self):
            super().__init__()
            self.invocations = []

        def supports_structured_streaming(self, target):
            return True

        async def execute(self, *, target, on_event=None, **kwargs):
            self.invocations.append(target.id)
            if on_event:
                await on_event({"kind": "stream.truncated", "data": {"reason": "quota"}})
                await on_event({"kind": "tool.started", "data": {"tool": "bash"}})
            return DriverResult("RETRYABLE", "", "", "transient error", "rate_limit")

    drivers = TruncatedToolDriver()
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        sub = await runtime.submit(project.id, "implement", "tool truncation test")
        job = await runtime.wait(sub.job_id, 10)
        assert job.state == "failed"
        assert len(drivers.invocations) == 1
        assert job.result.failure_kind == "replay_blocked"
    finally:
        await runtime.close()




@pytest.mark.asyncio
async def test_retry_cancellation_before_retry_invocation_releases_resources(tmp_path: Path) -> None:
    root = repository(tmp_path)
    base = config(tmp_path / "home")

    policy = RetryPolicy(2, ("rate_limit",), ())
    catalog = replace(
        base,
        targets=(TargetConfig(id="primary", backend="codex", retry=policy),),
        profiles={"balanced": {"implement": TargetSelection(("primary",)), "review": TargetSelection(("primary",)), "consult": TargetSelection(("primary",))}},
    )

    invocations = []
    job_holder = []

    class CancellingDriver(FakeDrivers):
        def supports_structured_streaming(self, target):
            return True

        async def execute(self, *, target, **kwargs):
            invocations.append(target.id)
            if job_holder:
                await runtime.cancel(job_holder[0])
            return DriverResult("RETRYABLE", "", "", "transient error", "rate_limit")

    drivers = CancellingDriver()
    runtime = Runtime(catalog)
    target = catalog.targets[0]
    target_key = target_execution_key(target)
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        with runtime.database._connection:
            runtime.database._connection.execute(
                "INSERT INTO target_health(target_id, consecutive_failures, circuit_open_until, cooldown_s, probe_job_id) VALUES (?, 1, '2000-01-01T00:00:00+00:00', 60, '')",
                (target_key,),
            )
        sub = await runtime.submit(project.id, "implement", "cancel prompt")
        job_holder.append(sub.job_id)
        job = await runtime.wait(sub.job_id, 10)
        assert job.state == "cancelled"
        assert len(invocations) == 1
        assert runtime.database.target_health(target_key)["probe_job_id"] == ""
        assert not runtime.target_executor._target_active
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_retry_injected_cleanup_failures_releases_resources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = repository(tmp_path)
    base = config(tmp_path / "home")

    policy = RetryPolicy(1, ("rate_limit",), ())
    catalog = replace(
        base,
        targets=(TargetConfig(id="primary", backend="codex", retry=policy),),
        profiles={"balanced": {"implement": TargetSelection(("primary",)), "review": TargetSelection(("primary",)), "consult": TargetSelection(("primary",))}},
    )

    runtime = Runtime(catalog)
    target = catalog.targets[0]
    target_key = target_execution_key(target)
    drivers = StreamingSequenceDrivers([DriverResult("SUCCESS", "ok", "", "", "")])
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        plan = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")

        # 1. Injected failure in prepare_session releases probe
        with runtime.database._connection:
            runtime.database._connection.execute(
                "INSERT INTO target_health(target_id, consecutive_failures, circuit_open_until, cooldown_s, probe_job_id) VALUES (?, 1, '2000-01-01T00:00:00+00:00', 60, '')",
                (target_key,),
            )
        async def failing_prepare(*_args, **_kwargs):
            raise RuntimeError("prepare session injected error")
        monkeypatch.setattr(runtime.target_executor, "_prepare_session", failing_prepare)
        cancel_event = CancelEvent()
        with pytest.raises(RuntimeError, match="prepare session injected error"):
            await runtime.target_executor.execute(
                job_id="fail-prep-job", project=project, workflow="implement", session="prep",
                plan=plan, prompt="p", cwd=root, cancel_event=cancel_event,
            )
        assert runtime.database.target_health(target_key)["probe_job_id"] == ""
        assert not runtime.target_executor._target_active
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_retry_ask_token_issue_failure_propagates_without_driver_call(tmp_path: Path) -> None:
    root = repository(tmp_path)
    catalog = config(tmp_path / "home")
    runtime = Runtime(catalog)
    drivers = FakeDrivers()
    runtime.drivers = drivers
    class BrokenAskRegistry:
        def issue_token(self, *_args, **_kwargs):
            raise RuntimeError("issue token fault")
        def revoke_token(self, *_args, **_kwargs):
            pass
    runtime.target_executor.ask_registry = BrokenAskRegistry()
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        plan = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")
        runtime.database.create_job(job_id="ask-issue-fault", project_id=project.id, workflow="implement", profile="balanced", prompt="p", execution_plan_json="{}", session="ctx")
        cancel_event = CancelEvent()
        with pytest.raises(RuntimeError, match="issue token fault"):
            await runtime.target_executor.execute(
                job_id="ask-issue-fault", project=project, workflow="implement", session="ctx",
                plan=plan, prompt="p", cwd=root, cancel_event=cancel_event,
            )
        assert not drivers.sessions
        assert not runtime.target_executor._target_active
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_retry_driver_exception_does_not_reuse_previous_result(tmp_path: Path) -> None:
    root = repository(tmp_path)
    base = config(tmp_path / "home")
    catalog = replace(base, 
        targets=(TargetConfig(id="primary", backend="codex", retry=RetryPolicy(1, (), ())),),
        profiles={"balanced": {"implement": TargetSelection(("primary",)), "review": TargetSelection(("primary",)), "consult": TargetSelection(("primary",))}})
    class ResultThenException(StreamingSequenceDrivers):
        def __init__(self):
            super().__init__([DriverResult("RETRYABLE", "", "", "transient", "rate_limit")])
            self.calls = 0
        async def execute(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return await super().execute(**kwargs)
            raise RuntimeError("second invocation fault")
    runtime = Runtime(catalog)
    drivers = ResultThenException()
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        sub = await runtime.submit(project.id, "implement", "p")
        job = await runtime.wait(sub.job_id, 10)
        events = _stream_events(runtime.database, sub.job_id)
        finishes = [event["data"] for event in events if event["kind"] == "attempt.finished"]
        assert job.state == "failed"
        assert len(finishes) == 2
        assert finishes[0]["error_code"] == "rate_limit"
        assert finishes[1]["error_code"] == "execution_error"
    finally:
        await runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["revoke", "health", "storage"])
async def test_retry_finalization_faults_release_target_resources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str) -> None:
    root = repository(tmp_path)
    catalog = config(tmp_path / "home")
    runtime = Runtime(catalog)
    runtime.drivers = StreamingSequenceDrivers([DriverResult("SUCCESS", "session", "done", "", "")])
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        plan = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")
        job_id = f"finalize-{fault}"
        runtime.database.create_job(job_id=job_id, project_id=project.id, workflow="implement", profile="balanced", prompt="p", execution_plan_json="{}", session="ctx")
        if fault == "revoke":
            class RevokeFault:
                def issue_token(self, *_args, **_kwargs): return "token"
                def revoke_token(self, *_args, **_kwargs): raise RuntimeError("revoke fault")
            runtime.target_executor.ask_registry = RevokeFault()
        elif fault == "health":
            def fail_health(*_args, **_kwargs): raise RuntimeError("health fault")
            monkeypatch.setattr(runtime.database, "record_target_success", fail_health)
        else:
            def fail_storage(*_args, **_kwargs): raise RuntimeError("storage fault")
            monkeypatch.setattr(runtime.database, "store_session", fail_storage)
        cancel_event = CancelEvent()
        with pytest.raises(RuntimeError, match=f"{fault} fault"):
            await runtime.target_executor.execute(
                job_id=job_id, project=project, workflow="implement", session="ctx", plan=plan,
                prompt="p", cwd=root, cancel_event=cancel_event,
            )
        assert not runtime.target_executor._target_active
        assert runtime.target_executor._target_users.get("primary", 0) == 0
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_retry_cancellation_during_attempt_setup_prevents_driver_invocation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = repository(tmp_path)
    base = config(tmp_path / "home")
    catalog = replace(base, 
        targets=(TargetConfig(id="primary", backend="codex", retry=RetryPolicy(1, (), ())),),
        profiles={"balanced": {"implement": TargetSelection(("primary",)), "review": TargetSelection(("primary",)), "consult": TargetSelection(("primary",))}})
    runtime = Runtime(catalog)
    drivers = ScriptedRecoveryDrivers([
        (DriverResult("RETRYABLE", "", "", "transient", "rate_limit"), False),
        (DriverResult("SUCCESS", "session", "unexpected", "", ""), False),
    ])
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        plan = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")
        job_id = "cancel-setup-race"
        runtime.database.create_job(job_id=job_id, project_id=project.id, workflow="implement", profile="balanced", prompt="p", execution_plan_json="{}", session="ctx")
        cancel_event = CancelEvent()
        starts = 0
        original_start = runtime.target_executor._start_attempt
        async def cancel_during_setup(*args, **kwargs):
            nonlocal starts
            starts += 1
            value = await original_start(*args, **kwargs)
            if starts == 2:
                cancel_event.set()
            return value
        monkeypatch.setattr(runtime.target_executor, "_start_attempt", cancel_during_setup)
        class TrackingAsk:
            issued = 0
            revoked = 0
            def issue_token(self, *_args, **_kwargs):
                self.issued += 1
                return f"token-{self.issued}"
            def revoke_token(self, *_args, **_kwargs):
                self.revoked += 1
        ask = TrackingAsk()
        runtime.target_executor.ask_registry = ask
        result = await runtime.target_executor.execute(
            job_id=job_id, project=project, workflow="implement", session="ctx", plan=plan,
            prompt="p", cwd=root, cancel_event=cancel_event,
        )
        assert len(drivers.calls) == 1
        assert result.result.outcome == "CANCELLED"
        assert ask.issued == ask.revoked == 2
        assert not runtime.target_executor._target_active
        assert runtime.target_executor._target_users.get("primary", 0) == 0
        attempt_finishes = [event for event in _stream_events(runtime.database, job_id) if event["kind"] == "attempt.finished"]
        assert len(attempt_finishes) == 2
        stream_finishes = [event for event in _stream_events(runtime.database, job_id) if event["kind"] == "attempt.finished"]
        assert len(stream_finishes) == 2
        assert stream_finishes[-1]["data"]["status"] == "cancelled"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_stored_target_policy_survives_current_policy_changes(tmp_path: Path) -> None:
    root = repository(tmp_path)
    base = config(tmp_path / "home")
    old_policy = RetryPolicy(1, ("temporary",), ())
    old_target = replace(
        base.targets[0], backend="codex", args=("--old-setting",), max_concurrency=1,
        retry=old_policy, env={"ROTATED_ENV": "SYNTHETIC_OLD_ENV"},
    )
    old_catalog = replace(base, targets=(old_target,))
    runtime = Runtime(old_catalog)
    project = register_project(runtime, str(root))
    stored_plan = resolve_execution_plan(get_workflow("implement"), old_catalog, "balanced")
    plan_json = json.dumps(execution_plan_data(stored_plan))
    job_id = "stored-policy-environment"
    runtime.database.create_job(
        job_id=job_id, project_id=project.id, workflow="implement", profile="balanced",
        prompt="stored policy", execution_plan_json=plan_json, session="stored-policy",
    )
    current_target = replace(
        old_target, backend="pi", args=("--new-setting",), max_concurrency=4,
        retry=RetryPolicy(0, (), ()), env={"ROTATED_ENV": "SYNTHETIC_CURRENT_ENV"},
    )
    current_catalog = replace(old_catalog, targets=(current_target,))
    runtime._catalog = current_catalog
    runtime.target_executor.refresh_configuration(current_catalog)
    observations = []
    class PolicyObservingDrivers(FakeDrivers):
        async def execute(self, *, target, env=None, **kwargs):
            observations.append((target.backend, target.args, target.max_concurrency, target.retry, (env or {}).get("ROTATED_ENV")))
            if len(observations) == 1:
                return DriverResult("RETRYABLE", "", "", "temporary", "temporary")
            return await super().execute(target=target, **kwargs)
    runtime.drivers = PolicyObservingDrivers()
    await runtime.start()
    try:
        job = await runtime.wait(job_id, 10)
        assert job.state == "succeeded"
        assert observations == [
            ("codex", ("--old-setting",), 1, old_policy, "SYNTHETIC_CURRENT_ENV"),
            ("codex", ("--old-setting",), 1, old_policy, "SYNTHETIC_CURRENT_ENV"),
        ]
        assert "SYNTHETIC_" not in runtime.database.job_record(job_id)["execution_plan_json"]
    finally:
        await runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("backend_name", ["claude", "pi", "codex", "agy"])
@pytest.mark.parametrize("streaming", [False, True])
async def test_real_adapter_observations_through_execution_persist_reported_consumption_alongside_derived_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, backend_name: str, streaming: bool
) -> None:
    root = repository(tmp_path)
    previous_which = shutil.which
    monkeypatch.setattr(
        "shutil.which",
        lambda cmd, *args, **kwargs: f"/usr/bin/{cmd}"
        if cmd in ("claude", "codex", "pi", "agy")
        else previous_which(cmd, *args, **kwargs),
    )
    monkeypatch.setattr("refract.drivers.DriverRegistry._detect_structured_mode", lambda *a, **k: streaming)

    if backend_name == "claude":
        c_lines = [
            json.dumps({
                "type": "assistant",
                "message": {
                    "id": "c-msg-1",
                    "role": "assistant",
                    "content": [{"type": "text", "text": "claude done"}],
                    "usage": {"input_tokens": 100, "cache_read_input_tokens": 30, "output_tokens": 20},
                },
            }),
            json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "claude done", "session_id": "c-sess-1"}),
        ]
        stub_claude(monkeypatch, tmp_path, c_lines)
    elif backend_name == "pi":
        p_lines = [
            json.dumps({"type": "session", "id": "pi-sess-1"}),
            json.dumps({"type": "turn_start"}),
            json.dumps({
                "type": "message_end",
                "message": {
                    "role": "assistant",
                    "responseId": "p-resp-1",
                    "content": [{"type": "text", "text": "pi done"}],
                    "usage": {"input": 120, "cacheRead": 40, "output": 25},
                },
            }),
            json.dumps({
                "type": "turn_end",
                "message": {
                    "role": "assistant",
                    "responseId": "p-resp-1",
                    "content": [{"type": "text", "text": "pi done"}],
                    "usage": {"input": 120, "cacheRead": 40, "output": 25},
                },
            }),
        ]
        monkeypatch.setattr("refract.backends.pi.run_process", fake_run_process(p_lines))
    elif backend_name == "codex":
        cdx_lines = [
            json.dumps({"type": "thread.started", "thread_id": "cdx-tid-1"}),
            json.dumps({"type": "item.completed", "item": {"type": "agent_message", "id": "m1", "text": "codex done"}}),
            json.dumps({
                "type": "turn.completed",
                "usage": {"input_tokens": 200, "cached_input_tokens": 50, "output_tokens": 35},
            }),
        ]
        monkeypatch.setattr("refract.backends.codex.run_process", shell_fake_as_process(lambda *a, **k: (l for l in cdx_lines)))
    elif backend_name == "agy":
        a_lines = [
            json.dumps({
                "event": "step_update",
                "step_update": {
                    "conversation_id": "00000000-0000-0000-0000-000000000001",
                    "step_index": 1,
                    "state": "DONE",
                    "usage": {"input_tokens": 300, "cache_read_tokens": 60, "output_tokens": 40},
                },
            }),
            json.dumps({
                "event": "result",
                "result": {"conversation_id": "00000000-0000-0000-0000-000000000001", "response": "agy done"},
            }),
        ]
        monkeypatch.setattr("refract.backends.agy.run_process", fake_run_process(a_lines))

    target = TargetConfig(id=f"{backend_name}-target", backend=backend_name)
    selection = TargetSelection((target.id,))
    catalog = replace(
        config(tmp_path / "home"),
        targets=(target,),
        profiles={"balanced": {"implement": selection, "review": selection, "consult": selection}},
    )

    runtime = Runtime(catalog)
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        submission = await runtime.submit(project.id, "implement", "test task")
        completed_job = await runtime.wait(submission.job_id, 10)
        assert completed_job.state == "succeeded"
        final_telemetry = completed_job.result.tokens
        assert final_telemetry is not None
        # Assert reported consumption is preserved alongside derived context
        assert final_telemetry["context_used"] is not None
        if backend_name == "pi":
            assert final_telemetry["context_window"] is None

        db_job = runtime.database.job(submission.job_id)
        assert db_job is not None
        db_telemetry = db_job.result.tokens
        assert db_telemetry is not None
        if backend_name == "pi":
            assert db_telemetry["context_window"] is None
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_retry_sequential_streams_and_ask_tokens(tmp_path: Path) -> None:
    root = repository(tmp_path)
    base = config(tmp_path / "home")

    policy = RetryPolicy(2, ("rate_limit",), ())
    catalog = replace(
        base,
        targets=(TargetConfig(id="primary", backend="codex", retry=policy),),
        profiles={"balanced": {"implement": TargetSelection(("primary",)), "review": TargetSelection(("primary",)), "consult": TargetSelection(("primary",))}},
    )

    observed_ask_tokens = []

    class RetryStreamDrivers(FakeDrivers):
        def __init__(self):
            super().__init__()
            self.attempt = 0

        def supports_structured_streaming(self, target):
            return True

        async def execute(self, *, target, env=None, on_event=None, **kwargs):
            self.attempt += 1
            if env and "REFRACT_ASK_TOKEN" in env:
                observed_ask_tokens.append((self.attempt, env["REFRACT_ASK_TOKEN"]))
            if on_event:
                await on_event({"kind": "stream.message", "text": f"attempt-{self.attempt}"})
            if self.attempt == 1:
                return DriverResult("RETRYABLE", "", "", "transient error", "rate_limit")
            return DriverResult("SUCCESS", "sess-1", "attempt 2 success", "", "")

    drivers = RetryStreamDrivers()
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        sub = await runtime.submit(project.id, "implement", "retry stream test")
        job = await runtime.wait(sub.job_id, 10)
        assert job.state == "succeeded"

        # 1. Distinct ask tokens per attempt
        assert len(observed_ask_tokens) == 2
        assert observed_ask_tokens[0][0] == 1
        assert observed_ask_tokens[1][0] == 2
        assert observed_ask_tokens[0][1] != observed_ask_tokens[1][1]
        assert not runtime.ask_registry._tokens

        # 2. Sequential attempt finished events in DB
        events = _stream_events(runtime.database, sub.job_id)
        finish_events = [e for e in events if e["kind"] == "attempt.finished"]
        assert len(finish_events) == 2
        assert finish_events[0]["attempt"] == 1
        assert finish_events[0]["data"]["outcome"] == "RETRYABLE"
        assert finish_events[1]["attempt"] == 2
        assert finish_events[1]["data"]["outcome"] == "SUCCESS"

        # 3. Stream events boundary and per-attempt records
        stream_events = _stream_events(runtime.database, sub.job_id)
        attempt_stream_finishes = [e for e in stream_events if e["kind"] == "attempt.finished"]
        assert len(attempt_stream_finishes) == 2
        assert attempt_stream_finishes[0]["attempt"] == 1
        assert attempt_stream_finishes[1]["attempt"] == 2

        # 4. Successful attempt's session stored in DB
        tkey = target_execution_key(catalog.targets[0])
        assert runtime.database.session(project.id, "implement", "implement", tkey) == "sess-1"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_retry_unknown_observation_blocks_replay(tmp_path: Path) -> None:
    root = repository(tmp_path)
    base = config(tmp_path / "home")

    policy = RetryPolicy(2, ("rate_limit",), ())
    catalog = replace(
        base,
        targets=(TargetConfig(id="primary", backend="codex", retry=policy),),
        profiles={"balanced": {"implement": TargetSelection(("primary",)), "review": TargetSelection(("primary",)), "consult": TargetSelection(("primary",))}},
    )

    class NonStreamingDriver(FakeDrivers):
        def __init__(self):
            super().__init__()
            self.invocations = []

        def supports_structured_streaming(self, target):
            return False

        async def execute(self, *, target, **kwargs):
            self.invocations.append(target.id)
            return DriverResult("RETRYABLE", "", "", "transient error", "rate_limit")

    drivers = NonStreamingDriver()
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        sub = await runtime.submit(project.id, "implement", "unknown observation test")
        job = await runtime.wait(sub.job_id, 10)
        assert job.state == "failed"
        assert len(drivers.invocations) == 1
    finally:
        await runtime.close()


def _attempt_runtime(tmp_path, drivers) -> tuple[Runtime, Path]:
    root = repository(tmp_path)
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = drivers
    runtime.target_executor.drivers = drivers
    return runtime, root


async def _execute_primary(runtime: Runtime, root: Path, cancel_event: CancelEvent | None = None):
    project = register_project(runtime, str(root))
    plan = resolve_execution_plan(get_workflow("implement"), runtime.config, "balanced")
    runtime.database.create_job(job_id="attempt-job", project_id=project.id, workflow="implement", profile="balanced", prompt="p", execution_plan_json="{}", session="s")
    return await runtime.target_executor.execute(
        job_id="attempt-job", project=project, workflow="implement", session="s", plan=plan,
        prompt="p", cwd=root, cancel_event=cancel_event or CancelEvent(),
    )


@pytest.mark.asyncio
async def test_attempt_without_ask_registry_runs_driver_without_ask_env(tmp_path) -> None:
    seen: list[dict[str, str]] = []

    class EnvDrivers(FakeDrivers):
        async def execute(self, *, env=None, **kwargs):
            seen.append(dict(env or {}))
            return DriverResult("SUCCESS", "sid", "ok", "", "")

    runtime, root = _attempt_runtime(tmp_path, EnvDrivers())
    try:
        runtime.target_executor.ask_registry = None
        result = await _execute_primary(runtime, root)
        assert result.result.outcome == "SUCCESS"
        assert seen == [{"REFRACT_JOB_ID": "attempt-job"}]
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_attempt_with_ask_registry_passes_ask_env_and_revokes_token(tmp_path) -> None:
    seen: list[dict[str, str]] = []

    class EnvDrivers(FakeDrivers):
        async def execute(self, *, env=None, **kwargs):
            seen.append(dict(env or {}))
            return DriverResult("SUCCESS", "sid", "ok", "", "")

    runtime, root = _attempt_runtime(tmp_path, EnvDrivers())
    try:
        revoked: list[str] = []
        real_revoke = runtime.ask_registry.revoke_token
        runtime.ask_registry.revoke_token = lambda job_id: (revoked.append(job_id), real_revoke(job_id))[1]
        await _execute_primary(runtime, root)
        assert sorted(seen[0]) == ["REFRACT_ASK_TIMEOUT_S", "REFRACT_ASK_TOKEN", "REFRACT_ASK_URL", "REFRACT_JOB_ID"]
        assert seen[0]["REFRACT_ASK_URL"] == f"http://{runtime.config.host}:{runtime.config.port}/ask"
        assert revoked == ["attempt-job"]
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_attempt_revoke_failure_propagates_with_outcome(tmp_path) -> None:
    runtime, root = _attempt_runtime(tmp_path, FakeDrivers())
    try:

        def broken_revoke(job_id: str) -> None:
            raise RuntimeError("revoke broke")

        runtime.ask_registry.revoke_token = broken_revoke
        with pytest.raises(RuntimeError, match="revoke broke") as caught:
            await _execute_primary(runtime, root)
        assert caught.value._refract_outcome["failure_kind"] == "request_fatal"
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_attempt_record_finished_failure_propagates_with_outcome(tmp_path) -> None:
    runtime, root = _attempt_runtime(tmp_path, FakeDrivers())
    try:

        async def broken_record(*args, **kwargs) -> None:
            raise RuntimeError("record broke")

        runtime.target_executor._record_attempt_finished = broken_record
        with pytest.raises(RuntimeError, match="record broke") as caught:
            await _execute_primary(runtime, root)
        assert caught.value._refract_outcome["failure_kind"] == "request_fatal"
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_attempt_driver_exception_wins_over_revoke_and_record_failures(tmp_path) -> None:
    class Exploding(FakeDrivers):
        async def execute(self, **kwargs):
            raise RuntimeError("driver broke")

    runtime, root = _attempt_runtime(tmp_path, Exploding())
    try:

        def broken_revoke(job_id: str) -> None:
            raise RuntimeError("revoke broke")

        async def broken_record(*args, **kwargs) -> None:
            raise RuntimeError("record broke")

        runtime.ask_registry.revoke_token = broken_revoke
        runtime.target_executor._record_attempt_finished = broken_record
        with pytest.raises(RuntimeError, match="driver broke"):
            await _execute_primary(runtime, root)
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_attempt_start_failure_propagates_with_outcome(tmp_path) -> None:
    runtime, root = _attempt_runtime(tmp_path, FakeDrivers())
    try:

        async def broken_start(*args, **kwargs):
            raise RuntimeError("start broke")

        runtime.target_executor._start_attempt = broken_start
        with pytest.raises(RuntimeError, match="start broke") as caught:
            await _execute_primary(runtime, root)
        assert caught.value._refract_outcome["failure_kind"] == "request_fatal"
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_attempt_cancelled_before_first_attempt_returns_cancelled(tmp_path) -> None:
    class Unreached(FakeDrivers):
        async def execute(self, **kwargs):
            raise AssertionError("driver must not run")

    runtime, root = _attempt_runtime(tmp_path, Unreached())
    try:
        cancel_event = CancelEvent()
        real_session = runtime.database.session

        def cancelling_session(*args, **kwargs):
            cancel_event.set()
            return real_session(*args, **kwargs)

        runtime.database.session = cancelling_session
        result = await _execute_primary(runtime, root, cancel_event)
        assert result.result.outcome == "CANCELLED"
        assert result.outcome["failure_kind"] == "cancelled"
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_attempt_cancel_set_during_driver_overrides_success(tmp_path) -> None:
    cancel_event = CancelEvent()

    class CancellingDrivers(FakeDrivers):
        async def execute(self, **kwargs):
            cancel_event.set()
            return DriverResult("SUCCESS", "sid", "ok", "", "")

    runtime, root = _attempt_runtime(tmp_path, CancellingDrivers())
    try:
        result = await _execute_primary(runtime, root, cancel_event)
        assert result.result.outcome == "CANCELLED"
        assert result.outcome["failure_kind"] == "cancelled"
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_attempt_driver_cancelled_error_propagates_with_cancelled_outcome(tmp_path) -> None:
    class Cancelled(FakeDrivers):
        async def execute(self, **kwargs):
            raise asyncio.CancelledError()

    runtime, root = _attempt_runtime(tmp_path, Cancelled())
    try:
        with pytest.raises(asyncio.CancelledError) as caught:
            await _execute_primary(runtime, root)
        assert caught.value._refract_outcome["failure_kind"] == "cancelled"
    finally:
        runtime.database.close()


_OUTCOME_CASES = [
    pytest.param(DriverResult("SUCCESS", "", "", "", ""), {}, None, id="success"),
    pytest.param(DriverResult("CANCELLED", "", "", "", ""), {}, "cancelled", id="cancelled"),
    pytest.param(DriverResult("RETRYABLE", "", "", "", ""), {"circuit_open": True}, "circuit_open", id="circuit-open-flag"),
    pytest.param(DriverResult("REQUEST_FATAL", "", "", "", "circuit_open"), {}, "circuit_open", id="circuit-open-code"),
    pytest.param(DriverResult("RETRYABLE", "", "", "", ""), {"replay_blocked": True}, "replay_blocked", id="replay-blocked"),
    pytest.param(DriverResult("REQUEST_FATAL", "", "", "", "context_overflow"), {}, "context_overflow", id="context-overflow"),
    pytest.param(DriverResult("TARGET_FATAL", "", "", "", "configuration_error"), {}, "request_fatal", id="configuration-error"),
    pytest.param(DriverResult("REQUEST_FATAL", "", "", "", "x"), {}, "request_fatal", id="request-fatal"),
    pytest.param(DriverResult("TARGET_FATAL", "", "", "", "x"), {}, "target_fatal", id="target-fatal"),
    pytest.param(DriverResult("RETRYABLE", "", "", "", "x"), {}, "transient", id="retryable"),
    pytest.param(DriverResult("SURPRISE", "", "", "", "x"), {}, "request_fatal", id="unknown-outcome"),
]


@pytest.mark.parametrize(("result", "options", "expected"), _OUTCOME_CASES)
def test_outcome_failure_kind(result, options, expected) -> None:
    assert TargetExecutor._outcome(result, None, 7, **options)["failure_kind"] == expected


def test_outcome_model_prefers_result_then_target_then_empty() -> None:
    target = TargetConfig(id="primary", backend="codex", model="configured")
    with_model = DriverResult("SUCCESS", "", "", "", "", model="reported")
    without_model = DriverResult("SUCCESS", "", "", "", "")
    assert TargetExecutor._outcome(with_model, target, 1)["model"] == "reported"
    assert TargetExecutor._outcome(without_model, target, 1)["model"] == "configured"
    assert TargetExecutor._outcome(without_model, None, 1)["model"] == ""
    assert TargetExecutor._outcome(without_model, None, None)["duration_ms"] is None


async def _invoke(runtime: Runtime, root: Path, drivers, tokens, **overrides):
    runtime.target_executor.drivers = drivers
    options = dict(
        job_id="inv-job", attempt=1, attempt_tokens=tokens,
        target=runtime.config.targets[0], prompt="p", session_id="", cwd=root,
        timeout_s=5.0, cancel_event=CancelEvent(), supports_streaming=True,
    )
    options.update(overrides)
    return await runtime.target_executor._run_target_invocation(**options)


@pytest.mark.asyncio
async def test_invocation_reports_tool_activity_and_stream_events(tmp_path) -> None:
    class Streaming(FakeDrivers):
        async def execute(self, *, on_event, **kwargs):
            await on_event({"kind": "tool.started", "entity_id": "t1"})
            await on_event({"kind": "telemetry.updated", "data": {"input": 3, "output": 4}})
            await on_event({"kind": "telemetry.updated", "data": "not a dict"})
            return DriverResult("SUCCESS", "sid", "ok", "", "")

    runtime, root = _attempt_runtime(tmp_path, FakeDrivers())
    try:
        runtime.database.create_job(job_id="inv-job", project_id=register_project(runtime, str(root)).id, workflow="implement", profile="balanced", prompt="p", execution_plan_json="{}", session="s")
        tokens: list = []
        result, tool_activity = await _invoke(runtime, root, Streaming(), tokens)
        assert (result.outcome, tool_activity) == ("SUCCESS", True)
        assert len(tokens) == 1
        assert (tokens[0].as_dict()["input"], tokens[0].as_dict()["output"]) == (3, 4)
        assert [e["kind"] for e in _stream_events(runtime.database, "inv-job")] == ["tool.started", "telemetry.updated"]
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_invocation_without_streaming_skips_events_and_merges_returned_tokens(tmp_path) -> None:
    class Plain(FakeDrivers):
        async def execute(self, *, on_event, **kwargs):
            assert on_event is None
            return DriverResult("SUCCESS", "sid", "ok", "", "", tokens={"input": 9, "output": 2})

    runtime, root = _attempt_runtime(tmp_path, FakeDrivers())
    try:
        tokens: list = []
        result, tool_activity = await _invoke(runtime, root, Plain(), tokens, supports_streaming=False)
        assert (result.outcome, tool_activity) == ("SUCCESS", False)
        assert (tokens[0].as_dict()["input"], tokens[0].as_dict()["output"]) == (9, 2)
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_invocation_malformed_backend_tokens_are_ignored(tmp_path, caplog) -> None:
    class Malformed(FakeDrivers):
        async def execute(self, *, on_event, **kwargs):
            return DriverResult("SUCCESS", "sid", "ok", "", "", tokens=object())

    runtime, root = _attempt_runtime(tmp_path, FakeDrivers())
    try:
        with caplog.at_level("WARNING"):
            result, _ = await _invoke(runtime, root, Malformed(), [], supports_streaming=False)
        assert result.outcome == "SUCCESS"
        assert [r.getMessage() for r in caplog.records if r.levelname == "WARNING"] == ["Ignoring malformed backend telemetry"]
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_invocation_telemetry_failure_is_logged_and_run_continues(tmp_path, caplog, monkeypatch) -> None:
    import refract.execution as execution_module

    class Streaming(FakeDrivers):
        async def execute(self, *, on_event, **kwargs):
            await on_event({"kind": "telemetry.updated", "data": {"input": 1}})
            return DriverResult("SUCCESS", "sid", "ok", "", "")

    def broken(values):
        raise ValueError("bad counters")

    runtime, root = _attempt_runtime(tmp_path, FakeDrivers())
    try:
        runtime.database.create_job(job_id="inv-job", project_id=register_project(runtime, str(root)).id, workflow="implement", profile="balanced", prompt="p", execution_plan_json="{}", session="s")
        monkeypatch.setattr(execution_module, "_counters_from", broken)
        with caplog.at_level("WARNING"):
            result, _ = await _invoke(runtime, root, Streaming(), [])
        assert result.outcome == "SUCCESS"
        assert "Telemetry update failed" in [r.getMessage() for r in caplog.records]
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_invocation_process_group_record_failure_is_logged(tmp_path, caplog) -> None:
    from refract.backends._process import spawn_hook

    class Spawning(FakeDrivers):
        async def execute(self, **kwargs):
            await spawn_hook.get()(1234)
            return DriverResult("SUCCESS", "sid", "ok", "", "")

    runtime, root = _attempt_runtime(tmp_path, FakeDrivers())
    try:

        def broken_pgid(job_id, pgid):
            raise RuntimeError("no job row")

        runtime.database.set_pgid = broken_pgid
        with caplog.at_level("WARNING"):
            result, _ = await _invoke(runtime, root, Spawning(), [], supports_streaming=False)
        assert result.outcome == "SUCCESS"
        assert "Worker process group not recorded" in [r.getMessage() for r in caplog.records]
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_invocation_driver_exception_propagates(tmp_path) -> None:
    class Exploding(FakeDrivers):
        async def execute(self, **kwargs):
            raise RuntimeError("driver broke")

    runtime, root = _attempt_runtime(tmp_path, FakeDrivers())
    exploding = Exploding()
    try:
        with pytest.raises(RuntimeError, match="driver broke"):
            await _invoke(runtime, root, exploding, [], supports_streaming=False)
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_invocation_cancel_event_overrides_driver_result(tmp_path) -> None:
    cancel_event = CancelEvent()

    class Cancelling(FakeDrivers):
        async def execute(self, **kwargs):
            cancel_event.set()
            return DriverResult("SUCCESS", "sid", "ok", "", "")

    runtime, root = _attempt_runtime(tmp_path, FakeDrivers())
    try:
        result, _ = await _invoke(runtime, root, Cancelling(), [], supports_streaming=False, cancel_event=cancel_event)
        assert result.outcome == "CANCELLED"
    finally:
        runtime.database.close()
