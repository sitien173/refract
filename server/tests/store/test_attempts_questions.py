"""Question compare-and-set and attempt rows."""

from __future__ import annotations

import sqlite3

import pytest

from refract.store import attempts, jobs, questions, schema
from refract.store.pool import Pool


@pytest.fixture
def conn(tmp_path):
    path = tmp_path / "refract.db"
    schema.initialize(path)
    pool = Pool(path)
    connection = pool.connection
    jobs.upsert_project(connection, "p", "/p")
    jobs.create(connection, job_id="j", project_id="p", workflow="consult", profile="prof",
                prompt="hello", plan_json="{}", session="s")
    connection.commit()
    yield connection
    pool.close()


def test_question_answer_is_compare_and_set(conn):
    question_id = questions.ask(conn, "j", "which file?")
    assert questions.get(conn, question_id)["state"] == "open"
    assert questions.answer(conn, question_id, "a.py") is True
    assert questions.answer(conn, question_id, "b.py") is False
    row = questions.get(conn, question_id)
    assert (row["state"], row["answer"], row["answered_at"] is not None) == ("answered", "a.py", True)


def test_expire_only_moves_open_questions(conn):
    open_id = questions.ask(conn, "j", "one")
    answered_id = questions.ask(conn, "j", "two")
    questions.answer(conn, answered_id, "yes")
    assert questions.expire_open(conn, "j") == 1
    assert questions.get(conn, open_id)["state"] == "expired"
    assert questions.get(conn, answered_id)["state"] == "answered"
    assert questions.answer(conn, open_id, "late") is False


def test_open_question_for_job_lists_only_open(conn):
    first = questions.ask(conn, "j", "one")
    questions.answer(conn, first, "x")
    second = questions.ask(conn, "j", "two")
    assert [row["id"] for row in questions.open_for_job(conn, "j")] == [second]


def test_questions_and_attempts_cascade_with_job(conn):
    attempts.begin(conn, "j", "t1")
    questions.ask(conn, "j", "q")
    conn.execute("DELETE FROM jobs WHERE id='j'")
    assert attempts.for_job(conn, "j") == []
    assert conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0] == 0


def test_attempt_seq_is_unique_per_job(conn):
    attempts.begin(conn, "j", "t1")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO attempts(job_id, seq, reason, target, state, started_at) "
                     "VALUES ('j', 1, 'retry', 't', 'running', 'x')")


def test_attempt_backend_comes_from_the_job_plan(conn):
    conn.execute("""UPDATE jobs SET plan_json='{"targets": [{"id": "t1", "backend": "codex"}]}' WHERE id='j'""")
    attempts.begin(conn, "j", "t1")
    attempts.begin(conn, "j", "unknown")
    assert [row["backend"] for row in attempts.for_job(conn, "j")] == ["codex", ""]


def test_earlier_attempts_default_to_not_replay_safe_and_keep_recorded_evidence(conn):
    jobs.start(conn, "j")
    attempts.begin(conn, "j", "t1")
    attempts.mark_replay_safe(conn, "j", True)
    attempts.begin(conn, "j", "t2")
    attempts.begin(conn, "j", "t3")
    jobs.finish(conn, "j", "succeeded", result="ok", target="t3", attempts=5, replay_safe=True)
    rows = attempts.for_job(conn, "j")
    assert [(r["seq"], r["target"], r["replay_safe"]) for r in rows] == [
        (1, "t1", 1), (2, "t2", 0), (3, "t3", 0), (4, "t3", 0), (5, "t3", 1),
    ]
