from __future__ import annotations

import asyncio
import json
import logging
import os
import stat
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from refract.config import DaemonConfig, TargetConfig, TargetSelection, TelemetryConfig, load_config
from refract.drivers import DriverResult
from refract import pricing, product_telemetry
from refract.database import Database
from refract.pricing import PricingError
from refract.product_telemetry import (
    BATCH_SIZE,
    COLLECTOR_URL,
    SendStatus,
    install_id,
    _redact,
    next_backoff,
    purge,
    send_outbox_once,
    telemetry_decision,
)
from refract.runtime import Runtime


@pytest.fixture
def config_factory(tmp_path):
    def make(*, enabled: bool = False, targets: tuple[TargetConfig, ...] = (),
             config_path=None) -> DaemonConfig:
        home = tmp_path / "home"
        home.mkdir(exist_ok=True)
        return DaemonConfig(
            home=home, targets=targets,
            telemetry=TelemetryConfig(enabled),
            config_path=config_path,
        )
    return make


def _terminal_job(runtime: Runtime, *, job_id: str = "job-one", root: str = "/project") -> None:
    project = runtime.database.upsert_project(project_id=f"project-{job_id}", root=root)
    runtime.database.create_job(
        job_id=job_id, project_id=project.id, workflow="implement", profile="balanced",
        prompt="prompt-sentinel", execution_plan_json=json.dumps({"targets": []}),
        session="session-sentinel",
    )
    runtime.database.finish_job(
        job_id, "succeeded", text="result-sentinel", target="target", model="model",
        tokens={"context_used": 7, "context_window": 8, "input": 9, "output": 10,
                "cache_read": 11, "cache_write": 12},
    )
    with runtime.database._connection:
        runtime.database._connection.execute(
            "UPDATE jobs SET error=?, execution_plan_json=? WHERE id=?",
            ("", json.dumps({"targets": []}), job_id),
        )


async def _drain_enqueue(runtime: Runtime) -> None:
    for _ in range(20):
        tasks = tuple(runtime._telemetry_enqueues)
        if not tasks:
            await asyncio.sleep(0)
            continue
        await asyncio.gather(*tasks)
        if not runtime._telemetry_enqueues:
            return


@pytest.mark.asyncio
async def test_runtime_start_warns_for_ignored_config_keys(config_factory, caplog) -> None:
    runtime = Runtime(replace(config_factory(), ignored_keys=("telemetry.endpoint",)))
    await runtime.start()
    try:
        records = [record for record in caplog.records if getattr(record, "event", None) == "config.ignored_keys"]
        assert len(records) == 1
        assert records[0].keys == ("telemetry.endpoint",)
    finally:
        await runtime.close()


def test_consent_uses_precedence_and_invalid_environment_is_ignored(tmp_path) -> None:
    config = DaemonConfig(home=tmp_path, telemetry=TelemetryConfig(True))
    assert telemetry_decision(config, {"DO_NOT_TRACK": "1", "REFRACT_TELEMETRY": "1"}) == (False, "DO_NOT_TRACK")
    assert telemetry_decision(config, {"REFRACT_TELEMETRY": "0"}) == (False, "REFRACT_TELEMETRY")
    assert telemetry_decision(config, {"REFRACT_TELEMETRY": "1"}) == (True, "REFRACT_TELEMETRY")
    assert telemetry_decision(config, {"REFRACT_TELEMETRY": "invalid"}) == (True, "config")
    assert telemetry_decision(DaemonConfig(home=tmp_path), {}) == (False, "default")
    assert telemetry_decision(
        DaemonConfig(home=tmp_path, telemetry=TelemetryConfig(False)), {},
    ) == (False, "config")


def test_error_redaction_removes_nested_environment_secrets_and_paths(tmp_path) -> None:
    text = f"abcdef abc {tmp_path} {str(tmp_path).replace('/', chr(92))}"
    result = _redact(text, ("abc", "abcdef"), str(tmp_path), tmp_path)
    assert "abcdef" not in result
    assert "abc" not in result
    assert "def" not in result
    assert str(tmp_path) not in result
    assert "[PATH]" in result


def test_redaction_handles_both_path_separator_forms(tmp_path) -> None:
    root = str(tmp_path / "project")
    variants = (root.replace("/", "\\"), root.replace("\\", "/"))
    for variant in variants:
        assert root not in _redact(f"path={variant}", (), root, tmp_path)
        assert variant not in _redact(f"path={variant}", (), root, tmp_path)


def test_redaction_case_folds_paths_when_windows_is_simulated(tmp_path) -> None:
    root = str(tmp_path / "ProjectRoot")
    assert "projectroot" not in _redact(f"{root.lower()}\\sub", (), root, tmp_path, windows=True).lower()


def test_redaction_cleans_secret_pattern_that_crosses_truncation_boundary(tmp_path) -> None:
    secret = "sk-" + "A" * 40
    value = "x" * 498 + secret
    result = _redact(value, (), "", tmp_path)
    assert len(result) <= 500
    assert "sk-" not in result
    assert "A" * 20 not in result


def test_redaction_removes_user_home_paths_outside_refract_home(tmp_path, monkeypatch) -> None:
    user_home = tmp_path / "user"
    monkeypatch.setattr("pathlib.Path.home", lambda: user_home)
    outside = str(user_home / "Documents" / "private.txt")
    assert outside not in _redact(outside, (), "/project", user_home / ".refract")


def test_send_batch_uses_fixed_collector_url() -> None:
    from refract.product_telemetry import send_batch

    requests = []

    class Response:
        status = 204

    assert send_batch("install", [], opener=lambda request, **_kwargs: requests.append(request) or Response()) == 204
    assert requests[0].full_url == COLLECTOR_URL


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_telemetry_opener_refuses_http_redirects(status) -> None:
    requested_paths = []

    class RedirectHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            requested_paths.append(self.path)
            if self.path == "/first":
                self.send_response(status)
                self.send_header("Location", "/second")
                self.end_headers()
            else:
                self.send_response(204)
                self.end_headers()

        def log_message(self, *_args):
            pass

    server = HTTPServer(("127.0.0.1", 0), RedirectHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/first"
        request = urllib.request.Request(url, data=b"payload", method="POST")
        handlers = [h for h in product_telemetry.TELEMETRY_OPENER.handlers if isinstance(h, product_telemetry._RefuseRedirects)]
        assert handlers
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), *handlers)
        with pytest.raises(urllib.error.HTTPError) as error:
            opener.open(request, timeout=5)
        assert error.value.code == status
        assert requested_paths == ["/first"]
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@pytest.mark.asyncio
async def test_delivery_redirect_http_error_drops_batch_and_records_status(
    tmp_path, config_factory, caplog, monkeypatch,
) -> None:
    database = Database(tmp_path / "redirect.db")
    config = config_factory(enabled=True)
    status = SendStatus()
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.setenv("REFRACT_TELEMETRY", "1")
    now = datetime.now(timezone.utc).isoformat()
    database.enqueue_telemetry("job:redirect", json.dumps({"event": "job"}), now)

    def opener(_request, *, timeout):
        raise urllib.error.HTTPError(COLLECTOR_URL, 302, "Found", {}, None)

    try:
        with caplog.at_level(logging.WARNING):
            await send_outbox_once(database, lambda: config, config.home, opener, status)
        assert database._connection.execute("SELECT COUNT(*) FROM telemetry_outbox").fetchone()[0] == 0
        assert status.last_error == "HTTP 302"
        assert sum(getattr(record, "event", None) == "telemetry.batch_rejected" for record in caplog.records) == 1
    finally:
        database.close()


def test_install_id_is_created_private_only_when_called(tmp_path) -> None:
    value = install_id(tmp_path)
    assert len(value) == 36
    if os.name == "posix":
        assert stat.S_IMODE((tmp_path / "telemetry_id").stat().st_mode) == 0o600


@pytest.mark.asyncio
async def test_consent_off_full_runtime_job_makes_no_network_or_telemetry_state(config_factory, monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.delenv("REFRACT_TELEMETRY", raising=False)
    calls = []
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: calls.append((a, kw)))
    monkeypatch.setattr(product_telemetry.TELEMETRY_OPENER, "open", lambda *a, **kw: calls.append((a, kw)))
    pricing_fetched = threading.Event()

    def pricing_fetch():
        pricing_fetched.set()
        raise PricingError("http")

    monkeypatch.setattr(pricing, "fetch_pricing", pricing_fetch)
    target = TargetConfig("worker", "pi")
    base = config_factory(enabled=False, targets=(target,))
    selection = {name: TargetSelection(("worker",)) for name in ("consult", "implement", "review", "other")}
    runtime = Runtime(replace(base, profiles={"balanced": selection}, default_profile="balanced"))
    async def fake_execute(**kwargs):
        return DriverResult("SUCCESS", "", "result-sentinel", "", "", model="model")
    runtime.drivers.execute = fake_execute
    runtime.drivers.available = lambda _target: True
    try:
        project = runtime.database.upsert_project(project_id="p", root=str(tmp_path))
        await runtime.start()
        submitted = await runtime.submit(project.id, "implement", "prompt-sentinel")
        job = await runtime.wait(submitted.job_id, timeout_s=10)
        await _drain_enqueue(runtime)
        assert job.state == "succeeded"
        assert await asyncio.to_thread(pricing_fetched.wait, 5)
        assert calls == []
        assert not (runtime.config.home / "telemetry_id").exists()
        assert runtime.database._connection.execute("SELECT COUNT(*) FROM telemetry_outbox").fetchone()[0] == 0
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_consent_on_runtime_job_creates_private_id_and_queues_exact_redacted_contract(config_factory, monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.delenv("REFRACT_TELEMETRY", raising=False)
    root = str(tmp_path / "private-project-root")
    target = TargetConfig("target", "codex", args=("args-sentinel",), env={"TOKEN": "env-sentinel"})
    runtime = Runtime(config_factory(enabled=True, targets=(target,)))
    try:
        project = runtime.database.upsert_project(project_id="p", root=root)
        runtime.database.create_job(
            job_id="sentinel-job", project_id=project.id, workflow="implement", profile="profile",
            prompt="prompt-sentinel", execution_plan_json=json.dumps({"prompt": "execution-sentinel"}),
            session="session",
        )
        runtime.database.finish_job("sentinel-job", "failed", text="result-sentinel",
                                    error=f"{root} env-sentinel args-sentinel")
        runtime.scheduler.complete = lambda *_args, **_kwargs: None
        await runtime._job_terminal("sentinel-job", "failed")
        await _drain_enqueue(runtime)
        row = runtime.database._connection.execute("SELECT * FROM telemetry_outbox").fetchone()
        payload = json.loads(row["payload"])
        assert row["event_key"] == "job:sentinel-job"
        assert set(payload) == {
            "event", "job_id", "retry_of", "finished_at", "workflow", "profile", "session",
            "target", "backend", "model", "state", "failure_kind", "duration_ms", "tokens",
            "attempts", "skipped_targets", "error",
        }
        assert payload["event"] == "job"
        assert set(payload["tokens"]) == {
            "input", "output", "cache_read", "cache_write", "context_used", "context_window",
        }
        encoded = row["payload"]
        for sentinel in ("prompt-sentinel", "result-sentinel", root, "args-sentinel",
                         "env-sentinel", "execution-sentinel", "execution_plan_json"):
            assert sentinel not in encoded
        id_path = runtime.config.home / "telemetry_id"
        assert id_path.exists()
        if os.name == "posix":
            assert stat.S_IMODE(id_path.stat().st_mode) == 0o600
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_two_terminal_callbacks_enqueue_one_job_event(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.delenv("REFRACT_TELEMETRY", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    try:
        _terminal_job(runtime)
        completes = []
        runtime.scheduler.complete = lambda *a, **kw: completes.append(a[0])
        await runtime._job_terminal("job-one", "succeeded")
        await runtime._job_terminal("job-one", "succeeded")
        await _drain_enqueue(runtime)
        rows = runtime.database._connection.execute(
            "SELECT event_key, payload FROM telemetry_outbox"
        ).fetchall()
        assert completes == ["job-one", "job-one"]
        assert len(rows) == 1
        assert rows[0]["event_key"] == "job:job-one"
        assert json.loads(rows[0]["payload"])["event"] == "job"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_enqueue_failure_and_blocking_enqueue_do_not_delay_or_change_terminal_job(config_factory, monkeypatch) -> None:
    runtime = Runtime(config_factory(enabled=True))
    try:
        _terminal_job(runtime)
        completes = []
        runtime.scheduler.complete = lambda *a, **kw: completes.append(a[0])
        original = runtime._telemetry_config_check
        monkeypatch.setattr(runtime, "_telemetry_config_check", lambda: (_ for _ in ()).throw(RuntimeError("enqueue failed")))
        started = time.monotonic()
        await runtime._job_terminal("job-one", "succeeded")
        assert time.monotonic() - started < 0.2
        await _drain_enqueue(runtime)
        assert runtime.database.job_record("job-one")["state"] == "succeeded"
        assert completes == ["job-one"]

        gate = threading.Event()
        monkeypatch.setattr(runtime, "_telemetry_config_check", lambda: (gate.wait(2), original())[1])
        started = time.monotonic()
        await runtime._job_terminal("job-one", "succeeded")
        assert time.monotonic() - started < 0.2
        assert runtime.database.job_record("job-one")["state"] == "succeeded"
        assert completes == ["job-one", "job-one"]
        gate.set()
        await _drain_enqueue(runtime)
    finally:
        await runtime.close()


def test_enqueue_over_row_limit_deletes_oldest_rows(tmp_path) -> None:
    database = Database(tmp_path / "rows.db")
    try:
        now = datetime.now(timezone.utc).isoformat()
        with database._connection:
            database._connection.executemany(
                "INSERT INTO telemetry_outbox(event_key, created_at, payload, next_attempt_at) VALUES (?, ?, '{}', ?)",
                ((f"old:{i}", now, now) for i in range(10_000)),
            )
        database.enqueue_telemetry("new:event", "{}", now)
        assert database._connection.execute("SELECT COUNT(*) FROM telemetry_outbox").fetchone()[0] == 10_000
        assert database._connection.execute("SELECT 1 FROM telemetry_outbox WHERE event_key='old:0'").fetchone() is None
        assert database._connection.execute("SELECT 1 FROM telemetry_outbox WHERE event_key='new:event'").fetchone()
    finally:
        database.close()


def test_enqueue_over_age_limit_deletes_oldest_rows(tmp_path) -> None:
    database = Database(tmp_path / "age.db")
    try:
        now = datetime.now(timezone.utc)
        old = (now - timedelta(days=31)).isoformat()
        current = now.isoformat()
        database.enqueue_telemetry("old:event", "{}", old)
        database.enqueue_telemetry("current:event", "{}", current)
        assert database._connection.execute("SELECT event_key FROM telemetry_outbox").fetchall()[0][0] == "current:event"
    finally:
        database.close()


def test_delivery_2xx_deletes_rows(tmp_path, config_factory) -> None:
    asyncio.run(_delivery_case(tmp_path, config_factory, status=204, expected_count=0))


@pytest.mark.parametrize("status", [429, 503])
def test_delivery_429_and_5xx_back_off_and_keep_rows(tmp_path, config_factory, status) -> None:
    asyncio.run(_delivery_case(tmp_path, config_factory, status=status, expected_count=1, expected_attempts=1))


def test_delivery_network_error_backs_off_and_keeps_rows(tmp_path, config_factory, caplog) -> None:
    with caplog.at_level(logging.WARNING):
        asyncio.run(_delivery_case(tmp_path, config_factory, error=OSError("offline"), expected_count=1, expected_attempts=1))
    assert any(getattr(record, "event", "") == "telemetry.send_failed" for record in caplog.records)


def test_delivery_network_error_updates_send_status(tmp_path, config_factory) -> None:
    send_status = SendStatus()
    asyncio.run(
        _delivery_case(
            tmp_path,
            config_factory,
            error=OSError("offline"),
            expected_count=1,
            expected_attempts=1,
            send_status=send_status,
        )
    )
    assert send_status.last_error == "network error"


@pytest.mark.parametrize("status", [0, 600])
def test_delivery_unknown_status_defers_with_backoff(tmp_path, config_factory, status) -> None:
    asyncio.run(_delivery_case(tmp_path, config_factory, status=status, expected_count=1, expected_attempts=1))


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_delivery_redirect_status_drops_batch_and_logs_warning(tmp_path, config_factory, caplog, status) -> None:
    with caplog.at_level(logging.WARNING):
        asyncio.run(_delivery_case(tmp_path, config_factory, status=status, expected_count=0))
    assert any(getattr(record, "event", "") == "telemetry.batch_rejected" for record in caplog.records)


def test_delivery_other_4xx_drops_batch_and_logs_warning(tmp_path, config_factory, caplog) -> None:
    with caplog.at_level(logging.WARNING):
        asyncio.run(_delivery_case(tmp_path, config_factory, status=422, expected_count=0))
    assert any(getattr(record, "event", "") == "telemetry.batch_rejected" for record in caplog.records)


def test_delivery_batch_is_limited_to_100_events(tmp_path, config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.setenv("REFRACT_TELEMETRY", "1")
    database = Database(tmp_path / "batch.db")
    config = config_factory(enabled=True)
    calls = []
    try:
        now = datetime.now(timezone.utc).isoformat()
        with database._connection:
            database._connection.executemany(
                "INSERT INTO telemetry_outbox(event_key, created_at, payload, next_attempt_at) VALUES (?, ?, ?, ?)",
                ((f"e:{i}", now, json.dumps({"event": "job", "job_id": str(i)}), now) for i in range(105)),
            )
        class Response:
            status = 200
        def opener(request, *, timeout):
            calls.append((json.loads(request.data), timeout))
            return Response()
        asyncio.run(send_outbox_once(database, lambda: config, config.home, opener))
        assert len(calls[0][0]["events"]) == BATCH_SIZE
        assert calls[0][1] == 10
        assert database._connection.execute("SELECT COUNT(*) FROM telemetry_outbox").fetchone()[0] == 5
    finally:
        database.close()


async def _delivery_case(
    tmp_path, config_factory, *, status=None, error=None,
    expected_count: int, expected_attempts: int = 0,
    send_status: SendStatus | None = None,
) -> None:
    database = Database(tmp_path / f"delivery-{status}-{expected_count}.db")
    config = config_factory(enabled=True)
    previous_dnt = os.environ.pop("DO_NOT_TRACK", None)
    previous_consent = os.environ.get("REFRACT_TELEMETRY")
    os.environ["REFRACT_TELEMETRY"] = "1"
    try:
        now = datetime.now(timezone.utc).isoformat()
        database.enqueue_telemetry("job:test", json.dumps({"event": "job"}), now)
        def opener(_request, *, timeout):
            if error is not None:
                raise error
            if status >= 400:
                raise urllib.error.HTTPError("https://example.invalid", status, "bad", {}, None)
            class Response:
                pass
            response = Response()
            response.status = status
            return response
        await send_outbox_once(database, lambda: config, config.home, opener, send_status)
        rows = database._connection.execute("SELECT * FROM telemetry_outbox").fetchall()
        assert len(rows) == expected_count
        if expected_attempts:
            assert rows[0]["send_attempts"] == expected_attempts
            assert rows[0]["next_attempt_at"] > now
    finally:
        database.close()
        if previous_dnt is not None:
            os.environ["DO_NOT_TRACK"] = previous_dnt
        if previous_consent is None:
            os.environ.pop("REFRACT_TELEMETRY", None)
        else:
            os.environ["REFRACT_TELEMETRY"] = previous_consent


def test_delivery_backoff_starts_at_one_minute_and_caps_at_one_day() -> None:
    assert next_backoff(0) == 60
    assert next_backoff(1) == 120
    assert next_backoff(30) == 24 * 60 * 60


@pytest.mark.asyncio
async def test_invalid_config_enqueue_does_not_touch_existing_telemetry(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.delenv("REFRACT_TELEMETRY", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    try:
        _terminal_job(runtime)
        now = datetime.now(timezone.utc).isoformat()
        runtime.database.enqueue_telemetry("existing", "{}", now)
        id_path = runtime.config.home / "telemetry_id"
        id_path.write_text("existing-id", encoding="utf-8")
        runtime.scheduler.complete = lambda *_args, **_kwargs: None
        runtime._telemetry_config_check = lambda: (_ for _ in ()).throw(ValueError("invalid"))
        await runtime._job_terminal("job-one", "succeeded")
        await _drain_enqueue(runtime)
        rows = runtime.database._connection.execute("SELECT event_key FROM telemetry_outbox").fetchall()
        assert [row[0] for row in rows] == ["existing"]
        assert id_path.read_text(encoding="utf-8") == "existing-id"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_invalid_config_send_purges_state_without_post(config_factory, tmp_path) -> None:
    database = Database(tmp_path / "invalid-config.db")
    config = config_factory(enabled=True)
    calls = []
    try:
        database.enqueue_telemetry("pending", "{}", datetime.now(timezone.utc).isoformat())
        id_path = config.home / "telemetry_id"
        id_path.write_text("existing-id", encoding="utf-8")
        def invalid_config():
            raise ValueError("invalid config")
        await send_outbox_once(database, invalid_config, config.home,
                               lambda *args, **kwargs: calls.append((args, kwargs)))
        assert calls == []
        assert database._connection.execute("SELECT COUNT(*) FROM telemetry_outbox").fetchone()[0] == 0
        assert not id_path.exists()
    finally:
        database.close()


@pytest.mark.asyncio
async def test_config_switch_off_before_job_end_does_not_enqueue(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.setenv("REFRACT_TELEMETRY", "0")
    runtime = Runtime(config_factory(enabled=True))
    try:
        _terminal_job(runtime)
        runtime.scheduler.complete = lambda *_args, **_kwargs: None
        await runtime._job_terminal("job-one", "succeeded")
        await _drain_enqueue(runtime)
        assert runtime.database._connection.execute("SELECT COUNT(*) FROM telemetry_outbox").fetchone()[0] == 0
        assert not (runtime.config.home / "telemetry_id").exists()
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_config_switch_off_before_send_purges_without_post(config_factory, tmp_path) -> None:
    database = Database(tmp_path / "switch.db")
    config = config_factory(enabled=False)
    calls = []
    try:
        now = datetime.now(timezone.utc).isoformat()
        database.enqueue_telemetry("job:pending", '{"event":"job"}', now)
        (config.home / "telemetry_id").write_text("id", encoding="utf-8")
        await send_outbox_once(database, lambda: config, config.home,
                               lambda *a, **kw: calls.append((a, kw)))
        assert calls == []
        assert database._connection.execute("SELECT COUNT(*) FROM telemetry_outbox").fetchone()[0] == 0
        assert not (config.home / "telemetry_id").exists()
    finally:
        database.close()


def test_telemetry_config_error_is_sanitized_without_values() -> None:
    from refract.config_inspection import sanitize_config_error
    assert sanitize_config_error("telemetry.enabled must be true or false") == \
        "telemetry.enabled must be valid"


def test_project_overlay_with_telemetry_is_rejected(tmp_path) -> None:
    from refract.config import load_config, load_project_config
    global_config = tmp_path / "global.toml"
    global_config.write_text(
        '[daemon]\ndefault_profile="base"\n[[targets]]\nid="t"\nbackend="codex"\n'
        '[profiles.base]\nimplement="t"\nreview="t"\nconsult="t"\n', encoding="utf-8",
    )
    base = load_config(global_config)
    root = tmp_path / "project"
    (root / ".refract").mkdir(parents=True)
    (root / ".refract" / "config.toml").write_text("[telemetry]\nenabled=true\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported project config sections"):
        load_project_config(root, base)


def _mcp_context(runtime: Runtime, client_name: str | None = "test-client"):
    from types import SimpleNamespace

    params = None if client_name is None else SimpleNamespace(client_info=SimpleNamespace(name=client_name))
    return SimpleNamespace(request_context=SimpleNamespace(
        lifespan_context=runtime, session=SimpleNamespace(client_params=params), request_id=1,
    ))


async def _call_mcp(operation: str, runtime: Runtime, client_name: str | None = "test-client") -> None:
    from refract.server import _logged_request

    async def tool(ctx) -> str:
        return "ok"

    await _logged_request(operation)(tool)(_mcp_context(runtime, client_name))


def _outbox(runtime: Runtime) -> dict[str, dict]:
    rows = runtime.database._connection.execute("SELECT event_key, payload FROM telemetry_outbox").fetchall()
    return {row[0]: json.loads(row[1]) for row in rows}


async def _dashboard_get(runtime: Runtime, path: str) -> int:
    from starlette.applications import Starlette

    from refract.dashboard import DashboardState, register_dashboard_routes
    from tests.test_dashboard_api import api_request

    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime)))
    status, _body, _headers = await api_request(app, path, method="GET")
    return status


@pytest.mark.asyncio
async def test_consent_on_mcp_calls_and_dashboard_reads_flush_into_one_matching_features_event(
    config_factory, monkeypatch,
) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    try:
        await _call_mcp("submit", runtime)
        await _call_mcp("submit", runtime)
        await _call_mcp("wait", runtime, "other-client")
        assert await _dashboard_get(runtime, "/dashboard/api/stats?days=7") == 200
        await runtime._flush_telemetry()
        events = [value for key, value in _outbox(runtime).items() if key.startswith("features:")]
        assert len(events) == 1
        event = events[0]
        assert event["event"] == "features"
        assert event["counts"] == {
            "mcp.submit": 2, "mcp.wait": 1, "mcp_client.test-client": 2,
            "mcp_client.other-client": 1, "dashboard.stats": 1,
        }
        assert set(event) == {"event", "period_start", "period_end", "counts"}
        assert f"features:{event['period_start']}" in _outbox(runtime)
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_missing_client_params_counts_tool_without_client_name(config_factory, monkeypatch, caplog) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    try:
        with caplog.at_level(logging.WARNING):
            await _call_mcp("list", runtime, None)
        assert not any(getattr(record, "event", "") == "telemetry.count_failed" for record in caplog.records)
        await runtime._flush_telemetry()
        counts = next(value["counts"] for key, value in _outbox(runtime).items() if key.startswith("features:"))
        assert counts == {"mcp.list": 1}
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_consent_off_creates_no_feature_counts(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    runtime = Runtime(config_factory(enabled=False))
    try:
        await _call_mcp("submit", runtime)
        assert await _dashboard_get(runtime, "/dashboard/api/stats?days=7") == 200
        assert runtime._feature_counts == {}
        await runtime._flush_telemetry()
        assert _outbox(runtime) == {}
        assert not (runtime.config.home / "telemetry_id").exists()
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_switch_to_off_clears_in_memory_counts(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    try:
        await _call_mcp("submit", runtime)
        assert runtime._feature_counts
        monkeypatch.setenv("REFRACT_TELEMETRY", "0")
        runtime._telemetry_config_check()
        assert runtime._feature_counts == {}
        await _call_mcp("submit", runtime)
        assert runtime._feature_counts == {}
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_close_flushes_counts_to_outbox_before_database_closes(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    seen: dict[str, dict] = {}
    original_close = runtime.database.close

    def close_and_record() -> None:
        seen.update(_outbox(runtime))
        original_close()

    runtime.database.close = close_and_record
    await _call_mcp("submit", runtime)
    await runtime.close()
    features = [value for key, value in seen.items() if key.startswith("features:")]
    assert [item["counts"] for item in features] == [{"mcp.submit": 1, "mcp_client.test-client": 1}]


@pytest.mark.asyncio
async def test_hourly_flush_task_enqueues_features_event(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.setattr("refract.runtime.FEATURE_FLUSH_INTERVAL_S", 0.01)
    runtime = Runtime(config_factory(enabled=True))
    try:
        await runtime.start()
        await _call_mcp("cancel", runtime)
        for _ in range(200):
            if any(key.startswith("features:") for key in _outbox(runtime)):
                break
            await asyncio.sleep(0.01)
        counts = next(v["counts"] for k, v in _outbox(runtime).items() if k.startswith("features:"))
        assert counts == {"mcp.cancel": 1, "mcp_client.test-client": 1}
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_two_flushes_on_one_utc_day_enqueue_one_heartbeat_with_documented_fields(
    config_factory, monkeypatch,
) -> None:
    import platform

    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    targets = (TargetConfig("a", "codex"), TargetConfig("b", "codex"), TargetConfig("c", "pi"))
    runtime = Runtime(config_factory(enabled=True, targets=targets))
    try:
        await runtime._flush_telemetry()
        runtime.database.clear_telemetry_outbox()
        await runtime._flush_telemetry()
        assert _outbox(runtime) == {}
        runtime.database.clear_telemetry_outbox()
        with monkeypatch.context() as patch:
            patch.setattr("refract.runtime.utc_now", lambda: "2099-01-02T00:00:00+00:00")
            await runtime._flush_telemetry()
            assert list(_outbox(runtime)) == ["heartbeat:2099-01-02"]
    finally:
        await runtime.close()
    # The first flush, replayed on a fresh runtime, carries the documented fields.
    fresh = Runtime(config_factory(enabled=True, targets=targets))
    try:
        fresh.database.clear_telemetry_outbox()
        (fresh.config.home / "telemetry_heartbeat").unlink()
        await fresh._flush_telemetry()
        key, event = next(iter(_outbox(fresh).items()))
        assert key == f"heartbeat:{datetime.now(timezone.utc).date().isoformat()}"
        assert event == {
            "event": "heartbeat", "os": platform.system(), "arch": platform.machine(),
            "python_version": platform.python_version(), "notifications_enabled": False,
            "backends": {"codex": 2, "pi": 1},
        }
    finally:
        await fresh.close()


@pytest.mark.asyncio
async def test_consent_off_flush_enqueues_no_heartbeat(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    runtime = Runtime(config_factory(enabled=False))
    try:
        await runtime._flush_telemetry()
        assert _outbox(runtime) == {}
    finally:
        await runtime.close()


STATUS_FIELDS = {"enabled", "source", "endpoint", "install_id", "queued", "last_send_at",
                 "last_error", "next_batch"}


def test_telemetry_status_with_consent_off_creates_no_telemetry_id(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    runtime = Runtime(config_factory(enabled=False))
    try:
        status = runtime.telemetry_status()
        assert set(status) == STATUS_FIELDS
        assert (status["enabled"], status["source"], status["install_id"]) == (False, "config", None)
        assert status["next_batch"] is None
        assert not (runtime.config.home / "telemetry_id").exists()
    finally:
        runtime.database.close()


def test_telemetry_status_reports_decision_source_for_environment_override(config_factory, monkeypatch) -> None:
    monkeypatch.setenv("DO_NOT_TRACK", "1")
    runtime = Runtime(config_factory(enabled=True))
    try:
        status = runtime.telemetry_status()
        assert (status["enabled"], status["source"]) == (False, "DO_NOT_TRACK")
        assert not (runtime.config.home / "telemetry_id").exists()
    finally:
        runtime.database.close()


def test_telemetry_status_with_invalid_config_reports_off(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    try:
        monkeypatch.setattr(runtime, "_telemetry_config_check",
                            lambda: (_ for _ in ()).throw(ValueError("invalid")))
        status = runtime.telemetry_status()
        assert status["enabled"] is False
        assert status["install_id"] is None
        assert not (runtime.config.home / "telemetry_id").exists()
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_next_batch_equals_sender_post_body_apart_from_sent_at(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    config = config_factory(enabled=True)
    runtime = Runtime(config)
    posted: list[dict] = []

    class Response:
        status = 204

    def opener(request, timeout=None):
        posted.append(json.loads(request.data))
        return Response()

    try:
        now = datetime.now(timezone.utc).isoformat()
        runtime.database.enqueue_telemetry("job:one", json.dumps({"event": "job", "job_id": "one"}), now)
        runtime.database.enqueue_telemetry("features:p", json.dumps({"event": "features", "counts": {}}), now)
        status = runtime.telemetry_status()
        assert status["enabled"] is True
        assert status["source"] == "config"
        assert status["queued"] == 2
        assert status["install_id"] == install_id(config.home)
        await send_outbox_once(runtime.database, runtime._telemetry_config_check, config.home, opener)
        assert len(posted) == 1
        sent = {key: value for key, value in posted[0].items() if key != "sent_at"}
        preview = {key: value for key, value in status["next_batch"].items() if key != "sent_at"}
        assert preview == sent
        assert preview["events"][0]["job_id"] == "one"
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_status_records_last_send_time_and_last_error(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    config = config_factory(enabled=True)
    runtime = Runtime(config)

    class Response:
        status = 500

    try:
        runtime.database.enqueue_telemetry("job:one", "{}", datetime.now(timezone.utc).isoformat())
        assert runtime.telemetry_status()["last_send_at"] is None
        await send_outbox_once(runtime.database, runtime._telemetry_config_check, config.home,
                               lambda *a, **k: Response(), runtime._telemetry_send_status)
        status = runtime.telemetry_status()
        assert status["last_error"] == "HTTP 500"
        assert status["last_send_at"] is None
        with runtime.database._connection:
            runtime.database._connection.execute("UPDATE telemetry_outbox SET next_attempt_at='2000-01-01'")
        Response.status = 200
        await send_outbox_once(runtime.database, runtime._telemetry_config_check, config.home,
                               lambda *a, **k: Response(), runtime._telemetry_send_status)
        status = runtime.telemetry_status()
        assert status["last_error"] is None
        assert status["last_send_at"] is not None
        assert status["queued"] == 0
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_close_during_in_flight_flush_enqueues_detached_counts_exactly_once(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.setattr("refract.runtime.FEATURE_FLUSH_INTERVAL_S", 0.01)
    runtime = Runtime(config_factory(enabled=True))
    entered, gate = threading.Event(), threading.Event()

    def gated_install_id(home):
        entered.set()
        gate.wait(5)
        return install_id(home)

    monkeypatch.setattr("refract.runtime.install_id", gated_install_id)
    seen: list[dict] = []
    original_close = runtime.database.close

    def close_and_record() -> None:
        seen.append(_outbox(runtime))
        original_close()

    runtime.database.close = close_and_record
    try:
        await runtime.start()
        await _call_mcp("cancel", runtime)
        assert await asyncio.to_thread(entered.wait, 5)
        closing = asyncio.create_task(runtime.close())
        await asyncio.sleep(0.1)
        gate.set()
        await closing
    finally:
        gate.set()
    features = [value["counts"] for key, value in seen[0].items() if key.startswith("features:")]
    assert features == [{"mcp.cancel": 1, "mcp_client.test-client": 1}]


def _heartbeat_keys(runtime: Runtime) -> list[str]:
    return [key for key in _outbox(runtime) if key.startswith("heartbeat:")]


@pytest.mark.asyncio
async def test_restart_with_pending_heartbeat_row_keeps_one_heartbeat(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    first = Runtime(config_factory(enabled=True))
    await first._flush_telemetry()
    first.database.close()
    second = Runtime(config_factory(enabled=True))
    try:
        await second._flush_telemetry()
        assert len(_heartbeat_keys(second)) == 1
    finally:
        second.database.close()


@pytest.mark.asyncio
async def test_restart_after_heartbeat_was_sent_enqueues_no_second_heartbeat_same_day(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    first = Runtime(config_factory(enabled=True))
    await first._flush_telemetry()
    first.database.clear_telemetry_outbox()
    first.database.close()
    second = Runtime(config_factory(enabled=True))
    try:
        await second._flush_telemetry()
        assert _heartbeat_keys(second) == []
    finally:
        second.database.close()


@pytest.mark.asyncio
async def test_restart_on_next_utc_day_enqueues_new_heartbeat(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    first = Runtime(config_factory(enabled=True))
    await first._flush_telemetry()
    first.database.clear_telemetry_outbox()
    first.database.close()
    second = Runtime(config_factory(enabled=True))
    try:
        monkeypatch.setattr("refract.runtime.utc_now", lambda: "2099-01-02T00:00:00+00:00")
        await second._flush_telemetry()
        assert _heartbeat_keys(second) == ["heartbeat:2099-01-02"]
    finally:
        second.database.close()


def test_opt_out_purge_removes_heartbeat_date_file(config_factory, tmp_path) -> None:
    config = config_factory(enabled=True)
    database = Database(tmp_path / "purge.db")
    try:
        (config.home / "telemetry_id").write_text("id", encoding="utf-8")
        (config.home / "telemetry_heartbeat").write_text("2026-11-10", encoding="utf-8")
        purge(database, config.home)
        assert not (config.home / "telemetry_heartbeat").exists()
    finally:
        database.close()


@pytest.mark.asyncio
async def test_sender_resolves_install_id_off_the_event_loop(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    config = config_factory(enabled=True)
    database = Database(config.home / "sender.db")
    threads: list[int] = []

    def recording_install_id(home):
        threads.append(threading.get_ident())
        return "id"

    class Response:
        status = 200

    monkeypatch.setattr("refract.product_telemetry.install_id", recording_install_id)
    try:
        database.enqueue_telemetry("job:one", "{}", datetime.now(timezone.utc).isoformat())
        await send_outbox_once(database, lambda: config, config.home, lambda *a, **k: Response())
        assert threads
        assert threading.get_ident() not in threads
    finally:
        database.close()


def test_telemetry_queue_count_counts_all_rows_including_deferred(tmp_path) -> None:
    database = Database(tmp_path / "count.db")
    try:
        now = datetime.now(timezone.utc).isoformat()
        assert database.telemetry_queue_count() == 0
        database.enqueue_telemetry("a", "{}", now)
        database.enqueue_telemetry("b", "{}", now)
        database.defer_telemetry([database.telemetry_batch(1)[0]["id"]], [3600])
        assert database.telemetry_queue_count() == 2
    finally:
        database.close()


def _gate_heartbeat_write(monkeypatch):
    from refract.product_telemetry import write_heartbeat_date

    entered, gate = threading.Event(), threading.Event()

    def gated(home, date):
        entered.set()
        gate.wait(5)
        write_heartbeat_date(home, date)

    monkeypatch.setattr("refract.runtime.write_heartbeat_date", gated)
    return entered, gate


@pytest.mark.asyncio
async def test_heartbeat_row_is_not_enqueued_until_the_date_write_completes(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    entered, gate = _gate_heartbeat_write(monkeypatch)
    try:
        flushing = asyncio.create_task(runtime._flush_telemetry())
        assert await asyncio.to_thread(entered.wait, 5)
        assert _heartbeat_keys(runtime) == []
        gate.set()
        await flushing
        assert len(_heartbeat_keys(runtime)) == 1
    finally:
        gate.set()
        runtime.database.close()


@pytest.mark.asyncio
async def test_failed_heartbeat_enqueue_removes_new_date_and_next_flush_retries(config_factory, monkeypatch, caplog) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    original = runtime.database.enqueue_telemetry

    def failing(*_args, **_kwargs):
        raise RuntimeError("enqueue failed")

    try:
        monkeypatch.setattr(runtime.database, "enqueue_telemetry", failing)
        with caplog.at_level(logging.WARNING):
            await runtime._flush_telemetry()
        assert any(getattr(r, "event", "") == "telemetry.flush_failed" for r in caplog.records)
        assert not (runtime.config.home / "telemetry_heartbeat").exists()
        monkeypatch.setattr(runtime.database, "enqueue_telemetry", original)
        await runtime._flush_telemetry()
        assert len(_heartbeat_keys(runtime)) == 1
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_failed_heartbeat_enqueue_restores_previous_date(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    path = runtime.config.home / "telemetry_heartbeat"
    path.write_text("2000-01-01", encoding="utf-8")

    def failing(*_args, **_kwargs):
        raise RuntimeError("enqueue failed")

    try:
        monkeypatch.setattr(runtime.database, "enqueue_telemetry", failing)
        await runtime._flush_telemetry()
        assert path.read_text(encoding="utf-8") == "2000-01-01"
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_opt_out_purge_waits_for_in_flight_flush_and_leaves_no_state_files(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    config = config_factory(enabled=True)
    runtime = Runtime(config)
    entered, gate = _gate_heartbeat_write(monkeypatch)
    try:
        flushing = asyncio.create_task(runtime._flush_telemetry())
        assert await asyncio.to_thread(entered.wait, 5)
        monkeypatch.setenv("REFRACT_TELEMETRY", "0")
        purging = asyncio.create_task(send_outbox_once(
            runtime.database, runtime._telemetry_config_check, config.home, purge_lock=runtime._flush_lock,
        ))
        await asyncio.sleep(0.1)
        gate.set()
        await asyncio.gather(flushing, purging)
        assert not (config.home / "telemetry_id").exists()
        assert not (config.home / "telemetry_heartbeat").exists()
        assert _outbox(runtime) == {}
    finally:
        gate.set()
        runtime.database.close()


@pytest.mark.asyncio
async def test_flush_skips_file_writes_when_consent_switches_off_after_config_load(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    original = runtime._telemetry_config_check

    def check_then_switch_off():
        config = original()
        runtime._set_telemetry_enabled(False)
        return config

    try:
        monkeypatch.setattr(runtime, "_telemetry_config_check", check_then_switch_off)
        await runtime._flush_telemetry()
        assert not (runtime.config.home / "telemetry_id").exists()
        assert not (runtime.config.home / "telemetry_heartbeat").exists()
        assert _outbox(runtime) == {}
    finally:
        runtime.database.close()


def test_heartbeat_write_failure_removes_temp_file(tmp_path, monkeypatch) -> None:
    from pathlib import Path

    from refract.product_telemetry import write_heartbeat_date

    def partial_write(self, data, *args, **kwargs):
        self.touch()
        raise OSError("disk full")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "write_text", partial_write)
        with pytest.raises(OSError):
            write_heartbeat_date(tmp_path, "2026-11-10")
    assert not (tmp_path / "telemetry_heartbeat.tmp").exists()
    assert not (tmp_path / "telemetry_heartbeat").exists()


def test_heartbeat_replace_failure_removes_temp_file(tmp_path, monkeypatch) -> None:
    from refract.product_telemetry import write_heartbeat_date

    def failing_replace(*_args, **_kwargs):
        raise OSError("replace failed")

    monkeypatch.setattr("refract.product_telemetry.os.replace", failing_replace)
    with pytest.raises(OSError):
        write_heartbeat_date(tmp_path, "2026-11-10")
    assert not (tmp_path / "telemetry_heartbeat.tmp").exists()


def test_purge_removes_stale_heartbeat_temp_file(tmp_path) -> None:
    database = Database(tmp_path / "stale.db")
    try:
        (tmp_path / "telemetry_heartbeat.tmp").write_text("2026-11-10", encoding="utf-8")
        purge(database, tmp_path)
        assert not (tmp_path / "telemetry_heartbeat.tmp").exists()
    finally:
        database.close()


def test_telemetry_status_uses_public_database_accessors_only(config_factory) -> None:
    from refract.product_telemetry import SendStatus, telemetry_status

    class FakeDatabase:
        def telemetry_batch(self, limit):
            return [{"payload": '{"event": "job"}'}]

        def telemetry_queue_count(self):
            return 7

    status = telemetry_status(FakeDatabase(), config_factory(enabled=True), True, "config", SendStatus())
    assert status["queued"] == 7
    assert status["next_batch"]["events"] == [{"event": "job"}]


@pytest.mark.asyncio
async def test_runtime_close_drains_in_flight_job_enqueue_before_database_close(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    _terminal_job(runtime)
    runtime.scheduler.complete = lambda *a, **kw: None
    original_check = runtime._telemetry_config_check
    entered, gate = threading.Event(), threading.Event()

    def gated_check():
        entered.set()
        gate.wait(5)
        return original_check()

    seen: list[dict] = []
    original_close = runtime.database.close

    def close_and_record() -> None:
        seen.append(_outbox(runtime))
        original_close()

    runtime.database.close = close_and_record
    monkeypatch.setattr(runtime, "_telemetry_config_check", gated_check)
    try:
        await runtime._job_terminal("job-one", "succeeded")
        assert await asyncio.to_thread(entered.wait, 5)
        closing = asyncio.create_task(runtime.close())
        await asyncio.sleep(0.1)
        assert not closing.done()
        assert not seen
        gate.set()
        await closing
    finally:
        gate.set()
    assert "job:job-one" in seen[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "name"),
    [
        ("/dashboard/api/stats?days=7", "dashboard.stats"),
        ("/dashboard/api/jobs", "dashboard.jobs"),
        ("/dashboard/api/jobs/job-one/output", "dashboard.output"),
        ("/dashboard/api/jobs/job-one", "dashboard.job_detail"),
        ("/dashboard/api/targets", "dashboard.targets"),
        ("/dashboard/api/cards", "dashboard.cards"),
        ("/dashboard/api/cards/card-one", "dashboard.card"),
    ],
)
async def test_dashboard_read_counts_exactly_its_feature_key(config_factory, monkeypatch, path, name) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    try:
        await _dashboard_get(runtime, path)
        assert runtime._feature_counts == {name: 1}
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_ask_request_counts_the_ask_feature_key(config_factory, monkeypatch) -> None:
    from starlette.applications import Starlette

    from refract.dashboard import DashboardState, register_dashboard_routes
    from tests.test_dashboard_api import api_request

    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    try:
        app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime)))
        await api_request(app, "/ask", method="POST")
        assert runtime._feature_counts == {"ask": 1}
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_flush_rechecks_consent_before_the_heartbeat_date_write(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    runtime = Runtime(config_factory(enabled=True))

    def install_id_then_switch_off(_home):
        runtime._set_telemetry_enabled(False)
        return "install"

    monkeypatch.setattr("refract.runtime.install_id", install_id_then_switch_off)
    try:
        await runtime._flush_telemetry()
        assert not (runtime.config.home / "telemetry_heartbeat").exists()
        assert _outbox(runtime) == {}
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_purge_cancel_keeps_the_lock_until_the_purge_thread_finishes(tmp_path, monkeypatch) -> None:
    entered, gate, finished = threading.Event(), threading.Event(), threading.Event()

    def gated_purge(_database, _home) -> None:
        entered.set()
        gate.wait(5)
        finished.set()

    monkeypatch.setattr("refract.product_telemetry.purge", gated_purge)
    lock = threading.Lock()
    def invalid_config():
        raise ValueError("invalid config")

    database = type("EmptyOutbox", (), {"telemetry_batch": staticmethod(lambda _limit: [])})()
    task = asyncio.create_task(send_outbox_once(database, invalid_config, tmp_path, purge_lock=lock))
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        task.cancel()
        await asyncio.sleep(0.1)
        assert lock.locked()
        assert not finished.is_set()
        gate.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished.is_set()
        assert not lock.locked()
    finally:
        gate.set()


def _fail_enqueue_once(runtime: Runtime, monkeypatch) -> None:
    original = runtime.database.enqueue_telemetry
    calls = []

    def flaky(*args, **kwargs):
        calls.append(args[0])
        if len(calls) == 1:
            raise RuntimeError("enqueue failed")
        return original(*args, **kwargs)

    monkeypatch.setattr(runtime.database, "enqueue_telemetry", flaky)


@pytest.mark.asyncio
async def test_failed_flush_merges_detached_counts_back_and_next_flush_sends_them(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    try:
        runtime.count_feature("mcp.submit")
        runtime.count_feature("mcp.submit")
        period_start = runtime._feature_period_start
        _fail_enqueue_once(runtime, monkeypatch)
        await runtime._flush_telemetry()
        assert runtime._feature_counts == {"mcp.submit": 2}
        assert runtime._feature_period_start == period_start
        runtime.count_feature("mcp.wait")
        await runtime._flush_telemetry()
        events = [value for key, value in _outbox(runtime).items() if key.startswith("features:")]
        assert [event["counts"] for event in events] == [{"mcp.submit": 2, "mcp.wait": 1}]
        assert events[0]["period_start"] == period_start
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_failed_flush_restore_respects_the_feature_name_limit(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.setattr("refract.runtime.MAX_FEATURE_NAMES", 3)
    runtime = Runtime(config_factory(enabled=True))
    try:
        runtime.count_feature("a")
        runtime.count_feature("b")
        original = runtime.database.enqueue_telemetry

        def fail_after_new_names(*_args, **_kwargs):
            runtime.count_feature("c")
            runtime.count_feature("d")
            monkeypatch.setattr(runtime.database, "enqueue_telemetry", original)
            raise RuntimeError("enqueue failed")

        monkeypatch.setattr(runtime.database, "enqueue_telemetry", fail_after_new_names)
        await runtime._flush_telemetry()
        assert runtime._feature_counts == {"c": 1, "d": 1, "a": 1}
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_failed_flush_drops_detached_counts_when_consent_is_off(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    try:
        runtime.count_feature("mcp.submit")

        def fail_and_switch_off(*_args, **_kwargs):
            runtime._set_telemetry_enabled(False)
            raise RuntimeError("enqueue failed")

        monkeypatch.setattr(runtime.database, "enqueue_telemetry", fail_and_switch_off)
        await runtime._flush_telemetry()
        assert runtime._feature_counts == {}
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_cancel_after_features_commit_does_not_restore_counts_or_lose_later_ones(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    entered, gate = threading.Event(), threading.Event()
    original = runtime.database.enqueue_telemetry
    committed: list[str] = []

    def commit_then_wait(key, payload, now):
        original(key, payload, now)
        if not committed:
            committed.append(key)
            entered.set()
            gate.wait(5)

    monkeypatch.setattr(runtime.database, "enqueue_telemetry", commit_then_wait)
    seen: list[dict] = []
    original_close = runtime.database.close

    def close_and_record() -> None:
        seen.append(_outbox(runtime))
        original_close()

    runtime.database.close = close_and_record
    try:
        runtime.count_feature("mcp.submit")
        flushing = asyncio.create_task(runtime._flush_telemetry())
        assert await asyncio.to_thread(entered.wait, 5)
        flushing.cancel()
        gate.set()
        with pytest.raises(asyncio.CancelledError):
            await flushing
        assert runtime._feature_counts == {}
        runtime.count_feature("mcp.wait")
        await runtime.close()
    finally:
        gate.set()
    features = [value["counts"] for key, value in seen[0].items() if key.startswith("features:")]
    assert sorted(features, key=lambda counts: sorted(counts)) == [{"mcp.submit": 1}, {"mcp.wait": 1}]


@pytest.mark.asyncio
async def test_flushes_within_one_clock_tick_keep_separate_feature_events(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.setattr("refract.runtime.utc_now", lambda: "2026-11-11T00:00:00+00:00")
    runtime = Runtime(config_factory(enabled=True))
    try:
        runtime.count_feature("mcp.submit")
        await runtime._flush_telemetry()
        runtime.count_feature("mcp.wait")
        await runtime._flush_telemetry()
        features = [value["counts"] for key, value in _outbox(runtime).items() if key.startswith("features:")]
        assert sorted(features, key=lambda counts: sorted(counts)) == [{"mcp.submit": 1}, {"mcp.wait": 1}]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_close_waits_for_an_in_flight_sender_database_call_before_closing_sqlite(config_factory, monkeypatch) -> None:
    from refract.product_telemetry import send_outbox_once

    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    entered, gate, finished, closed = (threading.Event() for _ in range(4))
    errors: list[BaseException] = []
    original_batch = runtime.database.telemetry_batch
    original_close = runtime.database.close

    def gated_batch(limit):
        entered.set()
        gate.wait(5)
        try:
            return original_batch(limit)
        except BaseException as exc:
            errors.append(exc)
            raise
        finally:
            finished.set()

    def close_and_signal() -> None:
        closed.set()
        original_close()

    runtime.database.telemetry_batch = gated_batch
    runtime.database.close = close_and_signal
    runtime._telemetry_task = asyncio.create_task(send_outbox_once(
        runtime.database, runtime._telemetry_config_check, runtime.config.home, purge_lock=runtime._flush_lock,
    ))
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        closing = asyncio.create_task(runtime.close())
        assert not await asyncio.to_thread(closed.wait, 0.5)
        gate.set()
        await closing
    finally:
        gate.set()
    assert finished.is_set()
    assert errors == []


class _Delivered:
    status = 200


@pytest.mark.asyncio
async def test_cancel_after_commit_and_delivery_does_not_restore_or_resend_counts(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    entered, gate = threading.Event(), threading.Event()
    original = runtime.database.enqueue_telemetry
    first: list[str] = []

    def commit_then_wait(key, payload, now):
        original(key, payload, now)
        if not first:
            first.append(key)
            entered.set()
            gate.wait(5)

    monkeypatch.setattr(runtime.database, "enqueue_telemetry", commit_then_wait)
    posts: list[object] = []

    def opener(request, timeout):
        posts.append(request)
        return _Delivered()

    try:
        runtime.count_feature("mcp.submit")
        flushing = asyncio.create_task(runtime._flush_telemetry())
        assert await asyncio.to_thread(entered.wait, 5)
        await send_outbox_once(runtime.database, runtime._telemetry_config_check, runtime.config.home, opener=opener)
        assert len(posts) == 1
        assert _outbox(runtime) == {}
        flushing.cancel()
        gate.set()
        with pytest.raises(asyncio.CancelledError):
            await flushing
        assert runtime._feature_counts == {}
        await runtime._flush_telemetry()
        assert not [key for key in _outbox(runtime) if key.startswith("features:")]
    finally:
        gate.set()
        await runtime.close()


@pytest.mark.asyncio
async def test_pre_commit_enqueue_failure_under_repeated_cancel_restores_counts_and_joins_thread(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    entered, gate, finished = threading.Event(), threading.Event(), threading.Event()

    def fail_before_commit(*_args, **_kwargs):
        entered.set()
        gate.wait(5)
        finished.set()
        raise RuntimeError("enqueue failed")

    monkeypatch.setattr(runtime.database, "enqueue_telemetry", fail_before_commit)
    period_start = runtime._feature_period_start
    try:
        runtime.count_feature("mcp.submit")
        flushing = asyncio.create_task(runtime._flush_telemetry())
        assert await asyncio.to_thread(entered.wait, 5)
        flushing.cancel()
        await asyncio.sleep(0)
        flushing.cancel()
        assert not flushing.done()
        gate.set()
        with pytest.raises(asyncio.CancelledError):
            await flushing
        assert finished.is_set()
        assert runtime._feature_counts == {"mcp.submit": 1}
        assert runtime._feature_period_start == period_start
        assert not (runtime.config.home / "telemetry_heartbeat").exists()
    finally:
        gate.set()
        runtime.database.close()


def _write_telemetry_config(path, *, enabled: bool = True, args: str = "--old-args-secret",
                            env: str = "old-env-secret",
                            endpoint: str | None = "https://telemetry.example.invalid/v1/events") -> None:
    endpoint_line = f'endpoint = "{endpoint}"\n' if endpoint is not None else ""
    path.write_text(
        f'[daemon]\ndefault_profile = "balanced"\n\n[telemetry]\nenabled = {str(enabled).lower()}\n'
        f'{endpoint_line}\n'
        f'[[targets]]\nid = "worker"\nbackend = "pi"\nargs = ["{args}"]\nenv = {{ TOKEN = "{env}" }}\n\n'
        '[profiles.balanced]\nimplement = "worker"\nreview = "worker"\nconsult = "worker"\nother = "worker"\n',
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_runtime_warns_when_reload_loads_ignored_telemetry_endpoint(tmp_path, caplog) -> None:
    config_path = tmp_path / "config.toml"
    _write_telemetry_config(config_path, endpoint=None)
    runtime = Runtime(load_config(config_path))
    try:
        await runtime.start()
        caplog.clear()
        _write_telemetry_config(config_path, endpoint="x")
        with runtime._lock:
            runtime._reload_catalog_locked()
        records = [
            record for record in caplog.records
            if getattr(record, "event", None) == "config.ignored_keys"
        ]
        assert len(records) == 1
        assert records[0].levelno == logging.WARNING
        assert records[0].keys == ("telemetry.endpoint",)
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_queued_event_redacts_values_the_job_ran_with_after_config_rotation(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.delenv("REFRACT_TELEMETRY", raising=False)
    config_path = tmp_path / "config.toml"
    _write_telemetry_config(config_path)
    runtime = Runtime(load_config(config_path))

    async def rotate_then_fail(**_kwargs):
        _write_telemetry_config(config_path, args="--rotated-arguments", env="rotated-environment-value")
        return DriverResult("REQUEST_FATAL", "", "", "failed with --old-args-secret and old-env-secret", "execution_error")

    runtime.drivers.execute = rotate_then_fail
    try:
        project = runtime.database.upsert_project(project_id="p", root=str(tmp_path / "root"))
        await runtime.start()
        submitted = await runtime.submit(project.id, "implement", "prompt")
        job = await runtime.wait(submitted.job_id, timeout_s=10)
        await _drain_enqueue(runtime)
        assert job.state == "failed"
        payload = _outbox(runtime)[f"job:{submitted.job_id}"]
        assert "old-args-secret" not in payload["error"]
        assert "old-env-secret" not in payload["error"]
        assert runtime.target_executor.run_secrets == {}
    finally:
        await runtime.close()


def _delivered_status(status: int):
    def opener(_request, *, timeout):
        return type("Response", (), {"status": status})()
    return opener


@pytest.mark.asyncio
async def test_second_terminal_callback_after_delivery_enqueues_nothing(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.delenv("REFRACT_TELEMETRY", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    try:
        _terminal_job(runtime)
        runtime.scheduler.complete = lambda *_args, **_kwargs: None
        await runtime._job_terminal("job-one", "succeeded")
        await _drain_enqueue(runtime)
        await send_outbox_once(runtime.database, runtime._telemetry_config_check, runtime.config.home,
                               _delivered_status(204), purge_lock=runtime._flush_lock)
        assert _outbox(runtime) == {}
        await runtime._job_terminal("job-one", "succeeded", changed=False)
        await _drain_enqueue(runtime)
        assert _outbox(runtime) == {}
    finally:
        await runtime.close()


class _ProbeLock:
    """The purge lock, signalling when a caller has to wait for it."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.contended = threading.Event()

    def __enter__(self) -> "_ProbeLock":
        if not self._lock.acquire(blocking=False):
            self.contended.set()
            self._lock.acquire()
        return self

    def __exit__(self, *_exc) -> None:
        self._lock.release()


@pytest.mark.asyncio
async def test_enqueue_past_its_consent_check_cannot_write_after_opt_out_purge(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.delenv("REFRACT_TELEMETRY", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    runtime._flush_lock = lock = _ProbeLock()
    loop = asyncio.get_running_loop()
    purged = asyncio.Event()
    paused, release = threading.Event(), threading.Event()
    real_metrics, real_clear = runtime.database.job_metrics_row, runtime.database.clear_telemetry_outbox

    def gated_metrics(job_id):
        paused.set()
        assert release.wait(10)
        return real_metrics(job_id)

    def signalling_clear():
        real_clear()
        loop.call_soon_threadsafe(purged.set)

    monkeypatch.setattr(runtime.database, "job_metrics_row", gated_metrics)
    monkeypatch.setattr(runtime.database, "clear_telemetry_outbox", signalling_clear)
    try:
        _terminal_job(runtime)
        runtime.scheduler.complete = lambda *_args, **_kwargs: None
        await runtime._job_terminal("job-one", "succeeded")
        assert await asyncio.to_thread(paused.wait, 10)
        monkeypatch.setenv("REFRACT_TELEMETRY", "0")
        purge_task = asyncio.create_task(send_outbox_once(
            runtime.database, runtime._telemetry_config_check, runtime.config.home, purge_lock=lock))
        waiters = {asyncio.create_task(asyncio.to_thread(lock.contended.wait, 10)), asyncio.create_task(purged.wait())}
        await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
        release.set()
        await purge_task
        await _drain_enqueue(runtime)
        assert runtime.telemetry_enabled is False
        assert _outbox(runtime) == {}
    finally:
        release.set()
        lock.contended.set()
        await runtime.close()


@pytest.mark.asyncio
async def test_sender_that_passed_its_gate_does_not_post_after_opt_out(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.delenv("REFRACT_TELEMETRY", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    posts = []
    paused, release = threading.Event(), threading.Event()
    real_batch = runtime.database.telemetry_batch

    def gated_batch(limit):
        paused.set()
        assert release.wait(10)
        return real_batch(limit)

    monkeypatch.setattr(runtime.database, "telemetry_batch", gated_batch)
    try:
        runtime.database.enqueue_telemetry("job:pending", '{"event":"job"}', datetime.now(timezone.utc).isoformat())
        sender_task = asyncio.create_task(send_outbox_once(
            runtime.database, runtime._telemetry_config_check, runtime.config.home,
            lambda *a, **kw: posts.append((a, kw)), purge_lock=runtime._flush_lock))
        assert await asyncio.to_thread(paused.wait, 10)
        monkeypatch.setenv("REFRACT_TELEMETRY", "0")
        runtime._telemetry_config_check()
        release.set()
        await sender_task
        assert posts == []
        assert _outbox(runtime) == {}
    finally:
        release.set()
        await runtime.close()


@pytest.mark.asyncio
async def test_job_that_ended_while_off_is_not_queued_after_opt_in(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.delenv("REFRACT_TELEMETRY", raising=False)
    runtime = Runtime(config_factory(enabled=False))
    try:
        _terminal_job(runtime)
        runtime.scheduler.complete = lambda *_args, **_kwargs: None
        await runtime._job_terminal("job-one", "succeeded")
        monkeypatch.setenv("REFRACT_TELEMETRY", "1")
        await _drain_enqueue(runtime)
        await runtime._job_terminal("job-one", "succeeded", changed=False)
        await _drain_enqueue(runtime)
        assert _outbox(runtime) == {}
        assert not (runtime.config.home / "telemetry_id").exists()
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_config_reload_that_observes_opt_out_updates_flag_and_clears_counts(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.delenv("REFRACT_TELEMETRY", raising=False)
    config_path = tmp_path / "config.toml"
    _write_telemetry_config(config_path)
    runtime = Runtime(load_config(config_path))
    try:
        await _call_mcp("submit", runtime)
        assert runtime._feature_counts
        _write_telemetry_config(config_path, enabled=False)
        runtime.publish_configuration()
        assert runtime.telemetry_enabled is False
        assert runtime._feature_counts == {}
        await _call_mcp("submit", runtime)
        assert runtime._feature_counts == {}
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_job_that_ends_during_shutdown_is_enqueued_before_the_database_closes(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.delenv("REFRACT_TELEMETRY", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    _terminal_job(runtime)
    queued_at_close = []
    real_close = runtime.database.close

    def recording_close():
        queued_at_close.extend(_outbox(runtime))
        real_close()

    runtime.database.close = recording_close

    async def terminate_during_close():
        await runtime._job_terminal("job-one", "interrupted")

    runtime.scheduler.close = terminate_during_close
    await runtime.close()
    assert "job:job-one" in queued_at_close


# Acceptance round 2: one consent owner, dedup at the source, secret release.

def _gated(monkeypatch, name: str, module: str = "refract.product_telemetry"):
    """Wrap a module function so a worker thread pauses on entry until released."""
    import importlib

    target = importlib.import_module(module)
    real = getattr(target, name)
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()

    def gated(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        try:
            return real(*args, **kwargs)
        finally:
            finished.set()

    monkeypatch.setattr(target, name, gated)
    return entered, release, finished


class _Response:
    status = 204


@pytest.mark.asyncio
async def test_cancelled_sender_joins_its_worker_before_the_purge_lock_releases(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.delenv("REFRACT_TELEMETRY", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    entered, release, finished = _gated(monkeypatch, "install_id")
    purged, posts_after_purge = threading.Event(), []
    real_clear = runtime.database.clear_telemetry_outbox
    monkeypatch.setattr(runtime.database, "clear_telemetry_outbox", lambda: (real_clear(), purged.set()))
    opener = lambda *a, **k: (posts_after_purge.append(True) if purged.is_set() else None, _Response())[1]
    try:
        runtime.database.enqueue_telemetry("job:pending", '{"event":"job"}', utc_now_text())
        sender_task = asyncio.create_task(send_outbox_once(
            runtime.database, runtime._telemetry_config_check, runtime.config.home, opener,
            purge_lock=runtime._flush_lock))
        assert await asyncio.to_thread(entered.wait, 10)
        sender_task.cancel()
        monkeypatch.setenv("REFRACT_TELEMETRY", "0")
        purge_task = asyncio.create_task(send_outbox_once(
            runtime.database, runtime._telemetry_config_check, runtime.config.home, opener,
            purge_lock=runtime._flush_lock))
        await asyncio.wait({sender_task, purge_task}, timeout=0.3)
        release.set()
        await asyncio.gather(sender_task, purge_task, return_exceptions=True)
        assert await asyncio.to_thread(finished.wait, 10)
        assert posts_after_purge == []
        assert not (runtime.config.home / "telemetry_id").exists()
        assert _outbox(runtime) == {}
    finally:
        release.set()
        await runtime.close()


def utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.mark.asyncio
async def test_opt_out_publish_waits_for_the_sender_and_no_post_follows_it(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.delenv("REFRACT_TELEMETRY", raising=False)
    config_path = tmp_path / "config.toml"
    _write_telemetry_config(config_path)
    runtime = Runtime(load_config(config_path))
    entered, release, finished = _gated(monkeypatch, "install_id")
    published, posts_after_publish = threading.Event(), []
    opener = lambda *a, **k: (posts_after_publish.append(True) if published.is_set() else None, _Response())[1]

    def publish_opt_out() -> None:
        _write_telemetry_config(config_path, enabled=False)
        runtime.publish_configuration()
        published.set()

    try:
        runtime.database.enqueue_telemetry("job:pending", '{"event":"job"}', utc_now_text())
        sender_task = asyncio.create_task(send_outbox_once(
            runtime.database, runtime._telemetry_config_check, runtime.config.home, opener,
            purge_lock=runtime._flush_lock))
        assert await asyncio.to_thread(entered.wait, 10)
        publishing = asyncio.create_task(asyncio.to_thread(publish_opt_out))
        await asyncio.wait({publishing}, timeout=0.3)
        release.set()
        await asyncio.gather(sender_task, publishing)
        assert posts_after_publish == []
        assert runtime.telemetry_enabled is False
        assert not (runtime.config.home / "telemetry_id").exists()
        assert _outbox(runtime) == {}
    finally:
        release.set()
        await runtime.close()


@pytest.mark.asyncio
async def test_job_finishing_after_an_unpublished_opt_in_is_queued(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.delenv("REFRACT_TELEMETRY", raising=False)
    config_path = tmp_path / "config.toml"
    _write_telemetry_config(config_path, enabled=False)
    runtime = Runtime(load_config(config_path))
    try:
        _terminal_job(runtime)
        runtime.scheduler.complete = lambda *_args, **_kwargs: None
        _write_telemetry_config(config_path, enabled=True)
        await runtime._job_terminal("job-one", "succeeded")
        await _drain_enqueue(runtime)
        assert list(_outbox(runtime)) == ["job:job-one"]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_job_finishing_after_an_unpublished_opt_out_is_not_queued(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.delenv("REFRACT_TELEMETRY", raising=False)
    config_path = tmp_path / "config.toml"
    _write_telemetry_config(config_path)
    runtime = Runtime(load_config(config_path))
    try:
        _terminal_job(runtime)
        runtime.scheduler.complete = lambda *_args, **_kwargs: None
        _write_telemetry_config(config_path, enabled=False)
        await runtime._job_terminal("job-one", "succeeded")
        await _drain_enqueue(runtime)
        assert _outbox(runtime) == {}
        assert not (runtime.config.home / "telemetry_id").exists()
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_second_terminal_callback_enqueues_nothing_after_the_seen_window_would_have_rolled(config_factory, monkeypatch) -> None:
    import refract.runtime as runtime_module

    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.delenv("REFRACT_TELEMETRY", raising=False)
    monkeypatch.setattr(runtime_module, "MAX_TELEMETRY_SEEN", 3, raising=False)
    runtime = Runtime(config_factory(enabled=True))
    try:
        _terminal_job(runtime)
        runtime.scheduler.complete = lambda *_args, **_kwargs: None
        await runtime._job_terminal("job-one", "succeeded")
        await _drain_enqueue(runtime)
        assert list(_outbox(runtime)) == ["job:job-one"]
        await send_outbox_once(runtime.database, runtime._telemetry_config_check, runtime.config.home,
                               _delivered_status(204), purge_lock=runtime._flush_lock)
        assert _outbox(runtime) == {}
        for index in range(5):
            await runtime._job_terminal(f"other-{index}", "succeeded")
        await _drain_enqueue(runtime)
        # The runner reports an already-terminal job again after cancellation.
        await runtime.runner._finish_cancelled_job("job-one", asyncio.CancelledError(), None)
        await _drain_enqueue(runtime)
        assert _outbox(runtime) == {}
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_invalid_ordinary_reload_turns_counting_off(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.delenv("REFRACT_TELEMETRY", raising=False)
    config_path = tmp_path / "config.toml"
    _write_telemetry_config(config_path)
    runtime = Runtime(load_config(config_path))
    try:
        await _call_mcp("submit", runtime)
        assert runtime._feature_counts
        config_path.write_text("[telemetry\nenabled = true\n", encoding="utf-8")
        with pytest.raises(ValueError):
            runtime.publish_configuration()
        assert runtime.telemetry_enabled is False
        assert runtime._feature_counts == {}
        await _call_mcp("submit", runtime)
        assert runtime._feature_counts == {}
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_run_secrets_are_released_when_terminal_persistence_keeps_failing(config_factory, monkeypatch) -> None:
    from types import SimpleNamespace

    from refract.scheduler import CancelEvent

    runtime = Runtime(config_factory(enabled=True))
    project = runtime.database.upsert_project(project_id="project-one", root="/project")
    runtime.database.create_job(
        job_id="job-one", project_id=project.id, workflow="implement", profile="balanced",
        prompt="prompt", execution_plan_json=json.dumps({"targets": []}), session="session",
    )

    async def execute(**kwargs):
        runtime.target_executor.run_secrets[kwargs["job_id"]] = ("launch-secret",)
        return SimpleNamespace(result=SimpleNamespace(outcome="FAILED", error="boom"), outcome={})

    def failing_finish(*_args, **_kwargs):
        raise RuntimeError("terminal storage down")

    monkeypatch.setattr("refract.execution.parse_execution_plan", lambda _plan: object())
    monkeypatch.setattr(runtime.target_executor, "execute", execute)
    monkeypatch.setattr(runtime.database, "finish_job", failing_finish)
    cancel_event = CancelEvent()
    try:
        with pytest.raises(RuntimeError):
            await runtime.runner.run("job-one", cancel_event)
        assert runtime.target_executor.run_secrets == {}
        runtime.target_executor.run_secrets["job-two"] = ("other-secret",)
    finally:
        await runtime.close()
    assert runtime.target_executor.run_secrets == {}


@pytest.mark.asyncio
async def test_stale_config_check_decision_cannot_re_enable_consent_after_opt_out(monkeypatch, tmp_path) -> None:
    import refract.runtime as runtime_module

    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.delenv("REFRACT_TELEMETRY", raising=False)
    config_path = tmp_path / "config.toml"
    _write_telemetry_config(config_path)
    runtime = Runtime(load_config(config_path))
    decided, release = threading.Event(), threading.Event()
    real_decision = runtime_module.telemetry_decision

    def gated_decision(config):
        result = real_decision(config)
        if sys._getframe(1).f_code.co_name == "_telemetry_config_check" and not decided.is_set():
            decided.set()
            assert release.wait(10)
        return result

    def stale_check() -> None:
        runtime._telemetry_config_check()

    def publish_opt_out() -> None:
        _write_telemetry_config(config_path, enabled=False)
        runtime.publish_configuration()

    monkeypatch.setattr(runtime_module, "telemetry_decision", gated_decision)
    try:
        runtime.database.enqueue_telemetry("job:pending", '{"event":"job"}', utc_now_text())
        runtime.count_feature("submit")
        (runtime.config.home / "telemetry_id").write_text("id", encoding="utf-8")
        checking = asyncio.create_task(asyncio.to_thread(stale_check))
        assert await asyncio.to_thread(decided.wait, 10)
        publishing = asyncio.create_task(asyncio.to_thread(publish_opt_out))
        await asyncio.wait({publishing}, timeout=0.3)
        release.set()
        await asyncio.gather(checking, publishing)
        assert runtime.telemetry_enabled is False
        assert runtime._feature_counts == {}
        assert not (runtime.config.home / "telemetry_id").exists()
        assert _outbox(runtime) == {}
    finally:
        release.set()
        await runtime.close()


def _run_job_stub(runtime: Runtime, monkeypatch, *, fresh: bool) -> None:
    from types import SimpleNamespace

    project = runtime.database.upsert_project(project_id="project-one", root="/project")
    runtime.database.create_job(
        job_id="job-one", project_id=project.id, workflow="implement", profile="balanced",
        prompt="prompt", execution_plan_json=json.dumps({"targets": []}), session="session", fresh=fresh,
    )

    async def execute(**_kwargs):
        return SimpleNamespace(
            result=SimpleNamespace(outcome="SUCCESS", error="", text="done", session_id="backend-session"),
            outcome={}, target_id="target", target_key="key", session_key="key", scoped_session="session",
        )

    runtime.scheduler.complete = lambda *_args, **_kwargs: None
    monkeypatch.setattr("refract.execution.parse_execution_plan", lambda _plan: object())
    monkeypatch.setattr(runtime.target_executor, "execute", execute)


@pytest.mark.asyncio
async def test_cancel_during_the_terminal_commit_queues_the_job_event_once(config_factory, monkeypatch) -> None:
    from refract.scheduler import CancelEvent

    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.delenv("REFRACT_TELEMETRY", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    _run_job_stub(runtime, monkeypatch, fresh=False)
    entered, release = threading.Event(), threading.Event()
    real_finish, real_enqueue, enqueued = runtime.database.finish_job, runtime.database.enqueue_telemetry, []

    def gated_finish(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return real_finish(*args, **kwargs)

    monkeypatch.setattr(runtime.database, "finish_job", gated_finish)
    monkeypatch.setattr(runtime.database, "enqueue_telemetry", lambda *a, **k: (enqueued.append(a[0]), real_enqueue(*a, **k))[1])
    try:
        task = asyncio.create_task(runtime.runner.run("job-one", CancelEvent()))
        assert await asyncio.to_thread(entered.wait, 10)
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        await _drain_enqueue(runtime)
        assert runtime.database.job("job-one").state == "succeeded"
        assert enqueued == ["job:job-one"]
        assert list(_outbox(runtime)) == ["job:job-one"]
    finally:
        release.set()
        await runtime.close()


@pytest.mark.asyncio
async def test_fresh_session_success_reports_the_transition_and_queues_its_event(config_factory, monkeypatch) -> None:
    from refract.scheduler import CancelEvent

    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.delenv("REFRACT_TELEMETRY", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    _run_job_stub(runtime, monkeypatch, fresh=True)
    try:
        await runtime.runner.run("job-one", CancelEvent())
        await _drain_enqueue(runtime)
        assert runtime.database.job("job-one").state == "succeeded"
        assert list(_outbox(runtime)) == ["job:job-one"]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_close_joins_an_in_flight_sender_thread(config_factory, monkeypatch) -> None:
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.delenv("REFRACT_TELEMETRY", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    entered, release, finished = _gated(monkeypatch, "install_id")
    opener = lambda *a, **k: _Response()
    # No purge lock is passed, so only the join in close can hold it back.
    try:
        runtime.database.enqueue_telemetry("job:pending", '{"event":"job"}', utc_now_text())
        runtime._telemetry_task = asyncio.create_task(send_outbox_once(
            runtime.database, runtime._telemetry_config_check, runtime.config.home, opener))
        assert await asyncio.to_thread(entered.wait, 10)
        closing = asyncio.create_task(runtime.close())
        await asyncio.wait({closing}, timeout=0.3)
        assert not closing.done()
        release.set()
        await closing
        assert finished.is_set()
    finally:
        release.set()


def _gate_finish(runtime: Runtime, monkeypatch):
    """Gate database.finish_job on events and count enqueue calls."""
    entered, release, enqueued = threading.Event(), threading.Event(), []
    real_finish, real_enqueue = runtime.database.finish_job, runtime.database.enqueue_telemetry

    def gated_finish(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return real_finish(*args, **kwargs)

    monkeypatch.setattr(runtime.database, "finish_job", gated_finish)
    monkeypatch.setattr(runtime.database, "enqueue_telemetry",
                        lambda *a, **k: (enqueued.append(a[0]), real_enqueue(*a, **k))[1])
    return entered, release, enqueued


async def _cancel_during_commit(runtime: Runtime, cancel_event, entered, release, enqueued, state: str) -> None:
    task = asyncio.create_task(runtime.runner.run("job-one", cancel_event))
    assert await asyncio.to_thread(entered.wait, 10)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    await _drain_enqueue(runtime)
    assert runtime.database.job("job-one").state == state
    assert [key for key in enqueued if key.startswith("job:")] == ["job:job-one"]
    assert [key for key in _outbox(runtime) if key.startswith("job:")] == ["job:job-one"]
    assert runtime.runner._commits == {}


@pytest.mark.asyncio
async def test_cancel_during_the_cancelled_before_execution_commit_queues_the_event_once(config_factory, monkeypatch) -> None:
    from refract.scheduler import CancelEvent

    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.delenv("REFRACT_TELEMETRY", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    _run_job_stub(runtime, monkeypatch, fresh=False)
    entered, release, enqueued = _gate_finish(runtime, monkeypatch)
    cancel_event = CancelEvent()
    cancel_event.set()
    try:
        await _cancel_during_commit(runtime, cancel_event, entered, release, enqueued, "cancelled")
    finally:
        release.set()
        await runtime.close()


@pytest.mark.asyncio
async def test_cancel_during_the_project_removed_commit_queues_the_event_once(config_factory, monkeypatch) -> None:
    from refract.scheduler import CancelEvent

    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.delenv("REFRACT_TELEMETRY", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    _run_job_stub(runtime, monkeypatch, fresh=False)
    entered, release, enqueued = _gate_finish(runtime, monkeypatch)
    monkeypatch.setattr(runtime.database, "project", lambda project_id: None)
    try:
        await _cancel_during_commit(runtime, CancelEvent(), entered, release, enqueued, "failed")
    finally:
        release.set()
        await runtime.close()


@pytest.mark.asyncio
async def test_cancel_during_the_unexpected_failure_commit_queues_the_event_once(config_factory, monkeypatch) -> None:
    from refract.scheduler import CancelEvent

    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.delenv("REFRACT_TELEMETRY", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    _run_job_stub(runtime, monkeypatch, fresh=False)

    async def explode(**_kwargs):
        raise RuntimeError("driver exploded")

    monkeypatch.setattr(runtime.target_executor, "execute", explode)
    entered, release, enqueued = _gate_finish(runtime, monkeypatch)
    try:
        await _cancel_during_commit(runtime, CancelEvent(), entered, release, enqueued, "failed")
    finally:
        release.set()
        await runtime.close()


@pytest.mark.asyncio
async def test_cancel_after_the_normal_path_reported_reports_unchanged(config_factory, monkeypatch) -> None:
    from refract.scheduler import CancelEvent

    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.delenv("REFRACT_TELEMETRY", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    _run_job_stub(runtime, monkeypatch, fresh=False)
    reports, notified, hold = [], [], asyncio.Event()
    real_terminal = runtime.runner.on_terminal
    runtime.runner.on_terminal = lambda job_id, state, **kw: (reports.append(kw["changed"]), real_terminal(job_id, state, **kw))[1]
    terminal_notice = asyncio.Event()

    async def notify(_job_id):
        notified.append(True)
        if len(notified) == 2:
            terminal_notice.set()
            await hold.wait()

    runtime.runner.notifier = notify
    try:
        task = asyncio.create_task(runtime.runner.run("job-one", CancelEvent()))
        await asyncio.wait_for(terminal_notice.wait(), 10)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await _drain_enqueue(runtime)
        assert reports == [True, False]
        assert [key for key in _outbox(runtime) if key.startswith("job:")] == ["job:job-one"]
    finally:
        hold.set()
        await runtime.close()


@pytest.mark.asyncio
async def test_run_finally_removes_the_commit_record(config_factory, monkeypatch) -> None:
    from refract.scheduler import CancelEvent

    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.delenv("REFRACT_TELEMETRY", raising=False)
    runtime = Runtime(config_factory(enabled=True))
    _run_job_stub(runtime, monkeypatch, fresh=False)
    try:
        await runtime.runner.run("job-one", CancelEvent())
        assert runtime.database.job("job-one").state == "succeeded"
        assert runtime.runner._commits == {}
    finally:
        await runtime.close()
