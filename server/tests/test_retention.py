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
            "context_used_tokens": {"value": 2400, "source": "provider", "quality": "reported", "observed_at": "2026-10-26T00:00:00Z"},
            "context_window_size": {"value": 128000, "source": "provider", "quality": "reported", "observed_at": "2026-10-26T00:00:00Z"},
            "context_remaining_percent": {"value": 98.125, "source": "derived", "quality": "derived", "observed_at": "2026-10-26T00:00:00Z"},
            "total_input_tokens": {"value": 5000, "source": "provider", "quality": "reported", "observed_at": "2026-10-26T00:00:00Z"},
            "total_output_tokens": {"value": 600, "source": "provider", "quality": "reported", "observed_at": "2026-10-26T00:00:00Z"},
        }
        db.merge_job_telemetry(job_id, telemetry)
        db.append_stream_events(job_id, [{"attempt": 1, "kind": "assistant_message", "data": {"text": "hello"}}])
        db.finish_job(job_id, "succeeded")

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
        saved_telemetry = job_view.result.metadata.telemetry
        assert saved_telemetry.context_used_tokens.value == 2400
        assert saved_telemetry.total_input_tokens.value == 5000
        assert saved_telemetry.completeness == "complete"
    finally:
        db.close()


def test_diagnostic_report_event_pruning_and_deduplication_scope(tmp_path):
    """Retention prunes report events for expired terminal jobs; deduplication lasts while retained."""
    runtime = Runtime(DaemonConfig(home=tmp_path))
    db = runtime.database
    try:
        db.upsert_project(project_id="proj", alias="proj", root="/proj")
        # Job 1: Old terminal job
        db.create_job(
            job_id="old-job",
            project_id="proj",
            workflow="implement",
            profile="balanced",
            prompt="work",
            execution_plan_json="{}",
            context_key="k1",
        )
        db.finish_job("old-job", "succeeded")
        with db._connection:
            db._connection.execute("UPDATE jobs SET updated_at='2000-01-01' WHERE id='old-job'")

        # Job 2: Recent terminal job
        db.create_job(
            job_id="recent-job",
            project_id="proj",
            workflow="review",
            profile="balanced",
            prompt="review",
            execution_plan_json="{}",
            context_key="k2",
        )
        db.finish_job("recent-job", "succeeded")

        # Independent key usage across different jobs
        res_old = db.record_error_report(
            job_id="old-job",
            category="protocol",
            expected="Expected protocol",
            observed="Observed anomaly",
            report_key="shared-key",
        )
        res_recent = db.record_error_report(
            job_id="recent-job",
            category="output",
            expected="Expected output",
            observed="Observed output anomaly",
            report_key="shared-key",
        )
        assert res_old["duplicate"] is False
        assert res_recent["duplicate"] is False
        assert res_old["report"]["id"] != res_recent["report"]["id"]

        # Prune history older than 2010
        runtime.prune_retained_transcripts()

        # Report event for old-job is pruned
        old_events = [e for e in db.events("old-job") if e["kind"] == "job.error_reported"]
        assert old_events == []
        assert db.diagnostic_counts(["old-job"]).get("old-job", 0) == 0
        assert db.job_record("old-job")["state"] == "succeeded"

        # Report event for recent-job is retained
        recent_events = [e for e in db.events("recent-job") if e["kind"] == "job.error_reported"]
        assert len(recent_events) == 1
        assert str(recent_events[0]["id"]) == res_recent["report"]["id"]
        assert db.diagnostic_counts(["recent-job"])["recent-job"] == 1

        # Deduplication scope: recent-job duplicate returns True with original ID
        dup_recent = db.record_error_report(
            job_id="recent-job",
            category="output",
            expected="Expected output",
            observed="Observed output anomaly",
            report_key="shared-key",
        )
        assert dup_recent["duplicate"] is True
        assert dup_recent["report"]["id"] == res_recent["report"]["id"]

        # Deduplication scope: pruned old-job can accept same key again as new report
        new_old = db.record_error_report(
            job_id="old-job",
            category="protocol",
            expected="Expected protocol",
            observed="Observed anomaly",
            report_key="shared-key",
        )
        assert new_old["duplicate"] is False
        assert new_old["report"]["id"] != res_old["report"]["id"]
    finally:
        db.close()
