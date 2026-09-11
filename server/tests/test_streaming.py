from __future__ import annotations

import asyncio
import sqlite3
from unittest.mock import MagicMock

import pytest

from openmcp.database import Database
from openmcp.models import JobStreamEvent
from openmcp.streaming import (
    FLUSH_INTERVAL_SECONDS,
    MAX_BATCH_BYTES,
    MAX_BATCH_EVENTS,
    MAX_JOB_BYTES,
    MAX_JOB_EVENTS,
    MAX_TEXT_EVENT_BYTES,
    TRUNCATION_KIND,
    JobStreamHub,
    StreamRecorder,
)


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "openmcp.db")
    project = database.upsert_project(project_id="p1", alias="p1", root="/p1")
    database.create_job(
        job_id="job-stream",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="hello",
        execution_plan_json="{}",
        context_key="k1",
    )
    yield database
    database.close()


@pytest.mark.asyncio
async def test_recorder_text_coalescing(db):
    committed_cursors = []
    recorder = StreamRecorder(
        database=db,
        job_id="job-stream",
        attempt=1,
        target_id="t1",
        backend="claude",
        on_commit=committed_cursors.append,
    )
    await recorder.record({
        "kind": "assistant.text.delta",
        "entity_id": "msg-1",
        "data": {"text": "Hello "},
    })
    await recorder.record({
        "kind": "assistant.text.delta",
        "entity_id": "msg-1",
        "data": {"text": "world!"},
    })
    # A different entity should not coalesce with msg-1
    await recorder.record({
        "kind": "assistant.text.delta",
        "entity_id": "msg-2",
        "data": {"text": "Other entity"},
    })
    await recorder.flush()

    events = db.stream_events("job-stream", after=0)
    assert len(events) == 2
    assert events[0].entity_id == "msg-1"
    assert events[0].data["text"] == "Hello world!"
    assert events[1].entity_id == "msg-2"
    assert events[1].data["text"] == "Other entity"
    assert len(committed_cursors) == 1
    assert committed_cursors[0] == events[1].id
    await recorder.close()


@pytest.mark.asyncio
async def test_recorder_50_event_batch_flush(db):
    recorder = StreamRecorder(
        database=db,
        job_id="job-stream",
        attempt=1,
        target_id="t1",
        backend="claude",
        flush_interval_s=10.0,  # avoid timer flush
    )
    for i in range(49):
        await recorder.record({
            "kind": "tool.started",
            "entity_id": f"tool-{i}",
            "data": {"tool": "search"},
        })
    # 49 events: not flushed yet
    assert db.stream_high_water("job-stream") == 0

    # 50th event triggers automatic batch flush
    await recorder.record({
        "kind": "tool.started",
        "entity_id": "tool-49",
        "data": {"tool": "search"},
    })
    assert db.stream_high_water("job-stream") > 0
    events = db.stream_events("job-stream", after=0, limit=100)
    assert len(events) == 50
    await recorder.close()


@pytest.mark.asyncio
async def test_recorder_64kib_batch_flush(db):
    recorder = StreamRecorder(
        database=db,
        job_id="job-stream",
        attempt=1,
        target_id="t1",
        backend="claude",
        flush_interval_s=10.0,
    )
    # Record events of ~6.8 KiB each to bring buffer near 64 KiB (~61.2 KiB)
    payload = "x" * 6800
    for i in range(9):
        await recorder.record({
            "kind": "stream.notice",
            "entity_id": f"notice-{i}",
            "data": {"text": payload},
        })
    # Add an initial text delta of 3 KiB (~64.2 KiB buffer total, below 64 KiB = 65536 B)
    await recorder.record({
        "kind": "assistant.text.delta",
        "entity_id": "msg-coalesce",
        "data": {"text": "y" * 3000},
    })
    # Total buffer bytes < 64 KiB: not flushed yet
    assert db.stream_high_water("job-stream") == 0

    # Coalescing another 3 KiB into msg-coalesce brings total to ~67.2 KiB, crossing 64 KiB
    await recorder.record({
        "kind": "assistant.text.delta",
        "entity_id": "msg-coalesce",
        "data": {"text": "z" * 3000},
    })
    # Must immediately trigger automatic batch flush upon crossing threshold
    assert db.stream_high_water("job-stream") > 0
    await recorder.close()


@pytest.mark.asyncio
async def test_recorder_reconstructs_durable_truncation_across_instances_and_reopen(tmp_path):
    db_path = tmp_path / "openmcp.db"
    db1 = Database(db_path)
    proj = db1.upsert_project(project_id="p1", alias="p1", root="/p1")
    db1.create_job(
        job_id="job-trunc",
        project_id=proj.id,
        workflow="consult",
        profile="balanced",
        prompt="p",
        execution_plan_json="{}",
        context_key="k",
    )
    rec1 = StreamRecorder(
        database=db1,
        job_id="job-trunc",
        attempt=1,
        target_id="t1",
        backend="claude",
        max_job_events=3,
    )
    for i in range(4):
        await rec1.record({
            "kind": "stream.notice",
            "entity_id": f"n-{i}",
            "data": {"text": f"val-{i}"},
        })
    await rec1.flush()
    assert rec1.truncated is True
    await rec1.close()
    db1.close()

    # Reopen database and initialize a fresh recorder instance with high ceiling
    db2 = Database(db_path)
    rec2 = StreamRecorder(
        database=db2,
        job_id="job-trunc",
        attempt=2,
        target_id="t2",
        backend="claude",
        max_job_events=20000,
        max_job_bytes=8 * 1024 * 1024,
    )
    assert rec2.truncated is True

    # Later content must be rejected
    await rec2.record({
        "kind": "assistant.text.delta",
        "entity_id": "msg-late",
        "data": {"text": "should be rejected"},
    })
    await rec2.flush()

    events = db2.stream_events("job-trunc", after=0, limit=100)
    for e in events:
        if e.kind == "assistant.text.delta":
            assert "should be rejected" not in e.data.get("text", "")

    trunc_markers = [e for e in events if e.kind == TRUNCATION_KIND]
    assert len(trunc_markers) == 1
    await rec2.close()
    db2.close()



@pytest.mark.asyncio
async def test_recorder_timer_flush(db):
    recorder = StreamRecorder(
        database=db,
        job_id="job-stream",
        attempt=1,
        target_id="t1",
        backend="claude",
        flush_interval_s=0.05,
    )
    await recorder.record({
        "kind": "assistant.message.started",
        "entity_id": "msg-1",
        "data": {"role": "assistant"},
    })
    assert db.stream_high_water("job-stream") == 0

    # Wait for timer to fire
    await asyncio.sleep(0.1)
    assert db.stream_high_water("job-stream") > 0
    events = db.stream_events("job-stream", after=0)
    assert len(events) == 1
    assert events[0].kind == "assistant.message.started"
    await recorder.close()


@pytest.mark.asyncio
async def test_recorder_8kib_text_splitting(db):
    recorder = StreamRecorder(
        database=db,
        job_id="job-stream",
        attempt=1,
        target_id="t1",
        backend="claude",
    )
    # 18 KiB of text in one delta
    large_text = "a" * (18 * 1024)
    await recorder.record({
        "kind": "assistant.text.delta",
        "entity_id": "msg-1",
        "data": {"text": large_text},
    })
    await recorder.flush()

    events = db.stream_events("job-stream", after=0)
    assert len(events) >= 3
    for e in events:
        assert len(e.data["text"].encode("utf-8")) <= MAX_TEXT_EVENT_BYTES
    reconstructed = "".join(e.data["text"] for e in events)
    assert reconstructed == large_text
    await recorder.close()


@pytest.mark.asyncio
async def test_recorder_job_event_limit_and_truncation_marker(db):
    max_events = 10
    recorder = StreamRecorder(
        database=db,
        job_id="job-stream",
        attempt=1,
        target_id="t1",
        backend="claude",
        max_job_events=max_events,
    )
    for i in range(15):
        await recorder.record({
            "kind": "stream.notice",
            "entity_id": f"notice-{i}",
            "data": {"text": f"notice {i}"},
        })
    await recorder.flush()

    events = db.stream_events("job-stream", after=0, limit=100)
    # Exactly max_events regular events + exactly 1 stream.truncated marker
    assert len(events) == max_events + 1
    assert events[-1].kind == TRUNCATION_KIND
    assert recorder.truncated is True

    # Recording further events drops them; truncation marker is not duplicated
    await recorder.record({
        "kind": "stream.notice",
        "entity_id": "notice-extra",
        "data": {"text": "extra"},
    })
    await recorder.flush()

    events_after = db.stream_events("job-stream", after=0, limit=100)
    assert len(events_after) == max_events + 1
    truncation_events = [e for e in events_after if e.kind == TRUNCATION_KIND]
    assert len(truncation_events) == 1
    await recorder.close()


@pytest.mark.asyncio
async def test_recorder_job_bytes_limit_and_truncation_marker(db):
    max_bytes = 1000
    recorder = StreamRecorder(
        database=db,
        job_id="job-stream",
        attempt=1,
        target_id="t1",
        backend="claude",
        max_job_bytes=max_bytes,
    )
    payload = "y" * 300
    for i in range(6):
        await recorder.record({
            "kind": "stream.notice",
            "entity_id": f"notice-{i}",
            "data": {"text": payload},
        })
    await recorder.flush()

    events = db.stream_events("job-stream", after=0, limit=100)
    assert len(events) > 0
    assert events[-1].kind == TRUNCATION_KIND
    assert recorder.truncated is True
    truncation_events = [e for e in events if e.kind == TRUNCATION_KIND]
    assert len(truncation_events) == 1
    await recorder.close()


@pytest.mark.asyncio
async def test_recorder_explicit_final_flush(db):
    recorder = StreamRecorder(
        database=db,
        job_id="job-stream",
        attempt=1,
        target_id="t1",
        backend="claude",
        flush_interval_s=10.0,
    )
    await recorder.record({
        "kind": "attempt.started",
        "entity_id": "attempt-1",
        "data": {},
    })
    assert db.stream_high_water("job-stream") == 0

    await recorder.close()
    assert db.stream_high_water("job-stream") > 0
    events = db.stream_events("job-stream", after=0)
    assert len(events) == 1
    assert events[0].kind == "attempt.started"


@pytest.mark.asyncio
async def test_recorder_failed_persistence_status_does_not_raise(db, monkeypatch):
    recorder = StreamRecorder(
        database=db,
        job_id="job-stream",
        attempt=1,
        target_id="t1",
        backend="claude",
    )
    def broken_append(*args, **kwargs):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(db, "append_stream_events", broken_append)

    committed = []
    recorder._on_commit = committed.append

    await recorder.record({
        "kind": "stream.notice",
        "entity_id": "notice-1",
        "data": {"text": "hello"},
    })
    # flush should catch exception, set recorder.failed = True, and not crash
    await recorder.flush()
    assert recorder.failed is True
    assert len(committed) == 0

    # Job in DB remains intact with unchanged result
    job = db.job("job-stream")
    assert job is not None
    assert job.result.text == ""
    await recorder.close()


@pytest.mark.asyncio
async def test_hub_publish_delivers_cursor() -> None:
    hub = JobStreamHub()
    q = hub.subscribe("job-1")
    hub.publish("job-1", 42)
    item = await asyncio.wait_for(q.get(), timeout=1.0)
    assert item == 42
    hub.unsubscribe("job-1", q)


@pytest.mark.asyncio
async def test_hub_coalescing_capacity_one() -> None:
    hub = JobStreamHub()
    q = hub.subscribe("job-1")
    hub.publish("job-1", 10)
    hub.publish("job-1", 20)
    hub.publish("job-1", 30)
    assert q.qsize() == 1
    item = await asyncio.wait_for(q.get(), timeout=1.0)
    assert item == 30
    assert q.empty()
    hub.unsubscribe("job-1", q)


@pytest.mark.asyncio
async def test_hub_unsubscribe_cleans_up() -> None:
    hub = JobStreamHub()
    q1 = hub.subscribe("job-1")
    q2 = hub.subscribe("job-1")
    assert len(hub._subscribers["job-1"]) == 2
    hub.unsubscribe("job-1", q1)
    assert len(hub._subscribers["job-1"]) == 1
    hub.unsubscribe("job-1", q2)
    assert "job-1" not in hub._subscribers


@pytest.mark.asyncio
async def test_hub_publish_cross_thread() -> None:
    import threading
    hub = JobStreamHub()
    q = hub.subscribe("job-1")

    def worker():
        hub.publish("job-1", 99)

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    item = await asyncio.wait_for(q.get(), timeout=1.0)
    assert item == 99
    hub.unsubscribe("job-1", q)
