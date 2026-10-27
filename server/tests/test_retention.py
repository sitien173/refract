import asyncio
from dataclasses import replace

import pytest

from refract.config import DaemonConfig
from refract.database import Database
from refract.runtime import Runtime


def test_turn_retention_caps_each_context_and_role(tmp_path):
    db = Database(tmp_path / "history.db", history_turns=2)
    try:
        db.upsert_project(project_id="p", alias="p", root="/p")
        for key, role in [("one", "consult"), ("two", "consult"), ("one", "review")]:
            for i in range(4):
                db.append_turn(project_id="p", context_key=key, role=role, target_id="t",
                               target_key="t", session_id="s", prompt=str(i), response=str(i))
            assert [t["prompt"] for t in db.recent_turns("p", key, role, 10)] == ["2", "3"]
        db.history_turns = 1
        db.prune_history("2000-01-01")
        assert db.recent_turns("p", "one", "consult", 10) == [
            {"target_id": "t", "prompt": "3", "response": "3"}
        ]
        assert db.session("p", "one", "consult", "t") == "s"
    finally:
        db.close()


def test_lifecycle_retention_preserves_active_and_recent_jobs(tmp_path):
    runtime = Runtime(DaemonConfig(home=tmp_path))
    db = runtime.database
    try:
        db.upsert_project(project_id="p", alias="p", root="/p")
        for name in ["old", "recent", "active"]:
            db.create_job(job_id=name, project_id="p", workflow="consult", profile="p",
                          prompt="hello", execution_plan_json="{}", context_key="k")
            if name != "active":
                db.finish_job(name, "succeeded")
            with db._connection:
                if name != "recent":
                    db._connection.execute("UPDATE jobs SET updated_at='2000-01-01' WHERE id=?", (name,))
        runtime.prune_retained_transcripts()
        assert db.events("old") == []
        assert db.events("recent")
        assert db.events("active")
        assert db.job("old") is not None
    finally:
        db.close()


@pytest.mark.asyncio
async def test_periodic_retention_retries_and_stops_on_close(tmp_path, monkeypatch):
    import refract.runtime as runtime_module

    runtime = Runtime(DaemonConfig(home=tmp_path))
    monkeypatch.setattr(runtime_module, "RETENTION_INTERVAL_S", 0.001)
    calls = 0
    retried = asyncio.Event()

    def prune():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("temporary failure")
        if calls >= 3:
            retried.set()
        return 0

    monkeypatch.setattr(runtime, "prune_retained_transcripts", prune)
    await runtime.start()
    task = runtime._retention_task
    try:
        await asyncio.wait_for(retried.wait(), 2)
    finally:
        await runtime.close()
    assert task.done()
    assert runtime._retention_task is None


def test_transcript_pruning_preserves_job_telemetry(tmp_path):
    """Transcript pruning prunes old events but strictly preserves metadata and telemetry."""
    runtime = Runtime(DaemonConfig(home=tmp_path))
    db = runtime.database
    try:
        db.upsert_project(project_id="proj", alias="proj", root="/proj")
        job_id = "old-pruned-telemetry-job"
        db.create_job(
            job_id=job_id,
            project_id="proj",
            workflow="implement",
            profile="balanced",
            prompt="do work",
            execution_plan_json="{}",
            context_key="k",
        )
        telemetry = {
            "version": 1,
            "completeness": "complete",
            "context_used_tokens": {"value": 2400, "source": "provider", "quality": "reported"},
            "context_window_size": {"value": 128000, "source": "provider", "quality": "reported"},
            "context_remaining_percent": {"value": 98.125, "source": "derived", "quality": "derived"},
            "total_input_tokens": {"value": 5000, "source": "provider", "quality": "reported"},
            "total_output_tokens": {"value": 600, "source": "provider", "quality": "reported"},
        }
        db.merge_job_telemetry(job_id, telemetry)
        db.append_stream_events(job_id, [{"attempt": 1, "kind": "assistant_message", "data": {"text": "hello"}}])
        db.finish_job(job_id, "succeeded", metadata={"telemetry": telemetry})

        # Age the job beyond the recent threshold
        with db._connection:
            db._connection.execute("UPDATE jobs SET updated_at='2000-01-01' WHERE id=?", (job_id,))

        # Verify events are present before pruning
        assert len(db.stream_events(job_id)) > 0

        # Run pruning
        pruned_count = runtime.prune_retained_transcripts()
        assert pruned_count > 0

        # Transcript events are pruned
        assert db.stream_events(job_id) == []

        # Job record and its telemetry remain completely intact
        job_view = db.job(job_id)
        assert job_view is not None
        assert "telemetry" in job_view.result.metadata
        saved_telemetry = job_view.result.metadata["telemetry"]
        assert saved_telemetry["context_used_tokens"]["value"] == 2400
        assert saved_telemetry["total_input_tokens"]["value"] == 5000
        assert saved_telemetry["completeness"] == "complete"
    finally:
        db.close()

