"""Shared HTTP plumbing: responses, loopback guard, CSRF and body parsing."""

from __future__ import annotations

import inspect
import ipaddress
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, cast
from urllib.parse import SplitResult, urlsplit

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from refract.models import OrchestrationError
from refract.store.pool import run_sync

DASHBOARD_HEADER = "X-Refract-Dashboard"
DASHBOARD_HEADER_VALUE = "1"
RUNTIME_INACTIVE = "Refract runtime is not active"
MALFORMED_BODY = "Malformed request body"
NOTHING_MODIFIED = "Nothing was modified."


@dataclass
class DashboardState:
    runtime: Any = None
    shutdown_token: str = ""
    request_exit: Callable[[], None] | None = None


def json_response(value: Any, status_code: int = 200) -> Response:
    return JSONResponse(value, status_code=status_code)


def error(message: str, status_code: int, *, code: str = "", unchanged: str = "", recovery: str = "") -> Response:
    return json_response({"error": message, "code": code, "unchanged": unchanged, "recovery": recovery}, status_code)


def api_json_response(data: Any, status_code: int = 200, *, headers: dict[str, str] | None = None) -> Response:
    resp_headers = {"Cache-Control": "no-store"}
    if headers:
        resp_headers.update(headers)
    return JSONResponse(data, status_code=status_code, headers=resp_headers)


def api_error(
    message: str,
    status_code: int,
    *,
    code: str = "",
    unchanged: str = "No job was changed.",
    recovery: str = "",
    headers: dict[str, str] | None = None,
) -> Response:
    return api_json_response(
        {"error": message, "code": code, "unchanged": unchanged, "recovery": recovery},
        status_code=status_code,
        headers=headers,
    )


def map_orchestration_error(exc: OrchestrationError) -> Response:
    status_code = 400
    if exc.code == "unknown_job":
        status_code = 404
    elif exc.code == "invalid_state":
        status_code = 409
    elif exc.code == "targets_unavailable":
        status_code = 503

    headers = {}
    if exc.retry_after_s is not None:
        headers["Retry-After"] = str(exc.retry_after_s)

    return api_error(
        str(exc),
        status_code,
        code=exc.code,
        unchanged="No job was changed.",
        recovery=exc.next_action,
        headers=headers,
    )


def runtime_of(state: DashboardState) -> Any:
    if state.runtime is None:
        raise RuntimeError(RUNTIME_INACTIVE)
    return state.runtime


def runtime_error() -> Response:
    return error(
        RUNTIME_INACTIVE,
        503,
        code="runtime_unavailable",
        unchanged="No dashboard data was changed.",
        recovery="Retry after the daemon has started.",
    )


def api_runtime(state: DashboardState) -> Any | Response:
    try:
        return runtime_of(state)
    except RuntimeError:
        return api_error(
            RUNTIME_INACTIVE,
            503,
            code="runtime_unavailable",
            unchanged=NOTHING_MODIFIED,
            recovery="Retry after the daemon has started.",
        )


def _host_name(request: Request) -> str:
    return request.headers.get("host", "")


def is_loopback_host(value: str) -> bool:
    try:
        hostname = urlsplit(f"//{value}").hostname
        if hostname is None:
            return False
        if hostname.lower() == "localhost":
            return True
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _is_loopback_client(request: Request) -> bool:
    try:
        return request.client is not None and ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        return False


def _forbidden(
    unchanged: str = "No configuration was changed.",
    recovery: str = "Use a loopback browser.",
) -> Response:
    return error("Forbidden", 403, code="forbidden", unchanged=unchanged, recovery=recovery)


def loopback_route(path: str, endpoint: Callable[[Request], Awaitable[Response] | Response], methods: list[str]) -> Route:
    """Serve ``endpoint`` only to loopback clients that address a loopback host.

    The check blocks DNS-rebinding pages, which reach the daemon from a
    loopback client but under a foreign Host header.
    """

    async def guarded(request: Request) -> Response:
        if not _is_loopback_client(request) or not is_loopback_host(_host_name(request)):
            return _forbidden()
        if inspect.iscoroutinefunction(endpoint):
            return await endpoint(request)
        return await run_sync(cast(Callable[[Request], Response], endpoint), request)

    return Route(path, guarded, methods=methods)


def _check_origin(request: Request, origin_split: SplitResult) -> Response | None:
    if not origin_split.hostname or not is_loopback_host(origin_split.hostname):
        return api_error("CSRF check failed: non-loopback Origin", 403, code="csrf_rejected")

    origin_scheme = origin_split.scheme.lower()
    req_scheme = request.url.scheme.lower()
    if origin_scheme != req_scheme:
        return api_error("CSRF check failed: scheme mismatch", 403, code="csrf_rejected")

    origin_host = origin_split.hostname.lower()
    req_host = (request.url.hostname or "").lower()
    if origin_host != req_host:
        return api_error("CSRF check failed: host mismatch", 403, code="csrf_rejected")

    default_port = 443 if origin_scheme == "https" else 80
    try:
        origin_port = origin_split.port or default_port
    except ValueError:
        return api_error("CSRF check failed: invalid Origin port", 403, code="csrf_rejected")
    req_port = request.url.port or default_port
    if origin_port != req_port:
        return api_error("CSRF check failed: port mismatch", 403, code="csrf_rejected")

    return None


def check_csrf(request: Request) -> Response | None:
    origin = request.headers.get("origin")
    if not origin or origin.lower() == "null":
        return api_error("CSRF check failed: Origin header required", 403, code="csrf_rejected")

    origin_error = _check_origin(request, urlsplit(origin))
    if origin_error is not None:
        return origin_error

    sec_fetch_site = request.headers.get("sec-fetch-site")
    if sec_fetch_site is not None and sec_fetch_site.strip().lower() != "same-origin":
        return api_error("CSRF check failed: Sec-Fetch-Site must be same-origin", 403, code="csrf_rejected")

    dashboard_header = request.headers.get("x-refract-dashboard")
    if dashboard_header != DASHBOARD_HEADER_VALUE:
        return api_error("CSRF check failed: missing or invalid dashboard header", 403, code="csrf_rejected")

    content_type = request.headers.get("content-type", "")
    media_type = content_type.split(";")[0].strip().lower()
    if media_type != "application/json":
        return api_error("Content-Type must be application/json", 415, code="unsupported_media_type")

    return None


def check_same_origin_get(request: Request) -> Response | None:
    """Same-origin policy for GET routes that browsers call without the POST-only dashboard header.

    A foreign or opaque Origin and any Sec-Fetch-Site other than same-origin are rejected. Requests
    that carry neither header, such as non-browser clients, pass.
    """
    origin = request.headers.get("origin")
    if origin is not None:
        if origin.lower() == "null":
            return api_error("CSRF check failed: opaque Origin", 403, code="csrf_rejected", unchanged=NOTHING_MODIFIED)
        origin_error = _check_origin(request, urlsplit(origin))
        if origin_error is not None:
            return origin_error
    sec_fetch_site = request.headers.get("sec-fetch-site")
    if sec_fetch_site is not None and sec_fetch_site.strip().lower() != "same-origin":
        return api_error(
            "CSRF check failed: Sec-Fetch-Site must be same-origin", 403, code="csrf_rejected", unchanged=NOTHING_MODIFIED
        )
    return None


async def parse_json_body(request: Request, unchanged: str = "No job was changed.") -> tuple[dict[str, Any] | None, Response | None]:
    try:
        raw_body = await request.body()
    except Exception:
        return None, api_error(MALFORMED_BODY, 400, code="invalid_request", unchanged=unchanged)

    if not raw_body:
        return {}, None

    try:
        body = json.loads(raw_body.decode("utf-8"))
    except Exception:
        return None, api_error("Malformed JSON body", 400, code="invalid_request", unchanged=unchanged)

    if not isinstance(body, dict):
        return None, api_error("JSON body must be an object", 400, code="invalid_request", unchanged=unchanged)

    return body, None
