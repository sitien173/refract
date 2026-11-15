"""`GET /dashboard/api/events`: hub signals as server-sent events."""

from __future__ import annotations

import json
import weakref
from collections.abc import AsyncIterator, Callable
from typing import Any

from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.routing import Route

from refract.api.http.common import DashboardState, api_runtime, check_same_origin_get, loopback_route
from refract.scheduling.hub import Subscription

KEEPALIVE_S = 15.0
RESYNC = "resync"
_KEEPALIVE_FRAME = ": keepalive\n\n"


def _frame(job_id: str, kind: str) -> str:
    return f"data: {json.dumps({'job_id': job_id, 'kind': kind}, separators=(',', ':'))}\n\n"


async def event_stream(
    subscription: Subscription, is_closing: Callable[[], bool], *, keepalive_s: float = KEEPALIVE_S
) -> AsyncIterator[str]:
    """One `data: {"job_id", "kind"}` frame per hub signal; ends on daemon shutdown.

    A subscriber that fell more than the backlog behind gets one `resync` frame after the kept signals;
    the client must refetch state. The subscription is released when the stream ends, is cancelled by
    a client disconnect, or is closed.
    """
    with subscription:
        yield ": connected\n\n"
        while not is_closing():
            woken = await subscription.wait(keepalive_s)
            # Clear before draining: a signal that lands in between sets the wake flag again.
            subscription.clear()
            for job_id, kind in subscription.drain():
                yield _frame(job_id, kind)
            if subscription.take_overflow():
                yield _frame("", RESYNC)
            if not woken:
                yield _KEEPALIVE_FRAME


class _SubscribedResponse(StreamingResponse):
    """Owns a subscription taken before the response starts, so no signal is lost at stream start.

    The generator releases it once it runs. This class releases it when the response ends without
    the generator ever starting, and when the response is dropped without being sent.
    """

    def __init__(self, subscription: Subscription, content: AsyncIterator[str], **kwargs: Any) -> None:
        super().__init__(content, **kwargs)
        self._subscription = subscription
        weakref.finalize(self, subscription.close)

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self._subscription.close()


def _events(state: DashboardState, request: Request) -> Response:
    origin_error = check_same_origin_get(request)
    if origin_error is not None:
        return origin_error
    runtime = api_runtime(state)
    if isinstance(runtime, Response):
        return runtime
    subscription = runtime.hub.subscribe()
    return _SubscribedResponse(
        subscription,
        event_stream(subscription, lambda: runtime.closing),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no", "X-Content-Type-Options": "nosniff"},
    )


def event_routes(state: DashboardState) -> list[Route]:
    async def events(request: Request) -> Response:
        return _events(state, request)

    return [loopback_route("/dashboard/api/events", events, methods=["GET"])]
