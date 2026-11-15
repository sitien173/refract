"""Schema v1 DDL, state CHECKs, and the .bak rename of databases on any other user_version."""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import sqlite3
import threading
from contextlib import closing
from pathlib import Path

import pytest

from refract.store import schema
from refract.store.pool import Pool

V1_TABLES = {
    "projects", "jobs", "attempts", "questions", "session_routes", "backend_sessions",
    "target_health", "cards", "card_jobs", "card_moves",
}


def open_pool(tmp_path: Path, name: str = "refract.db") -> Pool:
    path = tmp_path / name
    schema.initialize(path)
    return Pool(path)


def tables(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    return {row[0] for row in rows}


def make_legacy(path: Path, version: int, *, wal: bool) -> None:
    """Write a database at user_version `version`; with `wal`, keep its -wal and -shm beside it."""
    scratch = path.parent / f".scratch-{version}"
    scratch.mkdir()
    with closing(sqlite3.connect(scratch / "legacy.db")) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(f"PRAGMA user_version={version}")
        connection.execute("CREATE TABLE legacy (id INTEGER PRIMARY KEY, note TEXT)")
        connection.execute("INSERT INTO legacy(note) VALUES ('kept')")
        connection.commit()
        if wal:
            for suffix in ("", "-wal", "-shm"):
                shutil.copyfile(scratch / f"legacy.db{suffix}", Path(f"{path}{suffix}"))
    if not wal:
        with closing(sqlite3.connect(scratch / "legacy.db")) as connection:
            connection.execute("PRAGMA journal_mode=DELETE")
        shutil.copyfile(scratch / "legacy.db", path)
    shutil.rmtree(scratch)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_fresh_database_is_schema_v1_with_foreign_keys(tmp_path):
    pool = open_pool(tmp_path)
    try:
        connection = pool.connection
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert tables(connection) == V1_TABLES
        indexes = {row["name"] for row in connection.execute("PRAGMA index_list(card_jobs)")}
        assert any(
            [col["name"] for col in connection.execute(f"PRAGMA index_info({name})")] == ["job_id"]
            for name in indexes
        )
    finally:
        pool.close()


def test_reopening_a_v1_database_keeps_it(tmp_path):
    pool = open_pool(tmp_path)
    pool.connection.execute("INSERT INTO projects(id, root, created_at) VALUES ('p', '/p', 'now')")
    pool.connection.commit()
    pool.close()
    pool = open_pool(tmp_path)
    try:
        assert pool.connection.execute("SELECT root FROM projects").fetchone()[0] == "/p"
        assert [p.name for p in tmp_path.iterdir() if ".bak" in p.name] == []
    finally:
        pool.close()


def seed_job(connection: sqlite3.Connection, job_id: str = "j", state: str = "queued") -> None:
    connection.execute("INSERT OR IGNORE INTO projects(id, root, created_at) VALUES ('p', '/p', 'now')")
    connection.execute(
        "INSERT INTO jobs(id, project_id, workflow, profile, session, prompt, state, plan_json, created_at, updated_at) "
        "VALUES (?, 'p', 'consult', 'x', 's', 'hi', ?, '{}', 'now', 'now')",
        (job_id, state),
    )


@pytest.mark.parametrize(
    ("sql", "params"),
    [
        ("INSERT INTO jobs(id, project_id, workflow, profile, session, prompt, state, plan_json, created_at, updated_at) "
         "VALUES ('b', 'p', 'w', 'x', 's', 'hi', 'bogus', '{}', 'now', 'now')", ()),
        ("INSERT INTO attempts(job_id, seq, reason, target, state, started_at) VALUES ('j', 1, 'bogus', 't', 'running', 'now')", ()),
        ("INSERT INTO attempts(job_id, seq, reason, target, state, started_at) VALUES ('j', 1, 'initial', 't', 'bogus', 'now')", ()),
        ("INSERT INTO attempts(job_id, seq, reason, target, state, replay_safe, started_at) "
         "VALUES ('j', 1, 'initial', 't', 'running', 2, 'now')", ()),
        ("INSERT INTO questions(job_id, text, state, asked_at) VALUES ('j', 'q', 'bogus', 'now')", ()),
        ("INSERT INTO target_health(target_id, consecutive_failures) VALUES ('t', -1)", ()),
        ("INSERT INTO target_health(target_id, cooldown_s) VALUES ('t', -1)", ()),
        ("UPDATE jobs SET failure_kind='bogus' WHERE id='j'", ()),
    ],
)
def test_check_constraints_reject_unknown_values(tmp_path, sql, params):
    pool = open_pool(tmp_path)
    try:
        seed_job(pool.connection)
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            pool.connection.execute(sql, params)
    finally:
        pool.close()


def test_attempts_and_questions_cascade_with_the_job_and_seq_is_unique(tmp_path):
    pool = open_pool(tmp_path)
    try:
        connection = pool.connection
        seed_job(connection)
        connection.execute(
            "INSERT INTO attempts(job_id, seq, reason, target, state, started_at) VALUES ('j', 1, 'initial', 't', 'running', 'now')"
        )
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
            connection.execute(
                "INSERT INTO attempts(job_id, seq, reason, target, state, started_at) VALUES ('j', 1, 'retry', 't', 'running', 'now')"
            )
        connection.execute("INSERT INTO questions(job_id, text, state, asked_at) VALUES ('j', 'q', 'open', 'now')")
        connection.execute("DELETE FROM jobs WHERE id='j'")
        assert connection.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM questions").fetchone()[0] == 0
    finally:
        pool.close()


@pytest.mark.parametrize("version", [21, 2, 0])
def test_other_user_version_is_renamed_with_wal_and_shm(tmp_path, version, caplog):
    path = tmp_path / "refract.db"
    make_legacy(path, version, wal=True)
    before = {suffix: digest(Path(f"{path}{suffix}")) for suffix in ("", "-wal", "-shm")}
    with caplog.at_level(logging.WARNING):
        pool = open_pool(tmp_path)
    try:
        backup = tmp_path / f"refract.db.{version}.bak"
        for suffix in ("", "-wal", "-shm"):
            assert digest(Path(f"{backup}{suffix}")) == before[suffix]
        assert pool.connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert tables(pool.connection) == V1_TABLES
    finally:
        pool.close()
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING and str(backup) in r.getMessage()]
    assert len(warnings) == 1
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == warnings
    with closing(sqlite3.connect(backup)) as legacy:
        assert legacy.execute("SELECT note FROM legacy").fetchone()[0] == "kept"


def test_missing_wal_and_shm_are_fine(tmp_path):
    path = tmp_path / "refract.db"
    make_legacy(path, 21, wal=False)
    assert not Path(f"{path}-wal").exists()
    pool = open_pool(tmp_path)
    try:
        assert (tmp_path / "refract.db.21.bak").exists()
        assert sorted(p.name for p in tmp_path.iterdir() if p.name.startswith("refract.db.21.bak")) == [
            "refract.db.21.bak", "refract.db.21.bak-shm", "refract.db.21.bak-wal",
        ]
        assert pool.connection.execute("PRAGMA user_version").fetchone()[0] == 1
    finally:
        pool.close()


def test_existing_backup_is_never_overwritten(tmp_path):
    path = tmp_path / "refract.db"
    first = tmp_path / "refract.db.21.bak"
    first.write_bytes(b"older backup")
    make_legacy(path, 21, wal=False)
    pool = open_pool(tmp_path)
    try:
        assert first.read_bytes() == b"older backup"
        extra = [p for p in tmp_path.iterdir() if p.name.startswith("refract.db.21.bak") and p != first]
        assert sorted(p.name for p in extra) == ["refract.db.21.bak.1", "refract.db.21.bak.1-shm", "refract.db.21.bak.1-wal"]
        with closing(sqlite3.connect(tmp_path / "refract.db.21.bak.1")) as legacy:
            assert legacy.execute("SELECT note FROM legacy").fetchone()[0] == "kept"
    finally:
        pool.close()


def test_empty_database_file_is_used_without_a_backup(tmp_path):
    (tmp_path / "refract.db").touch()
    pool = open_pool(tmp_path)
    try:
        assert pool.connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert not [p for p in tmp_path.iterdir() if ".bak" in p.name]
    finally:
        pool.close()


def test_failed_schema_creation_leaves_no_half_built_database(tmp_path, monkeypatch):
    monkeypatch.setattr(schema, "DDL", schema.DDL.replace("PRAGMA user_version", "CREATE TABLE broken (;\nPRAGMA user_version"))
    with pytest.raises(sqlite3.Error):
        schema.initialize(tmp_path / "refract.db")
    with closing(sqlite3.connect(tmp_path / "refract.db")) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        assert tables(connection) == set()


def test_pool_runs_each_transaction_on_one_of_a_fixed_set_of_threads(tmp_path):
    pool = open_pool(tmp_path)
    pool.close()
    pool = Pool(tmp_path / "refract.db", size=3)
    seen: list[set[int]] = []
    lock = threading.Lock()
    barrier = threading.Barrier(3)

    def transaction(connection: sqlite3.Connection, index: int) -> int:
        if index < 3:
            barrier.wait(timeout=5)
        idents = {threading.get_ident()}
        with pool.transaction() as tx:
            assert tx is connection
            tx.execute("INSERT INTO projects(id, root, created_at) VALUES (?, ?, 'now')", (str(index), f"/{index}"))
            idents.add(threading.get_ident())
        with lock:
            seen.append(idents)
        return threading.get_ident()

    try:
        futures = [pool.submit(transaction, index) for index in range(12)]
        workers = {future.result(timeout=10) for future in futures}
        assert all(len(idents) == 1 for idents in seen)
        assert len(workers) == 3
        assert pool.run(lambda c: c.execute("SELECT COUNT(*) FROM projects").fetchone()[0]) == 12
    finally:
        pool.close()


def test_transaction_rolls_back_on_error_and_close_closes_every_connection(tmp_path):
    pool = open_pool(tmp_path)
    with pytest.raises(RuntimeError):
        with pool.transaction() as tx:
            tx.execute("INSERT INTO projects(id, root, created_at) VALUES ('p', '/p', 'now')")
            raise RuntimeError("boom")
    assert pool.connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0
    worker_connection = pool.run(lambda c: c)
    main_connection = pool.connection
    assert worker_connection is not main_connection
    pool.close()
    for connection in (worker_connection, main_connection):
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        pool.connection


@pytest.mark.parametrize(("from_state", "to_state"), [("bogus", "done"), ("todo", "bogus"), (None, "bogus")])
def test_card_moves_reject_unknown_card_states(tmp_path, from_state, to_state):
    pool = open_pool(tmp_path)
    try:
        seed_job(pool.connection)
        pool.connection.execute(
            "INSERT INTO cards(id, project_id, title, state, created_at, updated_at) VALUES ('c', 'p', 't', 'todo', 'now', 'now')"
        )
        with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
            pool.connection.execute(
                "INSERT INTO card_moves(card_id, from_state, to_state, at) VALUES ('c', ?, ?, 'now')", (from_state, to_state)
            )
        pool.connection.execute(
            "INSERT INTO card_moves(card_id, from_state, to_state, at) VALUES ('c', NULL, 'todo', 'now')"
        )
    finally:
        pool.close()


def test_retire_leaves_a_dangling_symlink_backup_intact_and_uses_the_next_name(tmp_path):
    path = tmp_path / "refract.db"
    make_legacy(path, 21, wal=False)
    dangling = tmp_path / "refract.db.21.bak"
    try:
        dangling.symlink_to(tmp_path / "missing-target")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    schema.initialize(path)
    assert dangling.is_symlink() and not dangling.exists()
    with closing(sqlite3.connect(tmp_path / "refract.db.21.bak.1")) as backup:
        assert backup.execute("SELECT note FROM legacy").fetchone()[0] == "kept"
    with closing(sqlite3.connect(path)) as fresh:
        assert fresh.execute("PRAGMA user_version").fetchone()[0] == 1


def test_retire_retries_the_whole_set_and_removes_partial_copies_when_a_name_is_taken_mid_set(tmp_path, monkeypatch):
    path = tmp_path / "refract.db"
    make_legacy(path, 21, wal=True)
    original = schema.shutil.copyfileobj
    raced = []

    def copyfileobj(src, dst, *args, **kwargs):
        if not raced and dst.name == f"{path}.21.bak-wal":
            raced.append(dst.name)
            Path(f"{path}.21.bak-shm").write_bytes(b"racing backup")
        return original(src, dst, *args, **kwargs)

    monkeypatch.setattr(schema.shutil, "copyfileobj", copyfileobj)
    schema.initialize(path)
    assert raced
    assert (tmp_path / "refract.db.21.bak-shm").read_bytes() == b"racing backup"
    assert not (tmp_path / "refract.db.21.bak").exists() and not (tmp_path / "refract.db.21.bak-wal").exists()
    assert (tmp_path / "refract.db.21.bak.1-wal").exists()
    with closing(sqlite3.connect(tmp_path / "refract.db.21.bak.1")) as backup:
        assert backup.execute("SELECT note FROM legacy").fetchone()[0] == "kept"


def test_retire_copy_error_leaves_originals_identical_and_reraises(tmp_path, monkeypatch):
    path = tmp_path / "refract.db"
    make_legacy(path, 21, wal=True)
    before = {suffix: Path(f"{path}{suffix}").read_bytes() for suffix in ("", "-wal", "-shm")}
    original = schema.shutil.copyfileobj

    def copyfileobj(src, dst, *args, **kwargs):
        if dst.name.endswith("-shm"):
            raise OSError("disk full")
        return original(src, dst, *args, **kwargs)

    monkeypatch.setattr(schema.shutil, "copyfileobj", copyfileobj)
    with pytest.raises(OSError, match="disk full"):
        schema.initialize(path)
    for suffix, data in before.items():
        assert Path(f"{path}{suffix}").read_bytes() == data
    assert not [p for p in tmp_path.iterdir() if ".bak" in p.name]


def test_retire_main_unlink_failure_leaves_a_complete_backup_set(tmp_path, monkeypatch):
    path = tmp_path / "refract.db"
    make_legacy(path, 21, wal=True)
    before = {suffix: Path(f"{path}{suffix}").read_bytes() for suffix in ("", "-wal", "-shm")}
    original = schema.os.unlink

    def unlink(name, *args, **kwargs):
        if str(name) == str(path):
            raise PermissionError("locked")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(schema.os, "unlink", unlink)
    with pytest.raises(PermissionError):
        schema.initialize(path)
    backup = f"{path}.21.bak"
    for suffix, data in before.items():
        assert Path(f"{backup}{suffix}").read_bytes() == data
    assert path.read_bytes() == before[""]
    assert not Path(f"{path}-wal").exists() and not Path(f"{path}-shm").exists()


def test_retire_without_sidecars_makes_empty_placeholders_and_a_usable_backup(tmp_path):
    path = tmp_path / "refract.db"
    make_legacy(path, 21, wal=False)
    schema.initialize(path)
    backup = tmp_path / "refract.db.21.bak"
    assert Path(f"{backup}-wal").read_bytes() == b"" and Path(f"{backup}-shm").read_bytes() == b""
    with closing(sqlite3.connect(backup)) as legacy:
        assert legacy.execute("PRAGMA user_version").fetchone()[0] == 21
        assert legacy.execute("SELECT note FROM legacy").fetchone()[0] == "kept"


def test_retire_does_not_pair_the_backup_with_an_unrelated_existing_wal(tmp_path):
    path = tmp_path / "refract.db"
    make_legacy(path, 21, wal=False)
    stray = tmp_path / "refract.db.21.bak-wal"
    stray.write_bytes(b"unrelated wal")
    schema.initialize(path)
    assert stray.read_bytes() == b"unrelated wal"
    assert not (tmp_path / "refract.db.21.bak").exists() and not (tmp_path / "refract.db.21.bak-shm").exists()
    with closing(sqlite3.connect(tmp_path / "refract.db.21.bak.1")) as backup:
        assert backup.execute("SELECT note FROM legacy").fetchone()[0] == "kept"


@pytest.mark.skipif(os.name == "nt", reason="directories cannot be opened for fsync on Windows")
def test_retire_fsyncs_the_directory_after_the_backups_and_before_any_unlink(tmp_path, monkeypatch):
    path = tmp_path / "refract.db"
    make_legacy(path, 21, wal=True)
    events: list[str] = []
    directory = os.stat(tmp_path)
    original_fsync, original_unlink = os.fsync, os.unlink

    def fsync(fd):
        stat = os.fstat(fd)
        if (stat.st_dev, stat.st_ino) == (directory.st_dev, directory.st_ino):
            events.append("fsync-dir")
        return original_fsync(fd)

    def unlink(name, *args, **kwargs):
        if str(name).startswith(str(path)) and ".bak" not in str(name):
            events.append("unlink-original")
        return original_unlink(name, *args, **kwargs)

    monkeypatch.setattr(schema.os, "fsync", fsync)
    monkeypatch.setattr(schema.os, "unlink", unlink)
    schema.initialize(path)
    assert events.index("fsync-dir") < events.index("unlink-original")
    assert events.count("fsync-dir") >= 1
    assert len(Path(f"{path}.21.bak").read_bytes()) > 0
