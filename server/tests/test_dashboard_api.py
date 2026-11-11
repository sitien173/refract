from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace
from urllib.parse import unquote
from typing import Any

import pytest
from starlette.applications import Starlette

from refract.dashboard import (
    DASHBOARD_HEADER,
    DASHBOARD_HEADER_VALUE,
    DashboardState,
    register_dashboard_routes,
)
from refract.models import ActionResult, SubmissionResult
from refract.pricing import PricingConfig
from refract.runtime import OrchestrationError


async def api_request(
    app: Starlette,
    path: str,
    *,
    method: str = "POST",
    headers: tuple[tuple[str, str], ...] = (),
    body: bytes = b"{}",
    client_host: str = "127.0.0.1",
    scheme: str = "http",
    server_port: int = 8765,
) -> tuple[int, dict[str, Any], dict[str, str]]:
    sent: list[dict[str, Any]] = []
    received = False

    async def receive() -> dict[str, Any]:
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    raw_path, _, query = path.partition("?")
    path_only = unquote(raw_path)
    header_list = list(headers)
    if not any(k.lower() == "host" for k, _ in header_list):
        header_list.append(("Host", f"127.0.0.1:{server_port}"))

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path_only,
        "raw_path": raw_path.encode(),
        "query_string": query.encode(),
        "headers": [(k.lower().encode(), v.encode()) for k, v in header_list],
        "client": (client_host, 1234),
        "server": ("127.0.0.1", server_port),
        "scheme": scheme,
        "root_path": "",
        "app": None,
    }
    await app(scope, receive, send)
    start = next(msg for msg in sent if msg["type"] == "http.response.start")
    chunks = [msg.get("body", b"") for msg in sent if msg["type"] == "http.response.body"]
    status_code = start["status"]
    raw_body = b"".join(chunks)
    resp_headers = {k.decode("latin1").lower(): v.decode("latin1") for k, v in start.get("headers", [])}
    try:
        parsed_json = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception:
        parsed_json = {"raw": raw_body.decode("utf-8", errors="replace")}
    return status_code, parsed_json, resp_headers


def valid_headers(
    *,
    origin: str = "http://127.0.0.1:8765",
    token_header: str = DASHBOARD_HEADER_VALUE,
    content_type: str = "application/json",
    sec_fetch_site: str | None = "same-origin",
) -> tuple[tuple[str, str], ...]:
    hdrs: list[tuple[str, str]] = [
        ("Origin", origin),
        (DASHBOARD_HEADER, token_header),
        ("Content-Type", content_type),
    ]
    if sec_fetch_site is not None:
        hdrs.append(("Sec-Fetch-Site", sec_fetch_site))
    return tuple(hdrs)


@pytest.mark.asyncio
async def test_dashboard_spa_shell_fallback_assets_and_traversal(tmp_path, monkeypatch) -> None:
    static = tmp_path / "app"
    static.mkdir()
    (static / "index.html").write_text("<main>Built dashboard shell</main>", encoding="utf-8")
    assets = static / "assets"
    assets.mkdir()
    (assets / "index-AbCd.js").write_bytes(b"export {}")
    monkeypatch.setattr("refract.dashboard._APP_STATIC_DIR", static, raising=False)
    app = Starlette(routes=register_dashboard_routes(DashboardState()))

    for path in ("/dashboard", "/dashboard/", "/dashboard/jobs/x", "/dashboard/targets"):
        status, body, headers = await api_request(app, path, method="GET")
        assert status == 200
        assert body["raw"] == "<main>Built dashboard shell</main>"
        assert headers.get("cache-control") == "no-cache"
        assert headers.get("x-content-type-options") == "nosniff"

    status, body, headers = await api_request(app, "/dashboard/assets/index-AbCd.js", method="GET")
    assert status == 200
    assert body["raw"] == "export {}"
    assert headers.get("cache-control") == "public, max-age=31536000, immutable"
    assert headers.get("x-content-type-options") == "nosniff"
    status, _, _ = await api_request(app, "/dashboard/assets/missing.js", method="GET")
    assert status == 404
    status, _, _ = await api_request(app, "/dashboard/assets/../index.html", method="GET")
    assert status == 404

    for path in ("/dashboard/", "/dashboard/assets/index-AbCd.js"):
        status, _, _ = await api_request(
            app,
            path,
            method="GET",
            headers=(("Host", "example.com"),),
        )
        assert status == 403

    status, _, _ = await api_request(
        app, "/dashboard/", method="GET", client_host="192.0.2.10"
    )
    assert status == 403


@pytest.mark.asyncio
async def test_nul_in_dashboard_asset_path_returns_404(tmp_path, monkeypatch) -> None:
    static = tmp_path / "app"
    (static / "assets").mkdir(parents=True)
    monkeypatch.setattr("refract.dashboard._APP_STATIC_DIR", static, raising=False)
    app = Starlette(routes=register_dashboard_routes(DashboardState()))

    status, _, _ = await api_request(app, "/dashboard/assets/a%00b", method="GET")
    assert status == 404


@pytest.mark.asyncio
async def test_unknown_dashboard_api_path_is_json_404_not_spa_shell() -> None:
    app = Starlette(routes=register_dashboard_routes(DashboardState()))
    status, body, headers = await api_request(app, "/dashboard/api/nope", method="GET")
    assert status == 404
    assert body["code"] == "not_found"
    assert "raw" not in body
    assert headers.get("content-type", "").startswith("application/json")


class FakeRuntime:
    def __init__(self) -> None:
        self.cancel_calls: list[str] = []
        self.retry_calls: list[str] = []
        self.answer_calls: list[tuple[str, str, str | None]] = []
        self.jobs: dict[str, dict[str, Any]] = {}

    async def cancel(self, job_id: str) -> ActionResult:
        self.cancel_calls.append(job_id)
        if job_id == "missing":
            raise OrchestrationError("Job does not exist.", code="unknown_job")
        if job_id == "running-job":
            return ActionResult(success=True, job_id=job_id, state="running")
        return ActionResult(success=True, job_id=job_id, state="cancelled")

    async def retry(self, job_id: str, target: str = "") -> SubmissionResult:
        self.retry_calls.append(job_id)
        if job_id == "missing":
            raise OrchestrationError("Job does not exist.", code="unknown_job")
        if job_id == "active-job":
            raise OrchestrationError("Job cannot be retried from state running.", code="invalid_state")
        if job_id == "overloaded":
            raise OrchestrationError(
                "All candidate targets are temporarily unavailable.",
                code="targets_unavailable",
                next_action="Wait for target recovery.",
                retry_after_s=15,
            )
        new_id = f"{job_id}-retry"
        return SubmissionResult(job_id=new_id, state="queued")

    async def job_answer(
        self, job_id: str, answer: str, expected_question_id: str | None = None
    ) -> ActionResult:
        self.answer_calls.append((job_id, answer, expected_question_id))
        if job_id == "missing":
            raise OrchestrationError("Job does not exist.", code="unknown_job")
        if job_id == "terminal-job":
            raise OrchestrationError("Job is in terminal state.", code="invalid_state")
        if expected_question_id == "stale-qid":
            raise OrchestrationError(
                f"No question is pending for job {job_id}, or it expired.",
                code="invalid_state",
            )
        return ActionResult(success=True, job_id=job_id, state="running")


@pytest.mark.asyncio
async def test_csrf_rejection_matrix() -> None:
    runtime = FakeRuntime()
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime)))
    target_url = "/dashboard/api/jobs/job-1/cancel"

    # 1. Missing Origin
    hdrs = (
        (DASHBOARD_HEADER, DASHBOARD_HEADER_VALUE),
        ("Content-Type", "application/json"),
    )
    status, body, headers = await api_request(app, target_url, headers=hdrs)
    assert status == 403
    assert body["code"] == "csrf_rejected"
    assert headers.get("cache-control") == "no-store"
    assert "access-control-allow-origin" not in headers

    # 2. Origin: null
    status, body, _ = await api_request(
        app, target_url, headers=valid_headers(origin="null")
    )
    assert status == 403
    assert body["code"] == "csrf_rejected"

    # 3. Foreign Origin
    status, body, _ = await api_request(
        app, target_url, headers=valid_headers(origin="http://evil.com:8765")
    )
    assert status == 403
    assert body["code"] == "csrf_rejected"

    # 4. Port mismatch
    status, body, _ = await api_request(
        app, target_url, headers=valid_headers(origin="http://127.0.0.1:9999")
    )
    assert status == 403
    assert body["code"] == "csrf_rejected"

    # 4b. Malformed Origin port
    for malformed_origin in (
        "http://localhost:abc",
        "http://localhost:99999",
        "http://127.0.0.1:abc",
        "http://127.0.0.1:99999",
    ):
        status, body, _ = await api_request(
            app, target_url, headers=valid_headers(origin=malformed_origin)
        )
        assert status == 403
        assert body["code"] == "csrf_rejected"

    # 5. Scheme mismatch
    status, body, _ = await api_request(
        app, target_url, headers=valid_headers(origin="https://127.0.0.1:8765")
    )
    assert status == 403
    assert body["code"] == "csrf_rejected"

    # 6. Missing custom header X-Refract-Dashboard
    hdrs = (
        ("Origin", "http://127.0.0.1:8765"),
        ("Content-Type", "application/json"),
    )
    status, body, _ = await api_request(app, target_url, headers=hdrs)
    assert status == 403
    assert body["code"] == "csrf_rejected"

    # 7. Wrong custom header value
    status, body, _ = await api_request(
        app, target_url, headers=valid_headers(token_header="wrong-val")
    )
    assert status == 403
    assert body["code"] == "csrf_rejected"

    # 8. Sec-Fetch-Site: cross-site
    status, body, _ = await api_request(
        app, target_url, headers=valid_headers(sec_fetch_site="cross-site")
    )
    assert status == 403
    assert body["code"] == "csrf_rejected"

    # 9. Non-JSON Content-Type
    status, body, _ = await api_request(
        app, target_url, headers=valid_headers(content_type="text/plain")
    )
    assert status in (400, 415)

    # 10. Malformed JSON body
    status, body, _ = await api_request(
        app, target_url, headers=valid_headers(), body=b"{bad-json"
    )
    assert status == 400
    assert body["code"] == "invalid_request"


@pytest.mark.asyncio
async def test_post_cancel_success_and_edge_cases() -> None:
    runtime = FakeRuntime()
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime)))

    # Cancel queued job
    status, body, headers = await api_request(
        app, "/dashboard/api/jobs/job-1/cancel", headers=valid_headers(), body=b"{}"
    )
    assert status == 200
    assert body == {"job_id": "job-1", "state": "cancelled", "success": True}
    assert headers.get("cache-control") == "no-store"
    assert "access-control-allow-origin" not in headers

    # Cancel running job (may return running)
    status, body, _ = await api_request(
        app, "/dashboard/api/jobs/running-job/cancel", headers=valid_headers(), body=b"{}"
    )
    assert status == 200
    assert body == {"job_id": "running-job", "state": "running", "success": True}

    # Cancel unknown job -> 404
    status, body, _ = await api_request(
        app, "/dashboard/api/jobs/missing/cancel", headers=valid_headers(), body=b"{}"
    )
    assert status == 404
    assert body["code"] == "unknown_job"


@pytest.mark.asyncio
async def test_post_retry_success_and_errors() -> None:
    runtime = FakeRuntime()
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime)))

    # Successful retry creates new job
    status, body, headers = await api_request(
        app, "/dashboard/api/jobs/job-source/retry", headers=valid_headers(), body=b"{}"
    )
    assert status == 200
    assert body == {"job_id": "job-source-retry", "state": "queued", "retry_of": "job-source"}
    assert body["job_id"] != "job-source"
    assert headers.get("cache-control") == "no-store"

    # Retry invalid state -> 409
    status, body, _ = await api_request(
        app, "/dashboard/api/jobs/active-job/retry", headers=valid_headers(), body=b"{}"
    )
    assert status == 409
    assert body["code"] == "invalid_state"

    # Retry targets unavailable -> 503 with retry info
    status, body, headers = await api_request(
        app, "/dashboard/api/jobs/overloaded/retry", headers=valid_headers(), body=b"{}"
    )
    assert status == 503
    assert body["code"] == "targets_unavailable"
    assert headers.get("retry-after") == "15"


@pytest.mark.asyncio
async def test_post_answer_matching_stale_and_validation() -> None:
    runtime = FakeRuntime()
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime)))

    # Valid answer with matching question_id
    payload = json.dumps({"answer": "Proceed with step 2", "question_id": "q-1"}).encode()
    status, body, headers = await api_request(
        app, "/dashboard/api/jobs/job-1/answer", headers=valid_headers(), body=payload
    )
    assert status == 200
    assert body == {"job_id": "job-1", "state": "running", "success": True}
    assert headers.get("cache-control") == "no-store"
    assert runtime.answer_calls == [("job-1", "Proceed with step 2", "q-1")]

    # Stale question_id -> 409 invalid_state
    payload_stale = json.dumps({"answer": "Proceed", "question_id": "stale-qid"}).encode()
    status, body, _ = await api_request(
        app, "/dashboard/api/jobs/job-1/answer", headers=valid_headers(), body=payload_stale
    )
    assert status == 409
    assert body["code"] == "invalid_state"

    # Bad answer payload (empty answer) -> 400
    payload_empty = json.dumps({"answer": "", "question_id": "q-1"}).encode()
    status, body, _ = await api_request(
        app, "/dashboard/api/jobs/job-1/answer", headers=valid_headers(), body=payload_empty
    )
    assert status == 400
    assert body["code"] == "invalid_request"

    # Missing question_id -> 400 invalid_request without calling runtime
    runtime.answer_calls.clear()
    payload_missing_qid = json.dumps({"answer": "Proceed"}).encode()
    status, body, _ = await api_request(
        app, "/dashboard/api/jobs/job-1/answer", headers=valid_headers(), body=payload_missing_qid
    )
    assert status == 400
    assert body["code"] == "invalid_request"
    assert runtime.answer_calls == []

    # Null question_id -> 400 invalid_request without calling runtime
    payload_null_qid = json.dumps({"answer": "Proceed", "question_id": None}).encode()
    status, body, _ = await api_request(
        app, "/dashboard/api/jobs/job-1/answer", headers=valid_headers(), body=payload_null_qid
    )
    assert status == 400
    assert body["code"] == "invalid_request"
    assert runtime.answer_calls == []

    # Empty question_id -> 400 invalid_request without calling runtime
    payload_empty_qid = json.dumps({"answer": "Proceed", "question_id": ""}).encode()
    status, body, _ = await api_request(
        app, "/dashboard/api/jobs/job-1/answer", headers=valid_headers(), body=payload_empty_qid
    )
    assert status == 400
    assert body["code"] == "invalid_request"
    assert runtime.answer_calls == []

    # Non-string question_id -> 400 invalid_request without calling runtime
    payload_non_str_qid = json.dumps({"answer": "Proceed", "question_id": 12345}).encode()
    status, body, _ = await api_request(
        app, "/dashboard/api/jobs/job-1/answer", headers=valid_headers(), body=payload_non_str_qid
    )
    assert status == 400
    assert body["code"] == "invalid_request"
    assert runtime.answer_calls == []


def _stats_test_app() -> tuple[Starlette, sqlite3.Connection]:
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("""CREATE TABLE job_metrics (job_id TEXT, finished_at TEXT, workflow TEXT,
        target TEXT, backend TEXT, model TEXT, state TEXT, failure_kind TEXT, duration_ms INTEGER,
        tok_input INTEGER, tok_output INTEGER, tok_cache_read INTEGER, tok_cache_write INTEGER,
        attempts INTEGER, skipped_targets INTEGER, retry_of TEXT)""")
    runtime = SimpleNamespace(database=SimpleNamespace(_connection=connection),
                              pricing=PricingConfig())
    return Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime))), connection


@pytest.mark.asyncio
async def test_stats_api_returns_valid_body() -> None:
    app, connection = _stats_test_app()
    try:
        status, body, _ = await api_request(app, "/dashboard/api/stats?days=7", method="GET")
        assert status == 200
        assert body["days"] == 7
    finally:
        connection.close()


@pytest.mark.asyncio
async def test_stats_api_rejects_days_two() -> None:
    app, connection = _stats_test_app()
    try:
        status, body, _ = await api_request(app, "/dashboard/api/stats?days=2", method="GET")
        assert status == 400
        assert "days" in body["error"]
    finally:
        connection.close()


@pytest.mark.asyncio
async def test_stats_api_rejects_non_integer_timezone_offset() -> None:
    app, connection = _stats_test_app()
    try:
        status, body, _ = await api_request(
            app, "/dashboard/api/stats?tz_offset_minutes=no", method="GET"
        )
        assert status == 400
        assert "tz_offset_minutes" in body["error"]
    finally:
        connection.close()


@pytest.mark.asyncio
async def test_stats_api_rejects_out_of_range_timezone_offset() -> None:
    app, connection = _stats_test_app()
    try:
        status, body, _ = await api_request(
            app, "/dashboard/api/stats?tz_offset_minutes=999999999999", method="GET"
        )
        assert status == 400
        assert body["error"] == "tz_offset_minutes must be an integer between -1440 and 1440"
    finally:
        connection.close()


@pytest.mark.asyncio
async def test_runtime_inactive_returns_503() -> None:
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=None)))
    status, body, headers = await api_request(
        app, "/dashboard/api/jobs/job-1/cancel", headers=valid_headers(), body=b"{}"
    )
    assert status == 503
    assert body["code"] == "runtime_unavailable"
    assert headers.get("cache-control") == "no-store"

    # GET /dashboard/api/jobs also returns 503 when runtime is None
    status, body, headers = await api_request(
        app, "/dashboard/api/jobs", method="GET"
    )
    assert status == 503
    assert body["code"] == "runtime_unavailable"
    assert headers.get("cache-control") == "no-store"


@pytest.mark.asyncio
async def test_get_jobs_contract_and_summary_keys(tmp_path: Any) -> None:
    from refract.database import Database

    db = Database(tmp_path / "refract.db")
    project = db.upsert_project(project_id="proj-1", root="/path/to/project")
    db.create_job(
        job_id="job-alpha",
        project_id=project.id,
        workflow="workflow-alpha",
        profile="balanced",
        prompt="run alpha",
        execution_plan_json="{}",
        session="sess-1",
        retry_of="job-orig",
    )
    with db._connection:
        db._connection.execute(
            "UPDATE jobs SET target='target-1', state='succeeded', failure_kind='timeout' WHERE id='job-alpha'"
        )

    runtime = SimpleNamespace(database=db)
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime)))

    status, body, headers = await api_request(app, "/dashboard/api/jobs", method="GET")
    assert status == 200
    assert headers.get("cache-control") == "no-store"

    assert set(body.keys()) == {"jobs", "next_cursor", "options"}
    assert body["next_cursor"] is None
    assert body["options"] == {
        "states": ["succeeded"],
        "projects": [{"id": "proj-1", "root": "/path/to/project"}],
        "workflows": ["workflow-alpha"],
        "targets": ["target-1"],
    }

    assert len(body["jobs"]) == 1
    job = body["jobs"][0]
    expected_keys = {
        "id", "state", "project_id", "project_root", "workflow", "profile",
        "target", "session", "retry_of", "failure_kind", "created_at", "updated_at"
    }
    assert set(job.keys()) == expected_keys
    assert job["id"] == "job-alpha"
    assert job["state"] == "succeeded"
    assert job["project_id"] == "proj-1"
    assert job["project_root"] == "/path/to/project"
    assert job["workflow"] == "workflow-alpha"
    assert job["profile"] == "balanced"
    assert job["target"] == "target-1"
    assert job["session"] == "sess-1"
    assert job["retry_of"] == "job-orig"
    assert job["failure_kind"] == "timeout"
    db.close()


@pytest.mark.asyncio
async def test_get_jobs_filters_and_pagination(tmp_path: Any) -> None:
    from refract.database import Database

    db = Database(tmp_path / "refract.db")
    p1 = db.upsert_project(project_id="p1", root="/r1")
    p2 = db.upsert_project(project_id="p2", root="/r2")

    now = "2026-11-05T12:00:0"
    for i in range(4):
        job_id = f"job_num_{i}"
        db.create_job(
            job_id=job_id,
            project_id=p1.id if i < 2 else p2.id,
            workflow="wf-1" if i % 2 == 0 else "wf-2",
            profile="balanced",
            prompt=f"p {i}",
            execution_plan_json="{}",
            session="s",
        )
        with db._connection:
            db._connection.execute(
                "UPDATE jobs SET created_at=?, target=?, state=? WHERE id=?",
                (f"{now}{i}+00:00", f"tg-{i % 2}", "running" if i == 0 else "succeeded", job_id),
            )

    runtime = SimpleNamespace(database=db)
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime)))

    # Filtering by state
    status, body, _ = await api_request(app, "/dashboard/api/jobs?state=running", method="GET")
    assert status == 200
    assert len(body["jobs"]) == 1
    assert body["jobs"][0]["id"] == "job_num_0"
    # Options remain unfiltered
    assert body["options"]["states"] == ["running", "succeeded"]

    # Filtering by project
    status, body, _ = await api_request(app, f"/dashboard/api/jobs?project={p2.id}", method="GET")
    assert status == 200
    assert len(body["jobs"]) == 2
    assert {j["id"] for j in body["jobs"]} == {"job_num_2", "job_num_3"}

    # Filtering by q with wildcards (e.g. "_" in job id)
    status, body, _ = await api_request(app, "/dashboard/api/jobs?q=_num_", method="GET")
    assert status == 200
    assert len(body["jobs"]) == 4

    # Pagination: limit=2
    status, body, _ = await api_request(app, "/dashboard/api/jobs?limit=2", method="GET")
    assert status == 200
    assert len(body["jobs"]) == 2
    assert [j["id"] for j in body["jobs"]] == ["job_num_3", "job_num_2"]
    cursor = body["next_cursor"]
    assert cursor is not None

    status, body, _ = await api_request(app, f"/dashboard/api/jobs?limit=2&cursor={cursor}", method="GET")
    assert status == 200
    assert len(body["jobs"]) == 2
    assert [j["id"] for j in body["jobs"]] == ["job_num_1", "job_num_0"]
    assert body["next_cursor"] is None

    # Invalid limit -> 400
    status, body, _ = await api_request(app, "/dashboard/api/jobs?limit=0", method="GET")
    assert status == 400
    assert body["code"] == "invalid_request"

    status, body, _ = await api_request(app, "/dashboard/api/jobs?limit=201", method="GET")
    assert status == 400
    assert body["code"] == "invalid_request"

    status, body, _ = await api_request(app, "/dashboard/api/jobs?limit=abc", method="GET")
    assert status == 400
    assert body["code"] == "invalid_request"

    # Invalid cursor -> 400
    status, body, _ = await api_request(app, "/dashboard/api/jobs?cursor=invalid-cursor", method="GET")
    assert status == 400
    assert body["code"] == "invalid_request"

    # Rejects non-loopback
    status, _, _ = await api_request(app, "/dashboard/api/jobs", method="GET", client_host="192.0.2.10")
    assert status == 403

    db.close()


@pytest.mark.asyncio
async def test_get_jobs_reads_no_result_files(tmp_path: Any, monkeypatch: Any) -> None:
    from pathlib import Path
    from refract.database import Database

    db = Database(tmp_path / "refract.db")
    project = db.upsert_project(project_id="proj", root="/proj")
    db.create_job(
        job_id="job-1",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="hello",
        execution_plan_json="{}",
        session="sess",
    )

    def explode(*args, **kwargs):
        raise RuntimeError("Result file was accessed during list query!")

    monkeypatch.setattr(Database, "result_path", explode)
    monkeypatch.setattr(Path, "read_text", explode)

    runtime = SimpleNamespace(database=db)
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime)))

    status, body, _ = await api_request(app, "/dashboard/api/jobs", method="GET")
    assert status == 200
    assert len(body["jobs"]) == 1
    assert body["jobs"][0]["id"] == "job-1"
    db.close()


def assert_no_forbidden_keys(obj: Any) -> None:
    forbidden = {"token", "future", "deadline", "execution_plan", "execution_plan_json", "pgid"}
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert k not in forbidden, f"Forbidden key '{k}' found at key in response!"
            assert_no_forbidden_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            assert_no_forbidden_keys(item)


@pytest.mark.asyncio
async def test_get_job_detail_contract_and_forbidden_keys(tmp_path: Any) -> None:
    from refract.ask import PendingQuestion
    from refract.database import Database

    db = Database(tmp_path / "refract.db")
    project = db.upsert_project(project_id="proj-1", root="/path/to/project")
    db.create_job(
        job_id="job-detail-test",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="the prompt string",
        execution_plan_json='{"forbidden": "plan"}',
        session="sess-1",
        retry_of="job-source",
    )
    with db._connection:
        db._connection.execute(
            """UPDATE jobs SET
                target='target-main',
                state='succeeded',
                failure_kind=NULL,
                error='an error message',
                model='claude-3',
                duration_ms=450,
                pgid=1234,
                started_at='2026-11-05T12:01:00+00:00',
                finished_at='2026-11-05T12:02:00+00:00',
                tok_context_used=100,
                tok_context_window=200,
                tok_input=50,
                tok_output=25,
                tok_cache_read=10,
                tok_cache_write=5
            WHERE id='job-detail-test'"""
        )
    db.results_dir.mkdir(parents=True, exist_ok=True)
    db.result_path("job-detail-test").write_text("the result text", encoding="utf-8")

    class FakeAskRegistry:
        def get_pending(self, job_id: str) -> Any:
            if job_id == "job-detail-test":
                return PendingQuestion(
                    question_id="q-42",
                    text="Should we continue?",
                    future=None,
                    deadline="2026-11-05T13:00:00+00:00",
                )
            return None

    runtime = SimpleNamespace(database=db, ask_registry=FakeAskRegistry())
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime)))

    status, body, headers = await api_request(
        app, "/dashboard/api/jobs/job-detail-test", method="GET"
    )
    assert status == 200
    assert headers.get("cache-control") == "no-store"

    expected_keys = {
        "id", "state", "project_id", "project_root", "workflow", "profile",
        "target", "session", "retry_of", "failure_kind", "created_at", "updated_at",
        "started_at", "finished_at", "prompt", "result", "pending_question",
    }
    assert set(body.keys()) == expected_keys
    assert body["id"] == "job-detail-test"
    assert body["state"] == "succeeded"
    assert body["project_id"] == "proj-1"
    assert body["project_root"] == "/path/to/project"
    assert body["workflow"] == "consult"
    assert body["profile"] == "balanced"
    assert body["target"] == "target-main"
    assert body["session"] == "sess-1"
    assert body["retry_of"] == "job-source"
    assert body["failure_kind"] is None
    assert body["started_at"] == "2026-11-05T12:01:00+00:00"
    assert body["finished_at"] == "2026-11-05T12:02:00+00:00"
    assert body["prompt"] == "the prompt string"

    result = body["result"]
    assert set(result.keys()) == {"text", "error", "failure_kind", "model", "duration_ms", "tokens"}
    assert result["text"] == "the result text"
    assert result["error"] == "an error message"
    assert result["failure_kind"] is None
    assert result["model"] == "claude-3"
    assert result["duration_ms"] == 450
    assert result["tokens"] == {
        "context_used": 100,
        "context_window": 200,
        "input": 50,
        "output": 25,
        "cache_read": 10,
        "cache_write": 5,
    }

    assert body["pending_question"] == {"question_id": "q-42", "text": "Should we continue?"}

    # Assert forbidden keys are absent recursively at all depths
    assert_no_forbidden_keys(body)

    # When no question is pending, pending_question is None
    class EmptyAskRegistry:
        def get_pending(self, job_id: str) -> Any:
            return None

    runtime_no_q = SimpleNamespace(database=db, ask_registry=EmptyAskRegistry())
    app_no_q = Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime_no_q)))
    status, body_no_q, _ = await api_request(
        app_no_q, "/dashboard/api/jobs/job-detail-test", method="GET"
    )
    assert status == 200
    assert body_no_q["pending_question"] is None

    # Unknown job -> 404 unknown_job
    status, body_404, _ = await api_request(
        app, "/dashboard/api/jobs/nonexistent-job", method="GET"
    )
    assert status == 404
    assert body_404["code"] == "unknown_job"

    # Rejects non-loopback
    status, _, _ = await api_request(
        app, "/dashboard/api/jobs/job-detail-test", method="GET", client_host="192.0.2.10"
    )
    assert status == 403

    db.close()


@pytest.mark.asyncio
async def test_get_output_1200_events_pagination(tmp_path: Any) -> None:
    from refract.database import Database

    db = Database(tmp_path / "refract.db")
    project = db.upsert_project(project_id="p1", root="/p1")
    db.create_job(
        job_id="job-stream",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="p",
        execution_plan_json="{}",
        session="s",
    )
    with db._connection:
        db._connection.execute("UPDATE jobs SET state='running' WHERE id='job-stream'")

    # Write 1200 events
    db.streams_dir.mkdir(parents=True, exist_ok=True)
    events = [{"kind": f"evt-{i}", "data": {"num": i}} for i in range(1, 1201)]
    stream_content = "".join(json.dumps(e) + "\n" for e in events)
    db.stream_path("job-stream").write_text(stream_content, encoding="utf-8")

    runtime = SimpleNamespace(database=db)
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime)))

    # Page 1: after=0 (default)
    status, body, headers = await api_request(app, "/dashboard/api/jobs/job-stream/output", method="GET")
    assert status == 200
    assert headers.get("cache-control") == "no-store"
    assert body["available"] is True
    assert body["state"] == "running"
    assert body["terminal"] is False
    assert len(body["events"]) == 500
    assert body["events"][0]["seq"] == 1
    assert body["events"][-1]["seq"] == 500
    assert body["next"] == 500
    assert body["has_more"] is True

    # Page 2: after=500
    status, body, _ = await api_request(app, "/dashboard/api/jobs/job-stream/output?after=500", method="GET")
    assert status == 200
    assert len(body["events"]) == 500
    assert body["events"][0]["seq"] == 501
    assert body["events"][-1]["seq"] == 1000
    assert body["next"] == 1000
    assert body["has_more"] is True

    # Page 3: after=1000
    status, body, _ = await api_request(app, "/dashboard/api/jobs/job-stream/output?after=1000", method="GET")
    assert status == 200
    assert len(body["events"]) == 200
    assert body["events"][0]["seq"] == 1001
    assert body["events"][-1]["seq"] == 1200
    assert body["next"] == 1200
    assert body["has_more"] is False

    db.close()


@pytest.mark.asyncio
async def test_get_output_partial_final_line_withheld(tmp_path: Any) -> None:
    from refract.database import Database

    db = Database(tmp_path / "refract.db")
    project = db.upsert_project(project_id="p1", root="/p1")
    db.create_job(
        job_id="job-partial",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="p",
        execution_plan_json="{}",
        session="s",
    )
    with db._connection:
        db._connection.execute("UPDATE jobs SET state='running' WHERE id='job-partial'")

    db.streams_dir.mkdir(parents=True, exist_ok=True)
    # 2 complete lines and 1 partial line with no trailing \n
    content = json.dumps({"kind": "evt-1"}) + "\n" + json.dumps({"kind": "evt-2"}) + "\n" + '{"kind": "evt-incomplete"'
    db.stream_path("job-partial").write_text(content, encoding="utf-8")

    runtime = SimpleNamespace(database=db)
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime)))

    status, body, _ = await api_request(app, "/dashboard/api/jobs/job-partial/output", method="GET")
    assert status == 200
    assert len(body["events"]) == 2
    assert [e["seq"] for e in body["events"]] == [1, 2]
    assert body["next"] == 2
    assert body["has_more"] is False
    assert body["available"] is True

    db.close()


@pytest.mark.asyncio
async def test_get_output_authoritative_seq_and_invalid_utf8(tmp_path: Any) -> None:
    from refract.database import Database

    db = Database(tmp_path / "refract.db")
    project = db.upsert_project(project_id="p1", root="/p1")
    db.create_job(
        job_id="job-seq-test",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="p",
        execution_plan_json="{}",
        session="s",
    )
    with db._connection:
        db._connection.execute("UPDATE jobs SET state='running' WHERE id='job-seq-test'")

    db.streams_dir.mkdir(parents=True, exist_ok=True)
    line1 = (json.dumps({"kind": "evt-1", "seq": 999}) + "\n").encode("utf-8")
    line2 = (json.dumps({"kind": "evt-2", "seq": "not-an-int"}) + "\n").encode("utf-8")
    line3 = b'{"kind": "evt-\xff-corrupt", "data": {}}\n'

    stream_file = db.stream_path("job-seq-test")
    stream_file.write_bytes(line1 + line2 + line3)

    runtime = SimpleNamespace(database=db)
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime)))

    status, body, _ = await api_request(app, "/dashboard/api/jobs/job-seq-test/output", method="GET")
    assert status == 200
    assert len(body["events"]) == 3
    assert body["events"][0]["seq"] == 1
    assert body["events"][0]["kind"] == "evt-1"
    assert body["events"][1]["seq"] == 2
    assert body["events"][1]["kind"] == "evt-2"
    assert body["events"][2]["seq"] == 3
    assert body["next"] == 3

    db.close()


@pytest.mark.asyncio
async def test_get_output_missing_stream_file(tmp_path: Any) -> None:
    from refract.database import Database

    db = Database(tmp_path / "refract.db")
    project = db.upsert_project(project_id="p1", root="/p1")
    db.create_job(
        job_id="job-done",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="p",
        execution_plan_json="{}",
        session="s",
    )
    with db._connection:
        db._connection.execute("UPDATE jobs SET state='succeeded' WHERE id='job-done'")

    runtime = SimpleNamespace(database=db)
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime)))

    status, body, _ = await api_request(app, "/dashboard/api/jobs/job-done/output", method="GET")
    assert status == 200
    assert body == {
        "events": [],
        "next": 0,
        "has_more": False,
        "available": False,
        "state": "succeeded",
        "terminal": True,
    }
    db.close()


@pytest.mark.asyncio
async def test_get_output_invalid_after_and_unknown_job(tmp_path: Any) -> None:
    from refract.database import Database

    db = Database(tmp_path / "refract.db")
    project = db.upsert_project(project_id="p1", root="/p1")
    db.create_job(
        job_id="job-val",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="p",
        execution_plan_json="{}",
        session="s",
    )

    runtime = SimpleNamespace(database=db)
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime)))

    # after < 0 -> 400 invalid_request
    status, body, _ = await api_request(app, "/dashboard/api/jobs/job-val/output?after=-1", method="GET")
    assert status == 400
    assert body["code"] == "invalid_request"

    # after non-int -> 400 invalid_request
    status, body, _ = await api_request(app, "/dashboard/api/jobs/job-val/output?after=abc", method="GET")
    assert status == 400
    assert body["code"] == "invalid_request"

    # Unknown job -> 404 unknown_job
    status, body, _ = await api_request(app, "/dashboard/api/jobs/no-such-job/output", method="GET")
    assert status == 404
    assert body["code"] == "unknown_job"

    db.close()


@pytest.mark.asyncio
async def test_get_targets_contract() -> None:
    from refract.models import ConfigHealth, TargetView

    targets = [
        TargetView(
            id="tgt-1", model="gpt-4o", backend="codex",
            max_concurrency=4, active=1, healthy=True, circuit_open_until="",
            breaker_state="closed", cooldown_s=60, probing=False,
        ),
        TargetView(
            id="tgt-2", model="claude-3-5", backend="claude",
            max_concurrency=2, active=0, healthy=True, circuit_open_until="",
            breaker_state="closed", cooldown_s=60, probing=False,
        ),
    ]
    health = ConfigHealth(valid=True, source_path="/path/to/config.toml")
    runtime = SimpleNamespace(targets=lambda: targets, config_health=health)
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime)))

    status, body, headers = await api_request(app, "/dashboard/api/targets", method="GET")
    assert status == 200
    assert headers.get("cache-control") == "no-store"
    assert "targets" in body
    assert "config" in body
    assert len(body["targets"]) == 2
    assert body["targets"][0]["id"] == "tgt-1"
    assert body["targets"][0]["model"] == "gpt-4o"
    assert body["config"]["valid"] is True
    assert body["config"]["source_path"] == "/path/to/config.toml"


@pytest.mark.asyncio
async def test_api_fallback_404_and_loopback_matrix() -> None:
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=SimpleNamespace())))

    # GET /dashboard/api/nope -> 404
    status, body, headers = await api_request(app, "/dashboard/api/nope", method="GET")
    assert status == 404
    assert body["code"] == "not_found"
    assert headers.get("cache-control") == "no-store"
    assert set(body.keys()) == {"error", "code", "unchanged", "recovery"}

    # POST /dashboard/api/nope -> 404
    status, body, _ = await api_request(app, "/dashboard/api/nope", method="POST")
    assert status == 404
    assert body["code"] == "not_found"

    # Unsupported method on registered API route (POST /dashboard/api/jobs) -> 404 not_found
    status, body, _ = await api_request(app, "/dashboard/api/jobs", method="POST")
    assert status == 404
    assert body["code"] == "not_found"
    assert body["unchanged"] == "Nothing was modified."

    # Non-loopback client on fallback -> 403
    status, _, _ = await api_request(app, "/dashboard/api/nope", method="GET", client_host="192.0.2.10")
    assert status == 403

    # Non-loopback client on targets -> 403
    status, _, _ = await api_request(app, "/dashboard/api/targets", method="GET", client_host="192.0.2.10")
    assert status == 403

    # Non-loopback client on output -> 403
    status, _, _ = await api_request(app, "/dashboard/api/jobs/job-1/output", method="GET", client_host="192.0.2.10")
    assert status == 403


def _card_app(tmp_path: Any) -> tuple[Starlette, Any]:
    from refract.database import Database

    db = Database(tmp_path / "refract.db")
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=SimpleNamespace(database=db))))
    return app, db


def _card_job(db: Any, project_id: str, job_id: str) -> None:
    db.create_job(
        job_id=job_id, project_id=project_id, workflow="implement", profile="default",
        prompt="p", execution_plan_json="{}", session="s",
    )


@pytest.mark.asyncio
async def test_get_cards_filter_options_and_no_body(tmp_path: Any) -> None:
    app, db = _card_app(tmp_path)
    p1 = db.upsert_project(project_id="p1", root=(tmp_path / "one").as_posix()).id
    p2 = db.upsert_project(project_id="p2", root=(tmp_path / "two").as_posix()).id
    _card_job(db, p1, "job-1")
    db.create_card(card_id="a", project_id=p1, title="A", body="secret-body", job_ids=["job-1"])
    db.create_card(card_id="b", project_id=p2, title="B", body="", job_ids=[])

    status, body, headers = await api_request(app, "/dashboard/api/cards", method="GET")
    assert status == 200
    assert headers.get("cache-control") == "no-store"
    assert set(body) == {"cards", "truncated", "options"}
    assert body["truncated"] is False
    assert {c["id"] for c in body["cards"]} == {"a", "b"}
    for card in body["cards"]:
        assert set(card) == {
            "id", "project_id", "project_root", "title", "state", "job_ids", "created_at", "updated_at",
        }
    assert next(c for c in body["cards"] if c["id"] == "a")["job_ids"] == ["job-1"]
    assert "secret-body" not in json.dumps(body)
    projects = [{"id": p1, "root": (tmp_path / "one").as_posix()}, {"id": p2, "root": (tmp_path / "two").as_posix()}]
    assert set(body["options"]) == {"projects"}
    assert sorted(body["options"]["projects"], key=lambda p: p["id"]) == projects

    status, body, _ = await api_request(app, f"/dashboard/api/cards?project={p1}", method="GET")
    assert status == 200
    assert [c["id"] for c in body["cards"]] == ["a"]
    assert len(body["options"]["projects"]) == 2

    status, body, _ = await api_request(app, "/dashboard/api/cards?project=", method="GET")
    assert {c["id"] for c in body["cards"]} == {"a", "b"}

    status, body, _ = await api_request(app, "/dashboard/api/cards?project=nope", method="GET")
    assert status == 200
    assert body["cards"] == []
    assert body["truncated"] is False
    assert len(body["options"]["projects"]) == 2
    assert all(set(p) == {"id", "root"} for p in body["options"]["projects"])


@pytest.mark.asyncio
async def test_get_cards_truncates_at_200_and_orders_open_first(tmp_path: Any) -> None:
    app, db = _card_app(tmp_path)
    p1 = db.upsert_project(project_id="p1", root=tmp_path.as_posix()).id
    for index in range(200):
        db.create_card(card_id=f"c{index:03d}", project_id=p1, title="t", body="", job_ids=[])

    status, body, _ = await api_request(app, "/dashboard/api/cards", method="GET")
    assert status == 200
    assert len(body["cards"]) == 200
    assert body["truncated"] is False

    db.create_card(card_id="c200", project_id=p1, title="t", body="", job_ids=[])
    status, body, _ = await api_request(app, "/dashboard/api/cards", method="GET")
    assert len(body["cards"]) == 200
    assert body["truncated"] is True

    (tmp_path / "order").mkdir()
    app, db = _card_app(tmp_path / "order")
    p1 = db.upsert_project(project_id="p1", root=tmp_path.as_posix()).id
    for card_id in ("x", "y", "z"):
        db.create_card(card_id=card_id, project_id=p1, title="t", body="", job_ids=[])
    db.move_card(card_id="x", state="cancelled", job_ids=[], note="")
    for step in ("in_progress", "in_review", "done"):
        db.move_card(card_id="y", state=step, job_ids=[], note="")
    status, body, _ = await api_request(app, "/dashboard/api/cards", method="GET")
    states = [c["state"] for c in body["cards"]]
    assert states[0] == "todo"
    assert set(states[1:]) == {"cancelled", "done"}


@pytest.mark.asyncio
async def test_get_card_detail_shapes_and_pruned_job(tmp_path: Any) -> None:
    app, db = _card_app(tmp_path)
    p1 = db.upsert_project(project_id="p1", root=tmp_path.as_posix()).id
    _card_job(db, p1, "job-live")
    _card_job(db, p1, "job-old")
    db.finish_job("job-old", "succeeded", text="x", target="primary")
    db.create_card(card_id="c1", project_id=p1, title="T", body="the body", job_ids=["job-old", "job-live"])
    db.move_card(card_id="c1", state="in_progress", job_ids=[], note="started")
    db.prune_history("9999-01-01T00:00:00Z")

    status, body, headers = await api_request(app, "/dashboard/api/cards/c1", method="GET")
    assert status == 200
    assert headers.get("cache-control") == "no-store"
    assert set(body) == {"card", "moves", "jobs"}
    assert set(body["card"]) == {
        "id", "project_id", "project_root", "title", "body", "state", "job_ids", "created_at", "updated_at",
    }
    assert body["card"]["body"] == "the body"
    assert [m["to_state"] for m in body["moves"]] == ["todo", "in_progress"]
    assert all(set(m) == {"from_state", "to_state", "note", "at"} for m in body["moves"])
    assert body["moves"][1]["note"] == "started"
    assert all(set(j) == {"id", "workflow", "state", "target", "available"} for j in body["jobs"])
    assert body["card"]["job_ids"] == [j["id"] for j in body["jobs"]]
    assert sorted(body["card"]["job_ids"]) == ["job-live", "job-old"]
    by_id = {j["id"]: j for j in body["jobs"]}
    assert by_id["job-old"] == {"id": "job-old", "workflow": None, "state": None, "target": None, "available": False}
    assert by_id["job-live"]["available"] is True
    assert by_id["job-live"]["workflow"] == "implement"


@pytest.mark.asyncio
async def test_get_card_unknown_id_is_404(tmp_path: Any) -> None:
    app, _ = _card_app(tmp_path)
    status, body, headers = await api_request(app, "/dashboard/api/cards/nope", method="GET")
    assert status == 404
    assert body["code"] == "unknown_card"
    assert body["unchanged"] == "Nothing was modified."
    assert set(body) == {"error", "code", "unchanged", "recovery"}
    assert headers.get("cache-control") == "no-store"


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/dashboard/api/cards", "/dashboard/api/cards/c1"])
async def test_card_routes_reject_post_with_fallback_404(path: str) -> None:
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=SimpleNamespace())))

    status, body, headers = await api_request(app, path, method="POST")
    assert status == 404
    assert body["code"] == "not_found"
    assert "unchanged" in body
    assert "recovery" in body
    assert headers.get("cache-control") == "no-store"


def _csrf_request(headers: tuple[tuple[str, str], ...], *, scheme: str = "http", host: str = "127.0.0.1:8765"):
    from starlette.requests import Request

    return Request({
        "type": "http", "http_version": "1.1", "method": "POST", "path": "/", "raw_path": b"/", "query_string": b"",
        "headers": [(b"host", host.encode()), *[(k.lower().encode(), v.encode()) for k, v in headers]],
        "client": ("127.0.0.1", 1234), "server": ("127.0.0.1", 8765), "scheme": scheme, "root_path": "",
    })


_CSRF_REJECTIONS = [
    pytest.param(dict(origin=""), {}, 403, "csrf_rejected", "CSRF check failed: Origin header required", id="empty-origin"),
    pytest.param(dict(origin="NULL"), {}, 403, "csrf_rejected", "CSRF check failed: Origin header required", id="null-origin"),
    pytest.param(dict(origin="not-a-url"), {}, 403, "csrf_rejected", "CSRF check failed: non-loopback Origin", id="origin-without-host"),
    pytest.param(dict(origin="http://evil.example:8765"), {}, 403, "csrf_rejected", "CSRF check failed: non-loopback Origin", id="foreign-origin"),
    pytest.param(dict(origin="https://127.0.0.1:8765"), {}, 403, "csrf_rejected", "CSRF check failed: scheme mismatch", id="scheme-mismatch"),
    pytest.param(dict(origin="http://localhost:8765"), {}, 403, "csrf_rejected", "CSRF check failed: host mismatch", id="host-mismatch"),
    pytest.param(dict(origin="http://127.0.0.1:abc"), {}, 403, "csrf_rejected", "CSRF check failed: invalid Origin port", id="invalid-port"),
    pytest.param(dict(origin="http://127.0.0.1:9999"), {}, 403, "csrf_rejected", "CSRF check failed: port mismatch", id="port-mismatch"),
    pytest.param(dict(origin="http://127.0.0.1"), {}, 403, "csrf_rejected", "CSRF check failed: port mismatch", id="default-port-mismatch"),
    # Pins current behavior, not intended behavior: a loopback IPv6 origin is rejected today.
    pytest.param(dict(origin="http://[::1]:8765"), {"host": "[::1]:8765"}, 403, "csrf_rejected", "CSRF check failed: non-loopback Origin", id="ipv6-origin-currently-rejected"),
    pytest.param(dict(sec_fetch_site="cross-site"), {}, 403, "csrf_rejected", "CSRF check failed: Sec-Fetch-Site must be same-origin", id="cross-site"),
    pytest.param(dict(token_header="0"), {}, 403, "csrf_rejected", "CSRF check failed: missing or invalid dashboard header", id="wrong-dashboard-header"),
    pytest.param(dict(content_type="text/plain"), {}, 415, "unsupported_media_type", "Content-Type must be application/json", id="wrong-media-type"),
]


@pytest.mark.parametrize(("header_options", "request_options", "status", "code", "message"), _CSRF_REJECTIONS)
def test_check_csrf_rejects_with_status_and_message(header_options, request_options, status, code, message) -> None:
    from refract.dashboard import _check_csrf

    response = _check_csrf(_csrf_request(valid_headers(**header_options), **request_options))
    assert response is not None
    body = json.loads(response.body)
    assert (response.status_code, body["code"], body["error"]) == (status, code, message)


@pytest.mark.parametrize(
    ("headers", "status", "message"),
    [
        pytest.param(
            (("Origin", "http://127.0.0.1:8765"), ("Content-Type", "application/json")),
            403,
            "CSRF check failed: missing or invalid dashboard header",
            id="missing-dashboard-header",
        ),
        pytest.param(
            (("Origin", "http://127.0.0.1:8765"), (DASHBOARD_HEADER, DASHBOARD_HEADER_VALUE)),
            415,
            "Content-Type must be application/json",
            id="missing-content-type",
        ),
    ],
)
def test_check_csrf_rejects_absent_headers(headers, status, message) -> None:
    from refract.dashboard import _check_csrf

    response = _check_csrf(_csrf_request(headers))
    assert response is not None
    assert (response.status_code, json.loads(response.body)["error"]) == (status, message)


@pytest.mark.parametrize(
    ("headers", "scheme", "host"),
    [
        pytest.param(valid_headers(), "http", "127.0.0.1:8765", id="same-origin"),
        pytest.param(valid_headers(sec_fetch_site=None), "http", "127.0.0.1:8765", id="no-sec-fetch-site"),
        pytest.param(valid_headers(sec_fetch_site=" Same-Origin "), "http", "127.0.0.1:8765", id="sec-fetch-site-case-and-space"),
        pytest.param(valid_headers(content_type="Application/JSON; charset=utf-8"), "http", "127.0.0.1:8765", id="media-type-parameters"),
        pytest.param(valid_headers(origin="HTTP://127.0.0.1:8765"), "http", "127.0.0.1:8765", id="origin-scheme-case"),
        pytest.param(valid_headers(origin="http://127.0.0.1"), "http", "127.0.0.1", id="default-http-port"),
        pytest.param(valid_headers(origin="https://127.0.0.1"), "https", "127.0.0.1", id="default-https-port"),
    ],
)
def test_check_csrf_accepts_same_origin_requests(headers, scheme, host) -> None:
    from refract.dashboard import _check_csrf

    assert _check_csrf(_csrf_request(headers, scheme=scheme, host=host)) is None


def _ask_app(runtime):
    return Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime)))


class _AskRegistry:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.error = error

    async def ask(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return "the answer"


_ASK_BAD_REQUEST = [
    pytest.param(b"", "Malformed request body", id="empty-body"),
    pytest.param(b"not-json", "Malformed request body", id="invalid-json"),
    pytest.param(b"[1]", "Malformed request body", id="non-object"),
    pytest.param(b'{"question":"q"}', "token must be a non-empty string", id="missing-token"),
    pytest.param(b'{"token":"","question":"q"}', "token must be a non-empty string", id="empty-token"),
    pytest.param(b'{"token":"t"}', "question must be a non-empty string", id="missing-question"),
    pytest.param(b'{"token":"t","question":"  "}', "question must be a non-empty string", id="blank-question"),
    pytest.param(b'{"token":"t","question":"q","job_id":5}', "job_id must be a string", id="non-string-job-id"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("body", "message"), _ASK_BAD_REQUEST)
async def test_ask_route_rejects_bad_requests(body, message) -> None:
    registry = _AskRegistry()
    status, parsed, _ = await api_request(_ask_app(SimpleNamespace(ask_registry=registry, config=SimpleNamespace())), "/ask", body=body)
    assert (status, parsed["error"], parsed["code"]) == (400, message, "bad_request")
    assert registry.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "runtime",
    [
        pytest.param(None, id="no-runtime"),
        pytest.param(SimpleNamespace(config=SimpleNamespace()), id="runtime-without-ask-registry"),
    ],
)
async def test_ask_route_reports_inactive_runtime_and_missing_registry(runtime) -> None:
    body = b'{"token":"t","question":"q"}'
    status, parsed, _ = await api_request(_ask_app(runtime), "/ask", body=body)
    assert (status, parsed["error"], parsed["code"]) == (503, "Refract runtime is not active", "runtime_unavailable")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "headers", "path", "expected_job_id"),
    [
        pytest.param(b'{"token":"t","question":" q ","job_id":"from-body"}', (("X-Refract-Job-Id", "from-header"),), "/ask?job_id=from-query", "from-body", id="body-job-id"),
        pytest.param(b'{"token":"t","question":" q "}', (("X-Refract-Job-Id", "from-header"),), "/ask?job_id=from-query", "from-header", id="header-job-id"),
        pytest.param(b'{"token":"t","question":" q "}', (), "/ask?job_id=from-query", "from-query", id="query-job-id"),
        pytest.param(b'{"token":"t","question":" q "}', (), "/ask", None, id="no-job-id"),
    ],
)
async def test_ask_route_job_id_sources_and_default_timeout(body, headers, path, expected_job_id) -> None:
    registry = _AskRegistry()
    status, parsed, _ = await api_request(_ask_app(SimpleNamespace(ask_registry=registry, config=SimpleNamespace())), path, body=body, headers=headers)
    assert (status, parsed) == (200, {"answer": "the answer"})
    assert registry.calls == [{"token": "t", "question": " q ", "timeout_s": 300, "job_id": expected_job_id}]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "status", "message", "code"),
    [
        pytest.param("auth", 403, "Forbidden", "forbidden", id="auth-error"),
        pytest.param("conflict", 409, "A question is already pending for this job", "conflict", id="conflict-error"),
    ],
)
async def test_ask_route_maps_registry_errors(error, status, message, code) -> None:
    from refract.ask import AskAuthError, AskConflictError

    registry = _AskRegistry({"auth": AskAuthError("no"), "conflict": AskConflictError("busy")}[error])
    got_status, parsed, _ = await api_request(
        _ask_app(SimpleNamespace(ask_registry=registry, config=SimpleNamespace(ask_timeout_s=9))), "/ask",
        body=b'{"token":"t","question":"q"}',
    )
    assert (got_status, parsed["error"], parsed["code"]) == (status, message, code)
    assert registry.calls[0]["timeout_s"] == 9


@pytest.mark.asyncio
async def test_telemetry_status_route_returns_runtime_status_before_api_fallback() -> None:
    status = {"enabled": False, "source": "default", "endpoint": "https://example.invalid", "install_id": None,
              "queued": 0, "last_send_at": None, "last_error": None, "next_batch": None}
    runtime = SimpleNamespace(telemetry_status=lambda: status)
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime)))
    code, body, headers = await api_request(app, "/dashboard/api/telemetry", method="GET")
    assert (code, body) == (200, status)
    assert headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_telemetry_status_route_is_loopback_only() -> None:
    runtime = SimpleNamespace(telemetry_status=lambda: {"enabled": True})
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=runtime)))
    code, _body, _headers = await api_request(app, "/dashboard/api/telemetry", method="GET", client_host="203.0.113.9")
    assert code == 403
    code, _body, _headers = await api_request(
        app, "/dashboard/api/telemetry", method="GET", headers=(("Host", "evil.example:8765"),),
    )
    assert code == 403


@pytest.mark.asyncio
async def test_telemetry_status_route_without_runtime_reports_unavailable() -> None:
    app = Starlette(routes=register_dashboard_routes(DashboardState()))
    code, body, _headers = await api_request(app, "/dashboard/api/telemetry", method="GET")
    assert code == 503
    assert body["code"] == "runtime_unavailable"
