"""Loopback-only dashboard pages and coordinator question endpoint."""

from __future__ import annotations

import ipaddress
import inspect
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, cast
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Route

from refract.ask import AskAuthError, AskConflictError
from refract.models import TERMINAL_STATES
from refract.runtime import OrchestrationError
from refract.workers import run_sync


DASHBOARD_HEADER = "X-Refract-Dashboard"
DASHBOARD_HEADER_VALUE = "1"


@dataclass
class DashboardState:
    runtime: Any = None


def _json_response(value: Any, status_code: int = 200) -> Response:
    return JSONResponse(value, status_code=status_code)


def _error(message: str, status_code: int, *, code: str = "", unchanged: str = "", recovery: str = "") -> Response:
    return _json_response({"error": message, "code": code, "unchanged": unchanged, "recovery": recovery}, status_code)


def _api_json_response(data: Any, status_code: int = 200, *, headers: dict[str, str] | None = None) -> Response:
    resp_headers = {"Cache-Control": "no-store"}
    if headers:
        resp_headers.update(headers)
    return JSONResponse(data, status_code=status_code, headers=resp_headers)


def _api_error(
    message: str,
    status_code: int,
    *,
    code: str = "",
    unchanged: str = "No job was changed.",
    recovery: str = "",
    headers: dict[str, str] | None = None,
) -> Response:
    return _api_json_response(
        {"error": message, "code": code, "unchanged": unchanged, "recovery": recovery},
        status_code=status_code,
        headers=headers,
    )


def _map_orchestration_error(exc: OrchestrationError) -> Response:
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

    return _api_error(
        str(exc),
        status_code,
        code=exc.code,
        unchanged="No job was changed.",
        recovery=exc.next_action,
        headers=headers,
    )


def _runtime(state: DashboardState) -> Any:
    if state.runtime is None:
        raise RuntimeError("Refract runtime is not active")
    return state.runtime


def _runtime_error() -> Response:
    return _error(
        "Refract runtime is not active",
        503,
        code="runtime_unavailable",
        unchanged="No dashboard data was changed.",
        recovery="Retry after the daemon has started.",
    )


def _host_name(request: Request) -> str:
    return request.headers.get("host", "")


def _is_loopback_host(value: str) -> bool:
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
    return _error(
        "Forbidden",
        403,
        code="forbidden",
        unchanged=unchanged,
        recovery=recovery,
    )


def _loopback_route(path: str, endpoint: Callable[[Request], Awaitable[Response] | Response], methods: list[str]) -> Route:
    """Serve ``endpoint`` only to loopback clients that address a loopback host.

    The check blocks DNS-rebinding pages, which reach the daemon from a
    loopback client but under a foreign Host header.
    """

    async def guarded(request: Request) -> Response:
        if not _is_loopback_client(request) or not _is_loopback_host(_host_name(request)):
            return _forbidden()
        if inspect.iscoroutinefunction(endpoint):
            return await endpoint(request)
        return await run_sync(cast(Callable[[Request], Response], endpoint), request)

    return Route(path, guarded, methods=methods)


_APP_STATIC_DIR = Path(__file__).parent / "dashboard_static" / "app"
_OUTPUT_PAGE = 500
def _register_ask_routes(state: DashboardState) -> list[Route]:
    async def ask(request: Request) -> Response:
        try:
            runtime = _runtime(state)
        except RuntimeError:
            return _runtime_error()

        try:
            raw_body = await request.body()
        except Exception:
            return _error("Malformed request body", 400, code="bad_request")

        if not raw_body:
            return _error("Malformed request body", 400, code="bad_request")

        try:
            body = json.loads(raw_body.decode("utf-8"))
        except Exception:
            return _error("Malformed request body", 400, code="bad_request")

        if not isinstance(body, dict):
            return _error("Malformed request body", 400, code="bad_request")

        token = body.get("token")
        question = body.get("question")
        job_id = body.get("job_id") or request.headers.get("x-refract-job-id") or request.query_params.get("job_id")

        if not isinstance(token, str) or not token:
            return _error("token must be a non-empty string", 400, code="bad_request")

        if not isinstance(question, str) or not question.strip():
            return _error("question must be a non-empty string", 400, code="bad_request")

        if job_id is not None and not isinstance(job_id, str):
            return _error("job_id must be a string", 400, code="bad_request")

        registry = getattr(runtime, "ask_registry", None)
        if registry is None:
            return _runtime_error()

        timeout_s = getattr(runtime.config, "ask_timeout_s", 300)
        try:
            answer = await registry.ask(
                token=token,
                question=question,
                timeout_s=timeout_s,
                job_id=job_id,
            )
            return _json_response({"answer": answer}, 200)
        except AskAuthError:
            return _error("Forbidden", 403, code="forbidden")
        except AskConflictError:
            return _error("A question is already pending for this job", 409, code="conflict")

    return [
        _loopback_route("/ask", ask, methods=["POST"]),
    ]



def _check_csrf(request: Request) -> Response | None:
    origin = request.headers.get("origin")
    if not origin or origin.lower() == "null":
        return _api_error("CSRF check failed: Origin header required", 403, code="csrf_rejected")

    origin_split = urlsplit(origin)
    if not origin_split.hostname or not _is_loopback_host(origin_split.hostname):
        return _api_error("CSRF check failed: non-loopback Origin", 403, code="csrf_rejected")

    origin_scheme = origin_split.scheme.lower()
    req_scheme = request.url.scheme.lower()
    if origin_scheme != req_scheme:
        return _api_error("CSRF check failed: scheme mismatch", 403, code="csrf_rejected")

    origin_host = origin_split.hostname.lower()
    req_host = (request.url.hostname or "").lower()
    if origin_host != req_host:
        return _api_error("CSRF check failed: host mismatch", 403, code="csrf_rejected")

    default_port = 443 if origin_scheme == "https" else 80
    try:
        origin_port = origin_split.port or default_port
    except ValueError:
        return _api_error("CSRF check failed: invalid Origin port", 403, code="csrf_rejected")
    req_port = request.url.port or default_port
    if origin_port != req_port:
        return _api_error("CSRF check failed: port mismatch", 403, code="csrf_rejected")

    sec_fetch_site = request.headers.get("sec-fetch-site")
    if sec_fetch_site is not None and sec_fetch_site.strip().lower() != "same-origin":
        return _api_error("CSRF check failed: Sec-Fetch-Site must be same-origin", 403, code="csrf_rejected")

    dashboard_header = request.headers.get("x-refract-dashboard")
    if dashboard_header != DASHBOARD_HEADER_VALUE:
        return _api_error("CSRF check failed: missing or invalid dashboard header", 403, code="csrf_rejected")

    content_type = request.headers.get("content-type", "")
    media_type = content_type.split(";")[0].strip().lower()
    if media_type != "application/json":
        return _api_error("Content-Type must be application/json", 415, code="unsupported_media_type")

    return None


async def _parse_json_body(request: Request) -> tuple[dict[str, Any] | None, Response | None]:
    try:
        raw_body = await request.body()
    except Exception:
        return None, _api_error("Malformed request body", 400, code="invalid_request")

    if not raw_body:
        return {}, None

    try:
        body = json.loads(raw_body.decode("utf-8"))
    except Exception:
        return None, _api_error("Malformed JSON body", 400, code="invalid_request")

    if not isinstance(body, dict):
        return None, _api_error("JSON body must be an object", 400, code="invalid_request")

    return body, None


async def _api_post_preamble(
    state: DashboardState, request: Request
) -> tuple[Any, str, dict[str, Any]] | Response:
    csrf_err = _check_csrf(request)
    if csrf_err is not None:
        return csrf_err

    body, body_err = await _parse_json_body(request)
    if body_err is not None:
        return body_err
    assert body is not None

    try:
        runtime = _runtime(state)
    except RuntimeError:
        return _api_error("Refract runtime is not active", 503, code="runtime_unavailable")

    job_id = request.path_params["job_id"]
    return runtime, job_id, body


async def _api_cancel(state: DashboardState, request: Request) -> Response:
    preamble = await _api_post_preamble(state, request)
    if isinstance(preamble, Response):
        return preamble
    runtime, job_id, _ = preamble

    try:
        result = await runtime.cancel(job_id)
        return _api_json_response({
            "job_id": result.job_id,
            "state": result.state,
            "success": result.success,
        })
    except OrchestrationError as exc:
        return _map_orchestration_error(exc)


async def _api_retry(state: DashboardState, request: Request) -> Response:
    preamble = await _api_post_preamble(state, request)
    if isinstance(preamble, Response):
        return preamble
    runtime, job_id, _ = preamble

    try:
        result = await runtime.retry(job_id)
        return _api_json_response({
            "job_id": result.job_id,
            "state": result.state,
            "retry_of": job_id,
        })
    except OrchestrationError as exc:
        return _map_orchestration_error(exc)


async def _api_answer(state: DashboardState, request: Request) -> Response:
    preamble = await _api_post_preamble(state, request)
    if isinstance(preamble, Response):
        return preamble
    runtime, job_id, body = preamble

    question_id = body.get("question_id")
    if not isinstance(question_id, str) or not question_id:
        return _api_error("question_id must be a non-empty string", 400, code="invalid_request")

    answer = body.get("answer")
    if not isinstance(answer, str) or not answer:
        return _api_error("answer must be a non-empty string", 400, code="invalid_request")

    try:
        result = await runtime.job_answer(job_id, answer, expected_question_id=question_id)
        return _api_json_response({
            "job_id": result.job_id,
            "state": result.state,
            "success": result.success,
        })
    except OrchestrationError as exc:
        return _map_orchestration_error(exc)


def _register_action_routes(state: DashboardState) -> list[Route]:
    async def cancel(request: Request) -> Response:
        return await _api_cancel(state, request)

    async def retry(request: Request) -> Response:
        return await _api_retry(state, request)

    async def answer(request: Request) -> Response:
        return await _api_answer(state, request)

    return [
        _loopback_route("/dashboard/api/jobs/{job_id}/cancel", cancel, methods=["POST"]),
        _loopback_route("/dashboard/api/jobs/{job_id}/retry", retry, methods=["POST"]),
        _loopback_route("/dashboard/api/jobs/{job_id}/answer", answer, methods=["POST"]),
    ]


def _api_runtime(state: DashboardState) -> Any | Response:
    try:
        return _runtime(state)
    except RuntimeError:
        return _api_error(
            "Refract runtime is not active",
            503,
            code="runtime_unavailable",
            unchanged="Nothing was modified.",
            recovery="Retry after the daemon has started.",
        )


def _api_get_jobs(state: DashboardState, request: Request) -> Response:
    runtime = _api_runtime(state)
    if isinstance(runtime, Response):
        return runtime

    limit_val = 100
    limit_param = request.query_params.get("limit")
    if limit_param is not None and limit_param != "":
        try:
            limit_val = int(limit_param)
            if limit_val <= 0 or limit_val > 200:
                return _api_error(
                    "limit must be between 1 and 200", 400, code="invalid_request", unchanged="Nothing was modified."
                )
        except ValueError:
            return _api_error(
                "limit must be an integer", 400, code="invalid_request", unchanged="Nothing was modified."
            )

    cursor_param = request.query_params.get("cursor") or None
    state_param = request.query_params.get("state") or None
    project_param = request.query_params.get("project") or None
    workflow_param = request.query_params.get("workflow") or None
    target_param = request.query_params.get("target") or None
    q_param = request.query_params.get("q") or None

    try:
        jobs, next_cursor = runtime.database.job_summaries(
            state=state_param,
            project_id=project_param,
            workflow=workflow_param,
            target=target_param,
            q=q_param,
            cursor=cursor_param,
            limit=limit_val,
        )
    except ValueError as exc:
        return _api_error(str(exc), 400, code="invalid_request", unchanged="Nothing was modified.")

    options = runtime.database.job_filter_options()
    return _api_json_response({
        "jobs": jobs,
        "next_cursor": next_cursor,
        "options": options,
    })


def _api_get_job_detail(state: DashboardState, request: Request) -> Response:
    runtime = _api_runtime(state)
    if isinstance(runtime, Response):
        return runtime

    job_id = request.path_params["job_id"]
    detail = runtime.database.job_detail(job_id)
    if detail is None:
        return _api_error("Job not found", 404, code="unknown_job", unchanged="Nothing was modified.")

    ask_registry = getattr(runtime, "ask_registry", None)
    pending = ask_registry.get_pending(job_id) if ask_registry else None
    pending_question = (
        {"question_id": pending.question_id, "text": pending.text}
        if pending is not None
        else None
    )

    detail["pending_question"] = pending_question
    return _api_json_response(detail)


def _stream_events_bounded(
    stream_path: Path, after: int, limit: int = _OUTPUT_PAGE
) -> tuple[list[dict[str, Any]], int, bool, bool]:
    """Stream events from `stream_path` without reading the entire file into memory.

    Returns (events, last_seq, has_more, available).
    """
    try:
        handle = stream_path.open("r", encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return [], after, False, False

    events: list[dict[str, Any]] = []
    last_seq = after
    has_more = False
    with handle:
        seq = 0
        for line in handle:
            seq += 1
            if seq <= after:
                continue
            if not line.endswith("\n"):
                # Partial final line: withheld, does not count toward has_more
                break
            if len(events) < limit:
                try:
                    payload = json.loads(line)
                    if not isinstance(payload, dict):
                        payload = {"kind": "invalid", "data": {}}
                except Exception:
                    payload = {"kind": "invalid", "data": {}}
                events.append({**payload, "seq": seq})
                last_seq = seq
            else:
                has_more = True
                break

    return events, last_seq, has_more, True


def _api_get_job_output(state: DashboardState, request: Request) -> Response:
    runtime = _api_runtime(state)
    if isinstance(runtime, Response):
        return runtime

    job_id = request.path_params["job_id"]
    job = runtime.database.job_record(job_id)
    if job is None:
        return _api_error("Job not found", 404, code="unknown_job", unchanged="Nothing was modified.")

    after_str = request.query_params.get("after")
    if after_str is None or after_str == "":
        after = 0
    else:
        try:
            after = int(after_str)
            if after < 0:
                return _api_error(
                    "after must be a non-negative integer", 400, code="invalid_request", unchanged="Nothing was modified."
                )
        except ValueError:
            return _api_error(
                "after must be an integer", 400, code="invalid_request", unchanged="Nothing was modified."
            )

    stream_path = runtime.database.stream_path(job_id)
    events, last_seq, has_more, available = _stream_events_bounded(stream_path, after, _OUTPUT_PAGE)

    job_state = job["state"]
    is_terminal = job_state in TERMINAL_STATES

    return _api_json_response({
        "events": events,
        "next": last_seq,
        "has_more": has_more,
        "available": available,
        "state": job_state,
        "terminal": is_terminal,
    })


def _api_get_targets(state: DashboardState, request: Request) -> Response:
    runtime = _api_runtime(state)
    if isinstance(runtime, Response):
        return runtime

    targets = [target.model_dump() for target in runtime.targets()]
    config = runtime.config_health.model_dump()
    return _api_json_response({
        "targets": targets,
        "config": config,
    })


def _api_fallback(request: Request) -> Response:
    return _api_error(
        "Not found",
        404,
        code="not_found",
        unchanged="Nothing was modified.",
        recovery="Check the API URL.",
    )


def _app_shell(request: Request) -> Response:
    try:
        root = _APP_STATIC_DIR.resolve(strict=True)
        index = (root / "index.html").resolve(strict=True)
    except (OSError, RuntimeError):
        return Response(status_code=404)
    if not index.is_relative_to(root) or not index.is_file():
        return Response(status_code=404)
    return FileResponse(index, media_type="text/html", headers={
        "Cache-Control": "no-cache",
        "X-Content-Type-Options": "nosniff",
    })


def _app_asset(request: Request) -> Response:
    relative = request.path_params.get("path", "")
    try:
        root = (_APP_STATIC_DIR / "assets").resolve(strict=True)
        asset = (root / relative).resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return Response(status_code=404)
    if not asset.is_relative_to(root) or not asset.is_file():
        return Response(status_code=404)
    return FileResponse(asset, headers={
        "Cache-Control": "public, max-age=31536000, immutable",
        "X-Content-Type-Options": "nosniff",
    })


def _register_app_routes() -> list[Route]:
    return [
        _loopback_route("/dashboard/assets", _app_asset, methods=["GET"]),
        _loopback_route("/dashboard/assets/{path:path}", _app_asset, methods=["GET"]),
        _loopback_route("/dashboard", _app_shell, methods=["GET"]),
        _loopback_route("/dashboard/", _app_shell, methods=["GET"]),
        _loopback_route("/dashboard/{path:path}", _app_shell, methods=["GET"]),
    ]


def _register_api_routes(state: DashboardState) -> list[Route]:
    def jobs(request: Request) -> Response:
        return _api_get_jobs(state, request)

    def output(request: Request) -> Response:
        return _api_get_job_output(state, request)

    def job_detail(request: Request) -> Response:
        return _api_get_job_detail(state, request)

    def targets(request: Request) -> Response:
        return _api_get_targets(state, request)

    all_methods = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]

    # Fallback for unknown /dashboard/api/* routes and unsupported HTTP methods on
    # registered API routes (which Starlette falls through to match here as JSON 404).
    return [
        _loopback_route("/dashboard/api/jobs", jobs, methods=["GET"]),
        _loopback_route("/dashboard/api/jobs/{job_id}/output", output, methods=["GET"]),
        _loopback_route("/dashboard/api/jobs/{job_id}", job_detail, methods=["GET"]),
        _loopback_route("/dashboard/api/targets", targets, methods=["GET"]),
        _loopback_route("/dashboard/api", _api_fallback, methods=all_methods),
        _loopback_route("/dashboard/api/{rest:path}", _api_fallback, methods=all_methods),
    ]


def register_dashboard_routes(state: DashboardState) -> list[Route]:
    return [
        *_register_action_routes(state),
        *_register_api_routes(state),
        *_register_app_routes(),
        *_register_ask_routes(state),
    ]


__all__ = ["DASHBOARD_HEADER", "DASHBOARD_HEADER_VALUE", "DashboardState", "register_dashboard_routes"]
