from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from refract.config import load_config
from refract.drivers import DriverResult
from refract.planning import target_execution_key
from refract.runtime import OrchestrationError, Runtime
from tests.orchestration_helpers import register_project, repository


_CONFIG = '''[daemon]
default_profile = "balanced"

[[targets]]
id = "a"
backend = "codex"

[[targets]]
id = "b"
backend = "claude"

[profiles.balanced]
consult = ["a", "b"]
review = ["a", "b"]
implement = ["a", "b"]
'''


class _Drivers:
    def __init__(self, outcomes: dict[str, str] | None = None) -> None:
        self.outcomes = outcomes or {}
        self.executed: list[str] = []

    @staticmethod
    def supports_structured_streaming(_target): return True

    @staticmethod
    def available(_target): return True

    async def execute(self, *, target, **_kwargs):
        self.executed.append(target.id)
        if self.outcomes.get(target.id) == "fail":
            return DriverResult("TARGET_FATAL", "", "", "boom", "target_fatal")
        return DriverResult("SUCCESS", f"session-{target.id}", f"done by {target.id}", "", "")


async def _runtime(tmp_path: Path, drivers: _Drivers | None = None) -> tuple[Runtime, object, _Drivers]:
    config_path = tmp_path / "config.toml"
    config_path.write_text(_CONFIG, encoding="utf-8")
    runtime = Runtime(load_config(config_path))
    root = tmp_path / "project"
    root.mkdir()
    project = register_project(runtime, str(root))
    drivers = drivers or _Drivers()
    runtime.drivers = drivers
    await runtime.start()
    return runtime, project, drivers


async def _run(runtime: Runtime, project, prompt: str = "x", session: str = "s") -> object:
    submitted = await runtime.submit(project.id, "consult", prompt, session=session)
    return await runtime.wait(submitted.job_id, 5)


def _set_sticky(runtime: Runtime, project, target: str, session: str = "s") -> None:
    runtime.database._connection.execute(
        "INSERT OR REPLACE INTO sessions(project_id, session, workflow, sticky_target, updated_at) VALUES (?, ?, 'consult', ?, 'now')",
        (project.id, session, target),
    )
    runtime.database._connection.commit()


def _open_circuit(runtime: Runtime, target: str) -> None:
    key = target_execution_key(next(item for item in runtime.catalog.targets if item.id == target))
    runtime.database._connection.execute(
        "INSERT OR REPLACE INTO target_health(target_id, consecutive_failures, circuit_open_until, cooldown_s, probe_job_id) VALUES (?, 1, '2999-01-01T00:00:00+00:00', 60, '')",
        (key,),
    )
    runtime.database._connection.commit()


def test_resolve_project_from_subdirectory_uses_git_root(tmp_path) -> None:
    root = repository(tmp_path)
    nested = root / "src" / "deep"
    nested.mkdir(parents=True)
    config_path = tmp_path / "config.toml"
    config_path.write_text(_CONFIG, encoding="utf-8")
    runtime = Runtime(load_config(config_path))
    try:
        from_nested = runtime.resolve_project(str(nested))
        from_root = runtime.resolve_project(str(root))
        assert from_nested.root == root.resolve().as_posix()
        assert from_nested.id == from_root.id
        assert len(runtime.database.projects()) == 1
    finally:
        runtime.database.close()


def test_resolve_project_outside_git_is_invalid_path(tmp_path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    config_path = tmp_path / "config.toml"
    config_path.write_text(_CONFIG, encoding="utf-8")
    runtime = Runtime(load_config(config_path))
    try:
        with pytest.raises(OrchestrationError) as raised:
            runtime.resolve_project(str(plain))
        assert raised.value.code == "invalid_path"
        assert runtime.database.projects() == []
    finally:
        runtime.database.close()


def test_resolve_project_path_is_not_shell_interpreted(tmp_path) -> None:
    root = repository(tmp_path)
    hostile = root / "x; touch pwned $(touch pwned2)"
    hostile.mkdir()
    config_path = tmp_path / "config.toml"
    config_path.write_text(_CONFIG, encoding="utf-8")
    runtime = Runtime(load_config(config_path))
    try:
        project = runtime.resolve_project(str(hostile))
        assert project.root == root.resolve().as_posix()
        assert not list(tmp_path.rglob("pwned*"))
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_success_records_sticky_target_and_next_submit_prefers_it(tmp_path) -> None:
    runtime, project, drivers = await _runtime(tmp_path)
    try:
        _set_sticky(runtime, project, "b")
        job = await _run(runtime, project)
        assert job.state == "succeeded"
        assert job.target_id == "b"
        assert drivers.executed == ["b"]
        assert runtime.database.sticky_target(project.id, "s", "consult") == "b"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_sticky_target_removed_from_profile_falls_back_to_profile_order(tmp_path) -> None:
    runtime, project, drivers = await _runtime(tmp_path)
    try:
        _set_sticky(runtime, project, "gone")
        job = await _run(runtime, project)
        assert drivers.executed == ["a"]
        assert runtime.database.sticky_target(project.id, "s", "consult") == "a"
        assert job.state == "succeeded"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_sticky_target_with_open_circuit_falls_back_and_success_updates_it(tmp_path) -> None:
    runtime, project, drivers = await _runtime(tmp_path)
    try:
        _set_sticky(runtime, project, "b")
        _open_circuit(runtime, "b")
        job = await _run(runtime, project)
        assert job.state == "succeeded"
        assert drivers.executed == ["a"]
        assert runtime.database.sticky_target(project.id, "s", "consult") == "a"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_failed_job_does_not_change_sticky_target(tmp_path) -> None:
    runtime, project, _drivers = await _runtime(tmp_path, _Drivers({"a": "fail"}))
    try:
        _set_sticky(runtime, project, "a")
        job = await _run(runtime, project)
        assert job.state == "failed"
        assert runtime.database.sticky_target(project.id, "s", "consult") == "a"
    finally:
        await runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["succeeded", "failed", "cancelled", "interrupted"])
async def test_retry_creates_new_job_and_never_mutates_source(tmp_path, state) -> None:
    runtime, project, drivers = await _runtime(tmp_path)
    try:
        source = await _run(runtime, project, prompt="original")
        runtime.database.finish_job(source.id, state, text="source text", target="a")
        before = runtime.database.job_record(source.id)
        source_file = runtime.database.result_path(source.id).read_bytes()

        retried = await runtime.retry(source.id)
        job = await runtime.wait(retried.job_id, 5)

        assert retried.job_id != source.id
        assert job.retry_of == source.id
        assert job.state == "succeeded"
        assert job.target_id == "b"
        assert drivers.executed[-1] == "b"
        assert runtime.database.job_record(job.id)["prompt"] == "original"
        assert runtime.database.job_record(job.id)["session"] == "s"
        assert runtime.database.job_record(source.id) == before
        assert runtime.database.result_path(source.id).read_bytes() == source_file
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_retry_with_target_pins_that_target_including_the_same_one(tmp_path) -> None:
    runtime, project, drivers = await _runtime(tmp_path)
    try:
        source = await _run(runtime, project)
        assert source.target_id == "a"
        retried = await runtime.retry(source.id, target="a")
        job = await runtime.wait(retried.job_id, 5)
        assert job.target_id == "a"
        assert drivers.executed == ["a", "a"]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_retry_with_unknown_target_lists_profile_targets(tmp_path) -> None:
    runtime, project, _drivers = await _runtime(tmp_path)
    try:
        source = await _run(runtime, project)
        jobs_before = len(runtime.database.jobs(project.id))
        with pytest.raises(OrchestrationError) as raised:
            await runtime.retry(source.id, target="nope")
        assert raised.value.code == "invalid_request"
        assert "a, b" in str(raised.value)
        assert len(runtime.database.jobs(project.id)) == jobs_before
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_retry_without_a_following_healthy_target_is_unavailable(tmp_path) -> None:
    runtime, project, _drivers = await _runtime(tmp_path)
    try:
        source = await _run(runtime, project)
        runtime.database.finish_job(source.id, "failed", target="b")
        with pytest.raises(OrchestrationError) as raised:
            await runtime.retry(source.id)
        assert raised.value.code == "targets_unavailable"
        assert "a, b" in raised.value.next_action
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_retry_from_active_state_is_invalid_state(tmp_path) -> None:
    runtime, project, _drivers = await _runtime(tmp_path)
    try:
        source = await _run(runtime, project)
        runtime.database._connection.execute("UPDATE jobs SET state='running' WHERE id=?", (source.id,))
        runtime.database._connection.commit()
        with pytest.raises(OrchestrationError) as raised:
            await runtime.retry(source.id)
        assert raised.value.code == "invalid_state"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_next_target_is_plain_name_of_following_healthy_target(tmp_path) -> None:
    runtime, project, _drivers = await _runtime(tmp_path, _Drivers({"a": "fail"}))
    try:
        job = await _run(runtime, project)
        assert job.state == "failed"
        assert job.target_id == "a"
        assert runtime.live_routing(job)["retry"]["next_target"] == "b"
        _open_circuit(runtime, "b")
        assert runtime.live_routing(job)["retry"]["next_target"] is None
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_result_text_is_written_to_private_file_under_state_directory(tmp_path) -> None:
    runtime, project, _drivers = await _runtime(tmp_path, _Drivers({"b": "fail"}))
    try:
        succeeded = await _run(runtime, project)
        path = runtime.database.result_path(succeeded.id)
        assert path == runtime.config.home / "results" / f"{succeeded.id}.md"
        assert path.read_text(encoding="utf-8") == "done by a"
        assert os.name == "nt" or stat.S_IMODE(path.stat().st_mode) == 0o600  # file modes are POSIX-only

        _open_circuit(runtime, "a")
        failed = await _run(runtime, project, session="other")
        assert failed.state == "failed"
        assert runtime.database.result_path(failed.id).read_text(encoding="utf-8") == ""
    finally:
        await runtime.close()
