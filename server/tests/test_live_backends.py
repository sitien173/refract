import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from refract.backends import BackendParams
from refract.backends.agy import execute as agy_execute
from refract.backends.claude import execute as claude_execute
from refract.backends.codex import execute as codex_execute
from refract.config import TargetConfig
from refract.drivers import DriverRegistry

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


@pytest.mark.live
@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["codex", "claude", "agy", "pi"])
@pytest.mark.parametrize("read_only", [False, True], ids=["normal", "read_only"])
async def test_live_ask_coordinator(backend: str, read_only: bool, tmp_path: Path) -> None:
    """Probe real target policy, inherited env, and tool-shell loopback access."""
    token = secrets.token_urlsafe(32)
    answer = "ASK_OK_" + secrets.token_hex(12)
    received = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            try:
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                valid = (
                    self.path == "/ask"
                    and secrets.compare_digest(body.get("token", ""), token)
                    and body.get("question") == "probe"
                )
            except (ValueError, TypeError, KeyError):
                valid = False
            if not valid:
                self.send_response(403)
                self.end_headers()
                return
            received.set()
            payload = json.dumps({"answer": answer}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = HTTPServer(("127.0.0.1", 0), Handler)
    server.timeout = 2
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    cli_bin = Path(__file__).resolve().parents[1] / ".venv" / "bin"
    env = {
        "PATH": str(cli_bin) + os.pathsep + os.environ.get("PATH", ""),
        "REFRACT_ASK_URL": f"http://127.0.0.1:{server.server_port}/ask",
        "REFRACT_ASK_TOKEN": token,
    }
    prompt = (
        "This is a bounded command reachability probe, not an implementation task. "
        "Run exactly `refract ask probe` using your shell tool, then reply with "
        "exactly its stdout. Use the inherited environment without inspecting or "
        "printing it. Do not read files, modify files, or change permissions. "
        "If shell tools are unavailable or the command fails, reply with BLOCKED "
        "and a short reason. Do not use another tool to bypass restrictions."
    )
    try:
        out = await DriverRegistry().execute(
            target=TargetConfig(id="ask-probe", backend=backend, read_only=read_only),
            prompt=prompt,
            cwd=tmp_path,
            session_id="",
            timeout_s=90,
            cancel_event=threading.Event(),
            env=env,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)

    # Never include raw output, env, or exception locals in probe reports.
    mode = "read_only" if read_only else "normal"
    observed = received.is_set()
    exact_answer = out.text.strip() == answer
    if out.outcome == "SUCCESS" and observed and exact_answer:
        print(f"ASK_PROBE {backend}/{mode}: reached listener; exact answer")
        return
    if out.outcome == "SUCCESS" and not observed and "BLOCKED" in out.text:
        restriction = (
            "shell unavailable under target policy"
            if read_only and backend in {"claude", "pi"}
            else "command unavailable or failed"
        )
        pytest.xfail(f"{backend}/{mode}: BLOCKED fallback; {restriction}; listener not reached")
    diagnostic = (out.error + " " + out.text).lower()
    reason = "unclassified backend failure"
    for phrase, label in [
        ("trusted directory", "untrusted working directory"),
        ("not a git repository", "non-Git working directory"),
        ("timed out", "backend timeout"),
        ("authentication", "authentication failure"),
        ("not logged in", "authentication unavailable"),
    ]:
        if phrase in diagnostic:
            reason = label
            break
    codex_home = os.environ.get("CODEX_HOME")
    if backend == "codex" and codex_home and not Path(codex_home).is_dir():
        reason = "inherited CODEX_HOME directory does not exist"
    pytest.fail(
        f"{backend}/{mode}: outcome={out.outcome}; reason={reason}; "
        f"listener_reached={observed}; exact_answer={exact_answer}",
        pytrace=False,
    )


@pytest.mark.live
@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["codex", "claude", "agy", "pi"])
async def test_live_telemetry_probe(backend: str, tmp_path: Path) -> None:
    """Opt-in live telemetry probe. Never treats missing prerequisites as passes."""
    if not os.environ.get("REFRACT_LIVE_TELEMETRY_OPT_IN"):
        pytest.skip("Live telemetry probe requires explicit REFRACT_LIVE_TELEMETRY_OPT_IN=1")

    codex_home = os.environ.get("CODEX_HOME")
    if backend == "codex" and codex_home and not Path(codex_home).is_dir():
        pytest.fail(f"{backend}: missing prerequisite (CODEX_HOME directory does not exist)", pytrace=False)

    driver = DriverRegistry()
    prompt = "Reply with exactly: PONG"
    out = await driver.execute(
        target=TargetConfig(id=f"{backend}-telemetry-probe", backend=backend),
        prompt=prompt,
        cwd=tmp_path,
        session_id="",
        timeout_s=90,
        cancel_event=threading.Event(),
    )
    if out.outcome == "FATAL":
        if out.error_class in {"missing_cli", "bad_cd"}:
            pytest.fail(f"{backend}: missing prerequisite ({out.error_class}): {out.error}", pytrace=False)
        pytest.fail(f"{backend}: execution failed ({out.error_class}): {out.error}", pytrace=False)

    assert out.outcome == "SUCCESS", f"{backend} probe failed: outcome={out.outcome}"
    if out.telemetry:
        assert isinstance(out.telemetry, dict)
        assert "version" in out.telemetry
        assert "completeness" in out.telemetry

