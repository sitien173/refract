"""The worker-facing `POST /ask` route; the question state lives in `refract.scheduling.asks`."""

from __future__ import annotations

import json
from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from refract.api.http.common import MALFORMED_BODY, DashboardState, error, json_response, loopback_route, runtime_error, runtime_of
from refract.scheduling.asks import AskAuthError, AskConflictError


async def _read_body(request: Request) -> dict[str, Any] | Response:
    try:
        raw_body = await request.body()
    except Exception:
        return error(MALFORMED_BODY, 400, code="invalid_request")

    if not raw_body:
        return error(MALFORMED_BODY, 400, code="invalid_request")

    try:
        body = json.loads(raw_body.decode("utf-8"))
    except Exception:
        return error(MALFORMED_BODY, 400, code="invalid_request")

    if not isinstance(body, dict):
        return error(MALFORMED_BODY, 400, code="invalid_request")

    return body


def _fields(request: Request, body: dict[str, Any]) -> tuple[str, str, str | None] | Response:
    token = body.get("token")
    question = body.get("question")
    job_id = body.get("job_id") or request.headers.get("x-refract-job-id") or request.query_params.get("job_id")

    if not isinstance(token, str) or not token:
        return error("token must be a non-empty string", 400, code="invalid_request")

    if not isinstance(question, str) or not question.strip():
        return error("question must be a non-empty string", 400, code="invalid_request")

    if job_id is not None and not isinstance(job_id, str):
        return error("job_id must be a string", 400, code="invalid_request")

    return token, question, job_id


async def _registry_response(registry: Any, token: str, question: str, timeout_s: Any, job_id: str | None) -> Response:
    try:
        answer = await registry.ask(token=token, question=question, timeout_s=timeout_s, job_id=job_id)
        return json_response({"answer": answer}, 200)
    except AskAuthError:
        return error("Forbidden", 403, code="forbidden")
    except AskConflictError:
        return error("A question is already pending for this job", 409, code="conflict")


def ask_routes(state: DashboardState) -> list[Route]:
    async def ask(request: Request) -> Response:
        try:
            runtime = runtime_of(state)
        except RuntimeError:
            return runtime_error()

        body = await _read_body(request)
        if isinstance(body, Response):
            return body

        fields = _fields(request, body)
        if isinstance(fields, Response):
            return fields
        token, question, job_id = fields

        registry = getattr(runtime, "ask_registry", None)
        if registry is None:
            return runtime_error()

        timeout_s = getattr(runtime.config, "ask_timeout_s", 300)
        return await _registry_response(registry, token, question, timeout_s, job_id)

    return [loopback_route("/ask", ask, methods=["POST"])]
