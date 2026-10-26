from __future__ import annotations

import asyncio
import pytest

from refract.ask import (
    NO_ANSWER_TEXT,
    AskAuthError,
    AskConflictError,
    AskRegistry,
)


@pytest.mark.asyncio
async def test_issue_token_and_validate() -> None:
    registry = AskRegistry()
    token = registry.issue_token("job-123")
    assert isinstance(token, str) and len(token) > 16

    # Valid token resolves to the job id
    assert registry.validate_token(token) == "job-123"
    assert registry.validate_token(token, job_id="job-123") == "job-123"

    # Wrong job id raises AskAuthError
    with pytest.raises(AskAuthError):
        registry.validate_token(token, job_id="job-456")

    # Unknown token raises AskAuthError
    with pytest.raises(AskAuthError):
        registry.validate_token("unknown-token")

    # Lone surrogate token and wrong job raise AskAuthError
    with pytest.raises(AskAuthError):
        registry.validate_token("\ud800")
    with pytest.raises(AskAuthError):
        registry.validate_token(token, job_id="\ud800")


@pytest.mark.asyncio
async def test_revoke_token() -> None:
    registry = AskRegistry()
    token = registry.issue_token("job-123")
    registry.revoke_token("job-123")

    with pytest.raises(AskAuthError):
        registry.validate_token(token)


@pytest.mark.asyncio
async def test_ask_and_deliver_answer() -> None:
    registry = AskRegistry()
    token = registry.issue_token("job-1")

    async def _answer_soon():
        await asyncio.sleep(0.02)
        assert registry.has_pending("job-1")
        assert registry.deliver_answer("job-1", "This is the coordinator answer")

    asyncio.create_task(_answer_soon())
    answer = await registry.ask(token, "How do I fix this?", timeout_s=1.0)
    assert answer == "This is the coordinator answer"
    assert not registry.has_pending("job-1")


@pytest.mark.asyncio
async def test_ask_conflict_when_already_pending() -> None:
    registry = AskRegistry()
    token = registry.issue_token("job-1")

    task1 = asyncio.create_task(registry.ask(token, "Question 1", timeout_s=1.0))
    await asyncio.sleep(0.01)

    with pytest.raises(AskConflictError):
        await registry.ask(token, "Question 2", timeout_s=1.0)

    registry.deliver_answer("job-1", "Done")
    await task1


@pytest.mark.asyncio
async def test_ask_timeout_returns_no_answer_text() -> None:
    registry = AskRegistry()
    token = registry.issue_token("job-1")

    answer = await registry.ask(token, "Will this time out?", timeout_s=0.02)
    assert answer == NO_ANSWER_TEXT
    assert not registry.has_pending("job-1")


@pytest.mark.asyncio
async def test_ask_timeout_is_bounded_by_workflow_deadline() -> None:
    registry = AskRegistry()
    token = registry.issue_token("job-deadline", workflow_timeout_s=0.15)
    await asyncio.sleep(0.06)

    started = asyncio.get_running_loop().time()
    answer = await registry.ask(token, "Late question", timeout_s=2.0)
    elapsed = asyncio.get_running_loop().time() - started

    assert answer == NO_ANSWER_TEXT
    assert elapsed < 0.15
    assert not registry.has_pending("job-deadline")


@pytest.mark.asyncio
async def test_ask_timeout_preserves_unlimited_workflow_and_configured_cap() -> None:
    registry = AskRegistry()
    normal = registry.issue_token("job-normal", workflow_timeout_s=1.0)
    async def answer_normal():
        await asyncio.sleep(0.01)
        registry.deliver_answer("job-normal", "normal answer")
    asyncio.create_task(answer_normal())
    assert await registry.ask(normal, "Normal question", timeout_s=0.5) == "normal answer"

    unlimited = registry.issue_token("job-unlimited", workflow_timeout_s=0)
    async def answer_soon():
        await asyncio.sleep(0.01)
        registry.deliver_answer("job-unlimited", "answered")
    asyncio.create_task(answer_soon())
    assert await registry.ask(unlimited, "Question", timeout_s=0.5) == "answered"

    short = registry.issue_token("job-short", workflow_timeout_s=0.03)
    started = asyncio.get_running_loop().time()
    assert await registry.ask(short, "Short workflow", timeout_s=1.0) == NO_ANSWER_TEXT
    assert asyncio.get_running_loop().time() - started < 0.2


@pytest.mark.asyncio
async def test_ask_cancel_releases_with_no_answer_text() -> None:
    registry = AskRegistry()
    token = registry.issue_token("job-1")

    async def _cancel_soon():
        await asyncio.sleep(0.02)
        registry.cancel("job-1")

    asyncio.create_task(_cancel_soon())
    answer = await registry.ask(token, "Waiting for answer...", timeout_s=1.0)
    assert answer == NO_ANSWER_TEXT
    assert not registry.has_pending("job-1")


@pytest.mark.asyncio
async def test_ask_atomic_validation_and_registration_rejects_revoked_token(monkeypatch) -> None:
    from refract.ask import PendingQuestion
    registry = AskRegistry()
    token = registry.issue_token("job-race-1")

    orig_init = PendingQuestion.__init__

    def _fake_init(self, *args, **kwargs):
        orig_init(self, *args, **kwargs)
        registry.revoke_token("job-race-1")

    monkeypatch.setattr(PendingQuestion, "__init__", _fake_init)

    with pytest.raises(AskAuthError):
        await registry.ask(token, "Question during revoke race", timeout_s=0.05)

    assert not registry.has_pending("job-race-1")



def test_stream_shell_command_lines_injects_env() -> None:
    import sys
    from refract.backends import BackendParams
    from refract.backends._shell import stream_shell_command_lines

    cmd = [
        sys.executable,
        "-c",
        "import os; print('URL=' + os.environ.get('REFRACT_ASK_URL', '')); print('TOK=' + os.environ.get('REFRACT_ASK_TOKEN', ''))",
    ]
    lines = list(
        stream_shell_command_lines(
            cmd,
            executable_name=sys.executable,
            terminate_wait_s=5,
            line_transform=lambda line: line.strip(),
            env={"REFRACT_ASK_URL": "http://127.0.0.1:8765/ask", "REFRACT_ASK_TOKEN": "secret-12345"},
        )
    )
    assert "URL=http://127.0.0.1:8765/ask" in lines
    assert "TOK=secret-12345" in lines


@pytest.mark.asyncio
async def test_execution_attempt_injects_and_revokes_token_and_keeps_secret(tmp_path, caplog) -> None:
    import logging
    from refract.backends import BackendParams
    from refract.config import DaemonConfig, TargetConfig
    from refract.database import Database
    from refract.drivers import DriverRegistry
    from refract.execution import TargetExecutor
    from tests.orchestration_helpers import config, register_project

    caplog.set_level(logging.DEBUG)
    home = tmp_path / "home"
    home.mkdir()
    cfg = config(home)
    db = Database(cfg.database_path)
    registry = AskRegistry()

    captured_env: dict[str, str] = {}

    class MockDrivers:
        def available(self, target):
            return True

        def supports_structured_streaming(self, target):
            return False

        async def execute(self, *, target, prompt, cwd, session_id, timeout_s, cancel_event, emitter=None, env=None):
            nonlocal captured_env
            if env:
                captured_env.update(env)
            from refract.drivers import DriverResult
            return DriverResult("SUCCESS", "sess-1", "Done", "", "")

    executor = TargetExecutor(cfg, db, MockDrivers(), ask_registry=registry)
    job_id = "job-exec-1"
    project = db.upsert_project(project_id="proj-1", alias="alias", root=str(tmp_path))
    db.create_job(
        job_id=job_id,
        project_id="proj-1",
        context_key="main",
        workflow="implement",
        profile="balanced",
        prompt="do work",
        execution_plan_json="{}",
        fresh_session=True,
    )
    db.start_job(job_id)

    target = TargetConfig(id="primary", backend="codex")
    from refract.planning import ExecutionPlan
    from refract.config import TargetSelection
    plan = ExecutionPlan(
        profile="balanced",
        workflow="implement",
        selection=TargetSelection(targets=("primary",)),
        targets=(target,),
    )
    from refract.scheduler import CancelEvent
    cancel_event = CancelEvent()

    result = await executor.execute(
        job_id=job_id,
        project=project,
        workflow="implement",
        context_key="main",
        plan=plan,
        prompt="do work",
        cwd=tmp_path,
        cancel_event=cancel_event,
    )

    assert result.result.outcome == "SUCCESS"
    assert "REFRACT_ASK_URL" in captured_env
    assert "REFRACT_ASK_TOKEN" in captured_env
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

    # Token is absent from database events
    events = db.events(job_id)
    for ev in events:
        import json
        ev_str = json.dumps(ev)
        assert issued_token not in ev_str


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
        token = runtime.ask_registry.issue_token("job-cancel-test")
        task = asyncio.create_task(
            runtime.ask_registry.ask(token, "Pending question", timeout_s=10.0)
        )
        await asyncio.sleep(0.01)
        assert runtime.ask_registry.has_pending("job-cancel-test")

        runtime.database.upsert_project(project_id="proj-c", alias="alias-c", root=str(tmp_path))
        runtime.database.create_job(
            job_id="job-cancel-test",
            project_id="proj-c",
            workflow="implement",
            profile="balanced",
            prompt="work",
            execution_plan_json="{}",
            context_key="main",
        )
        runtime.database.start_job("job-cancel-test")

        await runtime.cancel("job-cancel-test")
        answer = await task
        assert answer == NO_ANSWER_TEXT
        assert not runtime.ask_registry.has_pending("job-cancel-test")
        with pytest.raises(AskAuthError):
            await runtime.ask_registry.ask(token, "After cancellation", timeout_s=1.0)
    finally:
        runtime.database.close()


