"""Loopback-only dashboard pages and coordinator question endpoint."""

from __future__ import annotations

import functools
import ipaddress
import inspect
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from importlib import resources
from typing import Any, Awaitable, Callable, cast
from urllib.parse import quote, urlsplit

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route

from refract.ask import AskAuthError, AskConflictError
from refract.models import TERMINAL_STATES
from refract.workers import run_sync


@dataclass
class DashboardState:
    runtime: Any = None


def _json_response(value: Any, status_code: int = 200) -> Response:
    return JSONResponse(value, status_code=status_code)


def _error(message: str, status_code: int, *, code: str = "", unchanged: str = "", recovery: str = "") -> Response:
    return _json_response({"error": message, "code": code, "unchanged": unchanged, "recovery": recovery}, status_code)


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


_CSS_FILES = ("tokens.css", "fonts.css", "data-table.css", "tag.css", "announcement.css")
_JOB_LIMIT = 200
_OUTPUT_PAGE = 500
_STATE_TAGS = {"queued": "default", "running": "intermediate", "succeeded": "positive", "failed": "negative", "cancelled": "default", "interrupted": "negative"}
_BREAKER_TAGS = {"closed": "positive", "half_open": "intermediate", "open": "negative"}
_POLL_SCRIPT = r"""<script>
(() => {
  const output = document.getElementById("output");
  const state = document.getElementById("state");
  let after = Number(output.dataset.after);
  async function poll() {
    try {
      const response = await fetch(`${output.dataset.url}?after=${after}`);
      if (!response.ok) return;
      const payload = await response.json();
      for (const event of payload.events) {
        output.append(`#${event.seq} ${event.kind} ${JSON.stringify(event.data ?? {})}\n`);
      }
      after = payload.next;
      state.textContent = payload.state;
      if (payload.terminal) {
        location.reload();
        return;
      }
    } catch (error) {
      // Keep polling through transient network errors.
    }
    setTimeout(poll, 1000);
  }
  poll();
})();
</script>"""


@functools.cache
def _stylesheet() -> str:
    folder = resources.files("refract") / "dashboard_static" / "tds"
    return "\n".join((folder / name).read_text(encoding="utf-8") for name in _CSS_FILES)


def _page(title: str, body: str, *, script: str = "", status_code: int = 200) -> Response:
    return HTMLResponse(
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{escape(title)} - Refract</title>'
        f"<style>{_stylesheet()}</style></head><body>"
        '<nav><a href="/dashboard">Jobs</a><a href="/dashboard/targets">Targets</a></nav>'
        f"<main>{body}</main>{script}</body></html>",
        status_code=status_code,
    )


def _tag(text: str, variant: str, *, element_id: str = "") -> str:
    id_attribute = f' id="{element_id}"' if element_id else ""
    return f'<span{id_attribute} class="tds-tag tds-tag--md tds-tag--{variant}">{escape(text)}</span>'


def _table(title: str, headers: tuple[str, ...], rows: list[list[str]]) -> str:
    """Render a TDS data table; ``rows`` holds cells that are already escaped HTML."""
    head = "".join(f"<th>{escape(header)}</th>" for header in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return (
        '<div class="tds-data-table-container"><div class="tds-data-table__header"><div class="tds-data-table__header-text">'
        f'<div class="tds-data-table__header-title">{escape(title)}</div></div></div>'
        f'<div class="tds-data-table__wrapper"><table class="tds-data-table"><thead><tr>{head}</tr></thead>'
        f"<tbody>{body}</tbody></table></div></div>"
    )


def _age(timestamp: str) -> str:
    try:
        created = datetime.fromisoformat(timestamp)
    except ValueError:
        return ""
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    seconds = max(0, int((datetime.now(timezone.utc) - created).total_seconds()))
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return f"{seconds // size}{unit}"
    return f"{seconds}s"


def _job_href(job_id: str) -> str:
    return f"/dashboard/jobs/{quote(job_id, safe='')}"


def _events(database: Any, job_id: str, after: int) -> list[dict[str, Any]]:
    """Read stream events after ``after``; an event's seq is its line number in the stream file."""
    try:
        with database.stream_path(job_id).open(encoding="utf-8") as handle:
            lines = handle.readlines()
    except FileNotFoundError:
        return []
    events: list[dict[str, Any]] = []
    for seq, line in enumerate(lines, 1):
        if not line.endswith("\n") or len(events) >= _OUTPUT_PAGE:
            break
        if seq <= after:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            event = {"kind": "invalid", "data": {}}
        events.append({**event, "seq": seq})
    return events


def _event_line(event: dict[str, Any]) -> str:
    data = json.dumps(event.get("data") or {}, ensure_ascii=False, separators=(",", ":"))
    return f"#{event['seq']} {event.get('kind', '')} {data}\n"


def _job_list(runtime: Any) -> Response:
    database = runtime.database
    roots = {}
    jobs = []
    for project in database.projects():
        roots[project.id] = project.root
        jobs.extend(database.jobs(project.id))
    jobs.sort(key=lambda job: job.created_at, reverse=True)
    rows = [
        [
            f'<a href="{escape(_job_href(job.id))}">{escape(job.id)}</a>',
            _tag(job.state, _STATE_TAGS.get(job.state, "default")),
            escape(roots.get(job.project_id, job.project_id)),
            escape(job.workflow),
            escape(job.target_id),
            escape(_age(job.created_at)),
        ]
        for job in jobs[:_JOB_LIMIT]
    ]
    return _page("Jobs", _table("Jobs", ("Job", "State", "Project", "Workflow", "Target", "Age"), rows))


def _job_detail(runtime: Any, job_id: str) -> Response:
    database = runtime.database
    job = database.job(job_id)
    record = database.job_record(job_id)
    if job is None or record is None:
        return _page("Job not found", f"<h1>Job {escape(job_id)} was not found</h1>", status_code=404)
    result = job.result
    fields = [
        ("Project", job.project_id), ("Workflow", job.workflow), ("Profile", job.profile), ("Target", job.target_id),
        ("Session", job.session), ("Retry of", job.retry_of), ("Created", job.created_at), ("Updated", job.updated_at),
        ("Model", result.model or ""), ("Duration ms", "" if result.duration_ms is None else str(result.duration_ms)),
        ("Failure kind", result.failure_kind or ""),
        *((name, "" if value is None else str(value)) for name, value in (result.tokens or {}).items()),
    ]
    metadata = _table("Metadata", ("Field", "Value"), [[escape(name), escape(value)] for name, value in fields if value])
    events = _events(database, job_id, 0)
    active = job.state not in TERMINAL_STATES
    output_url = escape(f"{_job_href(job_id)}/output")
    body = (
        f"<h1>Job {escape(job_id)} {_tag(job.state, _STATE_TAGS.get(job.state, 'default'), element_id='state')}</h1>"
        f"{metadata}"
        f"<section><h2>Prompt</h2><pre>{escape(str(record.get('prompt', '')))}</pre></section>"
        + (f"<section><h2>Result</h2><pre>{escape(result.text)}</pre></section>" if result.text else "")
        + (f"<section><h2>Error</h2><pre>{escape(result.error)}</pre></section>" if result.error else "")
        + f'<section><h2>Output</h2><pre id="output" data-url="{output_url}" data-after="{events[-1]["seq"] if events else 0}">'
        f"{escape(''.join(_event_line(event) for event in events))}</pre></section>"
    )
    return _page(f"Job {job_id}", body, script=_POLL_SCRIPT if active else "")


def _job_output(runtime: Any, job_id: str, after_value: str) -> Response:
    job = runtime.database.job(job_id)
    if job is None:
        return _error("Job not found", 404, code="unknown_job")
    try:
        after = int(after_value)
    except ValueError:
        after = -1
    if after < 0:
        return _error("after must be a non-negative integer", 400, code="bad_request")
    events = _events(runtime.database, job_id, after)
    return _json_response({
        "events": events,
        "next": events[-1]["seq"] if events else after,
        "state": job.state,
        "terminal": job.state in TERMINAL_STATES,
    })


def _targets(runtime: Any) -> Response:
    rows = [
        [
            escape(target.id), escape(target.backend), escape(target.model),
            _tag(target.breaker_state.replace("_", " "), _BREAKER_TAGS.get(target.breaker_state, "default")),
            escape(target.circuit_open_until), escape(str(target.cooldown_s)),
            escape(f"{target.active}/{target.max_concurrency}"), "yes" if target.probing else "no",
        ]
        for target in runtime.targets()
    ]
    health = runtime.config_health()
    if health.valid:
        config = f"<p>Configuration is valid. Source: {escape(health.source_path)}. Revision: {escape(health.revision)}.</p>"
    else:
        config = (
            '<div class="tds-announcement tds-announcement--error" role="alert"><div class="tds-announcement__content">'
            '<p class="tds-announcement__title">Configuration error</p>'
            f'<p class="tds-announcement__message">{escape(health.latest_error or "Configuration is not loaded.")}</p>'
            f'<p class="tds-announcement__message">Source: {escape(health.source_path)}</p></div></div>'
        )
    table = _table(
        "Targets", ("Target", "Backend", "Model", "Circuit", "Open until", "Cooldown s", "Active", "Probing"), rows,
    )
    return _page("Targets", f"<section><h2>Configuration</h2>{config}</section>{table}")


def _register_page_routes(state: DashboardState) -> list[Route]:
    def guarded_runtime(render: Callable[..., Response]) -> Callable[[Request], Response]:
        def endpoint(request: Request) -> Response:
            try:
                runtime = _runtime(state)
            except RuntimeError:
                return _runtime_error()
            return render(runtime, request)

        return endpoint

    return [
        _loopback_route("/dashboard", guarded_runtime(lambda runtime, _: _job_list(runtime)), methods=["GET"]),
        _loopback_route("/dashboard/targets", guarded_runtime(lambda runtime, _: _targets(runtime)), methods=["GET"]),
        _loopback_route(
            "/dashboard/jobs/{job_id}",
            guarded_runtime(lambda runtime, request: _job_detail(runtime, request.path_params["job_id"])),
            methods=["GET"],
        ),
        _loopback_route(
            "/dashboard/jobs/{job_id}/output",
            guarded_runtime(lambda runtime, request: _job_output(
                runtime, request.path_params["job_id"], request.query_params.get("after", "0"),
            )),
            methods=["GET"],
        ),
    ]



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



def register_dashboard_routes(state: DashboardState) -> list[Route]:
    return [*_register_page_routes(state), *_register_ask_routes(state)]


__all__ = ["DashboardState", "register_dashboard_routes"]
