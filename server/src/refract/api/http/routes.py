"""Loopback-only dashboard pages and read API routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import FileResponse, Response
from starlette.routing import Route

from refract.api.http.actions import action_routes
from refract.api.http.ask import ask_routes
from refract.api.http.common import (
    DASHBOARD_HEADER,
    DASHBOARD_HEADER_VALUE,
    NOTHING_MODIFIED,
    DashboardState,
    api_error,
    api_json_response,
    api_runtime,
    loopback_route,
)
from refract.api.http.events import event_routes
from refract.api.http.insights import get_stats
from refract.models import TERMINAL_STATES

_APP_STATIC_DIR = Path(__file__).resolve().parents[2] / "dashboard_static" / "app"
_OUTPUT_PAGE = 500


def _jobs(state: DashboardState, request: Request) -> Response:
    runtime = api_runtime(state)
    if isinstance(runtime, Response):
        return runtime

    limit_val = 100
    limit_param = request.query_params.get("limit")
    if limit_param is not None and limit_param != "":
        try:
            limit_val = int(limit_param)
            if limit_val <= 0 or limit_val > 200:
                return api_error(
                    "limit must be between 1 and 200", 400, code="invalid_request", unchanged=NOTHING_MODIFIED
                )
        except ValueError:
            return api_error("limit must be an integer", 400, code="invalid_request", unchanged=NOTHING_MODIFIED)

    query = request.query_params
    try:
        jobs, next_cursor = runtime.database.job_summaries(
            state=query.get("state") or None,
            project_id=query.get("project") or None,
            workflow=query.get("workflow") or None,
            target=query.get("target") or None,
            q=query.get("q") or None,
            cursor=query.get("cursor") or None,
            limit=limit_val,
        )
    except ValueError as exc:
        return api_error(str(exc), 400, code="invalid_request", unchanged=NOTHING_MODIFIED)

    return api_json_response({
        "jobs": jobs,
        "next_cursor": next_cursor,
        "options": runtime.database.job_filter_options(),
    })


def _cards(state: DashboardState, request: Request) -> Response:
    runtime = api_runtime(state)
    if isinstance(runtime, Response):
        return runtime

    listing = runtime.database.list_cards(project_id=request.query_params.get("project") or None, limit=200)
    projects = [{"id": project.id, "root": project.root} for project in runtime.database.projects()]
    return api_json_response({
        "cards": listing["cards"],
        "truncated": listing["truncated"],
        "options": {"projects": projects},
    })


def _card(state: DashboardState, request: Request) -> Response:
    runtime = api_runtime(state)
    if isinstance(runtime, Response):
        return runtime

    detail = runtime.database.card_detail(request.path_params["card_id"])
    if detail is None:
        return api_error("Card not found", 404, code="unknown_card", unchanged=NOTHING_MODIFIED)

    jobs = [
        {key: job[key] for key in ("workflow", "state", "target", "available")} | {"id": job["job_id"]}
        for job in detail["jobs"]
    ]
    return api_json_response({
        "card": {**detail["card"], "job_ids": [job["id"] for job in jobs]},
        "moves": [{key: move[key] for key in ("from_state", "to_state", "note", "at")} for move in detail["moves"]],
        "jobs": jobs,
    })


def _job_detail(state: DashboardState, request: Request) -> Response:
    runtime = api_runtime(state)
    if isinstance(runtime, Response):
        return runtime

    job_id = request.path_params["job_id"]
    detail = runtime.database.job_detail(job_id)
    if detail is None:
        return api_error("Job not found", 404, code="unknown_job", unchanged=NOTHING_MODIFIED)

    pending = runtime.ask_registry.get_pending(job_id)
    detail["pending_question"] = None if pending is None else {"question_id": pending.question_id, "text": pending.text}
    return api_json_response(detail)


def _job_output(state: DashboardState, request: Request) -> Response:
    runtime = api_runtime(state)
    if isinstance(runtime, Response):
        return runtime

    job_id = request.path_params["job_id"]
    job = runtime.database.job_record(job_id)
    if job is None:
        return api_error("Job not found", 404, code="unknown_job", unchanged=NOTHING_MODIFIED)

    after_str = request.query_params.get("after")
    after = 0
    if after_str:
        try:
            after = int(after_str)
        except ValueError:
            return api_error("after must be an integer", 400, code="invalid_request", unchanged=NOTHING_MODIFIED)
        if after < 0:
            return api_error(
                "after must be a non-negative integer", 400, code="invalid_request", unchanged=NOTHING_MODIFIED
            )

    # The store reader stops at `jobs.events_committed`, so lines past the cursor are never served.
    events, last_seq, has_more, available = runtime.database.read_stream(job_id, after, _OUTPUT_PAGE)
    return api_json_response({
        "events": events,
        "next": last_seq,
        "has_more": has_more,
        "available": available,
        "state": job["state"],
        "terminal": job["state"] in TERMINAL_STATES,
    })


def _targets(state: DashboardState, request: Request) -> Response:
    runtime = api_runtime(state)
    if isinstance(runtime, Response):
        return runtime

    return api_json_response({
        "targets": [target.model_dump() for target in runtime.targets()],
        "config": runtime.config_health.model_dump(),
    })


def _stats(state: DashboardState, request: Request) -> Response:
    runtime = api_runtime(state)
    if isinstance(runtime, Response):
        return runtime
    try:
        days = int(request.query_params.get("days", "7"))
    except ValueError:
        return api_error("days must be one of 1, 7, 30, or 365", 400, code="invalid_request")
    try:
        offset = int(request.query_params.get("tz_offset_minutes", "0"))
    except ValueError:
        return api_error("tz_offset_minutes must be an integer", 400, code="invalid_request")
    try:
        return api_json_response(get_stats(runtime.database, days, offset))
    except ValueError as exc:
        return api_error(str(exc), 400, code="invalid_request")


def _api_fallback(request: Request) -> Response:
    return api_error(
        "Not found",
        404,
        code="not_found",
        unchanged=NOTHING_MODIFIED,
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


def _app_routes() -> list[Route]:
    return [
        loopback_route("/dashboard/assets", _app_asset, methods=["GET"]),
        loopback_route("/dashboard/assets/{path:path}", _app_asset, methods=["GET"]),
        loopback_route("/dashboard", _app_shell, methods=["GET"]),
        loopback_route("/dashboard/", _app_shell, methods=["GET"]),
        loopback_route("/dashboard/{path:path}", _app_shell, methods=["GET"]),
    ]


def _api_routes(state: DashboardState) -> list[Route]:
    def bound(handler: Any) -> Any:
        return lambda request: handler(state, request)

    all_methods = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]

    # Fallback for unknown /dashboard/api/* routes and unsupported HTTP methods on
    # registered API routes (which Starlette falls through to match here as JSON 404).
    return [
        loopback_route("/dashboard/api/stats", bound(_stats), methods=["GET"]),
        loopback_route("/dashboard/api/jobs", bound(_jobs), methods=["GET"]),
        loopback_route("/dashboard/api/jobs/{job_id}/output", bound(_job_output), methods=["GET"]),
        loopback_route("/dashboard/api/jobs/{job_id}", bound(_job_detail), methods=["GET"]),
        loopback_route("/dashboard/api/targets", bound(_targets), methods=["GET"]),
        loopback_route("/dashboard/api/cards", bound(_cards), methods=["GET"]),
        loopback_route("/dashboard/api/cards/{card_id}", bound(_card), methods=["GET"]),
        loopback_route("/dashboard/api", _api_fallback, methods=all_methods),
        loopback_route("/dashboard/api/{rest:path}", _api_fallback, methods=all_methods),
    ]


def register_dashboard_routes(state: DashboardState) -> list[Route]:
    return [
        *action_routes(state),
        *event_routes(state),
        *_api_routes(state),
        *_app_routes(),
        *ask_routes(state),
    ]


__all__ = ["DASHBOARD_HEADER", "DASHBOARD_HEADER_VALUE", "DashboardState", "register_dashboard_routes"]
