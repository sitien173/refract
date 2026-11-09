"""Card store: creation, state edges, links, listing and detail."""

from __future__ import annotations

import itertools
import uuid
from pathlib import Path

import pytest

from refract.database import CardError, Database

STATES = ("todo", "in_progress", "in_review", "done", "cancelled")
EDGES = {
    "todo": {"in_progress", "cancelled"},
    "in_progress": {"in_review", "cancelled"},
    "in_review": {"done", "in_progress", "cancelled"},
    "done": set(),
    "cancelled": set(),
}
PATHS = {
    "todo": (),
    "in_progress": ("in_progress",),
    "in_review": ("in_progress", "in_review"),
    "done": ("in_progress", "in_review", "done"),
    "cancelled": ("cancelled",),
}


@pytest.fixture
def database(tmp_path: Path) -> Database:
    return Database(tmp_path / "refract.db")


@pytest.fixture
def project_id(database: Database, tmp_path: Path) -> str:
    return database.upsert_project(project_id="p1", root=tmp_path.as_posix()).id


def _job(database: Database, project_id: str) -> str:
    job_id = str(uuid.uuid4())
    database.create_job(
        job_id=job_id, project_id=project_id, workflow="implement", profile="default",
        prompt="p", execution_plan_json="{}", session="s",
    )
    return job_id


def _card(database: Database, project_id: str, card_id: str = "c1", *, title: str = "t", body: str = "", job_ids: list[str] | None = None) -> dict:
    return database.create_card(card_id=card_id, project_id=project_id, title=title, body=body, job_ids=job_ids or [])


def _move(database: Database, card_id: str, state: str, *, job_ids: list[str] | None = None, note: str = "") -> dict:
    return database.move_card(card_id=card_id, state=state, job_ids=job_ids or [], note=note)


def _counts(database: Database) -> tuple[int, int, int]:
    return tuple(
        database._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("cards", "card_jobs", "card_moves")
    )


def _expect(code: str, call) -> CardError:
    with pytest.raises(CardError) as info:
        call()
    assert info.value.code == code
    return info.value


def test_create_card_starts_in_todo_with_initial_move_and_links(database: Database, project_id: str) -> None:
    job_id = _job(database, project_id)

    card = _card(database, project_id, title="Ship", body="b", job_ids=[job_id])

    assert (card["id"], card["state"], card["title"]) == ("c1", "todo", "Ship")
    detail = database.card_detail("c1")
    assert detail["card"]["body"] == "b"
    assert detail["card"]["project_root"] == database.project(project_id).root
    assert [(m["from_state"], m["to_state"]) for m in detail["moves"]] == [(None, "todo")]
    assert [(j["job_id"], j["available"], j["workflow"], j["state"]) for j in detail["jobs"]] == [(job_id, True, "implement", "queued")]


@pytest.mark.parametrize(("source", "target"), list(itertools.product(STATES, STATES)))
def test_state_edge_table(database: Database, project_id: str, source: str, target: str) -> None:
    _card(database, project_id)
    for step in PATHS[source]:
        _move(database, "c1", step)

    if source == target or target in EDGES[source]:
        assert _move(database, "c1", target)["card"]["state"] == target
    else:
        error = _expect("invalid_state", lambda: _move(database, "c1", target))
        assert source in error.message
        assert database.card_detail("c1")["card"]["state"] == source


def test_state_change_writes_one_move_row_with_note(database: Database, project_id: str) -> None:
    _card(database, project_id)

    result = _move(database, "c1", "in_progress", note="starting")

    assert result["moved"] is True
    moves = database.card_detail("c1")["moves"]
    assert [(m["from_state"], m["to_state"], m["note"]) for m in moves] == [(None, "todo", ""), ("todo", "in_progress", "starting")]
    assert moves[-1]["at"] == database.card_detail("c1")["card"]["updated_at"]


def test_same_state_appends_only_new_links_and_writes_no_move(database: Database, project_id: str) -> None:
    first, second = _job(database, project_id), _job(database, project_id)
    _card(database, project_id, job_ids=[first])
    before = database.card_detail("c1")

    unchanged = _move(database, "c1", "todo", job_ids=[first], note="ignored")
    assert unchanged["moved"] is False
    assert database.card_detail("c1")["card"]["updated_at"] == before["card"]["updated_at"]
    assert _counts(database) == (1, 1, 1)

    linked = _move(database, "c1", "todo", job_ids=[first, second], note="ignored")
    detail = database.card_detail("c1")
    assert linked["moved"] is False
    assert {j["job_id"] for j in detail["jobs"]} == {first, second}
    assert len(detail["moves"]) == 1
    assert detail["card"]["updated_at"] >= before["card"]["updated_at"]


def test_stale_compare_and_set_raises_invalid_state(database: Database, project_id: str) -> None:
    _card(database, project_id)
    real = database._connection

    class Racing:
        """Changes the card on the same connection just before the guarded UPDATE runs."""

        def __getattr__(self, name):
            return getattr(real, name)

        def __enter__(self):
            return real.__enter__()

        def __exit__(self, *exc):
            return real.__exit__(*exc)

        def execute(self, sql, *args):
            if sql.lstrip().startswith("UPDATE cards SET state"):
                real.execute("UPDATE cards SET state='cancelled' WHERE id='c1'")
            return real.execute(sql, *args)

    database._local.connection = Racing()
    error = _expect("invalid_state", lambda: _move(database, "c1", "in_progress"))
    database._local.connection = real

    assert error.message == "card changed; current state cancelled"
    assert database.card_detail("c1")["card"]["state"] == "todo"
    assert len(database.card_detail("c1")["moves"]) == 1


def test_unknown_card_and_unknown_target_state(database: Database, project_id: str) -> None:
    _expect("unknown_card", lambda: _move(database, "nope", "todo"))
    _card(database, project_id)
    _expect("invalid_state", lambda: _move(database, "c1", "bogus"))
    assert database.card_detail("nope") is None


def test_unknown_job_rejects_whole_call(database: Database, project_id: str) -> None:
    good = _job(database, project_id)

    _expect("unknown_job", lambda: _card(database, project_id, job_ids=[good, "missing"]))
    assert _counts(database) == (0, 0, 0)

    _card(database, project_id)
    _expect("unknown_job", lambda: _move(database, "c1", "in_progress", job_ids=[good, "missing"]))
    assert database.card_detail("c1")["card"]["state"] == "todo"
    assert _counts(database) == (1, 0, 1)


def test_sixty_fifth_link_rejects_whole_call(database: Database, project_id: str) -> None:
    jobs = [_job(database, project_id) for _ in range(65)]
    _card(database, project_id)
    for start in range(0, 64, 16):
        _move(database, "c1", "todo", job_ids=jobs[start:start + 16])
    assert _counts(database) == (1, 64, 1)

    _expect("invalid_request", lambda: _move(database, "c1", "in_progress", job_ids=[jobs[64]]))

    assert _counts(database) == (1, 64, 1)
    assert database.card_detail("c1")["card"]["state"] == "todo"


def test_links_survive_pruning_and_report_unavailable(database: Database, project_id: str) -> None:
    job_id = _job(database, project_id)
    database.finish_job(job_id, "succeeded", text="x", target="primary")
    _card(database, project_id, job_ids=[job_id])

    database.prune_history("9999-01-01T00:00:00Z")

    (job,) = database.card_detail("c1")["jobs"]
    assert job["job_id"] == job_id
    assert job["available"] is False
    assert (job["workflow"], job["state"], job["target"]) == (None, None, None)


def test_job_from_another_project_links(database: Database, project_id: str, tmp_path: Path) -> None:
    other = database.upsert_project(project_id="p2", root=(tmp_path / "other").as_posix()).id
    job_id = _job(database, other)

    _card(database, project_id, job_ids=[job_id])

    assert database.card_detail("c1")["jobs"][0]["available"] is True


def test_list_cards_orders_open_first_and_truncates(database: Database, project_id: str) -> None:
    for card_id in ("a", "b", "c", "d"):
        _card(database, project_id, card_id)
    _move(database, "a", "cancelled")
    for step in ("in_progress", "in_review", "done"):
        _move(database, "b", step)
    _move(database, "c", "in_progress")
    for card_id, stamp in (("a", "8"), ("b", "9"), ("c", "2"), ("d", "1")):
        database._connection.execute("UPDATE cards SET updated_at=? WHERE id=?", (stamp, card_id))
    database._connection.commit()

    listing = database.list_cards(project_id=project_id, limit=None)
    assert [c["id"] for c in listing["cards"]] == ["c", "d", "b", "a"]
    assert listing["truncated"] is False
    assert all(c["project_root"] == database.project(project_id).root for c in listing["cards"])

    limited = database.list_cards(project_id=project_id, limit=3)
    assert [c["id"] for c in limited["cards"]] == ["c", "d", "b"]
    assert limited["truncated"] is True
    assert database.list_cards(project_id=None, limit=4)["truncated"] is False
    assert database.list_cards(project_id="other", limit=None) == {"cards": [], "truncated": False}


def test_list_cards_sorts_each_group_by_updated_at_then_id_descending(database: Database, project_id: str) -> None:
    for card_id in ("a", "b", "c"):
        _card(database, project_id, card_id)
    database._connection.execute("UPDATE cards SET updated_at='2' WHERE id IN ('a','b')")
    database._connection.execute("UPDATE cards SET updated_at='1' WHERE id='c'")
    database._connection.commit()

    assert [c["id"] for c in database.list_cards(project_id=project_id, limit=None)["cards"]] == ["b", "a", "c"]


def test_card_detail_returns_moves_in_id_order(database: Database, project_id: str) -> None:
    _card(database, project_id)
    _move(database, "c1", "in_progress")
    _move(database, "c1", "in_review")

    moves = database.card_detail("c1")["moves"]

    assert [m["id"] for m in moves] == sorted(m["id"] for m in moves)
    assert [m["to_state"] for m in moves] == ["todo", "in_progress", "in_review"]


@pytest.mark.parametrize("title", ["", "   ", "x" * 201])
def test_bad_title_is_rejected(database: Database, project_id: str, title: str) -> None:
    _expect("invalid_request", lambda: _card(database, project_id, title=title))
    assert _counts(database) == (0, 0, 0)


def test_limits_are_rejected(database: Database, project_id: str) -> None:
    jobs = [_job(database, project_id) for _ in range(17)]
    _card(database, project_id, title="x" * 200, body="y" * 4000)

    _expect("invalid_request", lambda: _card(database, project_id, "c2", body="y" * 4001))
    _expect("invalid_request", lambda: _card(database, project_id, "c2", job_ids=jobs))
    _expect("invalid_request", lambda: _card(database, project_id, "c2", job_ids=[""]))
    _expect("invalid_request", lambda: _card(database, project_id, "c2", job_ids=["j" * 65]))
    _expect("invalid_request", lambda: _move(database, "c1", "in_progress", note="n" * 1001))
    _expect("invalid_request", lambda: _move(database, "c1", "in_progress", job_ids=jobs))
    _expect("invalid_request", lambda: _move(database, "c1", "in_progress", job_ids=["j" * 65]))
    assert _move(database, "c1", "in_progress", note="n" * 1000)["moved"] is True
    assert _counts(database) == (1, 0, 2)


def test_unknown_project_is_rejected(database: Database) -> None:
    _expect("invalid_request", lambda: database.create_card(card_id="c1", project_id="nope", title="t", body="", job_ids=[]))


def _named_job(database: Database, project_id: str, job_id: str) -> str:
    database.create_job(
        job_id=job_id, project_id=project_id, workflow="implement", profile="default",
        prompt="p", execution_plan_json="{}", session="s",
    )
    return job_id


def test_card_rows_carry_job_ids_in_link_order(database: Database, project_id: str, monkeypatch) -> None:
    # Link order is chronological with a job_id tie-break. Windows clocks tick about every 15 ms,
    # so two calls can share a timestamp; a strictly increasing clock keeps the calls distinct.
    ticks = itertools.count(1)
    monkeypatch.setattr("refract.database.utc_now", lambda: f"2030-01-01T00:00:{next(ticks):02d}+00:00")
    late, early_b, early_a = (_named_job(database, project_id, name) for name in ("job-z", "job-b", "job-a"))
    created = _card(database, project_id, "c1", job_ids=[late])
    assert created["job_ids"] == ["job-z"]

    moved = _move(database, "c1", "in_progress", job_ids=[early_b, early_a])["card"]
    assert moved["job_ids"] == ["job-z", "job-a", "job-b"]

    same = _move(database, "c1", "in_progress")["card"]
    assert same["job_ids"] == ["job-z", "job-a", "job-b"]

    listed = database.list_cards(project_id=project_id, limit=None)["cards"]
    assert listed[0]["job_ids"] == ["job-z", "job-a", "job-b"]
    assert [job["job_id"] for job in database.card_detail("c1")["jobs"]] == listed[0]["job_ids"]


def test_card_without_links_has_empty_job_ids(database: Database, project_id: str) -> None:
    assert _card(database, project_id, "c1")["job_ids"] == []
    assert _move(database, "c1", "in_progress")["card"]["job_ids"] == []
    assert database.list_cards(project_id=project_id, limit=None)["cards"][0]["job_ids"] == []


def test_list_cards_reads_links_with_one_extra_query(database: Database, project_id: str) -> None:
    job_id = _named_job(database, project_id, "job-1")
    for card_id in ("a", "b", "c"):
        _card(database, project_id, card_id, job_ids=[job_id])
    statements: list[str] = []
    database._connection.set_trace_callback(statements.append)
    cards = database.list_cards(project_id=project_id, limit=None)["cards"]
    database._connection.set_trace_callback(None)

    assert all(card["job_ids"] == ["job-1"] for card in cards)
    assert len([sql for sql in statements if "card_jobs" in sql]) == 1


def test_card_detail_card_keeps_its_keys(database: Database, project_id: str) -> None:
    _card(database, project_id)
    assert set(database.card_detail("c1")["card"]) == {
        "id", "project_id", "project_root", "title", "body", "state", "created_at", "updated_at",
    }
