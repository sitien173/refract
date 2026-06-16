from pathlib import Path

import pytest

from openmcp.backends.agy import AgyParams, execute as agy_execute
from openmcp.backends.codex import CodexParams, execute as codex_execute
from openmcp.backends.gemini import GeminiParams, execute as gemini_execute
from openmcp.server import run as server_run


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
    out = await agy_execute(AgyParams(PROMPT=PROMPT, cd=Path.cwd()))
    _assert_live_result("agy", out)


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_codex_execute() -> None:
    out = await codex_execute(CodexParams(PROMPT=PROMPT, cd=Path.cwd()))
    _assert_live_result("codex", out)


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_gemini_route_to_agy(monkeypatch) -> None:
    monkeypatch.setenv("OPENMCP_GEMINI_ROUTE_TO_AGY", "true")
    monkeypatch.setenv("OPENMCP_AGY_MODEL_DEFAULT", "gemini-3.5-flash")

    out = await server_run(backend="gemini", PROMPT=PROMPT, cd=Path.cwd())

    assert out.get("success") is True, out.get("error", "")
    assert out.get("agent_messages", "").strip(), "gemini route returned empty agent_messages"
    assert "PONG" in out.get("agent_messages", "").upper(), "gemini route output missing PONG"
    assert out.get("SESSION_ID", "").strip(), "gemini route returned empty SESSION_ID"


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_gemini_execute() -> None:
    out = await gemini_execute(GeminiParams(PROMPT=PROMPT, cd=Path.cwd(), model="gemini-2.5-flash"))
    _assert_live_result("gemini", out)
