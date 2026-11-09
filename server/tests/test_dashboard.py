from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from starlette.applications import Starlette

from refract.dashboard import DashboardState, register_dashboard_routes


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


def test_routes_are_dashboard_routes_ask_and_actions():
    routes = register_dashboard_routes(DashboardState())
    assert {route.path for route in routes} == {
        "/dashboard",
        "/dashboard/",
        "/dashboard/{path:path}",
        "/dashboard/assets",
        "/dashboard/assets/{path:path}",
        "/ask",
        "/dashboard/api/jobs/{job_id}/cancel",
        "/dashboard/api/jobs/{job_id}/retry",
        "/dashboard/api/jobs/{job_id}/answer",
        "/dashboard/api/shutdown",
        "/dashboard/api/jobs",
        "/dashboard/api/jobs/{job_id}",
        "/dashboard/api/jobs/{job_id}/output",
        "/dashboard/api/targets",
        "/dashboard/api/cards",
        "/dashboard/api/cards/{card_id}",
        "/dashboard/api",
        "/dashboard/api/{rest:path}",
    }


@pytest.mark.asyncio
async def test_dashboard_routes_serve_spa_shell_for_deep_links(tmp_path, monkeypatch):
    static = tmp_path / "app"
    static.mkdir()
    (static / "index.html").write_text("<main>SPA shell</main>", encoding="utf-8")
    monkeypatch.setattr("refract.dashboard._APP_STATIC_DIR", static, raising=False)
    app = Starlette(routes=register_dashboard_routes(DashboardState()))
    for path in ("/dashboard", "/dashboard/", "/dashboard/jobs/job-1", "/dashboard/targets"):
        status, body = await request(app, path)
        assert status == 200
        assert body == b"<main>SPA shell</main>"


@pytest.mark.asyncio
async def test_dashboard_assets_are_not_shell_fallback(tmp_path, monkeypatch):
    static = tmp_path / "app"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<main>SPA shell</main>", encoding="utf-8")
    monkeypatch.setattr("refract.dashboard._APP_STATIC_DIR", static, raising=False)
    app = Starlette(routes=register_dashboard_routes(DashboardState()))
    status, _ = await request(app, "/dashboard/assets/missing.js")
    assert status == 404
    status, _ = await request(app, "/dashboard/assets")
    assert status == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/dashboard", "/dashboard/jobs/job-run", "/dashboard/assets/a.js", "/dashboard/api/cards", "/dashboard/api/cards/c1"])
async def test_dashboard_routes_reject_non_loopback(path):
    app = Starlette(routes=register_dashboard_routes(DashboardState()))
    status, _ = await request(app, path, client_host="192.0.2.10")
    assert status == 403
    status, _ = await request(app, path, headers=(("Host", "evil.example"),))
    assert status == 403
