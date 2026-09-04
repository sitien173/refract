from __future__ import annotations

import hashlib

import pytest

from openmcp.config import load_config
from openmcp.runtime import OrchestrationError, Runtime


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
    project = runtime.register_project(str(project_root), "project")
    original = runtime.catalog
    original_revision = original.config_revision

    config_path.write_text("[daemon\ndefault_profile =", encoding="utf-8")
    with pytest.raises(OrchestrationError):
        await runtime.submit(project.id, "consult", "question")

    assert runtime.catalog is original
    health = runtime.configuration_health()
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
    project = runtime.register_project(str(project_root), "project")
    secret = "SUPER_SECRET_CONFIGURATION_VALUE"
    path.write_text(path.read_text(encoding="utf-8").rstrip() + f'\n[logging]\nlevel = "{secret}"\n', encoding="utf-8")

    with pytest.raises(OrchestrationError) as raised:
        await runtime.submit(project.id, "consult", "question")

    assert secret not in str(raised.value)
    assert secret not in runtime.configuration_health().latest_error
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
    project = runtime.register_project(str(project_root), "project")
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
    assert "SECRET_" not in runtime.configuration_health().latest_error
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
    project = runtime.register_project(str(project_root), "project")

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
    health = runtime.configuration_health()
    assert health.valid
    assert health.revision == hashlib.sha256(path.read_bytes()).hexdigest()
    assert health.last_known_good_revision == health.revision
    runtime.database.close()
