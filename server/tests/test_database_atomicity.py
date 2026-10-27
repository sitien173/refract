import sqlite3

import pytest

from refract.database import Database


@pytest.fixture
def database(tmp_path):
    db = Database(tmp_path / "atomic.db")
    db.upsert_project(project_id="p", alias="p", root="/p")
    yield db
    db.close()


def create_job(db):
    db.create_job(job_id="j", project_id="p", workflow="consult", profile="p",
                  prompt="hello", execution_plan_json="{}", context_key="k")


def reject_events(db):
    db._connection.execute("""CREATE TRIGGER reject_events BEFORE INSERT ON events
                              BEGIN SELECT RAISE(ABORT, 'event rejected'); END""")


def test_create_rolls_back_when_event_fails(database):
    reject_events(database)
    with pytest.raises(sqlite3.IntegrityError, match="event rejected"):
        create_job(database)
    assert database.job_record("j") is None


@pytest.mark.parametrize("operation", ["start", "finish", "retry"])
def test_state_change_rolls_back_when_event_fails(database, operation):
    create_job(database)
    if operation == "retry":
        database.finish_job("j", "failed", error="original failure")
    original = database.job_record("j")
    original_events = database.events("j")
    reject_events(database)
    operations = {
        "start": lambda: database.start_job("j"),
        "finish": lambda: database.finish_job("j", "succeeded", text="result", metadata={"execution": {"model": "m"}}),
        "retry": lambda: database.reset_retry("j"),
    }
    change_state = operations[operation]
    with pytest.raises(sqlite3.IntegrityError, match="event rejected"):
        change_state()
    assert database.job_record("j") == original
    assert database.events("j") == original_events


def test_fresh_success_rolls_back_session_turn_and_result(database):
    create_job(database)
    turn = dict(project_id="p", context_key="k", role="consult", target_id="t",
                target_key="t", session_id="old", prompt="hello", response="old result")
    database.append_turn(**turn)
    original = database.job_record("j")
    reject_events(database)
    turn.update(session_id="new", response="new result")
    with pytest.raises(sqlite3.IntegrityError, match="event rejected"):
        database.finish_fresh_job_success(job_id="j", **turn)
    assert database.job_record("j") == original
    assert database.session("p", "k", "consult", "t") == "old"
    assert database.recent_turns("p", "k", "consult", 10) == [
        {"target_id": "t", "prompt": "hello", "response": "old result"}
    ]


def test_stream_metadata_is_one_query_and_scoped_to_job(database):
    create_job(database)
    assert database._connection.execute("PRAGMA synchronous").fetchone()[0] == 1
    assert database.stream_metadata("j") == {
        "high_water": 0, "retained_from": 0, "truncated": False, "failed": False,
    }
    events = database.append_stream_events("j", [
        {"kind": "assistant.text.delta", "data": {"text": "hi"}},
        {"kind": "stream.truncated", "data": {}},
    ])
    database.event("j", "stream.persistence_failed", {"error": "test"})
    queries = []
    database._connection.set_trace_callback(queries.append)
    metadata = database.stream_metadata("j")
    database._connection.set_trace_callback(None)
    assert len(queries) == 1
    assert metadata == {"high_water": events[-1].id, "retained_from": events[0].id,
                        "truncated": True, "failed": True}
    assert database.stream_metadata("other") == {
        "high_water": 0, "retained_from": 0, "truncated": False, "failed": False,
    }
    with database._connection:
        database._connection.execute("DELETE FROM job_stream_events WHERE id=?", (events[0].id,))
    assert database.stream_metadata("j")["retained_from"] == events[-1].id


def test_merge_job_telemetry_rolls_back_on_error(database):
    create_job(database)
    database._connection.execute(
        """CREATE TRIGGER reject_job_updates BEFORE UPDATE ON jobs
           BEGIN SELECT RAISE(ABORT, 'job update rejected'); END"""
    )
    with pytest.raises(sqlite3.IntegrityError, match="job update rejected"):
        database.merge_job_telemetry("j", {"version": 1, "total_input_tokens": {"value": 100, "source": "provider", "quality": "reported"}})
    assert database.job_record("j")["result_metadata_json"] == "{}"


def test_concurrent_terminal_and_telemetry_race(database):
    import concurrent.futures
    import json
    import threading

    create_job(database)
    database.start_job("j")

    errors = []
    barrier = threading.Barrier(2)

    def do_finish():
        try:
            barrier.wait()
            database.finish_job("j", "succeeded", text="done", metadata={"execution": {"model": "m"}})
        except Exception as e:
            errors.append(e)

    def do_telemetry():
        try:
            barrier.wait()
            database.merge_job_telemetry("j", {
                "version": 1,
                "completeness": "complete",
                "total_input_tokens": {"value": 50, "source": "stream", "quality": "reported"},
                "attribution": {"attempt": 1, "invocation": 1},
            })
        except Exception as e:
            errors.append(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(do_finish)
        f2 = executor.submit(do_telemetry)
        f1.result()
        f2.result()

    assert not errors
    record = database.job_record("j")
    assert record["state"] == "succeeded"
    meta = json.loads(record["result_metadata_json"])
    assert meta["execution"]["model"] == "m"


