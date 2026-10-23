from pathlib import Path

import pytest

from refract.backends import BackendParams
from refract.backends.agy import execute as agy_execute
from refract.backends.claude import execute as claude_execute
from refract.backends.codex import execute as codex_execute


PROMPT = "Reply with exactly the word PONG and nothing else."


def _assert_live_result(name: str, out) -> None:
    if out.outcome == "FATAL":
        if out.error_class in {"missing_cli", "bad_cd"}:
            pytest.skip(f"{name}: {out.error_class}")
        pytest.fail(f"{name} fatal error ({out.error_class}): {out.error}")

    assert out.outcome == "OK", f"{name} unexpected outcome: {out.outcome}"
    assert out.agent_messages.strip(), f"{name} returned empty agent_messages"
    assert "PONG" in out.agent_messages.upper(), f"{name} output missing PONG"
    assert out.SESSION_ID.strip(), f"{name} returned empty SESSION_ID"


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_agy_execute() -> None:
    out = agy_execute(BackendParams(PROMPT=PROMPT, cd=Path.cwd()))
    _assert_live_result("agy", out)


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_codex_execute() -> None:
    out = codex_execute(BackendParams(PROMPT=PROMPT, cd=Path.cwd()))
    _assert_live_result("codex", out)


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_claude_execute() -> None:
    out = claude_execute(BackendParams(PROMPT=PROMPT, cd=Path.cwd()))
    _assert_live_result("claude", out)
