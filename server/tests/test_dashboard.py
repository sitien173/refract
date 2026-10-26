from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from refract.config import load_config
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
        lambda: DashboardState(runtime=runtime, csrf_token="test-token"),
    )
    try:
        yield runtime
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_dashboard_reads_fail_closed_without_runtime() -> None:
    app = create_application()

    status, _, body = await request(app, "/dashboard/api/overview")

    assert status == 503
    assert json.loads(body)["error"] == "Refract runtime is not active"


@pytest.mark.asyncio
async def test_dashboard_bootstrap_is_loopback_only_and_not_cached(active_runtime) -> None:
    app = create_application()

    status, headers, body = await request(
        app,
        "/dashboard/api/bootstrap",
        headers=(("Host", "127.0.0.1"),),
    )
    remote, _, _ = await request(
        app,
        "/dashboard/api/bootstrap",
        headers=(("Host", "127.0.0.1"),),
        client_host="192.0.2.1",
    )

    assert status == 200
    assert headers[b"cache-control"] == b"no-store"
    assert json.loads(body)["csrf_token"] == "test-token"
    assert remote == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    ["/dashboard/api/status", "/dashboard/api/projects", "/dashboard/api/jobs/missing/output", "/dashboard"],
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
async def test_configuration_targets_read_loopback_only_and_no_store(active_runtime) -> None:
    app = create_application()
    status, headers, body = await request(
        app,
        "/dashboard/api/configuration/targets",
        headers=(("Host", "127.0.0.1"),),
    )
    assert status == 200
    assert headers[b"cache-control"] == b"no-store"
    assert b"etag" in headers
    assert headers[b"etag"].startswith(b'"') and headers[b"etag"].endswith(b'"')
    payload = json.loads(body)
    assert "revision" in payload
    assert "source_path" in payload
    assert "targets" in payload
    primary = next(t for t in payload["targets"] if t["id"] == "primary")
    assert primary["backend"] == "codex"
    assert primary["backend_profile"] == "legacy-profile"
    assert primary["system_prompt"] == "act safe"
    assert primary["args"] == ["--flag"]

    remote_status, _, remote_body = await request(
        app,
        "/dashboard/api/configuration/targets",
        headers=(("Host", "127.0.0.1"),),
        client_host="192.0.2.1",
    )
    assert remote_status == 403
    assert json.loads(remote_body)["code"] == "forbidden"

    host_status, _, host_body = await request(
        app,
        "/dashboard/api/configuration/targets",
        headers=(("Host", "attacker.com"),),
    )
    assert host_status == 403
    assert json.loads(host_body)["code"] == "forbidden"


@pytest.mark.asyncio
async def test_configuration_target_get_by_id_and_not_found(active_runtime) -> None:
    app = create_application()
    status, headers, body = await request(
        app,
        "/dashboard/api/configuration/targets/primary",
        headers=(("Host", "127.0.0.1"),),
    )
    assert status == 200
    assert headers[b"cache-control"] == b"no-store"
    assert b"etag" in headers
    payload = json.loads(body)
    assert payload["target"]["id"] == "primary"
    assert payload["target"]["backend"] == "codex"
    assert payload["target"]["system_prompt"] == "act safe"

    slash_status, _, slash_body = await request(
        app,
        "/dashboard/api/configuration/targets/cc/opus-consult-reasoning",
        headers=(("Host", "127.0.0.1"),),
    )
    assert slash_status == 200
    assert json.loads(slash_body)["target"]["id"] == "cc/opus-consult-reasoning"

    missing_status, _, missing_body = await request(
        app,
        "/dashboard/api/configuration/targets/nonexistent",
        headers=(("Host", "127.0.0.1"),),
    )
    assert missing_status == 404
    assert json.loads(missing_body)["code"] == "not_found"

    remote_status, _, _ = await request(
        app,
        "/dashboard/api/configuration/targets/primary",
        headers=(("Host", "127.0.0.1"),),
        client_host="192.0.2.1",
    )
    assert remote_status == 403


@pytest.mark.asyncio
async def test_configuration_target_update_and_delete_accept_slash_id(active_runtime) -> None:
    app = create_application()
    _, _, list_body = await request(
        app,
        "/dashboard/api/configuration/targets",
        headers=(("Host", "127.0.0.1"),),
    )
    revision = json.loads(list_body)["revision"]
    headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-Refract-CSRF", "test-token"),
        ("If-Match", f'"{revision}"'),
    )
    target_id = "cc/opus-consult-reasoning"
    path = f"/dashboard/api/configuration/targets/{target_id}"
    update_body = json.dumps(
        {"id": target_id, "backend": "claude", "model": "claude-opus-5", "reasoning": "max"}
    ).encode()

    update_status, _, update_response = await request(
        app,
        path,
        method="PUT",
        body=update_body,
        headers=headers,
    )
    assert update_status == 200
    update_payload = json.loads(update_response)
    assert update_payload["target"]["reasoning"] == "max"

    delete_headers = (*headers[:-1], ("If-Match", f'"{update_payload["revision"]}"'))
    delete_status, _, delete_response = await request(
        app,
        path,
        method="DELETE",
        headers=delete_headers,
    )
    assert delete_status == 200
    assert json.loads(delete_response)["deleted"] == target_id


@pytest.mark.asyncio
async def test_configuration_target_mutations_require_security_headers(active_runtime) -> None:
    app = create_application()
    endpoints = [
        ("POST", "/dashboard/api/configuration/targets", json.dumps({"id": "t1", "backend": "codex"}).encode()),
        ("PUT", "/dashboard/api/configuration/targets/primary", json.dumps({"id": "primary", "backend": "codex"}).encode()),
        ("DELETE", "/dashboard/api/configuration/targets/primary", b""),
    ]
    for method, path, body in endpoints:
        st, _, bd = await request(
            app, path, method=method, body=body,
            headers=(("Host", "127.0.0.1"), ("Origin", "http://127.0.0.1"), ("X-Refract-CSRF", "test-token"), ("If-Match", '"123"')),
            client_host="192.0.2.1",
        )
        assert st == 403
        assert json.loads(bd)["code"] == "forbidden"

        st, _, bd = await request(
            app, path, method=method, body=body,
            headers=(("Host", "127.0.0.1"), ("Origin", "http://evil.com"), ("X-Refract-CSRF", "test-token"), ("If-Match", '"123"')),
        )
        assert st == 403
        assert json.loads(bd)["code"] == "forbidden"

        st, _, bd = await request(
            app, path, method=method, body=body,
            headers=(("Host", "127.0.0.1"), ("Origin", "http://127.0.0.1"), ("If-Match", '"123"')),
        )
        assert st == 403
        assert json.loads(bd)["code"] == "forbidden"

        st, _, bd = await request(
            app, path, method=method, body=body,
            headers=(("Host", "127.0.0.1"), ("Origin", "http://127.0.0.1"), ("X-Refract-CSRF", "test-token")),
        )
        assert st == 428
        assert json.loads(bd)["code"] == "revision_required"


@pytest.mark.asyncio
async def test_configuration_target_create_route(active_runtime) -> None:
    app = create_application()
    _, _, list_body = await request(app, "/dashboard/api/configuration/targets", headers=(("Host", "127.0.0.1"),))
    rev = json.loads(list_body)["revision"]

    headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-Refract-CSRF", "test-token"),
        ("If-Match", f'"{rev}"'),
    )

    data = {
        "id": "tertiary",
        "backend": "codex",
        "backend_profile": "balanced",
        "args": ["--arg1"],
        "max_concurrency": 2,
    }
    status, res_headers, body = await request(
        app, "/dashboard/api/configuration/targets", method="POST", body=json.dumps(data).encode(), headers=headers
    )
    assert status == 200
    assert res_headers[b"cache-control"] == b"no-store"
    assert b"etag" in res_headers
    payload = json.loads(body)
    assert payload["target"]["id"] == "tertiary"
    assert payload["target"]["backend_profile"] == "balanced"
    new_rev = payload["revision"]

    dup_headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-Refract-CSRF", "test-token"),
        ("If-Match", f'"{new_rev}"'),
    )
    dup_status, _, dup_body = await request(
        app, "/dashboard/api/configuration/targets", method="POST", body=json.dumps(data).encode(), headers=dup_headers
    )
    assert dup_status == 422
    assert json.loads(dup_body)["code"] == "configuration_invalid"

    bad_data = {
        "id": "extra_field_t",
        "backend": "codex",
        "unknown_extra": "rejected",
    }
    bad_status, _, bad_body = await request(
        app, "/dashboard/api/configuration/targets", method="POST", body=json.dumps(bad_data).encode(), headers=dup_headers
    )
    assert bad_status == 422
    assert json.loads(bad_body)["code"] == "configuration_invalid"

    stale_headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-Refract-CSRF", "test-token"),
        ("If-Match", '"stale-revision"'),
    )
    fresh_data = {"id": "fresh", "backend": "codex"}
    stale_status, _, stale_body = await request(
        app, "/dashboard/api/configuration/targets", method="POST", body=json.dumps(fresh_data).encode(), headers=stale_headers
    )
    assert stale_status == 409
    stale_payload = json.loads(stale_body)
    assert stale_payload["code"] == "configuration_conflict"
    assert stale_payload["current"] == new_rev


@pytest.mark.asyncio
async def test_configuration_target_update_route(active_runtime) -> None:
    app = create_application()
    _, _, list_body = await request(app, "/dashboard/api/configuration/targets", headers=(("Host", "127.0.0.1"),))
    rev = json.loads(list_body)["revision"]

    headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-Refract-CSRF", "test-token"),
        ("If-Match", f'"{rev}"'),
    )

    update_data = {
        "id": "primary",
        "backend": "codex",
        "model": "gpt-4o",
        "backend_profile": "balanced",
        "args": ["--updated"],
        "max_concurrency": 5,
    }
    status, res_headers, body = await request(
        app, "/dashboard/api/configuration/targets/primary", method="PUT", body=json.dumps(update_data).encode(), headers=headers
    )
    assert status == 200
    assert res_headers[b"cache-control"] == b"no-store"
    payload = json.loads(body)
    assert payload["target"]["model"] == "gpt-4o"
    assert payload["target"]["max_concurrency"] == 5
    new_rev = payload["revision"]

    rename_headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-Refract-CSRF", "test-token"),
        ("If-Match", f'"{new_rev}"'),
    )
    rename_data = dict(update_data, id="renamed")
    ren_status, _, ren_body = await request(
        app, "/dashboard/api/configuration/targets/primary", method="PUT", body=json.dumps(rename_data).encode(), headers=rename_headers
    )
    assert ren_status == 422
    assert json.loads(ren_body)["code"] == "configuration_invalid"

    missing_data = {"id": "missing", "backend": "codex"}
    mis_status, _, mis_body = await request(
        app, "/dashboard/api/configuration/targets/missing", method="PUT", body=json.dumps(missing_data).encode(), headers=rename_headers
    )
    assert mis_status == 404
    assert json.loads(mis_body)["code"] == "not_found"

    stale_headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-Refract-CSRF", "test-token"),
        ("If-Match", f'"{rev}"'),
    )
    stale_status, _, stale_body = await request(
        app, "/dashboard/api/configuration/targets/primary", method="PUT", body=json.dumps(update_data).encode(), headers=stale_headers
    )
    assert stale_status == 409
    assert json.loads(stale_body)["code"] == "configuration_conflict"


@pytest.mark.asyncio
async def test_configuration_target_delete_route(active_runtime) -> None:
    app = create_application()
    _, _, list_body = await request(app, "/dashboard/api/configuration/targets", headers=(("Host", "127.0.0.1"),))
    rev = json.loads(list_body)["revision"]

    headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-Refract-CSRF", "test-token"),
        ("If-Match", f'"{rev}"'),
    )
    create_status, _, create_body = await request(
        app, "/dashboard/api/configuration/targets", method="POST",
        body=json.dumps({"id": "to_delete", "backend": "pi"}).encode(),
        headers=headers,
    )
    assert create_status == 200
    rev2 = json.loads(create_body)["revision"]

    del_headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-Refract-CSRF", "test-token"),
        ("If-Match", f'"{rev2}"'),
    )
    del_status, del_headers_res, del_body = await request(
        app, "/dashboard/api/configuration/targets/to_delete", method="DELETE", headers=del_headers
    )
    assert del_status == 200
    assert del_headers_res[b"cache-control"] == b"no-store"
    assert json.loads(del_body)["deleted"] == "to_delete"
    rev3 = json.loads(del_body)["revision"]

    ref_headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-Refract-CSRF", "test-token"),
        ("If-Match", f'"{rev3}"'),
    )
    ref_status, _, ref_body = await request(
        app, "/dashboard/api/configuration/targets/primary", method="DELETE", headers=ref_headers
    )
    assert ref_status == 409
    ref_payload = json.loads(ref_body)
    assert ref_payload["code"] == "referenced"
    assert "references" in ref_payload
    assert len(ref_payload["references"]) > 0

    mis_status, _, mis_body = await request(
        app, "/dashboard/api/configuration/targets/missing", method="DELETE", headers=ref_headers
    )
    assert mis_status == 404
    assert json.loads(mis_body)["code"] == "not_found"


@pytest.mark.asyncio
async def test_configuration_target_error_redaction(active_runtime) -> None:
    app = create_application()
    _, _, list_body = await request(app, "/dashboard/api/configuration/targets", headers=(("Host", "127.0.0.1"),))
    rev = json.loads(list_body)["revision"]

    headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-Refract-CSRF", "test-token"),
        ("If-Match", f'"{rev}"'),
    )

    bad_data = {
        "id": "secret_target",
        "backend": "codex",
        "system_prompt": "SUPER_SECRET_OPERATOR_PROMPT_XYZ",
        "args": ["--"],
    }
    status, _, body = await request(
        app, "/dashboard/api/configuration/targets", method="POST", body=json.dumps(bad_data).encode(), headers=headers
    )
    assert status == 422
    payload = json.loads(body)
    assert payload["code"] == "configuration_invalid"
    assert "SUPER_SECRET_OPERATOR_PROMPT_XYZ" not in body.decode("utf-8")
    assert payload["error"] == "Target args cannot contain the reserved token"


@pytest.mark.asyncio
async def test_configuration_mutation_error_message_reaches_client(active_runtime) -> None:
    app = create_application()
    _, _, list_body = await request(app, "/dashboard/api/configuration/targets")
    rev = json.loads(list_body)["revision"]
    headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-Refract-CSRF", "test-token"),
        ("If-Match", f'"{rev}"'),
    )

    status, _, body = await request(
        app,
        "/dashboard/api/configuration/targets",
        method="POST",
        body=json.dumps({"id": "primary", "backend": "codex"}).encode(),
        headers=headers,
    )

    assert status == 422
    assert json.loads(body)["error"] == "Target 'primary' already exists."


@pytest.mark.asyncio
async def test_configuration_profiles_read_and_security(active_runtime) -> None:
    app = create_application()

    # Non-loopback host rejected with 403
    status, _, _ = await request(
        app, "/dashboard/api/configuration/profiles", headers=(("Host", "attacker.com"),)
    )
    assert status == 403
    # Non-loopback client rejected with 403
    status, _, _ = await request(
        app,
        "/dashboard/api/configuration/profiles",
        headers=(("Host", "127.0.0.1"),),
        client_host="192.168.1.50",
    )
    assert status == 403
    # Loopback read succeeds
    status, headers, body = await request(
        app, "/dashboard/api/configuration/profiles", headers=(("Host", "127.0.0.1"),)
    )
    assert status == 200
    assert headers[b"cache-control"] == b"no-store"
    assert b"etag" in headers
    data = json.loads(body)
    assert data["default_profile"] == "balanced"
    assert "primary" in data["available_targets"]
    assert len(data["profiles"]) == 1
    prof = data["profiles"][0]
    assert prof["id"] == "balanced"
    assert prof["declared"]["implement"]["targets"] == ["primary"]
    assert prof["effective"]["implement"]["targets"] == ["primary"]
    assert prof["sources"]["implement"] == "declared"

    # Single profile get
    status, headers, body = await request(
        app, "/dashboard/api/configuration/profiles/balanced", headers=(("Host", "127.0.0.1"),)
    )
    assert status == 200
    assert headers[b"cache-control"] == b"no-store"
    single = json.loads(body)
    assert single["profile"]["id"] == "balanced"

    # Missing profile get
    status, _, body = await request(
        app, "/dashboard/api/configuration/profiles/missing", headers=(("Host", "127.0.0.1"),)
    )
    assert status == 404
    assert json.loads(body)["code"] == "not_found"


@pytest.mark.asyncio
async def test_configuration_profiles_crud_and_references(active_runtime) -> None:
    app = create_application()
    _, _, list_body = await request(
        app, "/dashboard/api/configuration/profiles", headers=(("Host", "127.0.0.1"),)
    )
    rev = json.loads(list_body)["revision"]

    # CSRF check
    bad_csrf_headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-Refract-CSRF", "wrong-token"),
        ("If-Match", f'"{rev}"'),
    )
    status, _, _ = await request(
        app,
        "/dashboard/api/configuration/profiles",
        method="POST",
        body=json.dumps({"id": "p1"}).encode(),
        headers=bad_csrf_headers,
    )
    assert status == 403
    # If-Match missing check
    no_match_headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-Refract-CSRF", "test-token"),
    )
    status, _, body = await request(
        app,
        "/dashboard/api/configuration/profiles",
        method="POST",
        body=json.dumps({"id": "p1"}).encode(),
        headers=no_match_headers,
    )
    assert status == 428
    assert json.loads(body)["code"] == "revision_required"

    # If-Match stale check
    stale_headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-Refract-CSRF", "test-token"),
        ("If-Match", '"stale-rev"'),
    )
    status, _, body = await request(
        app,
        "/dashboard/api/configuration/profiles",
        method="POST",
        body=json.dumps({"id": "p1"}).encode(),
        headers=stale_headers,
    )
    assert status == 409
    assert json.loads(body)["code"] == "configuration_conflict"

    # Create profile "quality" extending "balanced"
    headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-Refract-CSRF", "test-token"),
        ("If-Match", f'"{rev}"'),
    )
    payload = {
        "id": "quality",
        "extends": "balanced",
        "implement": {
            "targets": ["fallback", "primary"],
            "timeout_s": 30,
        },
    }
    status, res_headers, body = await request(
        app,
        "/dashboard/api/configuration/profiles",
        method="POST",
        body=json.dumps(payload).encode(),
        headers=headers,
    )
    assert status == 200
    assert res_headers[b"cache-control"] == b"no-store"
    res_data = json.loads(body)
    new_rev = res_data["revision"]
    q_prof = res_data["profile"]
    assert q_prof["id"] == "quality"
    assert q_prof["declared"]["implement"]["targets"] == ["fallback", "primary"]
    assert q_prof["declared"]["implement"]["timeout_s"] == 30
    assert "max_attempts" not in q_prof["declared"]["implement"]
    # Undeclared workflows appear as null in declared
    assert q_prof["declared"]["review"] is None
    assert q_prof["declared"]["consult"] is None
    assert q_prof["declared"]["other"] is None
    # Inherited and effective policies
    assert q_prof["inherited"]["review"]["targets"] == ["primary"]
    assert q_prof["effective"]["review"]["targets"] == ["primary"]
    assert q_prof["sources"]["review"] == "balanced"
    assert q_prof["sources"]["implement"] == "declared"

    # Update: rename rejection
    update_headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-Refract-CSRF", "test-token"),
        ("If-Match", f'"{new_rev}"'),
    )
    rename_data = dict(payload, id="renamed")
    status, _, body = await request(
        app,
        "/dashboard/api/configuration/profiles/quality",
        method="PUT",
        body=json.dumps(rename_data).encode(),
        headers=update_headers,
    )
    assert status == 422
    assert json.loads(body)["code"] == "configuration_invalid"

    # Update: valid update adding review workflow
    valid_update = {
        "id": "quality",
        "extends": "balanced",
        "implement": {
            "targets": ["fallback", "primary"],
            "timeout_s": 30,
        },
        "review": {
            "targets": ["primary"],
        },
    }
    status, _, body = await request(
        app,
        "/dashboard/api/configuration/profiles/quality",
        method="PUT",
        body=json.dumps(valid_update).encode(),
        headers=update_headers,
    )
    assert status == 200
    updated_rev = json.loads(body)["revision"]

    # Delete blocked by default_profile: deleting balanced
    del_headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-Refract-CSRF", "test-token"),
        ("If-Match", f'"{updated_rev}"'),
    )
    status, _, body = await request(
        app,
        "/dashboard/api/configuration/profiles/balanced",
        method="DELETE",
        headers=del_headers,
    )
    assert status == 409
    ref_payload = json.loads(body)
    assert ref_payload["code"] == "referenced"
    assert any(ref["relationship"] == "default_profile" for ref in ref_payload["references"])

    # Create child extending quality to verify extends blocking
    child_payload = {
        "id": "child",
        "extends": "quality",
    }
    status, _, body = await request(
        app,
        "/dashboard/api/configuration/profiles",
        method="POST",
        body=json.dumps(child_payload).encode(),
        headers=del_headers,
    )
    assert status == 200
    rev_after_child = json.loads(body)["revision"]

    # Delete quality blocked by child extending it
    del_q_headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-Refract-CSRF", "test-token"),
        ("If-Match", f'"{rev_after_child}"'),
    )
    status, _, body = await request(
        app,
        "/dashboard/api/configuration/profiles/quality",
        method="DELETE",
        headers=del_q_headers,
    )
    assert status == 409
    ref_payload = json.loads(body)
    assert ref_payload["code"] == "referenced"
    assert any(ref["profile_id"] == "child" and ref["relationship"] == "extends" for ref in ref_payload["references"])

    # Delete child
    status, _, body = await request(
        app,
        "/dashboard/api/configuration/profiles/child",
        method="DELETE",
        headers=del_q_headers,
    )
    assert status == 200
    rev_after_child_del = json.loads(body)["revision"]

    # Delete quality succeeds now
    del_q2_headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-Refract-CSRF", "test-token"),
        ("If-Match", f'"{rev_after_child_del}"'),
    )
    status, _, body = await request(
        app,
        "/dashboard/api/configuration/profiles/quality",
        method="DELETE",
        headers=del_q2_headers,
    )
    assert status == 200
    assert json.loads(body)["deleted"] == "quality"


@pytest.mark.asyncio
async def test_project_profile_override_routes_crud_and_fallback(active_runtime) -> None:
    app = create_application()
    project_id = active_runtime.database.projects()[0].id
    url_base = f"/dashboard/api/projects/{project_id}/profile-overrides"

    # Security: non-loopback host rejected
    status, _, _ = await request(app, url_base, headers=(("Host", "attacker.com"),))
    assert status == 403
    # Unknown project rejected
    status, _, body = await request(
        app,
        "/dashboard/api/projects/unknown-proj/profile-overrides",
        headers=(("Host", "127.0.0.1"),),
    )
    assert status == 404

    # Initial list before any project config file exists
    status, headers, body = await request(app, url_base, headers=(("Host", "127.0.0.1"),))
    assert status == 200
    assert headers[b"cache-control"] == b"no-store"
    list_data = json.loads(body)
    assert list_data["overrides"] == []
    assert list_data["global_default_profile"] == "balanced"
    assert list_data["project_default_profile"] == "balanced"
    rev = list_data["revision"]

    # Create override for "balanced" - creating minimal project file on demand
    create_headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-Refract-CSRF", "test-token"),
        ("If-Match", f'"{rev}"'),
    )
    override_payload = {
        "id": "balanced",
        "extends": "balanced",
        "implement": {"targets": ["fallback"]},
    }
    status, _, body = await request(
        app,
        url_base,
        method="POST",
        body=json.dumps(override_payload).encode(),
        headers=create_headers,
    )
    assert status == 200
    created_data = json.loads(body)
    rev2 = created_data["revision"]
    created_ov = created_data["override"]
    assert created_ov["id"] == "balanced"
    assert created_ov["declared"]["implement"]["targets"] == ["fallback"]
    assert created_ov["effective"]["implement"]["targets"] == ["fallback"]
    assert created_ov["effective"]["review"]["targets"] == ["primary"]
    assert created_ov["sources"]["review"] == "global"

    # Single override GET
    status, _, body = await request(
        app,
        f"{url_base}/balanced",
        headers=(("Host", "127.0.0.1"),),
    )
    assert status == 200
    assert json.loads(body)["override"]["id"] == "balanced"

    # Update override
    update_headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-Refract-CSRF", "test-token"),
        ("If-Match", f'"{rev2}"'),
    )
    update_payload = {
        "id": "balanced",
        "extends": "balanced",
        "implement": {"targets": ["fallback"]},
        "review": {"targets": ["fallback"]},
    }
    status, _, body = await request(
        app,
        f"{url_base}/balanced",
        method="PUT",
        body=json.dumps(update_payload).encode(),
        headers=update_headers,
    )
    assert status == 200
    rev3 = json.loads(body)["revision"]

    # DELETE override - returns resulting effective global fallback!
    del_headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-Refract-CSRF", "test-token"),
        ("If-Match", f'"{rev3}"'),
    )
    status, del_h, body = await request(
        app,
        f"{url_base}/balanced",
        method="DELETE",
        headers=del_headers,
    )
    assert status == 200
    del_data = json.loads(body)
    assert del_data["deleted"] == "balanced"
    fallback = del_data["fallback"]
    assert fallback is not None
    assert fallback["id"] == "balanced"
    assert fallback["effective"]["implement"]["targets"] == ["primary"]
    assert fallback["effective"]["review"]["targets"] == ["primary"]

    # Existing runtime read endpoints remain compatible
    status, _, body = await request(
        app,
        "/dashboard/api/profiles",
        headers=(("Host", "127.0.0.1"),),
    )
    assert status == 200
    rt_profiles = json.loads(body)
    assert rt_profiles["default"] == "balanced"
    assert "balanced" in rt_profiles["available"]

    status, _, body = await request(
        app,
        f"/dashboard/api/projects/{project_id}",
        headers=(("Host", "127.0.0.1"),),
    )
    assert status == 200


@pytest.mark.asyncio
async def test_project_profile_override_conflict_and_validation(active_runtime) -> None:
    app = create_application()
    project_id = active_runtime.database.projects()[0].id
    url_base = f"/dashboard/api/projects/{project_id}/profile-overrides"

    # 1. Missing If-Match revision returns 428
    status, _, body = await request(
        app,
        url_base,
        method="POST",
        body=json.dumps({"id": "custom", "implement": {"targets": ["fallback"]}}).encode(),
        headers=(
            ("Host", "127.0.0.1"),
            ("Origin", "http://127.0.0.1"),
            ("X-Refract-CSRF", "test-token"),
        ),
    )
    assert status == 428
    assert json.loads(body)["code"] == "revision_required"

    # 2. Creating with non-matching revision when file does not exist returns 409 conflict
    status, _, body = await request(
        app,
        url_base,
        method="POST",
        body=json.dumps({"id": "custom", "implement": {"targets": ["fallback"]}}).encode(),
        headers=(
            ("Host", "127.0.0.1"),
            ("Origin", "http://127.0.0.1"),
            ("X-Refract-CSRF", "test-token"),
            ("If-Match", '"non-existent-rev"'),
        ),
    )
    assert status == 409
    assert json.loads(body)["code"] == "configuration_conflict"

    # 3. Validation: empty profile id returns 422
    status, _, body = await request(
        app,
        url_base,
        method="POST",
        body=json.dumps({"id": "   ", "implement": {"targets": ["fallback"]}}).encode(),
        headers=(
            ("Host", "127.0.0.1"),
            ("Origin", "http://127.0.0.1"),
            ("X-Refract-CSRF", "test-token"),
            ("If-Match", '""'),
        ),
    )
    assert status == 422
    assert json.loads(body)["code"] == "configuration_invalid"

    # 4. Successful creation on missing file with empty If-Match
    status, _, body = await request(
        app,
        url_base,
        method="POST",
        body=json.dumps({
            "id": "dev-profile",
            "extends": "balanced",
            "implement": {"targets": ["fallback"]},
        }).encode(),
        headers=(
            ("Host", "127.0.0.1"),
            ("Origin", "http://127.0.0.1"),
            ("X-Refract-CSRF", "test-token"),
            ("If-Match", '""'),
        ),
    )
    assert status == 200
    created = json.loads(body)
    new_rev = created["revision"]
    assert created["override"]["id"] == "dev-profile"

    # 5. Stale revision update returns 409 with current revision
    status, _, body = await request(
        app,
        f"{url_base}/dev-profile",
        method="PUT",
        body=json.dumps({
            "id": "dev-profile",
            "extends": "balanced",
            "implement": {"targets": ["primary"]},
        }).encode(),
        headers=(
            ("Host", "127.0.0.1"),
            ("Origin", "http://127.0.0.1"),
            ("X-Refract-CSRF", "test-token"),
            ("If-Match", '"stale-revision-value"'),
        ),
    )
    assert status == 409
    conflict_err = json.loads(body)
    assert conflict_err["code"] == "configuration_conflict"
    assert conflict_err["current"] == new_rev

    # 6. Conflict recovery: update with correct current revision succeeds
    status, _, body = await request(
        app,
        f"{url_base}/dev-profile",
        method="PUT",
        body=json.dumps({
            "id": "dev-profile",
            "extends": "balanced",
            "implement": {"targets": ["primary"]},
        }).encode(),
        headers=(
            ("Host", "127.0.0.1"),
            ("Origin", "http://127.0.0.1"),
            ("X-Refract-CSRF", "test-token"),
            ("If-Match", f'"{new_rev}"'),
        ),
    )
    assert status == 200
    assert json.loads(body)["override"]["effective"]["implement"]["targets"] == ["primary"]


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


@pytest.mark.asyncio
async def test_confirmed_removed_api_aliases_return_json_not_found(active_runtime, tmp_path) -> None:
    runtime = active_runtime
    project_root = tmp_path / "alias-project"
    project_root.mkdir()
    project = register_project(runtime, str(project_root), "alias-project")
    config_dir = project_root / ".refract"
    config_dir.mkdir()
    project_config = config_dir / "config.toml"
    project_config.write_text(
        '[profiles.balanced]\nextends = "balanced"\nimplement = "fallback"\n',
        encoding="utf-8",
    )
    source_read, _, _, _, _ = runtime.mutations.read_project_overrides(project_root)
    app = create_application()
    read_headers = (
        ("Host", "127.0.0.1"), ("Origin", "http://127.0.0.1"),
        ("X-Refract-CSRF", "test-token"), ("If-Match", f'"{source_read.revision}"'),
    )
    mutation_headers = read_headers
    valid_body = json.dumps({"id": "balanced", "extends": "balanced", "implement": {"targets": ["fallback"]}}).encode()
    requests = [
        ("GET", f"/dashboard/api/projects/{project.id}/configuration/profiles", read_headers, b""),
        ("POST", f"/dashboard/api/projects/{project.id}/configuration/profiles", mutation_headers, valid_body),
        ("GET", f"/dashboard/api/projects/{project.id}/configuration/profiles/balanced", read_headers, b""),
        ("PUT", f"/dashboard/api/projects/{project.id}/configuration/profiles/balanced", mutation_headers, valid_body),
        ("DELETE", f"/dashboard/api/projects/{project.id}/configuration/profiles/balanced", mutation_headers, b""),
    ]
    for method, path, headers, body in requests:
        status, response_headers, response_body = await request(app, path, method=method, headers=headers, body=body)
        payload = json.loads(response_body)
        assert status == 404
        assert response_headers[b"content-type"].startswith(b"application/json")
        assert payload["error"] == "Dashboard API route not found"
    for path in (
        "/dashboard/api/config",
        "/dashboard/api/config/health",
    ):
        status, _, body = await request(app, path, headers=read_headers)
        assert status == 404 and json.loads(body)["error"] == "Dashboard API route not found"
    for path in (
        "/dashboard/api/configuration",
        "/dashboard/api/status", "/dashboard/api/overview",
    ):
        status, _, _ = await request(app, path, headers=read_headers)
        assert status == 200


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


