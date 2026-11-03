from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from refract.config import TargetConfig, load_config
from refract.dashboard import _jsonable, _safe_execution_plan
from refract.planning import execution_plan_data, resolve_execution_plan
from refract.runtime import Runtime
from refract.server import create_application
from tests.orchestration_helpers import config
from tests.orchestration_helpers import register_project


def _set_job_state(database, job_id: str, state: str) -> None:
    with database._connection:
        database._connection.execute("UPDATE jobs SET state=? WHERE id=?", (state, job_id))


async def request(app, path, *, method="GET", headers=(), body=b"", client_host="127.0.0.1"):
    sent = []
    request_body = body
    received = False

    async def receive():
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": request_body, "more_body": False}

    async def send(message):
        sent.append(message)

    path_only, _, query_string = path.partition("?")
    if not any(key.lower() == "host" for key, _ in headers):
        # HTTP/1.1 clients always send Host; the dashboard requires a loopback one.
        headers = (("Host", "127.0.0.1:8765"), *headers)
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path_only,
        "raw_path": path_only.encode(),
        "query_string": query_string.encode(),
        "headers": [(key.lower().encode(), value.encode()) for key, value in headers],
        "client": (client_host, 1234),
        "server": ("127.0.0.1", 8765),
        "scheme": "http",
        "root_path": "",
        "app": None,
    }
    await app(scope, receive, send)
    start = next(message for message in sent if message["type"] == "http.response.start")
    chunks = [message.get("body", b"") for message in sent if message["type"] == "http.response.body"]
    return start["status"], dict(start["headers"]), b"".join(chunks)


@pytest.fixture
def active_runtime(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir(parents=True)
    cfg_file = home / "config.toml"
    cfg_file.write_text(
        """# operator comment
[daemon]
default_profile = "balanced"
max_jobs = 2

[[targets]]
id = "primary"
backend = "codex"
profile = "legacy-profile"
model = "gpt-4"
reasoning = "deep"
system_prompt = "act safe"
isolated = false
read_only = false
args = ["--flag"]
max_concurrency = 2

[[targets]]
id = "fallback"
backend = "pi"
isolated = true

[[targets]]
id = "cc/opus-consult-reasoning"
backend = "claude"
model = "claude-opus-5"

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
other = "primary"
""",
        encoding="utf-8",
    )
    runtime = Runtime(load_config(cfg_file))
    register_project(runtime, str(tmp_path), "project")
    from refract import server
    from refract.dashboard import DashboardState
    monkeypatch.setattr(
        server, "DashboardState",
        lambda: DashboardState(runtime=runtime),
    )
    try:
        yield runtime
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_dashboard_diagnostics_filters_pages_and_derives_job_counts(active_runtime) -> None:
    database = active_runtime.database
    project = database.projects()[0]
    for job_id in ("diag-job-1", "diag-job-2"):
        database.create_job(
            job_id=job_id, project_id=project.id, workflow="other", profile="balanced",
            prompt="private prompt", execution_plan_json="{}", context_key=job_id,
        )
    first = database.record_error_report(
        job_id="diag-job-1", category="protocol", expected="expected", observed="observed", report_key="one"
    )["report"]["id"]
    second = database.record_error_report(
        job_id="diag-job-2", category="output", expected="needed", observed="missing", report_key="two"
    )["report"]["id"]

    from refract.dashboard import DashboardState, register_dashboard_routes
    from starlette.applications import Starlette
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=active_runtime)))
    status, _, body = await request(app, "/dashboard/api/diagnostics?category=protocol&limit=1")
    assert status == 200
    page = json.loads(body)
    assert [row["id"] for row in page["reports"]] == [first]
    assert page["next_before"] is None
    status, _, body = await request(app, "/dashboard/api/diagnostics?project_id=project&job_id=diag-job-2&category=output")
    assert status == 200
    report = json.loads(body)["reports"][0]
    assert report["id"] == second
    assert report["current_state"] == "queued"
    assert "report_key" not in report and "private prompt" not in body.decode()
    status, _, body = await request(app, "/dashboard/api/jobs/diag-job-2")
    assert status == 200
    job = json.loads(body)
    assert job["suspect"] is True and job["diagnostic_count"] == 1
    status, _, body = await request(app, "/dashboard/api/diagnostics?limit=0")
    assert status == 400


@pytest.mark.asyncio
async def test_diagnostics_cursor_is_exclusive_and_unknown_filters_are_explicit(active_runtime) -> None:
    database = active_runtime.database
    project = database.projects()[0]
    database.create_job(job_id="paged-job", project_id=project.id, workflow="other", profile="p", prompt="", execution_plan_json="{}", context_key="paged")
    ids = []
    for key in ("a", "b"):
        ids.append(database.record_error_report(job_id="paged-job", category="protocol", expected="e", observed="o", report_key=key)["report"]["id"])
    from refract.dashboard import DashboardState, register_dashboard_routes
    from starlette.applications import Starlette
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=active_runtime)))
    status, _, body = await request(app, "/dashboard/api/diagnostics?limit=1")
    page = json.loads(body)
    assert status == 200 and page["reports"][0]["id"] == ids[1]
    assert page["next_before"] == ids[1]
    database.record_error_report(job_id="paged-job", category="protocol", expected="e", observed="o", report_key="c")
    status, _, body = await request(app, f"/dashboard/api/diagnostics?limit=1&before={page['next_before']}")
    older = json.loads(body)
    assert status == 200 and [row["id"] for row in older["reports"]] == [ids[0]]
    assert older["next_before"] is None
    assert (await request(app, "/dashboard/api/diagnostics?project_id=missing"))[0] == 404
    assert (await request(app, "/dashboard/api/diagnostics?job_id=missing"))[0] == 404
    assert (await request(app, "/dashboard/api/diagnostics?limit=101"))[0] == 400
    assert (await request(app, "/dashboard/api/diagnostics?before=0"))[0] == 400
    assert (await request(app, "/dashboard/api/diagnostics?unexpected=x"))[0] == 400
    assert (await request(app, "/dashboard/api/diagnostics", client_host="192.0.2.1"))[0] == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("parameter", ["limit", "before"])
async def test_diagnostics_rejects_extremely_long_decimal_query_values(active_runtime, parameter) -> None:
    from refract.dashboard import DashboardState, register_dashboard_routes
    from starlette.applications import Starlette
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=active_runtime)))

    status, _, _ = await request(app, f"/dashboard/api/diagnostics?{parameter}=" + "9" * 4500)

    assert status == 400


@pytest.mark.asyncio
@pytest.mark.parametrize("parameter", ["category", "project_id", "job_id"])
async def test_diagnostics_rejects_explicitly_empty_filters(active_runtime, parameter) -> None:
    from refract.dashboard import DashboardState, register_dashboard_routes
    from starlette.applications import Starlette
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=active_runtime)))

    status, _, _ = await request(app, f"/dashboard/api/diagnostics?{parameter}=")

    assert status == 400


@pytest.mark.asyncio
async def test_diagnostics_preserves_leading_zero_numeric_values(active_runtime) -> None:
    from refract.dashboard import DashboardState, register_dashboard_routes
    from starlette.applications import Starlette
    app = Starlette(routes=register_dashboard_routes(DashboardState(runtime=active_runtime)))

    limit_status, _, limit_body = await request(app, "/dashboard/api/diagnostics?limit=0001")
    before_status, _, before_body = await request(app, "/dashboard/api/diagnostics?before=0001")

    assert limit_status == before_status == 200
    assert json.loads(limit_body) == {"reports": [], "next_before": None}
    assert json.loads(before_body) == {"reports": [], "next_before": None}


@pytest.mark.asyncio
async def test_dashboard_reads_fail_closed_without_runtime() -> None:
    app = create_application()

    status, _, body = await request(app, "/dashboard/api/overview")

    assert status == 503
    assert json.loads(body)["error"] == "Refract runtime is not active"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    ["/dashboard/api/overview", "/dashboard/api/projects", "/dashboard/api/jobs/missing/output", "/dashboard"],
)
async def test_dashboard_routes_reject_rebound_host_and_remote_client(active_runtime, path) -> None:
    app = create_application()

    rebound, _, _ = await request(app, path, headers=(("Host", "attacker.example:8765"),))
    remote, _, _ = await request(app, path, headers=(("Host", "127.0.0.1"),), client_host="192.0.2.1")
    allowed, _, _ = await request(app, path, headers=(("Host", "127.0.0.1"),))

    assert rebound == 403
    assert remote == 403
    assert allowed != 403


@pytest.mark.asyncio
async def test_dashboard_overview_separates_daemon_and_configuration(active_runtime) -> None:
    app = create_application()

    status, _, body = await request(app, "/dashboard/api/overview")

    payload = json.loads(body)
    assert status == 200
    assert set(payload) >= {"daemon", "configuration"}
    assert "status" in payload["daemon"]
    assert "valid" in payload["configuration"]


@pytest.mark.asyncio
async def test_dashboard_project_includes_resolved_configuration(active_runtime) -> None:
    app = create_application()

    status, _, body = await request(app, "/dashboard/api/projects/project")

    payload = json.loads(body)
    assert status == 200
    assert payload["configuration"]["global_default_profile"] == "balanced"
    profile = payload["configuration"]["profiles"][0]
    assert profile["effective"]["consult"]["targets"] == ["primary"]
    assert profile["sources"]["consult"] == "global"


@pytest.mark.asyncio
async def test_dashboard_project_source_attribution_shows_project_override(active_runtime, tmp_path) -> None:
    project_root = tmp_path / "project-config"
    project_root.mkdir()
    project = register_project(active_runtime, str(project_root), "project-config")
    (project_root / ".refract").mkdir()
    (project_root / ".refract" / "config.toml").write_text(
        '[profiles.balanced]\nconsult = "primary"\n', encoding="utf-8"
    )
    app = create_application()

    status, _, body = await request(
        app, f"/dashboard/api/projects/{project.id}"
    )

    payload = json.loads(body)["configuration"]
    profile = next(item for item in payload["profiles"] if item["id"] == "balanced")
    assert status == 200
    assert profile["sources"]["consult"] == "project"
    assert profile["effective"]["consult"]["targets"] == ["primary"]


@pytest.mark.asyncio
async def test_dashboard_identical_project_override_reports_project_source(active_runtime, tmp_path) -> None:
    project_root = tmp_path / "identical-project"
    project_root.mkdir()
    project = register_project(active_runtime, str(project_root), "identical-project")
    (project_root / ".refract").mkdir()
    (project_root / ".refract" / "config.toml").write_text(
        """[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
other = "primary"
""",
        encoding="utf-8",
    )
    app = create_application()

    status, _, body = await request(app, f"/dashboard/api/projects/{project.id}")

    profile = next(item for item in json.loads(body)["configuration"]["profiles"] if item["id"] == "balanced")
    assert status == 200
    assert profile["sources"]["consult"] == "project"


@pytest.mark.asyncio
async def test_dashboard_project_self_extension_reports_global_inheritance(active_runtime, tmp_path) -> None:
    project_root = tmp_path / "self-project"
    project_root.mkdir()
    project = register_project(active_runtime, str(project_root), "self-project")
    (project_root / ".refract").mkdir()
    (project_root / ".refract" / "config.toml").write_text(
        '[profiles.balanced]\nextends = "balanced"\nconsult = "primary"\n',
        encoding="utf-8",
    )
    app = create_application()

    status, _, body = await request(app, f"/dashboard/api/projects/{project.id}")

    profile = next(item for item in json.loads(body)["configuration"]["profiles"] if item["id"] == "balanced")
    assert status == 200
    assert profile["parent"] == {"value": "balanced", "source": "project"}
    assert set(profile["inherited"]) == {"implement", "review", "other"}
    assert profile["inherited"]["implement"]["targets"] == ["primary"]
    assert profile["sources"]["implement"] == "global"
    assert profile["sources"]["consult"] == "project"


@pytest.mark.asyncio
async def test_dashboard_job_detail_redacts_execution_plan(active_runtime) -> None:
    runtime = active_runtime
    project = runtime.database.project("project")
    plan = resolve_execution_plan("consult", runtime.catalog, "balanced")
    runtime.database.create_job(
        job_id="job",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="secret job prompt",
        execution_plan_json=json.dumps(execution_plan_data(plan)),
        context_key="consult",
    )
    app = create_application()

    status, _, body = await request(app, "/dashboard/api/jobs/job")

    payload = json.loads(body)
    assert status == 200
    assert payload["prompt"] == "secret job prompt"
    assert "execution_plan" in payload
    serialized = json.dumps(payload)
    assert "system_prompt" not in serialized
    assert "raw_prompt" not in serialized
    assert "backend_profile" not in serialized
    assert '"args"' not in serialized
    assert payload["execution_plan"]["selection"]["targets"] == ["primary"]


@pytest.mark.asyncio
async def test_dashboard_job_detail_omits_marked_environment_metadata(active_runtime) -> None:
    from refract.dashboard import _safe_execution_plan

    plan = resolve_execution_plan("consult", active_runtime.catalog, "balanced")
    snapshot = execution_plan_data(plan)
    snapshot["environment_targets"] = ["primary"]
    snapshot["targets"][0]["envs_vars"] = ["synthetic-template-marker"]
    snapshot["targets"][0]["envs"] = {"SECRET": "synthetic-secret-marker"}
    snapshot["targets"][0]["context_window"] = 200000
    safe_plan = _safe_execution_plan(snapshot)
    assert safe_plan["targets"][0]["contextWindow"] == 200000
    safe = json.dumps(safe_plan)
    assert "environment_targets" not in safe
    assert "envs_vars" not in safe
    assert "envs" not in safe
    assert "synthetic-template-marker" not in safe
    assert "synthetic-secret-marker" not in safe


@pytest.mark.asyncio
async def test_environment_markers_stay_private_across_dashboard_http_surfaces(active_runtime) -> None:
    runtime = active_runtime
    source = runtime.catalog.config_path
    text = source.read_text(encoding="utf-8").replace(
        'args = ["--flag"]\nmax_concurrency = 2',
        'args = ["--flag"]\nmax_concurrency = 2\nenvs_vars = ["shared"]\n\n[targets.envs]\nLOCAL_MARKER = "global-local-secret-marker" # local comment',
    )
    text += '''\n[envs.shared]
GLOBAL_MARKER = "global-secret-marker"
GLOBAL_TEMPLATE = "${GLOBAL_MARKER}/template-marker"
'''
    source.write_text(text, encoding="utf-8")
    runtime.publish_configuration()

    project = runtime.database.project("project")
    project_path = Path(project.root) / ".refract" / "config.toml"
    project_path.parent.mkdir(parents=True, exist_ok=True)
    project_path.write_text('''[envs.shared]
PROJECT_MARKER = "project-secret-marker"
PROJECT_TEMPLATE = "${PROJECT_MARKER}/template-marker"

[[targets]]
id = "primary"
envs_vars = ["shared", "project_only"]

[targets.envs]
PROJECT_LOCAL = "project-local-secret-marker"

[envs.project_only]
ONLY_MARKER = "project-only-secret-marker"

[profiles.balanced]
consult = "primary"
''', encoding="utf-8")

    app = create_application()
    responses: list[bytes] = []
    for endpoint in (
        "/dashboard/api/overview",
        "/dashboard/api/settings",
        "/dashboard/api/targets",
        "/dashboard/api/profiles",
        f"/dashboard/api/projects/{project.id}",
    ):
        status, _, body = await request(app, endpoint)
        assert status == 200, (endpoint, body)
        responses.append(body)

    plan = execution_plan_data(resolve_execution_plan("consult", runtime.catalog, "balanced"))
    for job_id, marked in (("environment-legacy", False), ("environment-marked", True)):
        snapshot = dict(plan)
        if marked:
            snapshot["environment_targets"] = ["primary"]
            snapshot["targets"] = [dict(target) for target in snapshot["targets"]]
            snapshot["targets"][0].update(
                envs_vars=["global-secret-marker-template"],
                envs={"SECRET": "global-secret-marker"},
            )
        runtime.database.create_job(
            job_id=job_id, project_id=project.id, workflow="consult", profile="balanced",
            prompt="dashboard synthetic job", execution_plan_json=json.dumps(snapshot),
            context_key=job_id,
        )
        status, _, body = await request(app, f"/dashboard/api/jobs/{job_id}")
        assert status == 200
        responses.append(body)

    for marker in (
        "global-secret-marker", "${GLOBAL_MARKER}/template-marker", "global-local-secret-marker",
        "project-secret-marker", "${PROJECT_MARKER}/template-marker",
        "project-local-secret-marker", "project-only-secret-marker", "global-secret-marker-template",
    ):
        assert marker.encode() not in b"\n".join(responses), marker
    assert "global-secret-marker" in source.read_text(encoding="utf-8")
    assert "project-secret-marker" in project_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_dashboard_job_detail_preserves_prompt_whitespace_and_multiline(active_runtime) -> None:
    runtime = active_runtime
    project = runtime.database.project("project")
    plan = resolve_execution_plan("consult", runtime.catalog, "balanced")
    multiline_prompt = "Line 1\n  Line 2 with indentation\n\nLine 3"
    runtime.database.create_job(
        job_id="job-multiline",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt=multiline_prompt,
        execution_plan_json=json.dumps(execution_plan_data(plan)),
        context_key="consult",
    )
    app = create_application()

    status, _, body = await request(app, "/dashboard/api/jobs/job-multiline")

    payload = json.loads(body)
    assert status == 200
    assert payload["prompt"] == multiline_prompt
    serialized = json.dumps(payload)
    assert "system_prompt" not in serialized
    assert "raw_prompt" not in serialized


@pytest.mark.asyncio
async def test_dashboard_job_detail_empty_prompt(active_runtime) -> None:
    runtime = active_runtime
    project = runtime.database.project("project")
    plan = resolve_execution_plan("consult", runtime.catalog, "balanced")
    runtime.database.create_job(
        job_id="job-empty",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="",
        execution_plan_json=json.dumps(execution_plan_data(plan)),
        context_key="consult",
    )
    app = create_application()

    status, _, body = await request(app, "/dashboard/api/jobs/job-empty")

    payload = json.loads(body)
    assert status == 200
    assert payload["prompt"] == ""


def make_static(root: Path) -> None:
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<!doctype html><title>Refract</title>", encoding="utf-8")
    (root / "assets" / "app.js").write_text("console.log('ok')", encoding="utf-8")


@pytest.mark.asyncio
async def test_spa_routes_and_api_guard_are_ordered(monkeypatch, tmp_path) -> None:
    from refract import dashboard

    make_static(tmp_path)
    monkeypatch.setattr(dashboard, "_STATIC_DIR", tmp_path)
    app = create_application()

    index, headers, body = await request(app, "/dashboard")
    deep, _, deep_body = await request(app, "/dashboard/projects/project-1")
    typo, typo_headers, typo_body = await request(app, "/dashboard/api/not-a-route")
    missing_asset, _, _ = await request(app, "/dashboard/assets/missing.js")
    missing_namespace, _, namespace_body = await request(app, "/dashboard/assets")

    assert index == deep == 200
    assert body == deep_body
    assert headers[b"cache-control"] == b"no-store"
    assert typo == 404
    assert typo_headers[b"content-type"].startswith(b"application/json")
    assert b"<!doctype html>" not in typo_body
    assert missing_asset == missing_namespace == 404
    assert b"<!doctype html>" not in namespace_body


@pytest.mark.asyncio
async def test_missing_frontend_build_does_not_break_application(monkeypatch, tmp_path) -> None:
    from refract import dashboard

    monkeypatch.setattr(dashboard, "_STATIC_DIR", tmp_path / "missing-dashboard")
    app = create_application()

    status, _, body = await request(app, "/dashboard/")
    asset_status, _, _ = await request(app, "/dashboard/assets/app.js")

    assert status == 503
    assert b"Dashboard assets are unavailable" in body
    assert asset_status == 404


def test_builtin_workflows_contract() -> None:
    from refract.workflows import BUILTIN_WORKFLOWS

    assert BUILTIN_WORKFLOWS == ("consult", "implement", "other", "review")


def test_readme_documents_dashboard_boundaries() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "/dashboard/" in readme
    assert "loopback" in readme.lower()
    assert "read-only" in readme.lower()
    assert "remote administration" in readme.lower()


# ---------------------------------------------------------------------------
# Phase 2: Target configuration CRUD API tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_target_views_report_all_breaker_states(active_runtime) -> None:
    from dataclasses import replace
    from datetime import datetime, timedelta, timezone

    from refract.planning import target_execution_key

    base = active_runtime.catalog.targets[0]
    targets = tuple(replace(base, id=name) for name in ("closed", "open", "half_open", "probing"))
    now = datetime.now(timezone.utc)
    health = {
        "closed": {"circuit_open_until": "", "cooldown_s": 0, "probe_job_id": ""},
        "open": {
            "circuit_open_until": (now + timedelta(seconds=60)).isoformat(),
            "cooldown_s": 60,
            "probe_job_id": "",
        },
        "half_open": {
            "circuit_open_until": (now - timedelta(seconds=1)).isoformat(),
            "cooldown_s": 120,
            "probe_job_id": "",
        },
        "probing": {
            "circuit_open_until": (now - timedelta(seconds=1)).isoformat(),
            "cooldown_s": 240,
            "probe_job_id": "job-probe",
        },
    }
    for target in targets:
        row = health[target.id]
        key = target_execution_key(target)
        active_runtime.database._connection.execute(
            "INSERT OR REPLACE INTO target_health (target_id, consecutive_failures, circuit_open_until, cooldown_s, probe_job_id) VALUES (?, 1, ?, ?, ?)",
            (key, row["circuit_open_until"], row["cooldown_s"], row["probe_job_id"]),
        )

    views = active_runtime.target_executor.views(targets)

    closed_view, open_view, half_open_view, probing_view = views

    assert closed_view.breaker_state == "closed"
    assert closed_view.probing is False
    assert closed_view.cooldown_s == 0

    assert open_view.breaker_state == "open"
    assert open_view.probing is False
    assert open_view.cooldown_s == 60

    assert half_open_view.breaker_state == "half_open"
    assert half_open_view.probing is False
    assert half_open_view.cooldown_s == 120

    assert probing_view.breaker_state == "half_open"
    assert probing_view.probing is True
    assert probing_view.cooldown_s == 240


@pytest.mark.asyncio
async def test_runtime_targets_endpoint_remains_unchanged(active_runtime) -> None:
    app = create_application()
    status, headers, body = await request(app, "/dashboard/api/targets")
    assert status == 200
    payload = json.loads(body)
    assert isinstance(payload, list)
    assert len(payload) >= 1
    for target in payload:
        assert set(target.keys()) <= {
            "id", "model", "backend", "isolated", "read_only",
            "max_concurrency", "active", "healthy", "circuit_open_until",
            "breaker_state", "cooldown_s", "probing",
        }
        assert "system_prompt" not in target
        assert "args" not in target


@pytest.mark.asyncio
async def test_job_output_unknown_job_returns_404(active_runtime) -> None:
    app = create_application()
    status, _, body = await request(app, "/dashboard/api/jobs/missing-job/output")
    assert status == 404
    payload = json.loads(body)
    assert payload["error"] == "Unknown job"
    assert payload["code"] == "not_found"


@pytest.mark.asyncio
async def test_job_output_cursor_pagination_and_bounded_limits(active_runtime) -> None:
    runtime = active_runtime
    project = runtime.database.project("project")
    plan = resolve_execution_plan("consult", runtime.catalog, "balanced")
    runtime.database.create_job(
        job_id="job-stream-page",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="prompt",
        execution_plan_json=json.dumps(execution_plan_data(plan)),
        context_key="consult",
    )
    events_data = [
        {"kind": "assistant.text_delta", "data": {"text": f"part {i}"}}
        for i in range(1, 6)
    ]
    persisted = runtime.database.append_stream_events("job-stream-page", events_data)
    first_id = persisted[0].id
    second_id = persisted[1].id
    third_id = persisted[2].id
    fourth_id = persisted[3].id
    fifth_id = persisted[4].id

    app = create_application()

    # Page 1
    status, _, body = await request(app, "/dashboard/api/jobs/job-stream-page/output?after=0&limit=2")
    assert status == 200
    p1 = json.loads(body)
    assert len(p1["events"]) == 2
    assert [e["id"] for e in p1["events"]] == [first_id, second_id]
    assert p1["cursor"] == second_id
    assert p1["has_more"] is True
    assert p1["retained_from"] == first_id
    assert p1["stream_status"] == "active"

    # Page 2
    status, _, body = await request(app, f"/dashboard/api/jobs/job-stream-page/output?after={second_id}&limit=2")
    assert status == 200
    p2 = json.loads(body)
    assert len(p2["events"]) == 2
    assert [e["id"] for e in p2["events"]] == [third_id, fourth_id]
    assert p2["cursor"] == fourth_id
    assert p2["has_more"] is True

    # Page 3
    status, _, body = await request(app, f"/dashboard/api/jobs/job-stream-page/output?after={fourth_id}&limit=2")
    assert status == 200
    p3 = json.loads(body)
    assert len(p3["events"]) == 1
    assert [e["id"] for e in p3["events"]] == [fifth_id]
    assert p3["cursor"] == fifth_id
    assert p3["has_more"] is False

    # Page 4 (empty)
    status, _, body = await request(app, f"/dashboard/api/jobs/job-stream-page/output?after={fifth_id}&limit=2")
    assert status == 200
    p4 = json.loads(body)
    assert len(p4["events"]) == 0
    assert p4["cursor"] == fifth_id
    assert p4["has_more"] is False

    # Clamp limit to min 1
    status, _, body = await request(app, "/dashboard/api/jobs/job-stream-page/output?after=0&limit=0")
    assert status == 200
    assert len(json.loads(body)["events"]) == 1

    # Clamp limit to max 500
    status, _, body = await request(app, "/dashboard/api/jobs/job-stream-page/output?after=0&limit=999")
    assert status == 200
    assert len(json.loads(body)["events"]) == 5

    # Clamp after to min 0
    status, _, body = await request(app, "/dashboard/api/jobs/job-stream-page/output?after=-10&limit=2")
    assert status == 200
    assert len(json.loads(body)["events"]) == 2


@pytest.mark.asyncio
async def test_job_output_all_stream_statuses(active_runtime) -> None:
    runtime = active_runtime
    project = runtime.database.project("project")
    plan = resolve_execution_plan("consult", runtime.catalog, "balanced")
    app = create_application()

    # 1. unavailable: terminal job with no stream events
    runtime.database.create_job(
        job_id="job-unavailable",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="prompt",
        execution_plan_json=json.dumps(execution_plan_data(plan)),
        context_key="consult",
    )
    _set_job_state(runtime.database, "job-unavailable", "succeeded")
    status, _, body = await request(app, "/dashboard/api/jobs/job-unavailable/output")
    assert status == 200
    assert json.loads(body)["stream_status"] == "unavailable"

    # 2. active: non-terminal job with events
    runtime.database.create_job(
        job_id="job-active",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="prompt",
        execution_plan_json=json.dumps(execution_plan_data(plan)),
        context_key="consult",
    )
    runtime.database.append_stream_events("job-active", [{"kind": "assistant.text_delta", "data": {"text": "hi"}}])
    status, _, body = await request(app, "/dashboard/api/jobs/job-active/output")
    assert status == 200
    assert json.loads(body)["stream_status"] == "active"

    # 3. complete: terminal job with retained events and neither truncation nor failure
    runtime.database.create_job(
        job_id="job-complete",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="prompt",
        execution_plan_json=json.dumps(execution_plan_data(plan)),
        context_key="consult",
    )
    runtime.database.append_stream_events("job-complete", [{"kind": "assistant.text_delta", "data": {"text": "done"}}])
    _set_job_state(runtime.database, "job-complete", "succeeded")
    status, _, body = await request(app, "/dashboard/api/jobs/job-complete/output")
    assert status == 200
    assert json.loads(body)["stream_status"] == "complete"

    # 4. truncated: job with stream.truncated event
    runtime.database.create_job(
        job_id="job-truncated",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="prompt",
        execution_plan_json=json.dumps(execution_plan_data(plan)),
        context_key="consult",
    )
    runtime.database.append_stream_events(
        "job-truncated",
        [
            {"kind": "assistant.text_delta", "data": {"text": "mid"}},
            {"kind": "stream.truncated", "data": {"reason": "max_job_bytes"}},
        ],
    )
    _set_job_state(runtime.database, "job-truncated", "succeeded")
    status, _, body = await request(app, "/dashboard/api/jobs/job-truncated/output")
    assert status == 200
    assert json.loads(body)["stream_status"] == "truncated"

    # 5. failed: job with stream.persistence_failed event
    runtime.database.create_job(
        job_id="job-failed",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="prompt",
        execution_plan_json=json.dumps(execution_plan_data(plan)),
        context_key="consult",
    )
    runtime.database.append_stream_events("job-failed", [{"kind": "assistant.text_delta", "data": {"text": "init"}}])
    runtime.database.event("job-failed", "stream.persistence_failed", {"error": "disk full"})
    _set_job_state(runtime.database, "job-failed", "failed")
    status, _, body = await request(app, "/dashboard/api/jobs/job-failed/output")
    assert status == 200
    assert json.loads(body)["stream_status"] == "failed"


@pytest.mark.asyncio
async def test_job_output_payload_redaction(active_runtime) -> None:
    runtime = active_runtime
    project = runtime.database.project("project")
    plan = resolve_execution_plan("consult", runtime.catalog, "balanced")
    runtime.database.create_job(
        job_id="job-redact",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="super-secret-user-prompt",
        execution_plan_json=json.dumps(execution_plan_data(plan)),
        context_key="consult",
    )
    runtime.database.append_stream_events(
        "job-redact",
        [
            {
                "kind": "assistant.text_delta",
                "entity_id": "msg-1",
                "data": {"text": "safe public text"},
            }
        ],
    )
    app = create_application()
    status, _, body = await request(app, "/dashboard/api/jobs/job-redact/output")
    assert status == 200
    payload = json.loads(body)
    assert "super-secret-user-prompt" not in body.decode("utf-8")
    assert len(payload["events"]) == 1
    event = payload["events"][0]
    # Allowed normalized fields only
    allowed_keys = {
        "id", "version", "job_id", "created_at", "attempt", "target_id",
        "backend", "kind", "entity_id", "parent_entity_id", "data",
    }
    assert set(event.keys()) <= allowed_keys
    assert event["data"] == {"text": "safe public text"}


async def open_sse_client(app, path: str):
    import asyncio
    queue = asyncio.Queue()
    disconnected = asyncio.Event()

    async def receive():
        await disconnected.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            await queue.put(("start", message["status"], dict(message.get("headers", []))))
        elif message["type"] == "http.response.body":
            body = message.get("body", b"")
            if body:
                await queue.put(("body", body))

    path_only, _, query_string = path.partition("?")
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": path_only,
        "raw_path": path_only.encode(),
        "query_string": query_string.encode(),
        "headers": [(b"host", b"127.0.0.1")],
        "client": ("127.0.0.1", 1234),
        "server": ("127.0.0.1", 8765),
        "scheme": "http",
        "root_path": "",
        "app": None,
    }
    task = asyncio.create_task(app(scope, receive, send))

    class SSEHandle:
        async def read_start(self):
            tag, status, headers = await asyncio.wait_for(queue.get(), timeout=2.0)
            assert tag == "start"
            return status, headers

        async def read_chunk(self, timeout=2.0):
            tag, data = await asyncio.wait_for(queue.get(), timeout=timeout)
            assert tag == "body"
            return data

        async def close(self):
            disconnected.set()
            try:
                await asyncio.wait_for(task, timeout=2.0)
            except (asyncio.CancelledError, Exception):
                pass

    return SSEHandle()


@pytest.mark.asyncio
async def test_sse_unknown_job_returns_404(active_runtime) -> None:
    app = create_application()
    status, _, body = await request(app, "/dashboard/api/jobs/missing-job/output/updates")
    assert status == 404
    payload = json.loads(body)
    assert payload["error"] == "Unknown job"
    assert payload["code"] == "not_found"


@pytest.mark.asyncio
async def test_sse_initial_high_water_and_committed_delivery(active_runtime) -> None:
    runtime = active_runtime
    project = runtime.database.project("project")
    plan = resolve_execution_plan("consult", runtime.catalog, "balanced")
    runtime.database.create_job(
        job_id="job-sse-stream",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="prompt",
        execution_plan_json=json.dumps(execution_plan_data(plan)),
        context_key="consult",
    )
    persisted = runtime.database.append_stream_events(
        "job-sse-stream",
        [
            {"kind": "assistant.text_delta", "data": {"text": "one"}},
            {"kind": "assistant.text_delta", "data": {"text": "two"}},
        ],
    )
    hw2 = persisted[1].id
    app = create_application()

    sse = await open_sse_client(app, "/dashboard/api/jobs/job-sse-stream/output/updates")
    try:
        status, headers = await sse.read_start()
        assert status == 200
        # Read initial high-water event
        chunk1 = await sse.read_chunk()
        text1 = chunk1.decode("utf-8")
        assert "event: output-updated" in text1
        assert f"id: {hw2}" in text1
        assert json.loads(text1.split("data: ")[1].strip()) == {"cursor": hw2}

        # Durable commit publishes new cursor
        p3 = runtime.database.append_stream_events(
            "job-sse-stream",
            [{"kind": "assistant.text_delta", "data": {"text": "three"}}],
        )
        hw3 = p3[0].id
        runtime.stream_hub.publish("job-sse-stream", hw3)

        chunk2 = await sse.read_chunk()
        text2 = chunk2.decode("utf-8")
        assert "event: output-updated" in text2
        assert f"id: {hw3}" in text2
        assert json.loads(text2.split("data: ")[1].strip()) == {"cursor": hw3}
    finally:
        await sse.close()


@pytest.mark.asyncio
async def test_sse_capacity_one_coalescing(active_runtime) -> None:
    runtime = active_runtime
    project = runtime.database.project("project")
    plan = resolve_execution_plan("consult", runtime.catalog, "balanced")
    runtime.database.create_job(
        job_id="job-sse-coalesce",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="prompt",
        execution_plan_json=json.dumps(execution_plan_data(plan)),
        context_key="consult",
    )
    app = create_application()
    sse = await open_sse_client(app, "/dashboard/api/jobs/job-sse-coalesce/output/updates")
    try:
        await sse.read_start()
        # initial event (cursor 0)
        initial_chunk = await sse.read_chunk()
        assert "id: 0" in initial_chunk.decode("utf-8")

        # Rapid commits before reading
        p1 = runtime.database.append_stream_events("job-sse-coalesce", [{"kind": "assistant.text_delta", "data": {"text": "1"}}])
        p2 = runtime.database.append_stream_events("job-sse-coalesce", [{"kind": "assistant.text_delta", "data": {"text": "2"}}])
        p3 = runtime.database.append_stream_events("job-sse-coalesce", [{"kind": "assistant.text_delta", "data": {"text": "3"}}])
        final_hw = p3[0].id
        runtime.stream_hub.publish("job-sse-coalesce", final_hw)

        # Coalesced notification delivers latest high-water cursor
        chunk = await sse.read_chunk()
        text = chunk.decode("utf-8")
        assert f"id: {final_hw}" in text
        assert json.loads(text.split("data: ")[1].strip()) == {"cursor": final_hw}
    finally:
        await sse.close()


@pytest.mark.asyncio
async def test_sse_disconnect_cleans_up_subscription(active_runtime) -> None:
    runtime = active_runtime
    project = runtime.database.project("project")
    plan = resolve_execution_plan("consult", runtime.catalog, "balanced")
    runtime.database.create_job(
        job_id="job-sse-cleanup",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="prompt",
        execution_plan_json=json.dumps(execution_plan_data(plan)),
        context_key="consult",
    )
    app = create_application()
    sse = await open_sse_client(app, "/dashboard/api/jobs/job-sse-cleanup/output/updates")
    await sse.read_start()
    await sse.read_chunk()
    assert "job-sse-cleanup" in runtime.stream_hub._subscribers
    await sse.close()
    assert "job-sse-cleanup" not in runtime.stream_hub._subscribers


@pytest.mark.asyncio
async def test_sse_keepalive_emission(active_runtime, monkeypatch) -> None:
    import refract.dashboard as d_mod
    monkeypatch.setattr(d_mod, "SSE_KEEPALIVE_INTERVAL_S", 0.05)
    runtime = active_runtime
    project = runtime.database.project("project")
    plan = resolve_execution_plan("consult", runtime.catalog, "balanced")
    runtime.database.create_job(
        job_id="job-sse-keepalive",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="prompt",
        execution_plan_json=json.dumps(execution_plan_data(plan)),
        context_key="consult",
    )
    app = create_application()
    sse = await open_sse_client(app, "/dashboard/api/jobs/job-sse-keepalive/output/updates")
    try:
        await sse.read_start()
        await sse.read_chunk()  # Initial cursor
        chunk = await sse.read_chunk(timeout=1.0)
        assert chunk == b": keepalive\n\n"
    finally:
        await sse.close()


@pytest.mark.asyncio
async def test_project_jobs_are_grouped_bounded_and_keep_all_active(active_runtime, tmp_path) -> None:
    runtime = active_runtime
    project = runtime.database.project("project")
    for index in range(13):
        job_id = f"active-{index}"
        runtime.database.create_job(
            job_id=job_id, project_id=project.id, workflow="review", profile="balanced",
            prompt=job_id, execution_plan_json="{}", context_key=job_id,
        )
    for index in range(15):
        job_id = f"terminal-{index}"
        runtime.database.create_job(
            job_id=job_id, project_id=project.id, workflow="review", profile="balanced",
            prompt=job_id, execution_plan_json="{}", context_key=job_id,
        )
        runtime.database.finish_job(job_id, "succeeded")

    app = create_application()
    status, _, body = await request(app, f"/dashboard/api/projects/{project.id}/jobs")
    payload = json.loads(body)
    terminal = [job for job in runtime.database.jobs(project.id) if job.state in {"succeeded", "failed", "cancelled", "interrupted"}]
    expected_recent = [job.id for job in sorted(terminal, key=lambda job: (job.updated_at, job.id), reverse=True)][:10]
    assert status == 200
    assert set(payload) == {"active", "recent", "more_recent"}
    assert len(payload["active"]) == 13
    assert {job["id"] for job in payload["active"]} == {f"active-{i}" for i in range(13)}
    assert [job["id"] for job in payload["recent"]] == expected_recent
    assert payload["more_recent"] == 5 and type(payload["more_recent"]) is int

    empty_root = tmp_path / "empty-jobs-project"
    empty_root.mkdir()
    empty_project = register_project(runtime, str(empty_root), "empty-jobs")
    status, _, body = await request(app, f"/dashboard/api/projects/{empty_project.id}/jobs")
    assert status == 200
    assert json.loads(body) == {"active": [], "recent": [], "more_recent": 0}


@pytest.mark.asyncio


@pytest.mark.asyncio


@pytest.mark.asyncio


async def test_rest_to_subscription_race_resolved_by_initial_cursor(active_runtime) -> None:
    runtime = active_runtime
    project = runtime.database.project("project")
    plan = resolve_execution_plan("consult", runtime.catalog, "balanced")
    runtime.database.create_job(
        job_id="job-race",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="prompt",
        execution_plan_json=json.dumps(execution_plan_data(plan)),
        context_key="consult",
    )
    p1 = runtime.database.append_stream_events("job-race", [{"kind": "assistant.text_delta", "data": {"text": "1"}}])
    app = create_application()

    # 1. REST replay initially gets cursor p1[0].id
    _, _, body1 = await request(app, "/dashboard/api/jobs/job-race/output?after=0")
    rest_data = json.loads(body1)
    seen_cursor = rest_data["cursor"]
    assert seen_cursor == p1[0].id

    # 2. Race: second event commits BEFORE SSE connects
    p2 = runtime.database.append_stream_events("job-race", [{"kind": "assistant.text_delta", "data": {"text": "2"}}])
    hw2 = p2[0].id

    # 3. SSE connects and immediately emits current high-water (hw2)
    sse = await open_sse_client(app, "/dashboard/api/jobs/job-race/output/updates")
    try:
        await sse.read_start()
        chunk = await sse.read_chunk()
        text = chunk.decode("utf-8")
        assert f"id: {hw2}" in text
        sse_cursor = json.loads(text.split("data: ")[1].strip())["cursor"]
        assert sse_cursor == hw2

        # 4. Client observes sse_cursor > seen_cursor, fetches REST delta
        assert sse_cursor > seen_cursor
        _, _, body2 = await request(app, f"/dashboard/api/jobs/job-race/output?after={seen_cursor}")
        delta_data = json.loads(body2)
        assert len(delta_data["events"]) == 1
        assert delta_data["events"][0]["id"] == hw2
    finally:
        await sse.close()


@pytest.mark.asyncio
async def test_job_output_sse_catch_up_after_reconnect(active_runtime) -> None:
    runtime = active_runtime
    project = runtime.database.project("project")
    plan = resolve_execution_plan("consult", runtime.catalog, "balanced")
    job_id = "job-catchup"
    runtime.database.create_job(
        job_id=job_id,
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="prompt",
        execution_plan_json=json.dumps(execution_plan_data(plan)),
        context_key="consult",
    )
    p1 = runtime.database.append_stream_events(job_id, [{"kind": "assistant.text.delta", "data": {"text": "part 1"}}])
    c1 = p1[0].id
    app = create_application()

    # Client connects to SSE and reads cursor c1
    sse1 = await open_sse_client(app, f"/dashboard/api/jobs/{job_id}/output/updates")
    await sse1.read_start()
    chunk1 = await sse1.read_chunk()
    assert f"id: {c1}" in chunk1.decode("utf-8")

    # Client disconnects
    await sse1.close()

    # While disconnected, events 2 and 3 commit
    p2 = runtime.database.append_stream_events(job_id, [
        {"kind": "assistant.text.delta", "data": {"text": "part 2"}},
        {"kind": "assistant.text.delta", "data": {"text": "part 3"}},
    ])
    c2 = p2[0].id
    c3 = p2[1].id

    # Client reconnects to SSE, immediately receiving current high-water cursor c3
    sse2 = await open_sse_client(app, f"/dashboard/api/jobs/{job_id}/output/updates")
    try:
        await sse2.read_start()
        chunk2 = await sse2.read_chunk()
        text2 = chunk2.decode("utf-8")
        assert f"id: {c3}" in text2
        reconnected_cursor = json.loads(text2.split("data: ")[1].strip())["cursor"]
        assert reconnected_cursor == c3

        # Client catches up via REST replay for events after c1
        status, _, body = await request(app, f"/dashboard/api/jobs/{job_id}/output?after={c1}")
        assert status == 200
        replay_payload = json.loads(body)
        assert replay_payload["cursor"] == c3
        assert replay_payload["has_more"] is False
        assert [e["id"] for e in replay_payload["events"]] == [c2, c3]
        assert [e["data"]["text"] for e in replay_payload["events"]] == ["part 2", "part 3"]
    finally:
        await sse2.close()


@pytest.mark.asyncio
async def test_job_output_historical_fallback_preserves_authoritative_result(active_runtime) -> None:
    runtime = active_runtime
    project = runtime.database.project("project")
    plan = resolve_execution_plan("consult", runtime.catalog, "balanced")
    job_id = "job-historical-fallback"
    runtime.database.create_job(
        job_id=job_id,
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="consultation question",
        execution_plan_json=json.dumps(execution_plan_data(plan)),
        context_key="consult",
    )
    runtime.database.finish_job(
        job_id=job_id,
        state="succeeded",
        text="authoritative historical consultation answer",
    )
    app = create_application()

    # REST output reports unavailable stream status and zero cursor
    status, _, body = await request(app, f"/dashboard/api/jobs/{job_id}/output")
    assert status == 200
    output_data = json.loads(body)
    assert output_data["stream_status"] == "unavailable"
    assert output_data["events"] == []
    assert output_data["cursor"] == 0
    assert output_data["has_more"] is False

    # Job endpoint preserves authoritative output text
    status_job, _, body_job = await request(app, f"/dashboard/api/jobs/{job_id}")
    assert status_job == 200
    job_data = json.loads(body_job)
    assert job_data["result"]["text"] == "authoritative historical consultation answer"


@pytest.mark.asyncio
async def test_security_regressions_forbidden_provider_content_not_in_dashboard_or_db(
    active_runtime, monkeypatch, tmp_path
) -> None:
    from refract.backends import BackendParams
    from refract.backends.claude import execute as claude_sync
    from refract.backends.codex import execute as codex_sync
    from refract.backends.pi import execute as pi_sync
    from refract.backends.agy import execute as agy_execute_once

    runtime = active_runtime
    project = runtime.database.project("project")
    plan = resolve_execution_plan("consult", runtime.catalog, "balanced")

    forbidden_tokens = [
        "PROMPT_SECRET_NEVER_LEAK_P99",
        "REASONING_THINKING_NEVER_LEAK_R88",
        "TOOL_ARGUMENT_PATH_NEVER_LEAK_A77",
        "TOOL_RESULT_BODY_NEVER_LEAK_O66",
        "BASH_COMMAND_LINE_NEVER_LEAK_C55",
        "STDERR_DIAGNOSTIC_TRACE_NEVER_LEAK_D44",
        "API_KEY_CREDENTIAL_NEVER_LEAK_K33",
        "SUBAGENT_TRANSCRIPT_NEVER_LEAK_S22",
    ]

    dirty_claude_stream = [
        json.dumps({"type": "system", "content": f"system prompt {forbidden_tokens[0]}"}),
        json.dumps({
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "delta": {"type": "thinking_delta", "thinking": forbidden_tokens[1]},
                "index": 0,
            },
        }),
        json.dumps({
            "type": "stream_event",
            "event": {
                "type": "content_block_start",
                "content_block": {
                    "type": "tool_use",
                    "id": "toolu_sec",
                    "name": "Read",
                    "input": {"path": forbidden_tokens[2], "cmd": forbidden_tokens[4]},
                },
            },
        }),
        json.dumps({
            "type": "stream_event",
            "event": {"type": "content_block_stop", "index": 1},
        }),
        json.dumps({
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": "Safe public response."},
                "index": 2,
            },
        }),
        json.dumps({
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "Safe public response.",
            "session_id": "claude-sec-sess",
        }),
    ]

    dirty_codex_stream = [
        json.dumps({"type": "thread.started", "thread_id": forbidden_tokens[0]}),
        json.dumps({
            "type": "item.started",
            "item": {
                "type": "tool_call",
                "id": "codex_tool_1",
                "name": "bash",
                "input": f"cat {forbidden_tokens[2]} {forbidden_tokens[4]}",
            },
        }),
        json.dumps({
            "type": "item.completed",
            "item": {
                "type": "tool_call",
                "id": "codex_tool_1",
                "name": "bash",
                "output": f"root:{forbidden_tokens[3]}",
                "status": "completed",
            },
        }),
        json.dumps({
            "type": "item.completed",
            "item": {"type": "reasoning", "text": forbidden_tokens[1]},
        }),
        json.dumps({
            "type": "item.completed",
            "item": {"type": "agent_message", "id": "m1", "text": "Safe Codex response."},
        }),
    ]

    dirty_pi_stream = [
        json.dumps({"type": "session", "id": forbidden_tokens[0]}),
        json.dumps({
            "type": "message_update",
            "assistantMessageEvent": {
                "type": "thinking_delta",
                "delta": forbidden_tokens[1],
            },
        }),
        json.dumps({
            "type": "message_update",
            "assistantMessageEvent": {
                "type": "text_delta",
                "delta": "Safe Pi response.",
            },
        }),
        json.dumps({
            "type": "tool_execution_start",
            "toolCallId": "pi_tool_1",
            "toolName": "grep",
            "args": {"pattern": forbidden_tokens[2]},
        }),
        json.dumps({
            "type": "tool_execution_end",
            "toolCallId": "pi_tool_1",
            "isError": False,
            "result": forbidden_tokens[3],
        }),
        json.dumps({
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Safe Pi response."}],
            },
        }),
    ]

    dirty_agy_stream = [
        "Created conversation 12345678-1234-1234-1234-123456789abc",
        f"[diagnostic] {forbidden_tokens[5]} and trace {forbidden_tokens[6]}",
        json.dumps({
            "type": "assistant.text.delta",
            "text": "Safe Agy response.",
        }),
        json.dumps({
            "type": "tool.started",
            "tool_name": "execute_code",
            "arguments": {"script": forbidden_tokens[2], "secret": forbidden_tokens[4]},
        }),
        json.dumps({
            "type": "tool.completed",
            "status": "completed",
            "result": forbidden_tokens[3],
        }),
        json.dumps({
            "type": "result",
            "result": "Safe Agy response.",
        }),
    ]

    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/" + cmd)
    app = create_application()

    providers = [
        ("claude", "job-security-claude", "refract.backends.claude.run_shell_command", lambda e: claude_sync(BackendParams(PROMPT="p", cd=tmp_path, emitter=e)), dirty_claude_stream, "Safe public response."),
        ("codex", "job-security-codex", "refract.backends.codex.run_shell_command", lambda e: codex_sync(BackendParams(PROMPT="p", cd=tmp_path, emitter=e)), dirty_codex_stream, "Safe Codex response."),
        ("pi", "job-security-pi", "refract.backends.pi.run_shell_command", lambda e: pi_sync(BackendParams(PROMPT="p", cd=tmp_path, emitter=e)), dirty_pi_stream, "Safe Pi response."),
        ("agy", "job-security-agy", "refract.backends.agy.run_shell_command", lambda e: agy_execute_once(BackendParams(PROMPT="p", cd=tmp_path, emitter=e)), dirty_agy_stream, "Safe Agy response."),
    ]

    for name, job_id, patch_target, runner, stream_lines, safe_text in providers:
        events: list[dict[str, Any]] = []
        monkeypatch.setattr(patch_target, lambda *args, lines=stream_lines, **kwargs: (line for line in lines))
        res = runner(events.append)
        assert res.outcome == "OK"

        runtime.database.create_job(
            job_id=job_id,
            project_id=project.id,
            workflow="consult",
            profile="balanced",
            prompt=f"prompt for {name}",
            execution_plan_json=json.dumps(execution_plan_data(plan)),
            context_key="consult",
        )
        runtime.database.append_stream_events(job_id, events)
        runtime.database.finish_job(job_id, "succeeded", text=safe_text)

        # 1. Assert raw SQLite rows contain none of the non-tool forbidden tokens
        cursor = runtime.database._connection.execute(
            "SELECT id, kind, entity_id, parent_entity_id, data_json FROM job_stream_events WHERE job_id=?",
            (job_id,),
        )
        rows = cursor.fetchall()
        rows_text = " ".join(r["data_json"] for r in rows)
        private_tokens = [
            forbidden_tokens[0],
            forbidden_tokens[1],
            forbidden_tokens[5],
            forbidden_tokens[6],
            forbidden_tokens[7],
        ]
        for token in private_tokens:
            assert token not in rows_text, f"{name} SQLite row leaked {token}"

        # Approved tool payloads must persist in SQLite rows
        assert forbidden_tokens[2] in rows_text, f"{name} SQLite row missing tool input {forbidden_tokens[2]}"
        if name in {"codex", "pi", "agy"}:
            assert forbidden_tokens[3] in rows_text, f"{name} SQLite row missing tool output {forbidden_tokens[3]}"

        # 2. Assert REST /output endpoint contains none of the non-tool forbidden tokens
        status, _, body = await request(app, f"/dashboard/api/jobs/{job_id}/output")
        assert status == 200
        body_text = body.decode("utf-8")
        for token in private_tokens:
            assert token not in body_text, f"{name} REST output leaked {token}"

        # Approved tool payloads must be present in REST output
        assert forbidden_tokens[2] in body_text, f"{name} REST output missing tool input {forbidden_tokens[2]}"
        if name in {"codex", "pi", "agy"}:
            assert forbidden_tokens[3] in body_text, f"{name} REST output missing tool output {forbidden_tokens[3]}"

        # 3. Assert SSE stream contains none of the forbidden tokens (cursor notification only)
        sse = await open_sse_client(app, f"/dashboard/api/jobs/{job_id}/output/updates")
        try:
            await sse.read_start()
            chunk = await sse.read_chunk()
            for token in forbidden_tokens:
                assert token not in chunk.decode("utf-8"), f"{name} SSE leaked {token}"
        finally:
            await sse.close()


@pytest.mark.asyncio
async def test_dashboard_job_output_preserves_nested_tool_payloads(active_runtime) -> None:
    """Verify provider event -> normalized event -> StreamRecorder -> SQLite data_json -> dashboard output API preserving structural equality."""
    runtime = active_runtime
    project = runtime.database.project("project")
    plan = resolve_execution_plan("implement", runtime.catalog, "balanced")
    app = create_application()
    job_id = "job-tool-payloads-pipeline"

    runtime.database.create_job(
        job_id=job_id,
        project_id=project.id,
        workflow="implement",
        profile="balanced",
        prompt="test payloads",
        execution_plan_json=json.dumps(execution_plan_data(plan)),
        context_key="implement",
    )

    nested_input = {
        "params": [1, 2.5, "test", True, False, None, {"nested_key": "val"}],
        "empty_obj": {},
        "empty_arr": [],
        "zero": 0,
        "false_val": False,
        "empty_str": "",
    }
    nested_output = {
        "stdout": "output lines\nsecond line",
        "exit_code": 0,
        "records": [{"id": 1, "valid": True, "meta": None}],
    }

    events = [
        # Tool with complex nested input and output
        {"kind": "tool.started", "entity_id": "tool-1", "data": {"tool": "complex_tool", "input": nested_input}},
        {"kind": "tool.completed", "entity_id": "tool-1", "data": {"status": "completed", "output": nested_output}},
        # Tool with missing input and missing output
        {"kind": "tool.started", "entity_id": "tool-2", "data": {"tool": "bare_tool"}},
        {"kind": "tool.completed", "entity_id": "tool-2", "data": {"status": "completed"}},
        # Tool with provider-supplied null input and output
        {"kind": "tool.started", "entity_id": "tool-3", "data": {"tool": "null_tool", "input": None}},
        {"kind": "tool.completed", "entity_id": "tool-3", "data": {"status": "completed", "output": None}},
    ]

    runtime.database.append_stream_events(job_id, events)
    runtime.database.finish_job(job_id, "succeeded", text="Finished successfully.")

    # 1. Verify SQLite data_json rows preserve exact types and keys
    cursor = runtime.database._connection.execute(
        "SELECT id, kind, entity_id, data_json FROM job_stream_events WHERE job_id=? ORDER BY id",
        (job_id,),
    )
    db_rows = cursor.fetchall()
    assert len(db_rows) == 6

    row1_data = json.loads(db_rows[0]["data_json"])
    assert row1_data["tool"] == "complex_tool"
    assert row1_data["input"] == nested_input

    row2_data = json.loads(db_rows[1]["data_json"])
    assert row2_data["status"] == "completed"
    assert row2_data["output"] == nested_output

    row3_data = json.loads(db_rows[2]["data_json"])
    assert row3_data["tool"] == "bare_tool"
    assert "input" not in row3_data

    row4_data = json.loads(db_rows[3]["data_json"])
    assert row4_data["status"] == "completed"
    assert "output" not in row4_data

    row5_data = json.loads(db_rows[4]["data_json"])
    assert row5_data["tool"] == "null_tool"
    assert "input" in row5_data
    assert row5_data["input"] is None

    row6_data = json.loads(db_rows[5]["data_json"])
    assert row6_data["status"] == "completed"
    assert "output" in row6_data
    assert row6_data["output"] is None

    # 2. Verify REST /output endpoint returns exact types and structures
    status, _, body = await request(app, f"/dashboard/api/jobs/{job_id}/output?after=0&limit=10")
    assert status == 200
    payload = json.loads(body.decode("utf-8"))
    api_events = payload["events"]
    assert len(api_events) == 6

    assert api_events[0]["data"]["tool"] == "complex_tool"
    assert api_events[0]["data"]["input"] == nested_input

    assert api_events[1]["data"]["status"] == "completed"
    assert api_events[1]["data"]["output"] == nested_output

    assert api_events[2]["data"]["tool"] == "bare_tool"
    assert "input" not in api_events[2]["data"]

    assert api_events[3]["data"]["status"] == "completed"
    assert "output" not in api_events[3]["data"]

    assert api_events[4]["data"]["tool"] == "null_tool"
    assert "input" in api_events[4]["data"]
    assert api_events[4]["data"]["input"] is None

    assert api_events[5]["data"]["status"] == "completed"
    assert "output" in api_events[5]["data"]
    assert api_events[5]["data"]["output"] is None


@pytest.mark.asyncio
async def test_dashboard_settings_put_is_not_supported(active_runtime) -> None:
    status, _, _ = await request(
        create_application(), "/dashboard/api/settings", method="PUT",
        body=b'{"max_project_readers": 2}',
    )
    assert status == 404


@pytest.mark.asyncio
async def test_ask_malformed_body_and_empty_question(active_runtime) -> None:
    app = create_application()

    # Empty body
    status, _, _ = await request(app, "/ask", method="POST", body=b"")
    assert status == 400

    # Malformed JSON
    status, _, _ = await request(app, "/ask", method="POST", body=b"not-json")
    assert status == 400

    # Missing / empty token
    status, _, _ = await request(
        app, "/ask", method="POST",
        body=json.dumps({"token": "", "question": "valid"}).encode(),
    )
    assert status == 400

    # Missing / empty question
    status, _, _ = await request(
        app, "/ask", method="POST",
        body=json.dumps({"token": "tok", "question": "   "}).encode(),
    )
    assert status == 400


@pytest.mark.asyncio
async def test_ask_token_auth_and_wrong_job(active_runtime) -> None:
    app = create_application()
    token = active_runtime.ask_registry.issue_token("job-1")

    # Unknown tokens, including non-ASCII and escaped surrogate values, -> 403
    for unknown in ("unknown-token", "未知"):
        status, _, _ = await request(
            app, "/ask", method="POST",
            body=json.dumps({"token": unknown, "question": "q"}).encode(),
        )
        assert status == 403


    status, _, _ = await request(
        app, "/ask", method="POST",
        body=b'{"token": "\\ud800", "question": "q"}',
    )
    assert status == 403
    # Revoked token -> 403
    active_runtime.ask_registry.revoke_token("job-1")
    status, _, _ = await request(
        app, "/ask", method="POST",
        body=json.dumps({"token": token, "question": "q"}).encode(),
    )
    assert status == 403
    # Wrong job identifiers, including non-ASCII and escaped surrogate values, -> 403
    token2 = active_runtime.ask_registry.issue_token("job-2")
    for wrong_job in ("job-other", "未知"):
        status, _, _ = await request(
            app, "/ask", method="POST",
            body=json.dumps({"token": token2, "question": "q", "job_id": wrong_job}).encode(),
        )
        assert status == 403


    status, _, _ = await request(
        app, "/ask", method="POST",
        body=f'{{"token": "{token2}", "question": "q", "job_id": "\\ud800"}}'.encode("utf-8"),
    )
    assert status == 403

@pytest.mark.asyncio
async def test_ask_answered_and_conflict(active_runtime) -> None:
    import asyncio
    app = create_application()
    token = active_runtime.ask_registry.issue_token("job-ask-1")

    async def _respond():
        await asyncio.sleep(0.02)
        active_runtime.ask_registry.deliver_answer("job-ask-1", "Answer from coordinator")

    asyncio.create_task(_respond())
    status, _, body = await request(
        app, "/ask", method="POST",
        body=json.dumps({"token": token, "question": "What next?"}).encode(),
    )
    assert status == 200
    assert json.loads(body.decode()) == {"answer": "Answer from coordinator"}


@pytest.mark.asyncio
async def test_ask_second_pending_returns_409(active_runtime) -> None:
    import asyncio
    app = create_application()
    token = active_runtime.ask_registry.issue_token("job-conflict-1")

    first_req = asyncio.create_task(
        request(app, "/ask", method="POST", body=json.dumps({"token": token, "question": "Q1"}).encode())
    )
    await asyncio.sleep(0.01)

    # Second question while first is pending returns 409
    status, _, _ = await request(
        app, "/ask", method="POST",
        body=json.dumps({"token": token, "question": "Q2"}).encode(),
    )
    assert status == 409

    active_runtime.ask_registry.deliver_answer("job-conflict-1", "Answer 1")
    first_status, _, first_body = await first_req
    assert first_status == 200
    assert json.loads(first_body.decode()) == {"answer": "Answer 1"}


@pytest.mark.asyncio
async def test_ask_timeout_returns_no_answer_text(active_runtime) -> None:
    from dataclasses import replace
    from refract.ask import NO_ANSWER_TEXT
    app = create_application()
    token = active_runtime.ask_registry.issue_token("job-timeout-1")
    orig_config = active_runtime.config
    try:
        active_runtime.config = replace(orig_config, ask_timeout_s=0.02)
        status, _, body = await request(
            app, "/ask", method="POST",
            body=json.dumps({"token": token, "question": "Timing out?"}).encode(),
        )
        assert status == 200
        assert json.loads(body.decode()) == {"answer": NO_ANSWER_TEXT}
    finally:
        active_runtime.config = orig_config


@pytest.mark.asyncio
async def test_ask_non_loopback_rejected(active_runtime) -> None:
    app = create_application()
    token = active_runtime.ask_registry.issue_token("job-loopback-1")
    status, _, _ = await request(
        app, "/ask", method="POST", client_host="192.168.1.50",
        body=json.dumps({"token": token, "question": "Non-loopback"}).encode(),
    )
    assert status == 403


@pytest.mark.asyncio
async def test_dashboard_job_reads_expose_telemetry(active_runtime) -> None:
    app = create_application()
    project = active_runtime.database.project("project")
    job_id = "job-dashboard-telemetry"
    active_runtime.database.create_job(
        job_id=job_id,
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="hello",
        execution_plan_json="{}",
        context_key="k",
    )
    telemetry = {
        "version": 1,
        "completeness": "complete",
        "total_input_tokens": {"value": 500, "source": "provider", "quality": "reported"},
        "context_used_tokens": {"value": 2000, "source": "provider", "quality": "reported"},
    }
    active_runtime.database.merge_job_telemetry(job_id, telemetry)

    # 1. Direct job read
    status, _, body = await request(app, f"/dashboard/api/jobs/{job_id}")
    assert status == 200
    job_data = json.loads(body.decode())
    assert "telemetry" in job_data["result"]["metadata"]
    assert job_data["result"]["metadata"]["telemetry"]["total_input_tokens"]["value"] == 500
    assert job_data["result"]["metadata"]["telemetry"]["context_used_tokens"]["value"] == 2000

    # 2. Project jobs listing
    status, _, body = await request(app, f"/dashboard/api/projects/{project.id}/jobs")
    assert status == 200
    listing = json.loads(body.decode())
    active_jobs = [j for j in listing["active"] if j["id"] == job_id]
    assert len(active_jobs) == 1
    assert "telemetry" in active_jobs[0]["result"]["metadata"]
    assert active_jobs[0]["result"]["metadata"]["telemetry"]["total_input_tokens"]["value"] == 500


@pytest.mark.asyncio
async def test_dashboard_running_to_terminal_telemetry_progression(active_runtime) -> None:
    app = create_application()
    project = active_runtime.database.project("project")
    job_id = "job-tel-progression"
    active_runtime.database.create_job(
        job_id=job_id,
        project_id=project.id,
        workflow="implement",
        profile="balanced",
        prompt="progression test",
        execution_plan_json="{}",
        context_key="k",
    )
    with active_runtime.database._connection:
        active_runtime.database._connection.execute("UPDATE jobs SET state='running' WHERE id=?", (job_id,))

    # Live running telemetry
    live_telemetry = {
        "version": 1,
        "completeness": "complete",
        "context_used_tokens": {"value": 1800, "source": "response", "quality": "derived", "observed_at": "2026-10-26T00:00:01Z"},
        "context_window_size": {"value": 128000, "source": "session", "quality": "reported", "observed_at": "2026-10-26T00:00:01Z"},
        "context_remaining_percent": {"value": 98.59, "source": "derived", "quality": "derived", "observed_at": "2026-10-26T00:00:01Z"},
        "total_input_tokens": {"value": 450, "source": "provider", "quality": "reported", "observed_at": "2026-10-26T00:00:01Z"},
        "total_output_tokens": {"value": 80, "source": "provider", "quality": "reported", "observed_at": "2026-10-26T00:00:01Z"},
    }
    active_runtime.database.merge_job_telemetry(job_id, live_telemetry)

    status, _, body = await request(app, f"/dashboard/api/jobs/{job_id}")
    assert status == 200
    running_data = json.loads(body.decode())
    assert running_data["state"] == "running"
    tel_running = running_data["result"]["metadata"]["telemetry"]
    assert tel_running["completeness"] == "complete"
    assert tel_running["context_used_tokens"]["value"] == 1800
    assert tel_running["total_input_tokens"]["value"] == 450

    # Final terminal transition
    final_telemetry = {
        "version": 1,
        "completeness": "complete",
        "context_used_tokens": {"value": 1800, "source": "response", "quality": "derived", "observed_at": "2026-10-26T00:00:02Z"},
        "context_window_size": {"value": 128000, "source": "session", "quality": "reported", "observed_at": "2026-10-26T00:00:02Z"},
        "context_remaining_percent": {"value": 98.59, "source": "derived", "quality": "derived", "observed_at": "2026-10-26T00:00:02Z"},
        "total_input_tokens": {"value": 1200, "source": "provider", "quality": "reported", "observed_at": "2026-10-26T00:00:02Z"},
        "total_output_tokens": {"value": 310, "source": "provider", "quality": "reported", "observed_at": "2026-10-26T00:00:02Z"},
    }
    active_runtime.database.merge_job_telemetry(job_id, final_telemetry)
    active_runtime.database.finish_job(
        job_id,
        "succeeded",
        text="Final result completed",
    )

    status, _, body = await request(app, f"/dashboard/api/jobs/{job_id}")
    assert status == 200
    terminal_data = json.loads(body.decode())
    assert terminal_data["state"] == "succeeded"
    tel_terminal = terminal_data["result"]["metadata"]["telemetry"]
    assert tel_terminal["completeness"] == "complete"
    assert tel_terminal["total_input_tokens"]["value"] == 1200
    assert tel_terminal["total_output_tokens"]["value"] == 310


@pytest.mark.asyncio
async def test_dashboard_telemetry_persists_across_runtime_reload(tmp_path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    config_path = home / "config.toml"
    config_path.write_text(
        """
[daemon]
default_profile = "balanced"
max_jobs = 2

[[targets]]
id = "primary"
backend = "codex"
profile = "legacy-profile"
model = "gpt-4"

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
other = "primary"
""",
        encoding="utf-8",
    )
    cfg = load_config(config_path)

    # 1. First runtime session
    runtime1 = Runtime(cfg)
    try:
        runtime1.database.upsert_project(project_id="p-reload", alias="p-reload", root=str(tmp_path))
        job_id = "job-reload-telemetry"
        runtime1.database.create_job(
            job_id=job_id,
            project_id="p-reload",
            workflow="implement",
            profile="balanced",
            prompt="reload prompt",
            execution_plan_json="{}",
            context_key="k",
        )
        telemetry = {
            "version": 1,
            "completeness": "complete",
            "context_used_tokens": {"value": 3400, "source": "response", "quality": "derived", "observed_at": "2026-10-26T00:00:00Z"},
            "context_window_size": {"value": 200000, "source": "session", "quality": "reported", "observed_at": "2026-10-26T00:00:00Z"},
            "context_remaining_percent": {"value": 98.3, "source": "derived", "quality": "derived", "observed_at": "2026-10-26T00:00:00Z"},
            "total_input_tokens": {"value": 7500, "source": "provider", "quality": "reported", "observed_at": "2026-10-26T00:00:00Z"},
            "total_output_tokens": {"value": 1100, "source": "provider", "quality": "reported", "observed_at": "2026-10-26T00:00:00Z"},
            "cache_read_tokens": {"value": 2000, "source": "provider", "quality": "reported", "observed_at": "2026-10-26T00:00:00Z"},
            "cache_write_tokens": {"value": 500, "source": "provider", "quality": "reported", "observed_at": "2026-10-26T00:00:00Z"},
        }
        runtime1.database.merge_job_telemetry(job_id, telemetry)
        runtime1.database.finish_job(job_id, "succeeded")
    finally:
        runtime1.database.close()

    # 2. Reloaded runtime session from same database
    runtime2 = Runtime(cfg)
    from refract import server
    from refract.dashboard import DashboardState
    monkeypatch.setattr(
        server, "DashboardState",
        lambda: DashboardState(runtime=runtime2),
    )
    try:
        app = create_application()
        status, _, body = await request(app, f"/dashboard/api/jobs/{job_id}")
        assert status == 200
        reloaded = json.loads(body.decode())
        assert "telemetry" in reloaded["result"]["metadata"]
        tel = reloaded["result"]["metadata"]["telemetry"]
        assert tel["context_used_tokens"]["value"] == 3400
        assert tel["context_window_size"]["value"] == 200000
        assert tel["total_input_tokens"]["value"] == 7500
        assert tel["cache_read_tokens"]["value"] == 2000
        assert tel["cache_write_tokens"]["value"] == 500
    finally:
        runtime2.database.close()


@pytest.mark.asyncio
async def test_dashboard_historical_jobs_without_telemetry_return_cleanly(active_runtime) -> None:
    app = create_application()
    project = active_runtime.database.project("project")
    job_id = "job-historical-clean"
    active_runtime.database.create_job(
        job_id=job_id,
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="historical prompt",
        execution_plan_json="{}",
        context_key="k",
    )
    # Historical migrated job without telemetry
    active_runtime.database.finish_job(
        job_id,
        "succeeded",
        text="Historical result text",
    )

    status, _, body = await request(app, f"/dashboard/api/jobs/{job_id}")
    assert status == 200
    job_data = json.loads(body.decode())
    meta = job_data["result"]["metadata"]
    assert meta["telemetry"]["completeness"] == "unavailable"
    assert "context_window_used" not in meta
    assert "input_tokens" not in meta


@pytest.mark.asyncio
async def test_mcp_and_dashboard_detail_metadata_exact_key_and_null_parity(active_runtime) -> None:
    app = create_application()
    project = active_runtime.database.project("project")
    job_id = "job-parity-1"
    active_runtime.database.create_job(
        job_id=job_id,
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="parity test",
        execution_plan_json="{}",
        context_key="k",
    )
    active_runtime.database.finish_job(
        job_id,
        "succeeded",
        text="Result text",
        metadata={"execution": {"model": "test-model", "duration_ms": 100}},
    )
    job = active_runtime.database.job(job_id)
    assert job is not None
    mcp_meta = job.result.metadata.model_dump(mode="json")

    status, _, body = await request(app, f"/dashboard/api/jobs/{job_id}")
    assert status == 200
    dashboard_data = json.loads(body.decode())
    dashboard_meta = dashboard_data["result"]["metadata"]

    assert dashboard_meta == mcp_meta
    assert "failure" in dashboard_meta
    assert dashboard_meta["failure"] is None


@pytest.mark.asyncio
async def test_dashboard_and_mcp_project_same_live_retry_route(tmp_path, monkeypatch) -> None:
    from refract import server
    from refract.dashboard import DashboardState

    cfg = config(tmp_path / "home", (TargetConfig(id="first", backend="codex"), TargetConfig(id="next", backend="claude")))
    runtime = Runtime(cfg)
    root = tmp_path / "project"
    root.mkdir()
    project = register_project(runtime, str(root), "route-project")
    monkeypatch.setattr(server, "DashboardState", lambda: DashboardState(runtime=runtime))
    job_id = "job-route-parity"
    runtime.database.create_job(job_id=job_id, project_id=project.id, workflow="consult", profile="balanced", prompt="route", execution_plan_json="{}", context_key="route")
    runtime.database.finish_job(job_id, "failed", target_id="first", metadata={"failure": {"kind": "retryable"}, "retry": {"retryable": True}})
    job = runtime.database.job(job_id)
    assert job is not None
    expected = runtime.live_result_metadata(job)
    try:
        status, _, body = await request(create_application(), f"/dashboard/api/jobs/{job_id}")
        assert status == 200
        actual = json.loads(body)["result"]["metadata"]
        assert actual == expected
        assert actual["retry"]["next_target"].startswith("nt_")
    finally:
        runtime.database.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/dashboard/api/bootstrap",
        "/dashboard/api/status",
        "/dashboard/api/configuration",
        "/dashboard/api/configuration/targets",
        "/dashboard/api/configuration/targets/primary",
        "/dashboard/api/configuration/profiles",
        "/dashboard/api/configuration/profiles/balanced",
        "/dashboard/api/projects/p1/profile-overrides",
        "/dashboard/api/projects/p1/profile-overrides/balanced",
        "/dashboard/api/task-guide",
    ],
)
@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "DELETE"])
async def test_deleted_dashboard_routes_return_json_404(active_runtime, path, method) -> None:
    app = create_application()
    status, headers, body = await request(app, path, method=method)
    assert status == 404
    data = json.loads(body)
    assert data["code"] == "not_found"
    assert data["error"] == "Dashboard API route not found"


@pytest.mark.asyncio
async def test_profiles_endpoint_enriched_with_profile_config_data(active_runtime) -> None:
    app = create_application()
    status, _, body = await request(app, "/dashboard/api/profiles")
    assert status == 200
    data = json.loads(body)
    assert "default" in data
    assert "available" in data
    assert "profiles" in data
    assert isinstance(data["profiles"], list)
    assert len(data["profiles"]) > 0
    for profile in data["profiles"]:
        assert set(profile.keys()) == {
            "id",
            "parent",
            "declared",
            "inherited",
            "effective",
            "sources",
        }
        serialized = json.dumps(profile)
        assert "system_prompt" not in serialized
        assert '"args"' not in serialized




