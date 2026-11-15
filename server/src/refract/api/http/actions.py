"""State-changing dashboard routes: cancel, submit from a job, answer, and shutdown."""

from __future__ import annotations

import hmac
from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from refract.api.http.common import (
    DashboardState,
    api_error,
    api_json_response,
    check_csrf,
    loopback_route,
    map_orchestration_error,
    parse_json_body,
    runtime_of,
    RUNTIME_INACTIVE,
)
from refract.models import OrchestrationError

_DAEMON_NOT_STOPPED = "The daemon was not stopped."
_FROM_JOB_CONFLICTS = ("prompt", "workflow", "profile", "session")
_FROM_JOB_FIELDS = frozenset({"from_job", "target", "fresh"})


async def _post_preamble(state: DashboardState, request: Request) -> tuple[Any, dict[str, Any]] | Response:
    csrf_err = check_csrf(request)
    if csrf_err is not None:
        return csrf_err

    body, body_err = await parse_json_body(request)
    if body_err is not None:
        return body_err
    assert body is not None

    try:
        return runtime_of(state), body
    except RuntimeError:
        return api_error(RUNTIME_INACTIVE, 503, code="runtime_unavailable")


async def _cancel(state: DashboardState, request: Request) -> Response:
    preamble = await _post_preamble(state, request)
    if isinstance(preamble, Response):
        return preamble
    runtime, _ = preamble

    try:
        result = await runtime.cancel(request.path_params["job_id"])
        return api_json_response({"job_id": result.job_id, "state": result.state, "success": result.success})
    except OrchestrationError as exc:
        return map_orchestration_error(exc)


async def _submit_from_job(state: DashboardState, request: Request) -> Response:
    """Queue a copy of a terminal job through the `submit(from_job=...)` path the MCP tool uses."""
    preamble = await _post_preamble(state, request)
    if isinstance(preamble, Response):
        return preamble
    runtime, body = preamble

    # Same rule as the MCP `submit` tool: an empty string counts as unset.
    given = [name for name in _FROM_JOB_CONFLICTS if body.get(name, "") != ""]
    if given:
        return api_error(
            f"from_job cannot be combined with {', '.join(given)}.", 400, code="invalid_request",
            recovery="Pass either from_job, with optional target and fresh, or workflow and prompt.",
        )
    unknown = sorted(set(body) - _FROM_JOB_FIELDS - set(_FROM_JOB_CONFLICTS))
    if unknown:
        return api_error(
            f"Unsupported field: {', '.join(unknown)}.", 400, code="invalid_request",
            recovery="Pass only from_job, target and fresh.",
        )
    from_job = body.get("from_job")
    if not isinstance(from_job, str) or not from_job:
        return api_error("from_job must be a non-empty string", 400, code="invalid_request")
    target = body.get("target", "")
    if not isinstance(target, str):
        return api_error("target must be a string", 400, code="invalid_request")
    fresh = body.get("fresh")
    if fresh is not None and not isinstance(fresh, bool):
        return api_error("fresh must be a boolean", 400, code="invalid_request")

    try:
        result = await runtime.submit_from_job(from_job, target=target, fresh=fresh)
        return api_json_response({"job_id": result.job_id, "state": result.state, "from_job": from_job})
    except OrchestrationError as exc:
        return map_orchestration_error(exc)


async def _answer(state: DashboardState, request: Request) -> Response:
    preamble = await _post_preamble(state, request)
    if isinstance(preamble, Response):
        return preamble
    runtime, body = preamble

    question_id = body.get("question_id")
    if not isinstance(question_id, str) or not question_id:
        return api_error("question_id must be a non-empty string", 400, code="invalid_request")

    answer = body.get("answer")
    if not isinstance(answer, str) or not answer:
        return api_error("answer must be a non-empty string", 400, code="invalid_request")

    try:
        result = await runtime.job_answer(request.path_params["job_id"], answer, expected_question_id=question_id)
        return api_json_response({"job_id": result.job_id, "state": result.state, "success": result.success})
    except OrchestrationError as exc:
        return map_orchestration_error(exc)


async def _shutdown(state: DashboardState, request: Request) -> Response:
    """Latch the daemon shut for the stop command; bearer token only, no browser CSRF flow.

    The optional body ``{"force": true}`` stops the daemon even when jobs are queued or running.
    """
    scheme, _, supplied = request.headers.get("authorization", "").partition(" ")
    expected = state.shutdown_token
    if not expected or scheme.lower() != "bearer" or not hmac.compare_digest(supplied.encode(), expected.encode()):
        return api_error(
            "Unauthorized",
            401,
            code="unauthorized",
            unchanged=_DAEMON_NOT_STOPPED,
            recovery="Read the token from daemon.json in the Refract home directory.",
        )
    body, body_err = await parse_json_body(request, unchanged=_DAEMON_NOT_STOPPED)
    if body_err is not None:
        return body_err
    assert body is not None
    force = body.get("force", False)
    if not isinstance(force, bool):
        return api_error("force must be a boolean", 400, code="invalid_request", unchanged=_DAEMON_NOT_STOPPED)
    try:
        runtime = runtime_of(state)
    except RuntimeError:
        return api_error(RUNTIME_INACTIVE, 503, code="runtime_unavailable", unchanged=_DAEMON_NOT_STOPPED)
    if state.request_exit is None:
        return api_error("Daemon cannot exit on request", 503, code="shutdown_unavailable", unchanged=_DAEMON_NOT_STOPPED)
    result = runtime.shutdown_if_idle(force=force)
    if result["stopping"]:
        state.request_exit()
    return api_json_response(result)


def action_routes(state: DashboardState) -> list[Route]:
    async def shutdown(request: Request) -> Response:
        return await _shutdown(state, request)

    async def cancel(request: Request) -> Response:
        return await _cancel(state, request)

    async def submit_from_job(request: Request) -> Response:
        return await _submit_from_job(state, request)

    async def answer(request: Request) -> Response:
        return await _answer(state, request)

    return [
        loopback_route("/dashboard/api/jobs/{job_id}/cancel", cancel, methods=["POST"]),
        loopback_route("/dashboard/api/jobs", submit_from_job, methods=["POST"]),
        loopback_route("/dashboard/api/jobs/{job_id}/answer", answer, methods=["POST"]),
        loopback_route("/dashboard/api/shutdown", shutdown, methods=["POST"]),
    ]
