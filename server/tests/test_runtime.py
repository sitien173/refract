from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from refract.config import load_config
from refract.runtime import OrchestrationError, Runtime
from refract.planning import execution_plan_data, resolve_execution_plan, target_execution_key, next_target_token, resolve_next_target
from refract.result_metadata import JobResultMetadata, FailureMetadata, RetryMetadata
from tests.orchestration_helpers import config as make_config, register_project


def test_runtime_rejects_removed_marked_target_without_echoing_identifier(tmp_path) -> None:
    base = make_config(tmp_path / "home")
    target = replace(base.targets[0], envs={"LOCAL": "value"})
    runtime = Runtime(replace(base, targets=(target,)))
    root = tmp_path / "project"
    root.mkdir()
    project = register_project(runtime, str(root))
    runtime._catalog = replace(runtime.catalog, targets=())
    try:
        with pytest.raises(ValueError, match="Unknown target") as error:
            runtime._resolve_target_environment(project, target.id)
        assert target.id not in str(error.value)
    finally:
        import asyncio
        asyncio.run(runtime.close())


def test_environment_session_revision_is_opaque_and_runtime_scoped(tmp_path) -> None:
    base = make_config(tmp_path / "home")
    target = replace(base.targets[0], envs={"SECRET": "SYNTHETIC_REVISION_SECRET"})
    catalog = replace(base, targets=(target,))
    root = tmp_path / "project"
    root.mkdir()
    first_runtime = Runtime(catalog)
    project = register_project(first_runtime, str(root))
    try:
        _, first = first_runtime._resolve_target_environment(project, target.id)
        _, repeated = first_runtime._resolve_target_environment(project, target.id)
        assert first == repeated
    finally:
        import asyncio
        asyncio.run(first_runtime.close())

    second_runtime = Runtime(catalog)
    try:
        same_project = second_runtime.database.project(project.id)
        assert same_project is not None
        _, restarted = second_runtime._resolve_target_environment(same_project, target.id)
        assert restarted != first
    finally:
        import asyncio
        asyncio.run(second_runtime.close())


def test_runtime_resolves_current_project_environment_by_stored_target_id(tmp_path) -> None:
    base = make_config(tmp_path / "home")
    target = replace(base.targets[0], envs_vars=("shared",), args=("--safe",), max_concurrency=3)
    catalog = replace(base, targets=(target,), envs={"shared": {"ENDPOINT": "global"}})
    root = tmp_path / "project"
    root.mkdir()
    runtime = Runtime(catalog)
    project = register_project(runtime, str(root))
    project_config = root / ".refract" / "config.toml"
    project_config.parent.mkdir()
    project_config.write_text('[envs.shared]\nENDPOINT = "project-one"\n', encoding="utf-8")
    try:
        first, first_revision = runtime._resolve_target_environment(project, target.id)
        stored_plan = resolve_execution_plan("implement", catalog, "balanced")
        project_config.write_text('[envs.shared]\nENDPOINT = "project-two"\n', encoding="utf-8")
        second, second_revision = runtime._resolve_target_environment(project, target.id)
        assert first == {"ENDPOINT": "project-one"}
        assert second == {"ENDPOINT": "project-two"}
        assert first_revision != second_revision
        other_root = tmp_path / "other-project"
        other_root.mkdir()
        other_project = register_project(runtime, str(other_root))
        other_config = other_root / ".refract" / "config.toml"
        other_config.parent.mkdir()
        other_config.write_text('[envs.shared]\nENDPOINT = "isolated-project"\n', encoding="utf-8")
        other_values, other_revision = runtime._resolve_target_environment(other_project, target.id)
        assert other_values == {"ENDPOINT": "isolated-project"}
        assert other_revision != second_revision
        assert stored_plan.target(target.id).args == ("--safe",)
        assert stored_plan.target(target.id).max_concurrency == 3
    finally:
        import asyncio
        asyncio.run(runtime.close())


def test_resolve_target_environment_derives_revision_from_catalog_snapshot_not_subsequent_stat(tmp_path, monkeypatch) -> None:
    import refract.runtime as runtime_module

    base = make_config(tmp_path / "home")
    target = replace(base.targets[0], envs_vars=("shared",))
    catalog = replace(base, targets=(target,), envs={"shared": {"ENDPOINT": "global"}})
    root = tmp_path / "project"
    root.mkdir()
    runtime = Runtime(catalog)
    project = register_project(runtime, str(root))
    project_config = root / ".refract" / "config.toml"
    project_config.parent.mkdir()
    project_config.write_text('[envs.shared]\nENDPOINT = "v1"\n', encoding="utf-8")
    try:
        original_resolve = runtime_module.resolve_target_environment
        edited = False

        def edit_during_resolution(cat, tgt, inherited=None):
            nonlocal edited
            res = original_resolve(cat, tgt, inherited=inherited)
            if not edited:
                edited = True
                # Simulate an external edit between catalog acquisition and revision generation
                project_config.write_text('[envs.shared]\nENDPOINT = "v2"\n', encoding="utf-8")
            return res

        monkeypatch.setattr(runtime_module, "resolve_target_environment", edit_during_resolution)

        first_values, first_revision = runtime._resolve_target_environment(project, target.id)
        assert first_values == {"ENDPOINT": "v1"}

        second_values, second_revision = runtime._resolve_target_environment(project, target.id)
        assert second_values == {"ENDPOINT": "v2"}

        assert first_revision != second_revision
    finally:
        import asyncio
        asyncio.run(runtime.close())


def test_project_catalog_snapshot_retries_when_file_changes_during_load(tmp_path, monkeypatch) -> None:
    import refract.runtime as runtime_module

    base = make_config(tmp_path / "home")
    root = tmp_path / "project"
    root.mkdir()
    runtime = Runtime(base)
    old_identity = (1000, 100, 1)
    new_identity = (2000, 200, 2)
    identities = iter((old_identity, new_identity, new_identity, new_identity))
    loaded = []
    catalog = replace(base, envs={"shared": {"ENDPOINT": "current"}})

    def file_identity(path):
        return next(identities)

    def load_project(root_path, base_catalog):
        loaded.append(base_catalog)
        return catalog

    monkeypatch.setattr(runtime_module, "_file_identity", file_identity)
    monkeypatch.setattr(runtime_module, "load_project_config", load_project)
    try:
        # A distinct base object forces the project-catalog cache miss that exposed
        # the pre-load identity race during a global configuration reload.
        result, revision = runtime._project_catalog_snapshot(root, replace(base))
        assert result is catalog
        assert len(loaded) == 2
        assert runtime._project_catalogs[root][0] == new_identity
        assert revision == runtime._project_catalogs[root][3]
    finally:
        import asyncio
        asyncio.run(runtime.close())


def test_project_catalog_snapshot_fails_safely_after_continuous_file_churn(tmp_path, monkeypatch) -> None:
    import refract.runtime as runtime_module

    base = make_config(tmp_path / "home")
    root = tmp_path / "project"
    root.mkdir()
    runtime = Runtime(base)
    identities = iter((1000, 2000, 3000, 4000, 5000, 6000))
    loads = 0

    def file_identity(path):
        return (next(identities), 100, 1)

    def load_project(root_path, base_catalog):
        nonlocal loads
        loads += 1
        return replace(base_catalog, envs={"shared": {"TOKEN": "SYNTHETIC_SECRET"}})

    monkeypatch.setattr(runtime_module, "_file_identity", file_identity)
    monkeypatch.setattr(runtime_module, "load_project_config", load_project)
    try:
        with pytest.raises(ValueError, match="Project configuration changed during loading") as error:
            runtime._project_catalog_snapshot(root, replace(base))
        assert loads == 3
        assert "SYNTHETIC_SECRET" not in str(error.value)
        assert root not in runtime._project_catalogs
    finally:
        import asyncio
        asyncio.run(runtime.close())


def test_resolve_target_environment_mocked_sequence_does_not_label_old_binding_with_new_identity(tmp_path, monkeypatch) -> None:
    import refract.runtime as runtime_module

    base = make_config(tmp_path / "home")
    target = replace(base.targets[0], envs_vars=("shared",))
    catalog_old = replace(base, targets=(target,), envs={"shared": {"ENDPOINT": "old"}})
    catalog_new = replace(base, targets=(target,), envs={"shared": {"ENDPOINT": "new"}})

    root = tmp_path / "project"
    root.mkdir()
    runtime = Runtime(base)
    project = register_project(runtime, str(root))

    old_ident = (1000, 100, 1)
    new_ident = (2000, 200, 2)
    file_identities = [old_ident, old_ident, new_ident, new_ident]
    catalog_loads = [catalog_old, catalog_new]

    def mock_file_identity(path):
        return file_identities.pop(0) if file_identities else new_ident

    def mock_load_project_config(root_path, base_catalog):
        return catalog_loads.pop(0)

    monkeypatch.setattr(runtime_module, "_file_identity", mock_file_identity)
    monkeypatch.setattr(runtime_module, "load_project_config", mock_load_project_config)

    try:
        first_values, first_revision = runtime._resolve_target_environment(project, target.id)
        second_values, second_revision = runtime._resolve_target_environment(project, target.id)

        assert first_values == {"ENDPOINT": "old"}
        assert second_values == {"ENDPOINT": "new"}
        assert first_revision != second_revision
    finally:
        import asyncio
        asyncio.run(runtime.close())


@pytest.mark.asyncio
async def test_submit_pins_valid_token_and_prechecks_all_open_targets(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('''[daemon]\ndefault_profile = "balanced"\nbreaker_base_cooldown_s = 7\n\n[[targets]]\nid = "a"\nbackend = "codex"\nenvs = { A = "SYNTHETIC_MARKER" }\n\n[[targets]]\nid = "b"\nbackend = "claude"\n\n[profiles.balanced]\nconsult = ["a", "b"]\n''', encoding="utf-8")
    runtime = Runtime(load_config(path))
    root = tmp_path / "project"
    root.mkdir()
    project = register_project(runtime, str(root), "project")
    plan = resolve_execution_plan("consult", runtime.catalog, "balanced")
    token = next_target_token(runtime.catalog.config_revision, project.id, "balanced", "consult", plan.targets[1])
    try:
        first = await runtime.submit(project.id, "consult", "hello", next_target=token)
        stored = runtime.database.job_record(first.job_id)
        stored_plan = json.loads(stored["execution_plan_json"])
        assert stored_plan["selection"]["targets"] == ["b"]
        assert "environment_targets" not in stored_plan
        assert len(runtime.database.jobs(project.id)) == 1
        for target in plan.targets:
            runtime.database.record_target_failure(target_execution_key(target), immediate=True, base_cooldown_s=7)
        with pytest.raises(OrchestrationError) as raised:
            await runtime.submit(project.id, "consult", "no row")
        assert raised.value.code == "targets_unavailable"
        assert raised.value.retryable is True and type(raised.value.retry_after_s) is int
        assert len(runtime.database.jobs(project.id)) == 1
    finally:
        await runtime.close()


def test_next_target_token_is_bound_to_revision_project_profile_workflow_and_candidate(tmp_path) -> None:
    path = tmp_path / "config.toml"
    _config(path)
    config = load_config(path)
    plan = resolve_execution_plan("consult", config, "balanced")
    first = plan.targets[0]
    token = next_target_token(config.config_revision, "project", plan.profile, plan.workflow, first)

    expected = "nt_" + hashlib.sha256(json.dumps([config.config_revision, "project", plan.profile, plan.workflow, target_execution_key(first)], separators=(",", ":")).encode()).hexdigest()[:16]
    assert token == expected
    assert token.startswith("nt_") and len(token) == 19
    assert resolve_next_target(token, config.config_revision, "project", plan) == first
    assert resolve_next_target(token, "changed-revision", "project", plan) is None
    assert resolve_next_target(token, config.config_revision, "other-project", plan) is None


@pytest.mark.asyncio
async def test_context_overflow_projects_read_time_route_to_next_healthy_target(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    _two_target_config(config_path)
    runtime = Runtime(load_config(config_path))
    root = tmp_path / "overflow-project"
    root.mkdir()
    project = register_project(runtime, str(root), "overflow-project")
    plan = resolve_execution_plan("consult", runtime.catalog, "balanced")
    try:
        job_id = "overflow-route"
        runtime.database.create_job(job_id=job_id, project_id=project.id, workflow="consult", profile="balanced", prompt="overflow", execution_plan_json=json.dumps(execution_plan_data(plan)), context_key=job_id)
        runtime.database.finish_job(job_id, "failed", target_id="a", metadata={"failure": {"kind": "context_overflow"}, "retry": {"retryable": True}})
        view = runtime.database.job(job_id)
        result = runtime.live_result_metadata(view)
        assert result["retry"]["retryable"] is True
        assert result["retry"]["next_target"].startswith("nt_")
        assert json.loads(runtime.database.job_record(job_id)["result_metadata_json"])["retry"]["next_target"] is None
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_live_metadata_routes_after_failure_without_persisting_hint(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    _two_target_config(config_path)
    runtime = Runtime(load_config(config_path))
    root = tmp_path / "project"
    root.mkdir()
    project = register_project(runtime, str(root), "project")
    plan = resolve_execution_plan("consult", runtime.catalog, "balanced")
    metadata = JobResultMetadata(
        failure=FailureMetadata(kind="retryable"),
        retry=RetryMetadata(retryable=False, next_target=None),
    )
    try:
        for target_b_open in (False, True):
            job_id = "live-route-open" if target_b_open else "live-route-closed"
            runtime.database.create_job(job_id=job_id, project_id=project.id, workflow="consult", profile="balanced", prompt="fail", execution_plan_json=json.dumps(execution_plan_data(plan)), context_key=job_id)
            runtime.database.finish_job(job_id, "failed", target_id="a", metadata=metadata)
            if target_b_open:
                runtime.database._connection.execute("INSERT OR REPLACE INTO target_health(target_id, consecutive_failures, circuit_open_until, cooldown_s, probe_job_id) VALUES (?, 1, '2999-01-01T00:00:00+00:00', 60, '')", (target_execution_key(plan.targets[1]),))
            else:
                runtime.database.record_target_success(target_execution_key(plan.targets[1]))
            view = runtime.database.job(job_id)
            result = runtime.live_result_metadata(view)
            assert (result["retry"]["next_target"].startswith("nt_") and result["retry"]["retryable"] is True) if not target_b_open else (result["retry"]["next_target"] is None and result["retry"]["retryable"] is False)
            assert json.loads(runtime.database.job_record(job_id)["result_metadata_json"])["retry"]["next_target"] is None
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_live_result_metadata_preserves_telemetry(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    _two_target_config(config_path)
    runtime = Runtime(load_config(config_path))
    root = tmp_path / "project"
    root.mkdir()
    project = register_project(runtime, str(root), "project")
    plan = resolve_execution_plan("consult", runtime.catalog, "balanced")
    telemetry = {
        "version": 1,
        "completeness": "complete",
        "total_input_tokens": {"value": 250, "source": "provider", "quality": "reported"},
        "context_used_tokens": {"value": 1500, "source": "provider", "quality": "reported"},
    }
    try:
        job_id = "live-telemetry-test"
        runtime.database.create_job(
            job_id=job_id, project_id=project.id, workflow="consult",
            profile="balanced", prompt="hi",
            execution_plan_json=json.dumps(execution_plan_data(plan)),
            context_key=job_id,
        )
        runtime.database.merge_job_telemetry(job_id, telemetry)
        view = runtime.database.job(job_id)
        result = runtime.live_result_metadata(view)
        assert "telemetry" in result
        assert result["telemetry"]["total_input_tokens"]["value"] == 250
        assert result["telemetry"]["context_used_tokens"]["value"] == 1500
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_live_result_metadata_historical_empty_metadata(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    _two_target_config(config_path)
    runtime = Runtime(load_config(config_path))
    root = tmp_path / "project"
    root.mkdir()
    project = register_project(runtime, str(root), "project")
    plan = resolve_execution_plan("consult", runtime.catalog, "balanced")
    try:
        job_id = "live-historical-test"
        runtime.database.create_job(
            job_id=job_id, project_id=project.id, workflow="consult",
            profile="balanced", prompt="hi",
            execution_plan_json=json.dumps(execution_plan_data(plan)),
            context_key=job_id,
        )
        view = runtime.database.job(job_id)
        result = runtime.live_result_metadata(view)
        assert "telemetry" in result
        assert result["telemetry"]["completeness"] == "unavailable"
        assert result["execution"]["model"] is None
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_submit_rejects_foreign_profile_and_stale_revision_tokens_without_insert(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    _two_target_config(config_path)
    runtime = Runtime(load_config(config_path))
    root = tmp_path / "project"
    root.mkdir()
    project = register_project(runtime, str(root), "project")
    original = resolve_execution_plan("consult", runtime.catalog, "balanced")
    token = next_target_token(runtime.catalog.config_revision, project.id, "balanced", "consult", original.targets[1])
    try:
        for selected_profile in ("alternate",):
            with pytest.raises(OrchestrationError) as raised:
                await runtime.submit(project.id, "consult", "x", profile=selected_profile, next_target=token)
            assert raised.value.code == "invalid_request"
            assert raised.value.next_action == "Resubmit without next_target."
            assert runtime.database.jobs(project.id) == []
        config_path.write_text(config_path.read_text(encoding="utf-8").replace('backend = "claude"', 'backend = "claude"\nmodel = "changed"'), encoding="utf-8")
        with pytest.raises(OrchestrationError) as raised:
            await runtime.submit(project.id, "consult", "x", next_target=token)
        assert raised.value.code == "invalid_request"
        assert raised.value.next_action == "Resubmit without next_target."
        assert runtime.database.jobs(project.id) == []
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_retry_all_open_leaves_failed_job_untouched(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    _two_target_config(config_path)
    runtime = Runtime(load_config(config_path))
    root = tmp_path / "project"
    root.mkdir()
    project = register_project(runtime, str(root), "project")
    plan = resolve_execution_plan("consult", runtime.catalog, "balanced")
    job_id = "retry-open"
    metadata = JobResultMetadata(
        failure=FailureMetadata(kind="retryable"),
        retry=RetryMetadata(retryable=False, next_target=None),
    )
    runtime.database.create_job(job_id=job_id, project_id=project.id, workflow="consult", profile="balanced", prompt="x", execution_plan_json=json.dumps(execution_plan_data(plan)), context_key="retry-open")
    runtime.database.record_job_attempt(job_id, "a")
    runtime.database.finish_job(job_id, "failed", target_id="a", metadata=metadata)
    for target in plan.targets:
        runtime.database._connection.execute("INSERT OR REPLACE INTO target_health(target_id, consecutive_failures, circuit_open_until, cooldown_s, probe_job_id) VALUES (?, 1, '2999-01-01T00:00:00+00:00', 60, '')", (target_execution_key(target),))
    runtime.database._connection.commit()
    prior = runtime.database.job_record(job_id)
    events = runtime.database.events(job_id)
    try:
        with pytest.raises(OrchestrationError) as raised:
            await runtime.retry(job_id)
        assert raised.value.code == "targets_unavailable"
        assert raised.value.retryable is True and type(raised.value.retry_after_s) is int
        after = runtime.database.job_record(job_id)
        assert after["state"] == prior["state"] == "failed"
        assert after["attempts"] == prior["attempts"]
        assert runtime.database.events(job_id) == events
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_retry_after_uses_reloaded_cooldown_for_held_probes(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    _two_target_config(config_path)
    content = config_path.read_text(encoding="utf-8").replace('default_profile = "balanced"', 'default_profile = "balanced"\nbreaker_base_cooldown_s = 7')
    config_path.write_text(content, encoding="utf-8")
    runtime = Runtime(load_config(config_path))
    root = tmp_path / "project"
    root.mkdir()
    project = register_project(runtime, str(root), "project")
    plan = resolve_execution_plan("consult", runtime.catalog, "balanced")
    job_id = "retry-reloaded-cooldown"
    runtime.database.create_job(job_id=job_id, project_id=project.id, workflow="consult", profile="balanced", prompt="x", execution_plan_json=json.dumps(execution_plan_data(plan)), context_key=job_id)
    runtime.database.finish_job(job_id, "failed")
    changed = config_path.read_text(encoding="utf-8").replace("breaker_base_cooldown_s = 7", "breaker_base_cooldown_s = 23")
    config_path.write_text(changed, encoding="utf-8")
    runtime.publish_configuration()
    for target in plan.targets:
        runtime.database._connection.execute("INSERT OR REPLACE INTO target_health(target_id, consecutive_failures, circuit_open_until, cooldown_s, probe_job_id) VALUES (?, 1, '', 0, 'held-probe')", (target_execution_key(target),))
    runtime.database._connection.commit()
    try:
        with pytest.raises(OrchestrationError) as raised:
            await runtime.retry(job_id)
        assert raised.value.code == "targets_unavailable"
        assert raised.value.retry_after_s == 23
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_submit_with_next_target_executes_second_candidate(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    _two_target_config(config_path)
    runtime = Runtime(load_config(config_path))
    root = tmp_path / "project"
    root.mkdir()
    project = register_project(runtime, str(root), "project")
    plan = resolve_execution_plan("consult", runtime.catalog, "balanced")
    token = next_target_token(runtime.catalog.config_revision, project.id, "balanced", "consult", plan.targets[1])
    executed = []
    class Drivers:
        @staticmethod
        def supports_structured_streaming(_target): return True
        @staticmethod
        def available(_target): return True
        async def execute(self, *, target, **kwargs):
            executed.append(target.id)
            from refract.drivers import DriverResult
            return DriverResult("SUCCESS", "session-b", "done", "", "")
    runtime.drivers = Drivers()
    await runtime.start()
    try:
        submitted = await runtime.submit(project.id, "consult", "run b", next_target=token)
        job = await runtime.wait(submitted.job_id, 5)
        assert job.state == "succeeded"
        assert executed == ["b"]
        assert runtime.database.job_record(job.id)["target_id"] == "b"
    finally:
        await runtime.close()


def _two_target_config(path) -> None:
    path.write_text('''[daemon]\ndefault_profile = "balanced"\n\n[[targets]]\nid = "a"\nbackend = "codex"\n\n[[targets]]\nid = "b"\nbackend = "claude"\n\n[profiles.balanced]\nconsult = ["a", "b"]\nreview = ["a", "b"]\n\n[profiles.alternate]\nconsult = ["a", "b"]\nreview = ["a", "b"]\n''', encoding="utf-8")


def _config(path) -> None:
    path.write_text('''[daemon]
default_profile = "balanced"

[[targets]]
id = "primary"
backend = "codex"

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
''', encoding="utf-8")


@pytest.mark.asyncio
async def test_failed_reload_preserves_catalog_health_and_blocks_submission(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    config_path = home / "config.toml"
    _config(config_path)
    runtime = Runtime(load_config(config_path))
    project_root = tmp_path / "project"
    project_root.mkdir()
    project = register_project(runtime, str(project_root), "project")
    original = runtime.catalog
    original_revision = original.config_revision

    config_path.write_text("[daemon\ndefault_profile =", encoding="utf-8")
    with pytest.raises(OrchestrationError):
        await runtime.submit(project.id, "consult", "question")

    assert runtime.catalog is original
    health = runtime.config_health
    assert not health.valid
    assert health.last_known_good_revision == original_revision
    assert health.revision != original_revision
    with pytest.raises(OrchestrationError):
        await runtime.submit(project.id, "consult", "question")
    await runtime.close()


@pytest.mark.asyncio
async def test_configuration_error_does_not_expose_secret(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    path = home / "config.toml"
    _config(path)
    runtime = Runtime(load_config(path))
    project_root = tmp_path / "project"
    project_root.mkdir()
    project = register_project(runtime, str(project_root), "project")
    secret = "SUPER_SECRET_CONFIGURATION_VALUE"
    path.write_text(path.read_text(encoding="utf-8").rstrip() + f'\n[logging]\nlevel = "{secret}"\n', encoding="utf-8")

    with pytest.raises(OrchestrationError) as raised:
        await runtime.submit(project.id, "consult", "question")

    assert secret not in str(raised.value)
    assert secret not in runtime.config_health.latest_error
    await runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_kind", ["profile", "workflow"])
async def test_configuration_identifiers_do_not_leak_from_errors(tmp_path, invalid_kind) -> None:
    home = tmp_path / "home"
    home.mkdir()
    path = home / "config.toml"
    _config(path)
    runtime = Runtime(load_config(path))
    project_root = tmp_path / "project"
    project_root.mkdir()
    project = register_project(runtime, str(project_root), "project")
    content = path.read_text(encoding="utf-8")
    if invalid_kind == "profile":
        content += '[profiles."SECRET_PROFILE"]\n'
    else:
        content = content.replace(
            'consult = "primary"', 'SECRET_WORKFLOW = "primary"'
        )
    path.write_text(content, encoding="utf-8")

    with pytest.raises(OrchestrationError) as raised:
        await runtime.submit(project.id, "consult", "question")

    assert "SECRET_" not in str(raised.value)
    assert "SECRET_" not in runtime.config_health.latest_error
    await runtime.close()


@pytest.mark.asyncio
async def test_new_job_records_global_revision(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    path = home / "config.toml"
    _config(path)
    runtime = Runtime(load_config(path))
    project_root = tmp_path / "project"
    project_root.mkdir()
    project = register_project(runtime, str(project_root), "project")

    submission = await runtime.submit(project.id, "consult", "question")

    job = runtime.database.job(submission.job_id)
    assert job and job.config_revision == hashlib.sha256(path.read_bytes()).hexdigest()
    await runtime.close()


def test_initial_health_is_seeded(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    path = home / "config.toml"
    _config(path)
    catalog = load_config(path)
    runtime = Runtime(catalog)
    health = runtime.config_health
    assert health.valid
    assert health.revision == hashlib.sha256(path.read_bytes()).hexdigest()
    assert health.last_known_good_revision == health.revision
    runtime.database.close()


# ---------------------------------------------------------------------------
# Configuration publication boundary (dashboard target-profile CRUD phase 1).
# ---------------------------------------------------------------------------


def test_publish_configuration_refreshes_catalog_and_executor(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    path = home / "config.toml"
    _config(path)
    runtime = Runtime(load_config(path))
    try:
        previous = runtime.catalog
        path.write_text(
            path.read_text(encoding="utf-8") + "\n# refreshed\n",
            encoding="utf-8",
        )
        runtime.publish_configuration()
        assert runtime.catalog is not previous
        assert runtime.target_executor.config is runtime.catalog
        health = runtime.config_health
        assert health.valid
        assert health.revision == hashlib.sha256(path.read_bytes()).hexdigest()
    finally:
        runtime.database.close()

def test_catalog_reload_after_manual_edit_refreshes_executor(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    path = home / "config.toml"
    _config(path)
    runtime = Runtime(load_config(path))
    try:
        path.write_text(path.read_text(encoding="utf-8") + "\n# manual edit\n", encoding="utf-8")
        runtime.publish_configuration()
        assert runtime.target_executor.config is runtime.catalog
        assert runtime.target_executor.config.config_revision == hashlib.sha256(path.read_bytes()).hexdigest()
    finally:
        runtime.database.close()

@pytest.mark.asyncio
async def test_catalog_cache_reuses_parses_and_invalidates_on_changes(tmp_path, monkeypatch) -> None:
    import refract.runtime as module

    path = tmp_path / "config.toml"
    _config(path)
    runtime = Runtime(load_config(path))
    root = tmp_path / "project"
    root.mkdir()
    project = register_project(runtime, str(root), "project")
    counts = {"global": 0, "project": 0}
    global_loader = module.load_config
    project_loader = module.load_project_config

    def global_load(*args):
        counts["global"] += 1
        return global_loader(*args)

    def project_load(*args):
        counts["project"] += 1
        return project_loader(*args)

    monkeypatch.setattr(module, "load_config", global_load)
    monkeypatch.setattr(module, "load_project_config", project_load)
    try:
        first = runtime.catalog_for_project(project.id)
        assert runtime.catalog_for_project(project.id) is first
        await runtime.submit(project.id, "consult", "cached")
        assert counts == {"global": 1, "project": 1}
        path.write_text(path.read_text() + "\n# changed\n")
        second = runtime.catalog_for_project(project.id)
        assert second is not first
        assert counts == {"global": 2, "project": 2}
        local = root / ".refract" / "config.toml"
        local.parent.mkdir()
        local.write_text('[profiles.balanced]\nextends = "balanced"\n')
        third = runtime.catalog_for_project(project.id)
        assert third is not second
        assert runtime.catalog_for_project(project.id) is third
        local.unlink()
        assert runtime.catalog_for_project(project.id) is not third
        assert counts == {"global": 2, "project": 4}
        path.write_text("invalid TOML [")
        for _ in range(2):
            with pytest.raises(OrchestrationError):
                runtime.catalog_for_project(project.id)
        assert not runtime.config_health.valid
        _config(path)
        assert runtime.catalog_for_project(project.id)
        assert runtime.config_health.valid
    finally:
        await runtime.close()


def test_config_mutation_service_exposes_shared_lock(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    path = home / "config.toml"
    _config(path)
    runtime = Runtime(load_config(path))
    try:
        assert runtime.mutations.lock is not None
        # The lock is re-entrant so reloads inside a commit do not deadlock.
        with runtime.mutations.lock:
            runtime.publish_configuration()
            runtime.publish_configuration()
    finally:
        runtime.database.close()

@pytest.mark.asyncio
async def test_project_override_runtime_activation_and_plan_preservation(tmp_path) -> None:
    from refract.models import ProfileEditorData, WorkflowPolicyData

    home = tmp_path / "home"
    home.mkdir()
    path = home / "config.toml"
    _config(path)
    runtime = Runtime(load_config(path))
    project_root = tmp_path / "project"
    project_root.mkdir()
    project = register_project(runtime, str(project_root), "project")

    # Submit job 1 under initial configuration
    sub1 = await runtime.submit(project.id, "consult", "initial question")
    record1_before = runtime.database.job_record(sub1.job_id)
    assert record1_before is not None
    plan1_before = record1_before["execution_plan_json"]

    # Create project profile override without daemon restart
    _, new_override = runtime.mutations.create_project_override(
        project_root,
        ProfileEditorData(
            id="balanced",
            extends="balanced",
            workflows={"consult": WorkflowPolicyData(targets=["primary"], timeout_s=99)},
        ),
        expected_revision="",
    )

    # Runtime activation: project catalog immediately reflects the override
    proj_catalog = runtime.catalog_for_project_cached(project.id)
    assert proj_catalog.profiles["balanced"]["consult"].timeout_s == 99

    # Submit job 2 under updated override
    sub2 = await runtime.submit(project.id, "consult", "follow-up question")
    job2 = runtime.database.job(sub2.job_id)
    assert job2 is not None

    # Existing job 1 retains its original execution plan
    record1_after = runtime.database.job_record(sub1.job_id)
    assert record1_after is not None
    assert record1_after["execution_plan_json"] == plan1_before

    await runtime.close()


@pytest.mark.asyncio
async def test_runtime_start_prunes_expired_terminal_transcripts_without_pruning_active_jobs(tmp_path) -> None:
    from datetime import datetime, timedelta, timezone

    home = tmp_path / "home"
    home.mkdir()
    path = home / "config.toml"
    _config(path)
    runtime = Runtime(load_config(path))
    project_root = tmp_path / "project"
    project_root.mkdir()
    project = register_project(runtime, str(project_root), "project")

    # 1. Expired terminal job (10 days old)
    old_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    runtime.database.create_job(
        job_id="job-expired-term",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="p1",
        execution_plan_json="{}",
        context_key="c1",
    )
    with runtime.database._connection:
        runtime.database._connection.execute(
            "UPDATE jobs SET state='succeeded', updated_at=? WHERE id='job-expired-term'",
            (old_ts,),
        )
    runtime.database.append_stream_events("job-expired-term", [{
        "kind": "assistant.text.delta",
        "entity_id": "msg-1",
        "data": {"text": "old terminal transcript"},
    }])

    # 2. Recent terminal job (2 days old)
    recent_ts = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    runtime.database.create_job(
        job_id="job-recent-term",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="p2",
        execution_plan_json="{}",
        context_key="c2",
    )
    with runtime.database._connection:
        runtime.database._connection.execute(
            "UPDATE jobs SET state='succeeded', updated_at=? WHERE id='job-recent-term'",
            (recent_ts,),
        )
    runtime.database.append_stream_events("job-recent-term", [{
        "kind": "assistant.text.delta",
        "entity_id": "msg-1",
        "data": {"text": "recent terminal transcript"},
    }])

    # 3. Active running job (10 days old) - should NOT be pruned despite being old
    runtime.database.create_job(
        job_id="job-old-running",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="p3",
        execution_plan_json="{}",
        context_key="c3",
    )
    with runtime.database._connection:
        runtime.database._connection.execute(
            "UPDATE jobs SET state='running', updated_at=? WHERE id='job-old-running'",
            (old_ts,),
        )
    runtime.database.append_stream_events("job-old-running", [{
        "kind": "assistant.text.delta",
        "entity_id": "msg-1",
        "data": {"text": "active running transcript"},
    }])

    # Verify initial stream data exists
    assert runtime.database.stream_high_water("job-expired-term") > 0
    assert runtime.database.stream_high_water("job-recent-term") > 0
    assert runtime.database.stream_high_water("job-old-running") > 0

    # Start runtime (triggers start retention cleanup)
    await runtime.start()

    # Expired terminal transcript is pruned
    assert runtime.database.stream_high_water("job-expired-term") == 0

    # Recent terminal and active running transcripts are preserved
    assert runtime.database.stream_high_water("job-recent-term") > 0
    # Note: runtime.start() interrupts active jobs upon restart, changing running -> interrupted,
    # but the stream events of active jobs prior to start were not pruned by the retention step!
    assert runtime.database.stream_high_water("job-old-running") > 0

    # All job records themselves remain intact
    assert runtime.database.job("job-expired-term") is not None
    assert runtime.database.job("job-recent-term") is not None
    assert runtime.database.job("job-old-running") is not None

    await runtime.close()


@pytest.mark.asyncio
async def test_stream_durable_reload_reconstructs_cursor_and_events(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    config_path = home / "config.toml"
    _config(config_path)
    runtime = Runtime(load_config(config_path))
    project_root = tmp_path / "project"
    project_root.mkdir()
    project = register_project(runtime, str(project_root), "project")
    job_id = "job-reload-test"
    runtime.database.create_job(
        job_id=job_id,
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="hello",
        execution_plan_json="{}",
        context_key="c1",
    )
    events = [
        {"kind": "assistant.message.started", "entity_id": "msg-1", "data": {}},
        {"kind": "assistant.text.delta", "entity_id": "msg-1", "data": {"text": "chunk 1"}},
        {"kind": "assistant.text.delta", "entity_id": "msg-1", "data": {"text": "chunk 2"}},
        {"kind": "assistant.message.completed", "entity_id": "msg-1", "data": {}},
    ]
    persisted = runtime.database.append_stream_events(job_id, events)
    expected_hw = persisted[-1].id
    expected_retained = persisted[0].id
    await runtime.close()

    reopened = Runtime(load_config(config_path))
    try:
        assert reopened.database.stream_high_water(job_id) == expected_hw
        assert reopened.database.stream_retained_from(job_id) == expected_retained
        totals = reopened.database.stream_totals(job_id)
        assert totals.events == 4
        assert totals.bytes > 0
        replayed = reopened.database.stream_events(job_id, after=0)
        assert len(replayed) == 4
        assert [e.id for e in replayed] == [p.id for p in persisted]
        assert [e.kind for e in replayed] == [e["kind"] for e in events]
        assert replayed[1].data["text"] == "chunk 1"
        assert replayed[2].data["text"] == "chunk 2"
    finally:
        await reopened.close()


@pytest.mark.asyncio
async def test_stream_truncation_marker_durable_across_reload(tmp_path) -> None:
    from refract.streaming import StreamRecorder

    home = tmp_path / "home"
    home.mkdir()
    config_path = home / "config.toml"
    _config(config_path)
    runtime = Runtime(load_config(config_path))
    project_root = tmp_path / "project"
    project_root.mkdir()
    project = register_project(runtime, str(project_root), "project")
    job_id = "job-trunc-reload"
    runtime.database.create_job(
        job_id=job_id,
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="hello",
        execution_plan_json="{}",
        context_key="c1",
    )
    recorder = StreamRecorder(
        database=runtime.database,
        job_id=job_id,
        attempt=1,
        target_id="primary",
        backend="codex",
        max_job_bytes=100,
    )
    await recorder.record({"kind": "assistant.text.delta", "entity_id": "msg-1", "data": {"text": "x" * 60}})
    await recorder.record({"kind": "assistant.text.delta", "entity_id": "msg-1", "data": {"text": "y" * 60}})
    await recorder.close()

    assert runtime.database.stream_is_truncated(job_id) is True
    await runtime.close()

    reopened = Runtime(load_config(config_path))
    try:
        assert reopened.database.stream_is_truncated(job_id) is True
        new_recorder = StreamRecorder(
            database=reopened.database,
            job_id=job_id,
            attempt=1,
            target_id="primary",
            backend="codex",
        )
        assert new_recorder.truncated is True
        await new_recorder.record({"kind": "assistant.text.delta", "entity_id": "msg-2", "data": {"text": "suppressed"}})
        await new_recorder.close()

        events = reopened.database.stream_events(job_id, after=0)
        assert not any(e.data.get("text") == "suppressed" for e in events)
        assert any(e.kind == "stream.truncated" for e in events)
    finally:
        await reopened.close()


@pytest.mark.asyncio
async def test_stream_persistence_failure_retains_prior_events(tmp_path) -> None:
    from refract.streaming import StreamRecorder

    home = tmp_path / "home"
    home.mkdir()
    config_path = home / "config.toml"
    _config(config_path)
    runtime = Runtime(load_config(config_path))
    project_root = tmp_path / "project"
    project_root.mkdir()
    project = register_project(runtime, str(project_root), "project")
    job_id = "job-persist-fail"
    runtime.database.create_job(
        job_id=job_id,
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="hello",
        execution_plan_json="{}",
        context_key="c1",
    )
    runtime.database.append_stream_events(job_id, [
        {"kind": "assistant.text.delta", "entity_id": "msg-1", "data": {"text": "safe before failure"}}
    ])
    assert runtime.database.stream_high_water(job_id) > 0

    recorder = StreamRecorder(
        database=runtime.database,
        job_id=job_id,
        attempt=1,
        target_id="primary",
        backend="codex",
    )

    def broken_append(*args, **kwargs):
        raise RuntimeError("simulated disk full error")

    runtime.database.append_stream_events = broken_append
    await recorder.record({"kind": "assistant.text.delta", "entity_id": "msg-2", "data": {"text": "will fail"}})
    await recorder.flush()

    assert recorder.failed is True
    del runtime.database.append_stream_events
    events = runtime.database.stream_events(job_id, after=0)
    assert len(events) == 1
    assert events[0].data["text"] == "safe before failure"
    lifecycle = runtime.database.events(job_id)
    assert any(e.get("kind") == "stream.persistence_failed" for e in lifecycle)
    await runtime.close()


@pytest.mark.asyncio
async def test_stream_historical_fallback_for_jobs_without_events(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    config_path = home / "config.toml"
    _config(config_path)
    runtime = Runtime(load_config(config_path))
    project_root = tmp_path / "project"
    project_root.mkdir()
    project = register_project(runtime, str(project_root), "project")
    job_id = "job-legacy"
    runtime.database.create_job(
        job_id=job_id,
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="hello",
        execution_plan_json="{}",
        context_key="c1",
    )
    runtime.database.finish_job(job_id, "succeeded", text="authoritative historical result")

    assert runtime.database.stream_high_water(job_id) == 0
    assert runtime.database.stream_retained_from(job_id) == 0
    assert runtime.database.stream_events(job_id, after=0) == []
    assert runtime.database.stream_is_truncated(job_id) is False
    job = runtime.database.job(job_id)
    assert job is not None
    assert job.result.text == "authoritative historical result"
    await runtime.close()


def test_resolve_project_is_canonical_idempotent_and_handles_alias_collisions(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    _config(config_path)
    runtime = Runtime(load_config(config_path))
    first_root = tmp_path / "one" / "shared"
    second_root = tmp_path / "two" / "shared"
    first_root.mkdir(parents=True)
    second_root.mkdir(parents=True)
    try:
        first = runtime.resolve_project(str(first_root))
        symlink_root = tmp_path / "shared-link"
        symlink_root.symlink_to(first_root, target_is_directory=True)
        repeated = runtime.resolve_project(str(symlink_root), alias="ignored-alias")
        second = runtime.resolve_project(str(second_root))

        assert repeated.id == first.id
        assert repeated.alias == first.alias == "shared"
        assert repeated.root == first_root.resolve().as_posix()
        assert second.alias == "shared-2"

        explicit_root = tmp_path / "explicit"
        explicit_root.mkdir()
        with pytest.raises(OrchestrationError) as raised:
            runtime.resolve_project(str(explicit_root), alias="shared")
        assert raised.value.code == "alias_taken"
    finally:
        runtime.database.close()

def test_resolve_project_rereads_concurrent_root_winner(tmp_path, monkeypatch) -> None:
    import sqlite3

    config_path = tmp_path / "config.toml"
    _config(config_path)
    runtime = Runtime(load_config(config_path))
    root = tmp_path / "raced-root"
    root.mkdir()
    original_upsert = runtime.database.upsert_project
    simulated_race = False

    def race_on_root(**kwargs):
        nonlocal simulated_race
        if kwargs["root"] == root.resolve().as_posix() and not simulated_race:
            simulated_race = True
            winner = original_upsert(
                project_id="concurrent-winner",
                alias=kwargs["alias"],
                root=kwargs["root"],
            )
            raise sqlite3.IntegrityError("UNIQUE constraint failed: projects.root")
        return original_upsert(**kwargs)

    monkeypatch.setattr(runtime.database, "upsert_project", race_on_root)
    try:
        project = runtime.resolve_project(str(root))
        assert project.id == "concurrent-winner"
        assert runtime.database.project("concurrent-winner").root == root.resolve().as_posix()
    finally:
        runtime.database.close()

def test_resolve_project_preserves_alias_of_concurrent_canonical_winner(tmp_path, monkeypatch) -> None:
    from refract.database import Database

    config_path = tmp_path / "config.toml"
    _config(config_path)
    runtime = Runtime(load_config(config_path))
    other = Database(runtime.config.database_path)
    root = tmp_path / "real-race"
    root.mkdir()
    original_projects = runtime.database.projects
    inserted = False

    def insert_winner_after_stale_read():
        nonlocal inserted
        rows = original_projects()
        if not inserted:
            inserted = True
            other.upsert_project(project_id="race-winner", alias="winner", root=root.resolve().as_posix())
        return rows

    monkeypatch.setattr(runtime.database, "projects", insert_winner_after_stale_read)
    try:
        resolved = runtime.resolve_project(str(root), alias="loser")
        stored = other.project("race-winner")
        assert resolved.id == "race-winner"
        assert resolved.alias == "winner"
        assert stored is not None and stored.alias == "winner"
    finally:
        other.close()
        runtime.database.close()


def test_target_execution_key_matches_literal_pre_change_fixture() -> None:
    from refract.config import TargetConfig
    from refract.planning import target_execution_key

    # Exact historical key fixture before Phase 1
    target_plain = TargetConfig(id="primary", backend="codex")
    assert target_execution_key(target_plain) == "primary:fcb7f648a676a587"

    target_with_args = TargetConfig(
        id="native-with-custom-args",
        backend="pi",
        isolated=True,
        read_only=True,
        args=("--verbose", "--system-prompt", "advisory only"),
    )
    assert target_execution_key(target_with_args) == "native-with-custom-args:66e11d34a73875df"

    # Adding or modifying retry_policy produces the EXACT same historical key
    target_with_retry = TargetConfig(id="primary", backend="codex", retry_policy="transient")
    assert target_execution_key(target_with_retry) == "primary:fcb7f648a676a587"

    target_with_other_retry = TargetConfig(id="primary", backend="codex", retry_policy="aggressive")
    assert target_execution_key(target_with_other_retry) == "primary:fcb7f648a676a587"


def test_retry_only_configuration_changes_preserve_existing_sessions(tmp_path) -> None:
    from refract.planning import target_execution_key

    config_path = tmp_path / "config.toml"
    _config(config_path)
    runtime = Runtime(load_config(config_path))
    root = tmp_path / "project"
    root.mkdir()
    project = register_project(runtime, str(root), "project")
    try:
        target_initial = runtime.catalog.targets[0]
        key_initial = target_execution_key(target_initial)
        runtime.database._upsert_session(
            project_id=project.id,
            context_key="ctx_1",
            role="implement",
            target_id=target_initial.id,
            target_key=key_initial,
            lane="",
            session_id="sess_historical_123",
            clear_sessions=False,
        )
        assert runtime.database.session(project.id, "ctx_1", "implement", key_initial) == "sess_historical_123"

        # Reconfigure target with retryPolicy = "transient"
        config_path.write_text(
            """[daemon]
default_profile = "balanced"

[retryPolicies.transient]
retryAttempt = 2
errorCodes = ["rate_limit"]

[[targets]]
id = "primary"
backend = "codex"
retryPolicy = "transient"

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
""",
            encoding="utf-8",
        )
        runtime.publish_configuration()
        target_reconfigured = runtime.catalog.targets[0]
        key_reconfigured = target_execution_key(target_reconfigured)
        assert key_reconfigured == key_initial
        assert runtime.database.session(project.id, "ctx_1", "implement", key_reconfigured) == "sess_historical_123"
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_manual_retry_receives_fresh_policy_budget_with_cumulative_attempts(tmp_path) -> None:
    from dataclasses import replace
    from refract.config import RetryPolicy, TargetConfig, TargetSelection
    from refract.drivers import DriverResult
    from tests.orchestration_helpers import FakeDrivers, config, repository

    root = repository(tmp_path)
    base = config(tmp_path / "home")

    policy = RetryPolicy(1, ("rate_limit",), ())
    catalog = replace(
        base,
        retry_policies={"transient": policy},
        targets=(TargetConfig(id="primary", backend="codex", retry_policy="transient"),),
        profiles={"balanced": {"implement": TargetSelection(("primary",)), "review": TargetSelection(("primary",)), "consult": TargetSelection(("primary",))}},
    )

    class ManualRetrySequenceDrivers(FakeDrivers):
        def __init__(self):
            super().__init__()
            self.invocations = []

        def supports_structured_streaming(self, target):
            return True

        async def execute(self, *, target, **kwargs):
            self.invocations.append(len(self.invocations) + 1)
            attempt_idx = len(self.invocations)
            if attempt_idx in {1, 2, 3}:
                return DriverResult("RETRYABLE", "", "", f"transient {attempt_idx}", "rate_limit")
            return DriverResult("SUCCESS", "sess-manual", "manual recovery done", "", "")

    drivers = ManualRetrySequenceDrivers()
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        sub = await runtime.submit(project.id, "implement", "manual retry budget test")
        job = await runtime.wait(sub.job_id, 10)
        assert job.state == "failed"
        assert job.attempts == 2
        assert len(drivers.invocations) == 2

        # Explicit manual retry gets fresh policy budget
        await runtime.retry(job.id)
        job2 = await runtime.wait(job.id, 10)
        assert job2.state == "succeeded"
        assert job2.attempts == 4
        assert len(drivers.invocations) == 4
    finally:
        await runtime.close()


def test_live_result_metadata_dynamic_routing_and_context_overflow(tmp_path) -> None:
    from refract.models import JobView, JobResult
    from refract.result_metadata import JobResultMetadata, ExecutionMetadata, FailureMetadata, RetryMetadata

    config_path = tmp_path / "config.toml"
    _config(config_path)
    runtime = Runtime(load_config(config_path))
    try:
        # 1. Success job
        succ_meta = JobResultMetadata(execution=ExecutionMetadata(model="m1", duration_ms=10))
        job_succ = JobView(
            id="j1", project_id="p1", workflow="consult", profile="balanced",
            state="succeeded", context_key="c1", created_at="now", updated_at="now",
            result=JobResult(metadata=succ_meta),
        )
        live_succ = runtime.live_result_metadata(job_succ)
        assert set(live_succ) == {"execution", "failure", "retry", "telemetry"}
        assert live_succ["retry"] == {"retryable": None, "next_target": None}

        # 2. Context overflow job
        overflow_meta = JobResultMetadata(
            failure=FailureMetadata(kind="context_overflow"),
            retry=RetryMetadata(retryable=True, next_target=None),
        )
        job_overflow = JobView(
            id="j2", project_id="p1", workflow="consult", profile="balanced",
            state="failed", context_key="c1", created_at="now", updated_at="now",
            result=JobResult(metadata=overflow_meta),
        )
        live_overflow = runtime.live_result_metadata(job_overflow)
        assert set(live_overflow) == {"execution", "failure", "retry", "telemetry"}
        assert live_overflow["failure"]["kind"] == "context_overflow"
        assert live_overflow["retry"] == {"retryable": True, "next_target": None}
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_runtime_tracer_lifecycle_start_and_close(tmp_path) -> None:
    from unittest.mock import MagicMock
    from refract.observability import Tracer

    config_path = tmp_path / "config.toml"
    _config(config_path)
    runtime = Runtime(load_config(config_path))

    await runtime.start()
    assert isinstance(runtime.tracer, Tracer)
    original_tracer = runtime.tracer

    mock_flush = MagicMock()
    mock_shutdown = MagicMock()
    original_tracer.flush = mock_flush  # type: ignore[method-assign]
    original_tracer.shutdown = mock_shutdown  # type: ignore[method-assign]

    await runtime.close()
    mock_flush.assert_called_once()
    mock_shutdown.assert_called_once()


def test_runtime_publish_configuration_rebuilds_tracer_on_langfuse_change(tmp_path, monkeypatch) -> None:
    from unittest.mock import MagicMock

    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    home = tmp_path / "home"
    home.mkdir()
    config_path = home / "config.toml"
    _config(config_path)
    runtime = Runtime(load_config(config_path))
    try:
        initial_tracer = runtime.tracer

        # Non-langfuse modification does not rebuild tracer
        config_path.write_text(config_path.read_text(encoding="utf-8") + "\n# comment\n", encoding="utf-8")
        runtime.publish_configuration()
        assert runtime.tracer is initial_tracer

        # Langfuse modification flushes old client and rebuilds tracer
        mock_old_flush = MagicMock()
        mock_old_shutdown = MagicMock()
        initial_tracer.flush = mock_old_flush  # type: ignore[method-assign]
        initial_tracer.shutdown = mock_old_shutdown  # type: ignore[method-assign]

        config_path.write_text(
            config_path.read_text(encoding="utf-8")
            + "\n[langfuse]\nenabled = true\nsample_rate = 0.5\n",
            encoding="utf-8",
        )
        with runtime.mutations.lock:
            runtime._publish_configuration_locked()

        mock_old_flush.assert_called_once()
        mock_old_shutdown.assert_called_once()
        assert runtime.tracer is not initial_tracer
        assert runtime.tracer.config.enabled is True
        assert runtime.tracer.config.sample_rate == 0.5
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_runtime_real_tracer_thread_identity_and_close_order(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("langfuse")
    import threading
    from unittest.mock import MagicMock
    from refract.observability import Tracer

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")

    config_path = tmp_path / "config.toml"
    _config(config_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8") + "\n[langfuse]\nenabled = true\n",
        encoding="utf-8",
    )
    catalog = load_config(config_path)
    runtime = Runtime(catalog)

    # 1. Runtime.__init__ must only initialize an inactive holder, even when config is enabled
    assert runtime.tracer.is_active is False

    loop_thread_id = threading.get_ident()
    call_order: list[tuple[str, int]] = []

    # 2. Runtime.start builds configured client off event loop thread
    await runtime.start()
    assert runtime.tracer.is_active is True
    first_tracer = runtime.tracer

    first_tracer_flush = MagicMock(side_effect=lambda: call_order.append(("flush", threading.get_ident())))
    first_tracer_shutdown = MagicMock(side_effect=lambda: call_order.append(("shutdown", threading.get_ident())))
    original_flush = first_tracer.flush
    original_shutdown = first_tracer.shutdown
    first_tracer.flush = lambda: (first_tracer_flush(), original_flush())  # type: ignore[method-assign]
    first_tracer.shutdown = lambda: (first_tracer_shutdown(), original_shutdown())  # type: ignore[method-assign]

    # Exercise tracer replacement without restarting the unrelated scheduler.
    await runtime.close()
    runtime = Runtime(catalog)
    await runtime.start()
    assert runtime.tracer is not first_tracer
    first_tracer_flush.assert_called_once()
    first_tracer_shutdown.assert_called_once()
    assert len(call_order) == 2
    assert call_order[0][0] == "flush"
    assert call_order[1][0] == "shutdown"
    assert call_order[0][1] != loop_thread_id
    assert call_order[1][1] != loop_thread_id

    # 4. Runtime.close calls flush then shutdown via run_sync off the event loop thread
    call_order.clear()
    second_tracer = runtime.tracer
    second_tracer_flush = MagicMock(side_effect=lambda: call_order.append(("flush", threading.get_ident())))
    second_tracer_shutdown = MagicMock(side_effect=lambda: call_order.append(("shutdown", threading.get_ident())))
    original_flush = second_tracer.flush
    original_shutdown = second_tracer.shutdown
    second_tracer.flush = lambda: (second_tracer_flush(), original_flush())  # type: ignore[method-assign]
    second_tracer.shutdown = lambda: (second_tracer_shutdown(), original_shutdown())  # type: ignore[method-assign]

    await runtime.close()
    second_tracer_flush.assert_called_once()
    second_tracer_shutdown.assert_called_once()
    assert len(call_order) == 2
    assert call_order[0][0] == "flush"
    assert call_order[1][0] == "shutdown"
    assert call_order[0][1] != loop_thread_id
    assert call_order[1][1] != loop_thread_id
