import sqlite3

import pytest

from refract.database import Database


@pytest.fixture
def database(tmp_path):
    db = Database(tmp_path / "atomic.db")
    db.upsert_project(project_id="p", root="/p")
    yield db
    db.close()


def create_job(db):
    db.create_job(job_id="j", project_id="p", workflow="consult", profile="p",
                  prompt="hello", execution_plan_json="{}", session="k")


def test_fresh_success_rolls_back_session_and_result(database):
    create_job(database)
    session = dict(project_id="p", session="k", workflow="consult", target="t", target_key="t")
    database.store_session(project_id="p", session="k", workflow="consult", target_key="t", backend_session_id="old")
    original = database.job_record("j")
    database._connection.execute("""CREATE TRIGGER reject_job_update BEFORE UPDATE ON jobs
                                    BEGIN SELECT RAISE(ABORT, 'job rejected'); END""")
    with pytest.raises(sqlite3.IntegrityError, match="job rejected"):
        database.finish_fresh_job_success(job_id="j", backend_session_id="new", text="new result", **session)
    assert database.job_record("j") == original
    assert database.session("p", "k", "consult", "t") == "old"


