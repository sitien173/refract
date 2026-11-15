"""`GET /dashboard/api/events`: server-sent hub signals, subscriber cleanup and the loopback guard."""

from __future__ import annotations

import asyncio
import gc
import json
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.applications import Starlette

from refract.api.http.common import DashboardState
from refract.api.http.events import RESYNC, event_stream
from refract.api.http.routes import register_dashboard_routes
from refract.scheduling.hub import Hub
from tests.test_dashboard_api import api_request

_PATH = "/dashboard/api/events"


def _frame(text: str) -> dict[str, str]:
    return json.loads(text.removeprefix("data: "))


async def _until(predicate, timeout_s: float = 2.0) -> None:
    async with asyncio.timeout(timeout_s):
        while not predicate():
            await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_stream_delivers_terminal_signal_and_ends_on_closing() -> None:
    hub = Hub()
    closing = False
    stream = event_stream(hub.subscribe(), lambda: closing, keepalive_s=0.05)

    assert await anext(stream) == ": connected\n\n"
    hub.publish("job-1", "terminal")
    frame = await anext(stream)
    assert _frame(frame) == {"job_id": "job-1", "kind": "terminal"}

    closing = True
    hub.wake()
    with pytest.raises(StopAsyncIteration):
        while True:
            await anext(stream)
    assert hub.subscriber_count == 0


@pytest.mark.asyncio
async def test_stream_sends_keepalive_when_idle() -> None:
    hub = Hub()
    stream = event_stream(hub.subscribe(), lambda: False, keepalive_s=0.01)
    await anext(stream)
    assert await anext(stream) == ": keepalive\n\n"
    await stream.aclose()
    assert hub.subscriber_count == 0


@pytest.mark.asyncio
async def test_asgi_client_disconnect_removes_the_subscriber() -> None:
    hub = Hub()
    runtime = SimpleNamespace(hub=hub, closing=False)
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime)))
    sent: list[dict[str, Any]] = []
    disconnect = asyncio.Event()

    async def receive() -> dict[str, Any]:
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = {
        "type": "http", "http_version": "1.1", "method": "GET", "path": _PATH, "raw_path": _PATH.encode(),
        "query_string": b"", "headers": [(b"host", b"127.0.0.1:8765")], "client": ("127.0.0.1", 1234),
        "server": ("127.0.0.1", 8765), "scheme": "http", "root_path": "", "app": None,
    }
    task = asyncio.ensure_future(app(scope, receive, send))
    try:
        await _until(lambda: hub.subscriber_count == 1)
        hub.publish("job-9", "terminal")
        await _until(lambda: any(b"job-9" in message.get("body", b"") for message in sent))
        start = next(message for message in sent if message["type"] == "http.response.start")
        assert start["status"] == 200
        assert dict(start["headers"])[b"content-type"].startswith(b"text/event-stream")

        disconnect.set()
        await asyncio.wait_for(task, 2.0)
        assert hub.subscriber_count == 0
    finally:
        disconnect.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_task_cancellation_removes_the_subscriber() -> None:
    hub = Hub()
    stream = event_stream(hub.subscribe(), lambda: False)

    entered = asyncio.Event()

    async def consume() -> None:
        async for _ in stream:
            entered.set()

    task = asyncio.ensure_future(consume())
    await asyncio.wait_for(entered.wait(), 2.0)
    assert hub.subscriber_count == 1
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert hub.subscriber_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("client_host", "host"), [("192.0.2.10", "127.0.0.1:8765"), ("127.0.0.1", "evil.example:8765")]
)
async def test_events_rejects_non_loopback_client_or_host(client_host: str, host: str) -> None:
    hub = Hub()
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=SimpleNamespace(hub=hub, closing=False))))

    status, body, _ = await api_request(
        app, _PATH, method="GET", client_host=client_host, headers=(("Host", host),)
    )

    assert status == 403 and body["code"] == "forbidden"
    assert hub.subscriber_count == 0


def _scope(headers: list[tuple[bytes, bytes]]) -> dict[str, Any]:
    return {
        "type": "http", "http_version": "1.1", "method": "GET", "path": _PATH, "raw_path": _PATH.encode(),
        "query_string": b"", "headers": [(b"host", b"127.0.0.1:8765"), *headers], "client": ("127.0.0.1", 1234),
        "server": ("127.0.0.1", 8765), "scheme": "http", "root_path": "", "app": None,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers",
    [
        (("Origin", "http://evil.example"),),
        (("Origin", "http://127.0.0.1:9999"),),
        (("Origin", "null"),),
        (("Sec-Fetch-Site", "cross-site"),),
        (("Sec-Fetch-Site", "same-site"),),
        (("Origin", "http://127.0.0.1:8765"), ("Sec-Fetch-Site", "cross-site")),
    ],
)
async def test_events_rejects_foreign_origin_and_cross_site(headers) -> None:
    hub = Hub()
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=SimpleNamespace(hub=hub, closing=False))))

    status, body, _ = await api_request(app, _PATH, method="GET", headers=headers)

    assert status == 403 and body["code"] == "csrf_rejected"
    assert hub.subscriber_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers",
    [(), (("Origin", "http://127.0.0.1:8765"),), (("Sec-Fetch-Site", "same-origin"),)],
)
async def test_events_allows_same_origin_and_absent_headers(headers) -> None:
    hub = Hub()
    runtime = SimpleNamespace(hub=hub, closing=True)
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime)))
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = _scope([(k.lower().encode(), v.encode()) for k, v in headers])
    await asyncio.wait_for(app(scope, receive, send), 2.0)

    assert sent[0]["status"] == 200
    assert hub.subscriber_count == 0


@pytest.mark.asyncio
async def test_signal_published_at_response_start_is_not_lost() -> None:
    hub = Hub()
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=SimpleNamespace(hub=hub, closing=False))))
    sent: list[dict[str, Any]] = []
    disconnect = asyncio.Event()

    async def receive() -> dict[str, Any]:
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)
        if message["type"] == "http.response.start":
            # Headers are out, the generator has not run: the boundary where a late subscription misses signals.
            hub.publish("job-early", "terminal")

    task = asyncio.ensure_future(app(_scope([]), receive, send))
    try:
        await _until(lambda: any(b"job-early" in message.get("body", b"") for message in sent))
    finally:
        disconnect.set()
        await asyncio.wait_for(task, 2.0)
    assert hub.subscriber_count == 0


@pytest.mark.asyncio
async def test_subscription_is_released_when_the_response_never_starts() -> None:
    hub = Hub()
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=SimpleNamespace(hub=hub, closing=False))))

    async def receive() -> dict[str, Any]:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    async def send(_message: dict[str, Any]) -> None:
        raise OSError("client went away before the response started")

    with pytest.raises(BaseException):
        await asyncio.wait_for(app(_scope([]), receive, send), 2.0)
    assert hub.subscriber_count == 0


def test_dropped_response_releases_its_subscription() -> None:
    from refract.api.http.events import _events
    from starlette.requests import Request

    async def build() -> tuple[Hub, object]:
        hub = Hub()
        state = DashboardState(runtime=SimpleNamespace(hub=hub, closing=False))
        response = _events(state, Request(_scope([])))
        assert hub.subscriber_count == 1
        return hub, response

    hub, response = asyncio.run(build())
    del response
    gc.collect()
    assert hub.subscriber_count == 0


@pytest.mark.asyncio
async def test_blocked_consumer_gets_one_resync_after_backlog_overflow() -> None:
    hub = Hub()
    stream = event_stream(hub.subscribe(), lambda: False, keepalive_s=0.5)
    assert await anext(stream) == ": connected\n\n"
    for n in range(1500):
        hub.publish(f"job-{n}", "queued")
    await _until(lambda: hub._subscribers and next(iter(hub._subscribers))._wake.is_set())
    await asyncio.sleep(0.05)

    frames = []
    for _ in range(1025):
        frames.append(await anext(stream))
    assert all(f.startswith("data: ") for f in frames)
    assert _frame(frames[-1]) == {"job_id": "", "kind": RESYNC}
    assert [_frame(f)["kind"] for f in frames[:-1]] == ["queued"] * 1024
    assert _frame(frames[0])["job_id"] == "job-476"
    await stream.aclose()
    assert hub.subscriber_count == 0
