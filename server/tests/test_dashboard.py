from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from starlette.applications import Starlette

from refract.dashboard import DashboardState, register_dashboard_routes
from refract.models import ConfigHealth, JobResult, JobView, ProjectView, TargetView


async def request(app, path, *, method="GET", headers=(), body=b"", client_host="127.0.0.1"):
    sent = []
    received = False

    async def receive():
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        sent.append(message)

    path, _, query = path.partition("?")
    if not any(key.lower() == "host" for key, _ in headers):
        headers = (("Host", "127.0.0.1:8765"), *headers)
    scope = {
        "type": "http", "http_version": "1.1", "method": method, "path": path,
        "raw_path": path.encode(), "query_string": query.encode(), "headers": [(k.lower().encode(), v.encode()) for k, v in headers],
        "client": (client_host, 1234), "server": ("127.0.0.1", 8765), "scheme": "http", "root_path": "", "app": None,
    }
    await app(scope, receive, send)
    start = next(message for message in sent if message["type"] == "http.response.start")
    chunks = [message.get("body", b"") for message in sent if message["type"] == "http.response.body"]
    return start["status"], b"".join(chunks)


class Registry:
    def __init__(self):
        self.calls = []

    async def ask(self, **kwargs):
        self.calls.append(kwargs)
        return "registered answer"


@pytest.mark.asyncio
async def test_loopback_post_ask_reaches_registry():
    registry = Registry()
    runtime = SimpleNamespace(ask_registry=registry, config=SimpleNamespace(ask_timeout_s=17))
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime)))

    status, body = await request(
        app, "/ask", method="POST",
        headers=(("content-type", "application/json"),),
        body=json.dumps({"token": "token", "question": "What next?", "job_id": "job-1"}).encode(),
    )

    assert status == 200
    assert json.loads(body) == {"answer": "registered answer"}
    assert registry.calls == [{"token": "token", "question": "What next?", "timeout_s": 17, "job_id": "job-1"}]


@pytest.mark.asyncio
async def test_non_loopback_post_ask_is_forbidden():
    registry = Registry()
    runtime = SimpleNamespace(ask_registry=registry, config=SimpleNamespace(ask_timeout_s=17))
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime)))

    status, body = await request(
        app, "/ask", method="POST", client_host="192.0.2.10",
        headers=(("content-type", "application/json"),),
        body=b'{"token":"token","question":"question"}',
    )

    assert status == 403
    assert json.loads(body)["error"] == "Forbidden"
    assert registry.calls == []


@pytest.mark.asyncio
async def test_ask_host_rejects_dns_rebinding() -> None:
    registry = Registry()
    runtime = SimpleNamespace(ask_registry=registry, config=SimpleNamespace(ask_timeout_s=17))
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime)))

    status, body = await request(
        app, "/ask", method="POST", headers=(("Host", "attacker.example"), ("content-type", "application/json")),
        body=b'{"token":"token","question":"question"}',
    )

    assert status == 403
    assert json.loads(body)["error"] == "Forbidden"
    assert registry.calls == []


@pytest.mark.asyncio
async def test_ask_malformed_body_and_empty_question() -> None:
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=SimpleNamespace(
        ask_registry=Registry(), config=SimpleNamespace(ask_timeout_s=17)
    ))))
    for body in (b"", b"not-json", b'{"question":"valid"}', b'{"token":"tok","question":"   "}'):
        status, _ = await request(app, "/ask", method="POST", body=body)
        assert status == 400


@pytest.mark.asyncio
async def test_ask_token_auth_and_wrong_job() -> None:
    from refract.ask import AskRegistry

    registry = AskRegistry()
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=SimpleNamespace(
        ask_registry=registry, config=SimpleNamespace(ask_timeout_s=17)
    ))))
    token = registry.issue_token("job-1")
    for payload in (
        {"token": "unknown-token", "question": "q"},
        {"token": "未知", "question": "q"},
        {"token": token, "question": "q", "job_id": "other-job"},
    ):
        status, _ = await request(app, "/ask", method="POST", body=json.dumps(payload).encode())
        assert status == 403
    registry.revoke_token("job-1")
    status, _ = await request(app, "/ask", method="POST", body=json.dumps({"token": token, "question": "q"}).encode())
    assert status == 403


@pytest.mark.asyncio
async def test_ask_answered_and_conflict() -> None:
    import asyncio
    from refract.ask import AskRegistry

    registry = AskRegistry()
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=SimpleNamespace(
        ask_registry=registry, config=SimpleNamespace(ask_timeout_s=2)
    ))))
    token = registry.issue_token("job-ask")

    async def answer() -> None:
        while not registry.has_pending("job-ask"):
            await asyncio.sleep(0)
        registry.deliver_answer("job-ask", "Answer from coordinator")

    responder = asyncio.create_task(answer())
    status, body = await request(app, "/ask", method="POST", body=json.dumps({"token": token, "question": "What next?"}).encode())
    await responder
    assert status == 200
    assert json.loads(body) == {"answer": "Answer from coordinator"}


@pytest.mark.asyncio
async def test_ask_second_pending_returns_409() -> None:
    import asyncio
    from refract.ask import AskRegistry

    registry = AskRegistry()
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=SimpleNamespace(
        ask_registry=registry, config=SimpleNamespace(ask_timeout_s=2)
    ))))
    token = registry.issue_token("job-conflict")
    first_request = asyncio.create_task(request(app, "/ask", method="POST", body=json.dumps({"token": token, "question": "first"}).encode()))
    while not registry.has_pending("job-conflict"):
        await asyncio.sleep(0)
    status, _ = await request(app, "/ask", method="POST", body=json.dumps({"token": token, "question": "second"}).encode())
    assert status == 409
    registry.deliver_answer("job-conflict", "first answer")
    first_status, first_body = await first_request
    assert first_status == 200
    assert json.loads(first_body) == {"answer": "first answer"}


@pytest.mark.asyncio
async def test_ask_non_loopback_rejected() -> None:
    registry = Registry()
    runtime = SimpleNamespace(ask_registry=registry, config=SimpleNamespace(ask_timeout_s=17))
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime)))
    status, body = await request(
        app, "/ask", method="POST", client_host="192.168.1.50",
        headers=(("content-type", "application/json"),), body=b'{"token":"token","question":"question"}',
    )
    assert status == 403
    assert json.loads(body)["error"] == "Forbidden"
    assert registry.calls == []


def _job(job_id, state, *, created_at="2026-11-04T10:00:00+00:00", result=None):
    return JobView(
        id=job_id, project_id="project-1", workflow="implement", profile="default", state=state, session="",
        target_id="codex-main", retry_of="", created_at=created_at, updated_at=created_at, result=result or JobResult(),
    )


class FakeDatabase:
    def __init__(self, tmp_path, jobs, prompts):
        self.tmp_path = tmp_path
        self._jobs = jobs
        self._prompts = prompts

    def projects(self):
        return [ProjectView(id="project-1", root="/work/alpha", created_at="2026-11-04T09:00:00+00:00")]

    def jobs(self, project_id):
        return list(self._jobs.values()) if project_id == "project-1" else []

    def job(self, job_id):
        return self._jobs.get(job_id)

    def job_record(self, job_id):
        return {"id": job_id, "prompt": self._prompts[job_id]} if job_id in self._jobs else None

    def stream_path(self, job_id):
        return self.tmp_path / f"{job_id}.jsonl"


def _dashboard(tmp_path, *, targets=(), health=None):
    finished = JobResult(text="All done", model="gpt-5", duration_ms=1200, tokens={"tok_input": 10, "tok_output": 4})
    jobs = {
        "job-run": _job("job-run", "running"),
        "job-done": _job("job-done", "succeeded", created_at="2026-11-04T09:30:00+00:00", result=finished),
    }
    prompts = {"job-run": "<script>alert(1)</script> fix it", "job-done": "write docs"}
    runtime = SimpleNamespace(
        database=FakeDatabase(tmp_path, jobs, prompts),
        targets=lambda: list(targets),
        config_health=lambda: health or ConfigHealth(valid=True, source_path="/cfg/config.toml"),
    )
    return Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime)))


def test_routes_are_the_four_dashboard_routes_and_ask():
    routes = register_dashboard_routes(DashboardState())
    assert {route.path for route in routes} == {
        "/dashboard", "/dashboard/jobs/{job_id}", "/dashboard/jobs/{job_id}/output", "/dashboard/targets", "/ask",
    }


@pytest.mark.asyncio
async def test_job_list_shows_state_project_workflow_target_and_age(tmp_path):
    status, body = await request(_dashboard(tmp_path), "/dashboard")
    page = body.decode()
    assert status == 200
    for text in ("job-run", "job-done", "running", "succeeded", "/work/alpha", "implement", "codex-main", "Age"):
        assert text in page
    assert page.index("job-run") < page.index("job-done")
    assert 'href="/dashboard/jobs/job-run"' in page
    assert "tds-data-table" in page and "--surface-neutral-01" in page


@pytest.mark.asyncio
async def test_running_job_detail_shows_prompt_and_polls_output(tmp_path):
    status, body = await request(_dashboard(tmp_path), "/dashboard/jobs/job-run")
    page = body.decode()
    assert status == 200
    assert "fix it" in page
    assert "/dashboard/jobs/job-run/output" in page
    assert "<script>" in page


@pytest.mark.asyncio
async def test_finished_job_detail_shows_result_metadata_and_does_not_poll(tmp_path):
    status, body = await request(_dashboard(tmp_path), "/dashboard/jobs/job-done")
    page = body.decode()
    assert status == 200
    for text in ("write docs", "All done", "gpt-5", "1200", "tok_input", "succeeded"):
        assert text in page
    assert "<script" not in page


@pytest.mark.asyncio
async def test_prompt_script_is_escaped(tmp_path):
    _, body = await request(_dashboard(tmp_path), "/dashboard/jobs/job-run")
    page = body.decode()
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert "<script>alert(1)" not in page


@pytest.mark.asyncio
async def test_unknown_job_is_404(tmp_path):
    status, _ = await request(_dashboard(tmp_path), "/dashboard/jobs/missing")
    assert status == 404
    status, _ = await request(_dashboard(tmp_path), "/dashboard/jobs/missing/output")
    assert status == 404


@pytest.mark.asyncio
async def test_targets_page_shows_open_circuit_and_config_error(tmp_path):
    target = TargetView(
        id="codex-main", model="gpt-5", backend="codex", max_concurrency=2, active=1, healthy=False,
        circuit_open_until="2026-11-04T11:00:00+00:00", breaker_state="open", cooldown_s=60, probing=False,
    )
    health = ConfigHealth(valid=False, source_path="/cfg/config.toml", latest_error="targets[0].model <bad> is required")
    status, body = await request(_dashboard(tmp_path, targets=[target], health=health), "/dashboard/targets")
    page = body.decode()
    assert status == 200
    for text in ("codex-main", "gpt-5", "codex", "open", "2026-11-04T11:00:00+00:00", "/cfg/config.toml"):
        assert text in page
    assert "targets[0].model &lt;bad&gt; is required" in page
    assert "tds-announcement--error" in page


@pytest.mark.asyncio
async def test_output_returns_events_after_n(tmp_path):
    events = [{"kind": f"event-{index}", "data": {"index": index}} for index in (1, 2, 3)]
    (tmp_path / "job-run.jsonl").write_text("".join(json.dumps(event) + "\n" for event in events))
    status, body = await request(_dashboard(tmp_path), "/dashboard/jobs/job-run/output?after=1")
    assert status == 200
    payload = json.loads(body)
    assert [event["seq"] for event in payload["events"]] == [2, 3]
    assert [event["kind"] for event in payload["events"]] == ["event-2", "event-3"]
    assert payload["next"] == 3
    assert payload["state"] == "running"
    assert payload["terminal"] is False


@pytest.mark.asyncio
async def test_output_without_stream_file_is_empty_and_terminal_for_finished_job(tmp_path):
    status, body = await request(_dashboard(tmp_path), "/dashboard/jobs/job-done/output?after=0")
    assert status == 200
    assert json.loads(body) == {"events": [], "next": 0, "state": "succeeded", "terminal": True}


@pytest.mark.asyncio
async def test_output_rejects_bad_after(tmp_path):
    status, _ = await request(_dashboard(tmp_path), "/dashboard/jobs/job-run/output?after=x")
    assert status == 400


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path", ["/dashboard", "/dashboard/jobs/job-run", "/dashboard/jobs/job-run/output", "/dashboard/targets"],
)
async def test_dashboard_routes_reject_non_loopback(tmp_path, path):
    status, _ = await request(_dashboard(tmp_path), path, client_host="192.0.2.10")
    assert status == 403
    status, _ = await request(_dashboard(tmp_path), path, headers=(("Host", "evil.example"),))
    assert status == 403
