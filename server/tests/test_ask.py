from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest

from refract.scheduling.asks import (
    NO_ANSWER_TEXT,
    AskAuthError,
    AskConflictError,
    AskRegistry,
)
from refract.store.database import Database
from refract.scheduling.hub import Hub


def _make(tmp_path: Path, *job_ids: str) -> tuple[AskRegistry, Database, Hub]:
    db = Database(tmp_path / "refract.db")
    db.upsert_project(project_id="proj", root=str(tmp_path))
    for job_id in job_ids:
        db.create_job(
            job_id=job_id,
            project_id="proj",
            session=job_id,
            workflow="implement",
            profile="balanced",
            prompt="work",
            plan_json="{}",
            fresh=True,
        )
        db.start_job(job_id)
    hub = Hub()
    return AskRegistry(db, hub), db, hub


async def _wait_open(registry: AskRegistry, job_id: str):
    """Wait on a hub subscription for the job's open question row."""
    with registry._hub.subscribe({job_id}) as sub:
        while True:
            sub.clear()
            pending = registry.get_pending(job_id)
            if pending is not None:
                return pending
            await sub.wait(2)


def _states(db: Database, job_id: str) -> list[str]:
    conn = sqlite3.connect(db._path)
    try:
        return [r[0] for r in conn.execute("SELECT state FROM questions WHERE job_id = ?", (job_id,))]
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_issue_token_and_validate(tmp_path) -> None:
    registry, db, _ = _make(tmp_path)
    token = registry.issue_token("job-123")
    assert isinstance(token, str)
    assert len(token) > 16
    assert registry.validate_token(token) == "job-123"
    assert registry.validate_token(token, job_id="job-123") == "job-123"
    with pytest.raises(AskAuthError):
        registry.validate_token(token, job_id="job-456")
    with pytest.raises(AskAuthError):
        registry.validate_token("unknown-token")
    with pytest.raises(AskAuthError):
        registry.validate_token("\ud800")
    with pytest.raises(AskAuthError):
        registry.validate_token(token, job_id="\ud800")
    db.close()


@pytest.mark.asyncio
async def test_revoke_token(tmp_path) -> None:
    registry, db, _ = _make(tmp_path)
    token = registry.issue_token("job-123")
    registry.revoke_token("job-123")
    with pytest.raises(AskAuthError):
        registry.validate_token(token)
    db.close()


@pytest.mark.asyncio
async def test_ask_writes_open_row_and_publishes_question_and_answer(tmp_path) -> None:
    registry, db, hub = _make(tmp_path, "job-1")
    token = registry.issue_token("job-1")
    with hub.subscribe({"job-1"}) as sub:
        task = asyncio.create_task(registry.ask(token, "How do I fix this?", timeout_s=2.0))
        pending = await _wait_open(registry, "job-1")
        assert pending.text == "How do I fix this?"
        assert _states(db, "job-1") == ["open"]
        assert registry.deliver_answer("job-1", "This is the coordinator answer")
        assert await task == "This is the coordinator answer"
        kinds = [kind for _job, kind in sub.drain()]
    assert kinds[0] == "question"
    assert "answer" in kinds
    assert _states(db, "job-1") == ["answered"]
    assert not registry.has_pending("job-1")
    db.close()


@pytest.mark.asyncio
async def test_concurrent_second_answer_returns_false_for_invalid_state(tmp_path) -> None:
    registry, db, _ = _make(tmp_path, "job-1")
    token = registry.issue_token("job-1")
    task = asyncio.create_task(registry.ask(token, "Pick", timeout_s=2.0))
    await _wait_open(registry, "job-1")
    results = [registry.deliver_answer("job-1", "first"), registry.deliver_answer("job-1", "second")]
    assert results == [True, False]
    assert await task == "first"
    db.close()


@pytest.mark.asyncio
async def test_ask_conflict_when_already_pending(tmp_path) -> None:
    registry, db, _ = _make(tmp_path, "job-1")
    token = registry.issue_token("job-1")
    task1 = asyncio.create_task(registry.ask(token, "Question 1", timeout_s=2.0))
    await _wait_open(registry, "job-1")
    with pytest.raises(AskConflictError):
        await registry.ask(token, "Question 2", timeout_s=1.0)
    registry.deliver_answer("job-1", "Done")
    await task1
    db.close()


@pytest.mark.asyncio
async def test_ask_timeout_marks_row_expired(tmp_path) -> None:
    registry, db, _ = _make(tmp_path, "job-1")
    token = registry.issue_token("job-1")
    assert await registry.ask(token, "Will this time out?", timeout_s=0.05) == NO_ANSWER_TEXT
    assert _states(db, "job-1") == ["expired"]
    assert not registry.has_pending("job-1")
    db.close()


@pytest.mark.asyncio
async def test_ask_timeout_is_bounded_by_workflow_deadline(tmp_path) -> None:
    registry, db, _ = _make(tmp_path, "job-deadline")
    token = registry.issue_token("job-deadline", workflow_timeout_s=0.15)
    await asyncio.sleep(0.06)  # test setup: let part of the workflow deadline elapse
    started = asyncio.get_running_loop().time()
    answer = await registry.ask(token, "Late question", timeout_s=2.0)
    assert answer == NO_ANSWER_TEXT
    assert asyncio.get_running_loop().time() - started < 0.15
    assert not registry.has_pending("job-deadline")
    db.close()


@pytest.mark.asyncio
async def test_ask_timeout_preserves_unlimited_workflow_and_configured_cap(tmp_path) -> None:
    registry, db, _ = _make(tmp_path, "job-normal", "job-unlimited", "job-short")
    normal = registry.issue_token("job-normal", workflow_timeout_s=1.0)
    task = asyncio.create_task(registry.ask(normal, "Normal question", timeout_s=0.5))
    await _wait_open(registry, "job-normal")
    registry.deliver_answer("job-normal", "normal answer")
    assert await task == "normal answer"

    unlimited = registry.issue_token("job-unlimited", workflow_timeout_s=0)
    task = asyncio.create_task(registry.ask(unlimited, "Question", timeout_s=0.5))
    await _wait_open(registry, "job-unlimited")
    registry.deliver_answer("job-unlimited", "answered")
    assert await task == "answered"

    short = registry.issue_token("job-short", workflow_timeout_s=0.03)
    started = asyncio.get_running_loop().time()
    assert await registry.ask(short, "Short workflow", timeout_s=1.0) == NO_ANSWER_TEXT
    assert asyncio.get_running_loop().time() - started < 0.2
    db.close()


@pytest.mark.asyncio
async def test_ask_revoke_token_releases_with_no_answer_text(tmp_path) -> None:
    registry, db, _ = _make(tmp_path, "job-1")
    token = registry.issue_token("job-1")
    task = asyncio.create_task(registry.ask(token, "Waiting for answer...", timeout_s=2.0))
    await _wait_open(registry, "job-1")
    registry.revoke_token("job-1")
    assert await task == NO_ANSWER_TEXT
    assert _states(db, "job-1") == ["expired"]
    db.close()


@pytest.mark.asyncio
async def test_ask_cancel_expires_row_and_removes_subscriber(tmp_path) -> None:
    registry, db, hub = _make(tmp_path, "job-1")
    token = registry.issue_token("job-1")
    task = asyncio.create_task(registry.ask(token, "Question", timeout_s=5))
    await _wait_open(registry, "job-1")
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert _states(db, "job-1") == ["expired"]
    assert hub.subscriber_count == 0
    db.close()


@pytest.mark.asyncio
async def test_answer_after_question_deadline_is_rejected(tmp_path) -> None:
    registry, db, _ = _make(tmp_path, "job-late")
    token = registry.issue_token("job-late")
    assert await registry.ask(token, "Still there?", timeout_s=0.05) == NO_ANSWER_TEXT
    assert registry.deliver_answer("job-late", "too late") is False
    assert _states(db, "job-late") == ["expired"]
    db.close()


@pytest.mark.asyncio
async def test_revoked_tokens_are_not_retained(tmp_path) -> None:
    registry, db, _ = _make(tmp_path)
    tokens = [registry.issue_token(f"job-{index}", workflow_timeout_s=60) for index in range(20)]
    tokens.append(registry.issue_token("job-0"))
    for index in range(20):
        registry.revoke_token(f"job-{index}")
    assert registry._tokens == {}
    for token in tokens:
        with pytest.raises(AskAuthError, match="unknown"):
            registry.validate_token(token)
    db.close()


def test_ask_client_timeout_is_ask_timeout_plus_ten(monkeypatch, capsys) -> None:
    import socket

    from refract import cli

    seen: dict[str, float] = {}

    def unresponsive(request, timeout=None):
        seen["timeout"] = timeout
        raise socket.timeout("timed out")

    monkeypatch.setattr(cli, "urlopen", unresponsive)
    monkeypatch.setenv("REFRACT_ASK_URL", "http://127.0.0.1:1/ask")
    monkeypatch.setenv("REFRACT_ASK_TOKEN", "token")
    monkeypatch.setenv("REFRACT_ASK_TIMEOUT_S", "45")

    with pytest.raises(SystemExit) as exc_info:
        cli.main(["ask", "Anyone there?"])

    assert exc_info.value.code == 1
    assert seen["timeout"] == 55
    assert "connection failed" in capsys.readouterr().err.lower()

    monkeypatch.delenv("REFRACT_ASK_TIMEOUT_S")
    with pytest.raises(SystemExit):
        cli.main(["ask", "Anyone there?"])
    assert seen["timeout"] == 310


@pytest.mark.asyncio
async def test_execution_attempt_injects_and_revokes_token_and_keeps_secret(tmp_path, caplog) -> None:
    import logging
    from refract.config import DaemonConfig, TargetConfig
    from refract.store.database import Database
    from refract.runner.drivers import DriverRegistry
    from refract.runner.attempts import TargetExecutor
    from tests.orchestration_helpers import config, register_project

    caplog.set_level(logging.DEBUG)
    home = tmp_path / "home"
    home.mkdir()
    cfg = config(home)
    db = Database(cfg.database_path)
    registry = AskRegistry(db, Hub())

    captured_env: dict[str, str] = {}

    class MockDrivers:
        def available(self, target):
            return True

        async def supports_structured_streaming(self, target, cancel_event=None):
            return False

        async def execute(self, *, target, prompt, cwd, session_id, timeout_s, cancel_event, on_event=None, env=None, on_spawn=None):
            nonlocal captured_env
            if env:
                captured_env.update(env)
            from refract.runner.drivers import DriverResult
            return DriverResult("SUCCESS", "sess-1", "Done", "", "")

    executor = TargetExecutor(cfg, db, MockDrivers(), ask_registry=registry)
    job_id = "job-exec-1"
    project = db.upsert_project(project_id="proj-1", root=str(tmp_path))
    db.create_job(
        job_id=job_id,
        project_id="proj-1",
        session="main",
        workflow="implement",
        profile="balanced",
        prompt="do work",
        plan_json="{}",
        fresh=True,
    )
    db.start_job(job_id)

    target = TargetConfig(id="primary", backend="codex")
    from refract.runner.planning import ExecutionPlan
    from refract.config import TargetSelection
    plan = ExecutionPlan(
        profile="balanced",
        workflow="implement",
        selection=TargetSelection(targets=("primary",)),
        targets=(target,),
    )
    from refract.scheduling.cancel import CancelEvent
    cancel_event = CancelEvent()

    result = await executor.execute(
        job_id=job_id,
        project=project,
        workflow="implement",
        session="main",
        plan=plan,
        prompt="do work",
        cwd=tmp_path,
        cancel_event=cancel_event,
    )

    assert result.result.outcome == "SUCCESS"
    assert "REFRACT_ASK_URL" in captured_env
    assert "REFRACT_ASK_TOKEN" in captured_env
    assert captured_env["REFRACT_ASK_TIMEOUT_S"] == str(cfg.ask_timeout_s)
    issued_token = captured_env["REFRACT_ASK_TOKEN"]

    # Token is revoked after the attempt ends
    with pytest.raises(AskAuthError):
        registry.validate_token(issued_token)

    # Token is absent from log records
    for record in caplog.records:
        assert issued_token not in record.getMessage()
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            for v in record.extra.values():
                assert issued_token not in str(v)

    # Token is absent from the stored job row
    assert all(issued_token not in str(value) for value in db.job_record(job_id).values())


@pytest.mark.asyncio
async def test_runtime_cancel_releases_pending_ask(tmp_path) -> None:
    from refract.config import load_config
    from refract.runtime import Runtime
    from tests.orchestration_helpers import config

    home = tmp_path / "home"
    home.mkdir()
    cfg = config(home)
    runtime = Runtime(cfg)
    try:
        runtime.database.upsert_project(project_id="proj-c", root=str(tmp_path))
        runtime.database.create_job(
            job_id="job-cancel-test",
            project_id="proj-c",
            workflow="implement",
            profile="balanced",
            prompt="work",
            plan_json="{}",
            session="main",
        )
        runtime.database.start_job("job-cancel-test")
        token = runtime.ask_registry.issue_token("job-cancel-test")
        task = asyncio.create_task(
            runtime.ask_registry.ask(token, "Pending question", timeout_s=10.0)
        )
        await _wait_open(runtime.ask_registry, "job-cancel-test")

        await runtime.cancel("job-cancel-test")
        answer = await task
        assert answer == NO_ANSWER_TEXT
        assert not runtime.ask_registry.has_pending("job-cancel-test")
        with pytest.raises(AskAuthError):
            await runtime.ask_registry.ask(token, "After cancellation", timeout_s=1.0)
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_deliver_answer_with_matching_and_mismatched_expected_question_id(tmp_path) -> None:
    registry, db, _ = _make(tmp_path, "job-qid-test")
    token = registry.issue_token("job-qid-test")
    task = asyncio.create_task(registry.ask(token, "Question with ID", timeout_s=2.0))
    pending = await _wait_open(registry, "job-qid-test")
    assert not registry.deliver_answer("job-qid-test", "Wrong answer", expected_question_id="wrong-qid")
    assert registry.has_pending("job-qid-test")
    assert registry.deliver_answer("job-qid-test", "Right answer", expected_question_id=pending.question_id)
    assert not registry.has_pending("job-qid-test")
    assert await task == "Right answer"
    db.close()


@pytest.mark.asyncio
async def test_runtime_job_answer_with_expected_question_id(tmp_path) -> None:
    from refract.runtime import OrchestrationError, Runtime
    from tests.orchestration_helpers import config

    home = tmp_path / "home"
    home.mkdir()
    cfg = config(home)
    runtime = Runtime(cfg)
    try:
        job_id = "job-qid-runtime"
        runtime.database.upsert_project(project_id="proj-qid", root=str(tmp_path))
        runtime.database.create_job(
            job_id=job_id,
            project_id="proj-qid",
            workflow="implement",
            profile="balanced",
            prompt="work",
            plan_json="{}",
            session="main",
        )
        runtime.database.start_job(job_id)

        token = runtime.ask_registry.issue_token(job_id)
        task = asyncio.create_task(
            runtime.ask_registry.ask(token, "Runtime question", timeout_s=5.0)
        )
        await asyncio.sleep(0.01)
        pending = await _wait_open(runtime.ask_registry, job_id)
        assert pending is not None

        # Mismatch raises OrchestrationError with code "invalid_state" and keeps question pending
        with pytest.raises(OrchestrationError) as exc_info:
            await runtime.job_answer(job_id, "Bad answer", expected_question_id="wrong-id")
        assert exc_info.value.code == "invalid_state"
        assert runtime.ask_registry.has_pending(job_id)

        # Match succeeds
        res = await runtime.job_answer(job_id, "Good answer", expected_question_id=pending.question_id)
        assert res.success is True
        assert await task == "Good answer"
        assert not runtime.ask_registry.has_pending(job_id)
    finally:
        runtime.database.close()




@pytest.mark.asyncio
@pytest.mark.parametrize("question", ["", "   "])
async def test_ask_rejects_blank_question_before_validating_token(tmp_path, question) -> None:
    registry, db, _ = _make(tmp_path)
    with pytest.raises(ValueError, match="question must be a non-empty string"):
        await registry.ask("unknown-token", question, timeout_s=1.0)
    db.close()


@pytest.mark.asyncio
async def test_ask_with_no_time_left_returns_no_answer_without_writing_a_row(tmp_path) -> None:
    registry, db, _ = _make(tmp_path, "job-1")
    token = registry.issue_token("job-1")
    assert await registry.ask(token, "Question", timeout_s=0) == NO_ANSWER_TEXT
    assert _states(db, "job-1") == []
    db.close()
