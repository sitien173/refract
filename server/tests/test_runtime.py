from __future__ import annotations

import hashlib
import json

import pytest

from openmcp.config import load_config
from openmcp.runtime import OrchestrationError, Runtime


def _config(path) -> None:
    path.write_text('''[daemon]
default_profile = "balanced"

[[targets]]
id = "primary"
backend = "codex"

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
''', encoding="utf-8")


@pytest.mark.asyncio
async def test_failed_reload_preserves_catalog_health_and_blocks_submission(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    config_path = home / "config.toml"
    _config(config_path)
    runtime = Runtime(load_config(config_path))
    project_root = tmp_path / "project"
    project_root.mkdir()
    project = runtime.register_project(str(project_root), "project")
    original = runtime.catalog
    original_revision = original.config_revision

    config_path.write_text("[daemon\ndefault_profile =", encoding="utf-8")
    with pytest.raises(OrchestrationError):
        await runtime.submit(project.id, "consult", "question")

    assert runtime.catalog is original
    health = runtime.configuration_health()
    assert not health.valid
    assert health.last_known_good_revision == original_revision
    assert health.revision != original_revision
    with pytest.raises(OrchestrationError):
        await runtime.submit(project.id, "consult", "question")
    await runtime.close()


@pytest.mark.asyncio
async def test_configuration_error_does_not_expose_secret(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    path = home / "config.toml"
    _config(path)
    runtime = Runtime(load_config(path))
    project_root = tmp_path / "project"
    project_root.mkdir()
    project = runtime.register_project(str(project_root), "project")
    secret = "SUPER_SECRET_CONFIGURATION_VALUE"
    path.write_text(path.read_text(encoding="utf-8").rstrip() + f'\n[logging]\nlevel = "{secret}"\n', encoding="utf-8")

    with pytest.raises(OrchestrationError) as raised:
        await runtime.submit(project.id, "consult", "question")

    assert secret not in str(raised.value)
    assert secret not in runtime.configuration_health().latest_error
    await runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_kind", ["profile", "workflow"])
async def test_configuration_identifiers_do_not_leak_from_errors(tmp_path, invalid_kind) -> None:
    home = tmp_path / "home"
    home.mkdir()
    path = home / "config.toml"
    _config(path)
    runtime = Runtime(load_config(path))
    project_root = tmp_path / "project"
    project_root.mkdir()
    project = runtime.register_project(str(project_root), "project")
    content = path.read_text(encoding="utf-8")
    if invalid_kind == "profile":
        content += '[profiles."SECRET_PROFILE"]\n'
    else:
        content = content.replace(
            'consult = "primary"', 'SECRET_WORKFLOW = "primary"'
        )
    path.write_text(content, encoding="utf-8")

    with pytest.raises(OrchestrationError) as raised:
        await runtime.submit(project.id, "consult", "question")

    assert "SECRET_" not in str(raised.value)
    assert "SECRET_" not in runtime.configuration_health().latest_error
    await runtime.close()


@pytest.mark.asyncio
async def test_new_job_records_global_revision(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    path = home / "config.toml"
    _config(path)
    runtime = Runtime(load_config(path))
    project_root = tmp_path / "project"
    project_root.mkdir()
    project = runtime.register_project(str(project_root), "project")

    submission = await runtime.submit(project.id, "consult", "question")

    job = runtime.database.job(submission.job_id)
    assert job and job.config_revision == hashlib.sha256(path.read_bytes()).hexdigest()
    await runtime.close()


def test_initial_health_is_seeded(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    path = home / "config.toml"
    _config(path)
    catalog = load_config(path)
    runtime = Runtime(catalog)
    health = runtime.configuration_health()
    assert health.valid
    assert health.revision == hashlib.sha256(path.read_bytes()).hexdigest()
    assert health.last_known_good_revision == health.revision
    runtime.database.close()


# ---------------------------------------------------------------------------
# Configuration publication boundary (dashboard target-profile CRUD phase 1).
# ---------------------------------------------------------------------------


def test_publish_configuration_refreshes_catalog_and_executor(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    path = home / "config.toml"
    _config(path)
    runtime = Runtime(load_config(path))
    try:
        previous = runtime.catalog
        path.write_text(
            path.read_text(encoding="utf-8") + "\n# refreshed\n",
            encoding="utf-8",
        )
        runtime.publish_configuration()
        assert runtime.catalog is not previous
        assert runtime.target_executor.config is runtime.catalog
        health = runtime.configuration_health()
        assert health.valid
        assert health.revision == hashlib.sha256(path.read_bytes()).hexdigest()
    finally:
        runtime.database.close()


def test_config_mutation_service_exposes_shared_lock(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    path = home / "config.toml"
    _config(path)
    runtime = Runtime(load_config(path))
    try:
        assert runtime.mutations.lock is not None
        # The lock is re-entrant so reloads inside a commit do not deadlock.
        with runtime.mutations.lock:
            runtime.reload_configuration()
            runtime.publish_configuration()
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_project_override_runtime_activation_and_plan_preservation(tmp_path) -> None:
    from openmcp.models import ProfileEditorData, WorkflowPolicyData

    home = tmp_path / "home"
    home.mkdir()
    path = home / "config.toml"
    _config(path)
    runtime = Runtime(load_config(path))
    project_root = tmp_path / "project"
    project_root.mkdir()
    project = runtime.register_project(str(project_root), "project")

    # Submit job 1 under initial configuration
    sub1 = await runtime.submit(project.id, "consult", "initial question")
    record1_before = runtime.database.job_record(sub1.job_id)
    assert record1_before is not None
    plan1_before = record1_before["execution_plan_json"]

    # Create project profile override without daemon restart
    _, new_override = runtime.mutations.create_project_override(
        project_root,
        ProfileEditorData(
            id="balanced",
            extends="balanced",
            workflows={"consult": WorkflowPolicyData(targets=["primary"], max_attempts=3, timeout_s=99)},
        ),
        expected_revision="",
    )

    # Runtime activation: project catalog immediately reflects the override
    proj_catalog = runtime.catalog_for_project_cached(project.id)
    assert proj_catalog.profiles["balanced"]["consult"].max_attempts == 3
    assert proj_catalog.profiles["balanced"]["consult"].timeout_s == 99

    # Submit job 2 under updated override
    sub2 = await runtime.submit(project.id, "consult", "follow-up question")
    job2 = runtime.database.job(sub2.job_id)
    assert job2 is not None

    # Existing job 1 retains its original execution plan
    record1_after = runtime.database.job_record(sub1.job_id)
    assert record1_after is not None
    assert record1_after["execution_plan_json"] == plan1_before

    await runtime.close()


@pytest.mark.asyncio
async def test_runtime_start_prunes_expired_terminal_transcripts_without_pruning_active_jobs(tmp_path) -> None:
    from datetime import datetime, timedelta, timezone

    home = tmp_path / "home"
    home.mkdir()
    path = home / "config.toml"
    _config(path)
    runtime = Runtime(load_config(path))
    project_root = tmp_path / "project"
    project_root.mkdir()
    project = runtime.register_project(str(project_root), "project")

    # 1. Expired terminal job (10 days old)
    old_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    runtime.database.create_job(
        job_id="job-expired-term",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="p1",
        execution_plan_json="{}",
        context_key="c1",
    )
    with runtime.database._connection:
        runtime.database._connection.execute(
            "UPDATE jobs SET state='succeeded', updated_at=? WHERE id='job-expired-term'",
            (old_ts,),
        )
    runtime.database.append_stream_events("job-expired-term", [{
        "kind": "assistant.text.delta",
        "entity_id": "msg-1",
        "data": {"text": "old terminal transcript"},
    }])

    # 2. Recent terminal job (2 days old)
    recent_ts = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    runtime.database.create_job(
        job_id="job-recent-term",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="p2",
        execution_plan_json="{}",
        context_key="c2",
    )
    with runtime.database._connection:
        runtime.database._connection.execute(
            "UPDATE jobs SET state='succeeded', updated_at=? WHERE id='job-recent-term'",
            (recent_ts,),
        )
    runtime.database.append_stream_events("job-recent-term", [{
        "kind": "assistant.text.delta",
        "entity_id": "msg-1",
        "data": {"text": "recent terminal transcript"},
    }])

    # 3. Active running job (10 days old) - should NOT be pruned despite being old
    runtime.database.create_job(
        job_id="job-old-running",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="p3",
        execution_plan_json="{}",
        context_key="c3",
    )
    with runtime.database._connection:
        runtime.database._connection.execute(
            "UPDATE jobs SET state='running', updated_at=? WHERE id='job-old-running'",
            (old_ts,),
        )
    runtime.database.append_stream_events("job-old-running", [{
        "kind": "assistant.text.delta",
        "entity_id": "msg-1",
        "data": {"text": "active running transcript"},
    }])

    # Verify initial stream data exists
    assert runtime.database.stream_high_water("job-expired-term") > 0
    assert runtime.database.stream_high_water("job-recent-term") > 0
    assert runtime.database.stream_high_water("job-old-running") > 0

    # Start runtime (triggers start retention cleanup)
    await runtime.start()

    # Expired terminal transcript is pruned
    assert runtime.database.stream_high_water("job-expired-term") == 0

    # Recent terminal and active running transcripts are preserved
    assert runtime.database.stream_high_water("job-recent-term") > 0
    # Note: runtime.start() interrupts active jobs upon restart, changing running -> interrupted,
    # but the stream events of active jobs prior to start were not pruned by the retention step!
    assert runtime.database.stream_high_water("job-old-running") > 0

    # All job records themselves remain intact
    assert runtime.database.job("job-expired-term") is not None
    assert runtime.database.job("job-recent-term") is not None
    assert runtime.database.job("job-old-running") is not None

    await runtime.close()


@pytest.mark.asyncio
async def test_stream_durable_reload_reconstructs_cursor_and_events(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    config_path = home / "config.toml"
    _config(config_path)
    runtime = Runtime(load_config(config_path))
    project_root = tmp_path / "project"
    project_root.mkdir()
    project = runtime.register_project(str(project_root), "project")
    job_id = "job-reload-test"
    runtime.database.create_job(
        job_id=job_id,
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="hello",
        execution_plan_json="{}",
        context_key="c1",
    )
    events = [
        {"kind": "assistant.message.started", "entity_id": "msg-1", "data": {}},
        {"kind": "assistant.text.delta", "entity_id": "msg-1", "data": {"text": "chunk 1"}},
        {"kind": "assistant.text.delta", "entity_id": "msg-1", "data": {"text": "chunk 2"}},
        {"kind": "assistant.message.completed", "entity_id": "msg-1", "data": {}},
    ]
    persisted = runtime.database.append_stream_events(job_id, events)
    expected_hw = persisted[-1].id
    expected_retained = persisted[0].id
    await runtime.close()

    reopened = Runtime(load_config(config_path))
    try:
        assert reopened.database.stream_high_water(job_id) == expected_hw
        assert reopened.database.stream_retained_from(job_id) == expected_retained
        totals = reopened.database.stream_totals(job_id)
        assert totals.events == 4
        assert totals.bytes > 0
        replayed = reopened.database.stream_events(job_id, after=0)
        assert len(replayed) == 4
        assert [e.id for e in replayed] == [p.id for p in persisted]
        assert [e.kind for e in replayed] == [e["kind"] for e in events]
        assert replayed[1].data["text"] == "chunk 1"
        assert replayed[2].data["text"] == "chunk 2"
    finally:
        await reopened.close()


@pytest.mark.asyncio
async def test_stream_truncation_marker_durable_across_reload(tmp_path) -> None:
    from openmcp.streaming import StreamRecorder

    home = tmp_path / "home"
    home.mkdir()
    config_path = home / "config.toml"
    _config(config_path)
    runtime = Runtime(load_config(config_path))
    project_root = tmp_path / "project"
    project_root.mkdir()
    project = runtime.register_project(str(project_root), "project")
    job_id = "job-trunc-reload"
    runtime.database.create_job(
        job_id=job_id,
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="hello",
        execution_plan_json="{}",
        context_key="c1",
    )
    recorder = StreamRecorder(
        database=runtime.database,
        job_id=job_id,
        attempt=1,
        target_id="primary",
        backend="codex",
        max_job_bytes=100,
    )
    await recorder.record({"kind": "assistant.text.delta", "entity_id": "msg-1", "data": {"text": "x" * 60}})
    await recorder.record({"kind": "assistant.text.delta", "entity_id": "msg-1", "data": {"text": "y" * 60}})
    await recorder.close()

    assert runtime.database.stream_is_truncated(job_id) is True
    await runtime.close()

    reopened = Runtime(load_config(config_path))
    try:
        assert reopened.database.stream_is_truncated(job_id) is True
        new_recorder = StreamRecorder(
            database=reopened.database,
            job_id=job_id,
            attempt=1,
            target_id="primary",
            backend="codex",
        )
        assert new_recorder.truncated is True
        await new_recorder.record({"kind": "assistant.text.delta", "entity_id": "msg-2", "data": {"text": "suppressed"}})
        await new_recorder.close()

        events = reopened.database.stream_events(job_id, after=0)
        assert not any(e.data.get("text") == "suppressed" for e in events)
        assert any(e.kind == "stream.truncated" for e in events)
    finally:
        await reopened.close()


@pytest.mark.asyncio
async def test_stream_persistence_failure_retains_prior_events(tmp_path) -> None:
    from openmcp.streaming import StreamRecorder

    home = tmp_path / "home"
    home.mkdir()
    config_path = home / "config.toml"
    _config(config_path)
    runtime = Runtime(load_config(config_path))
    project_root = tmp_path / "project"
    project_root.mkdir()
    project = runtime.register_project(str(project_root), "project")
    job_id = "job-persist-fail"
    runtime.database.create_job(
        job_id=job_id,
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="hello",
        execution_plan_json="{}",
        context_key="c1",
    )
    runtime.database.append_stream_events(job_id, [
        {"kind": "assistant.text.delta", "entity_id": "msg-1", "data": {"text": "safe before failure"}}
    ])
    assert runtime.database.stream_high_water(job_id) > 0

    recorder = StreamRecorder(
        database=runtime.database,
        job_id=job_id,
        attempt=1,
        target_id="primary",
        backend="codex",
    )

    def broken_append(*args, **kwargs):
        raise RuntimeError("simulated disk full error")

    runtime.database.append_stream_events = broken_append
    await recorder.record({"kind": "assistant.text.delta", "entity_id": "msg-2", "data": {"text": "will fail"}})
    await recorder.flush()

    assert recorder.failed is True
    del runtime.database.append_stream_events
    events = runtime.database.stream_events(job_id, after=0)
    assert len(events) == 1
    assert events[0].data["text"] == "safe before failure"
    lifecycle = runtime.database.events(job_id)
    assert any(e.get("kind") == "stream.persistence_failed" for e in lifecycle)
    await runtime.close()


@pytest.mark.asyncio
async def test_stream_historical_fallback_for_jobs_without_events(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    config_path = home / "config.toml"
    _config(config_path)
    runtime = Runtime(load_config(config_path))
    project_root = tmp_path / "project"
    project_root.mkdir()
    project = runtime.register_project(str(project_root), "project")
    job_id = "job-legacy"
    runtime.database.create_job(
        job_id=job_id,
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="hello",
        execution_plan_json="{}",
        context_key="c1",
    )
    runtime.database.finish_job(job_id, "succeeded", text="authoritative historical result")

    assert runtime.database.stream_high_water(job_id) == 0
    assert runtime.database.stream_retained_from(job_id) == 0
    assert runtime.database.stream_events(job_id, after=0) == []
    assert runtime.database.stream_is_truncated(job_id) is False
    job = runtime.database.job(job_id)
    assert job is not None
    assert job.result.text == "authoritative historical result"
    await runtime.close()
