"""Transaction-boundary tests for safe TOML configuration mutation."""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
import threading
from pathlib import Path

import pytest
import tomlkit

import openmcp.config_mutation

from openmcp.config import load_config
from openmcp.config_mutation import (
    ConfigurationMutationError,
    ConfigurationMutationService,
    commit_bytes,
    create_bytes,
    load_source,
)
from openmcp.runtime import Runtime
from tests.orchestration_helpers import config as make_config

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _global_text() -> str:
    return """# operator comment
[daemon]
default_profile = "balanced"

[[targets]]
id = "primary"
backend = "codex"
profile = "legacy-profile"
max_concurrency = 2

[[targets]]
id = "fallback"
backend = "pi"
isolated = true

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
"""


def _global_source(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir(parents=True)
    path = home / "config.toml"
    path.write_text(_global_text(), encoding="utf-8")
    return path


def _runtime_for(tmp_path: Path) -> Runtime:
    source = _global_source(tmp_path)
    return Runtime(load_config(source))


def _revision(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _empty_project_document() -> tomlkit.TOMLDocument:
    doc = tomlkit.document()
    profiles = tomlkit.table()
    quality = tomlkit.table()
    quality["consult"] = "primary"
    profiles["quality"] = quality
    doc["profiles"] = profiles
    return doc


def _runtime_with_project(tmp_path: Path) -> tuple[Runtime, Path]:
    runtime = _runtime_for(tmp_path)
    project_root = tmp_path / "project"
    project_root.mkdir()
    runtime.register_project(str(project_root), "project")
    return runtime, project_root


# ---------------------------------------------------------------------------
# Preservation: unrelated regions, comments, ordering, quoting, shorthand,
# and legacy keys survive a surgical edit.
# ---------------------------------------------------------------------------


def test_unrelated_regions_remain_byte_identical(tmp_path) -> None:
    source = _global_source(tmp_path)
    original = source.read_bytes()
    service = ConfigurationMutationService(object())
    document = service.read_document(load_source(source))
    target = service.find_target(document, "primary")
    assert target is not None
    service.set_target_value(target, "max_concurrency", 5)

    serialized = service.candidate_bytes(document)

    # Unrelated regions outside the edited table stay byte-for-byte identical.
    assert b'[daemon]\ndefault_profile = "balanced"' in serialized
    assert b'# operator comment' in serialized
    # The untouched second target block is byte identical.
    fallback_block = original.split(b"[[targets]]")[2]
    assert fallback_block in serialized


def test_comments_ordering_and_legacy_keys_are_preserved(tmp_path) -> None:
    source = _global_source(tmp_path)
    service = ConfigurationMutationService(object())
    document = service.read_document(load_source(source))
    target = service.find_target(document, "primary")
    service.set_target_value(target, "model", "new-model")

    serialized = service.candidate_bytes(document).decode("utf-8")

    assert "# operator comment" in serialized
    assert serialized.count("[[targets]]") == 2
    # Legacy key spelling is not normalized away.
    assert 'profile = "legacy-profile"' in serialized
    # Ordering: primary table still precedes fallback.
    assert serialized.index("id = \"primary\"") < serialized.index("id = \"fallback\"")


def test_multiline_string_quoting_preserved(tmp_path) -> None:
    source = _global_source(tmp_path)
    text = source.read_text(encoding="utf-8")
    text = text.replace(
        'backend = "codex"\nprofile = "legacy-profile"',
        'backend = "codex"\nsystem_prompt = """\noperator\nprompt\n"""',
    )
    source.write_text(text, encoding="utf-8")
    service = ConfigurationMutationService(object())
    document = service.read_document(load_source(source))
    target = service.find_target(document, "primary")
    service.set_target_value(target, "isolated", True)

    serialized = service.candidate_bytes(document).decode("utf-8")

    assert 'system_prompt = """' in serialized
    assert "operator\nprompt" in serialized


def test_profile_shorthand_and_forms_remain_preserved(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """[daemon]
default_profile = "balanced"

[[targets]]
id = "primary"
backend = "codex"

[[targets]]
id = "fallback"
backend = "pi"

[profiles.balanced]
implement = 'primary'
review = ["primary", "fallback"]
consult = { targets = ["primary"], max_attempts = 2, timeout_s = 60 }
""",
        encoding="utf-8",
    )
    service = ConfigurationMutationService(object())
    document = service.read_document(load_source(path))
    profile = service.find_profile(document, "balanced")
    assert profile is not None
    # Editing the consult policy mutates the existing inline table in place.
    service.set_workflow_policy(
        profile,
        "consult",
        targets=["fallback", "primary"],
        max_attempts=3,
        timeout_s=90,
    )

    serialized = service.candidate_bytes(document).decode("utf-8")

    # Untouched single-quoted shorthand keeps its literal style.
    assert "implement = 'primary'" in serialized
    # Untouched array shorthand keeps its form.
    assert 'review = ["primary", "fallback"]' in serialized
    # The edited inline policy remains a single-line inline table.
    assert (
        "consult = { targets = [\"fallback\", \"primary\"], max_attempts = 3, "
        "timeout_s = 90 }" in serialized
    )


def test_edited_shorthand_expands_only_the_edited_workflow(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """[daemon]
default_profile = "balanced"

[[targets]]
id = "primary"
backend = "codex"

[profiles.balanced]
implement = "primary"
review = "primary"
consult = { targets = ["primary"], max_attempts = 2, timeout_s = 60 }
""",
        encoding="utf-8",
    )
    service = ConfigurationMutationService(object())
    document = service.read_document(load_source(path))
    profile = service.find_profile(document, "balanced")
    # The implement shorthand must become an inline policy because the edit
    # adds max_attempts; the untouched review shorthand must remain a string.
    service.set_workflow_policy(
        profile, "implement", targets=["primary"], max_attempts=3, timeout_s=30
    )

    serialized = service.candidate_bytes(document).decode("utf-8")

    # Inline table renders without extra spaces by default; accept either form.
    assert (
        "implement = {targets = [\"primary\"], max_attempts = 3, timeout_s = 30}"
        in serialized
        or (
            "implement = { targets = [\"primary\"], max_attempts = 3, "
            "timeout_s = 30 }" in serialized
        )
    )
    assert 'review = "primary"' in serialized


def test_new_target_uses_backend_profile_only(tmp_path) -> None:
    source = _global_source(tmp_path)
    service = ConfigurationMutationService(object())
    document = service.read_document(load_source(source))
    table = service.target_table()
    table["id"] = "tertiary"
    table["backend"] = "codex"
    table["backend_profile"] = "balanced"
    document["targets"].append(table)

    serialized = service.candidate_bytes(document).decode("utf-8")

    assert 'backend_profile = "balanced"' in serialized
    assert 'profile = "legacy-profile"' in serialized  # original legacy stays
    assert serialized.count('backend_profile') == 1
    # The new table carries no legacy key.
    new_block = serialized.split("[[targets]]")[-1]
    assert 'backend_profile = "balanced"' in new_block
    assert 'profile = "legacy' not in new_block
    assert 'review = "primary"' in serialized


# ---------------------------------------------------------------------------
# Concurrency: stale expected revisions fail without changing files.
# ---------------------------------------------------------------------------


def test_stale_revision_is_rejected_without_writing(tmp_path) -> None:
    source = _global_source(tmp_path)
    runtime = Runtime(load_config(source))
    try:
        service = runtime.mutations
        expected = service.source_read().revision
        document = service.read_document(load_source(source))
        target = service.find_target(document, "primary")
        service.set_target_value(target, "max_concurrency", 9)

        with pytest.raises(ConfigurationMutationError) as raised:
            service.commit_document(document, expected_revision="a" * 64)

        error = raised.value
        assert error.code == "configuration_conflict"
        assert error.current_revision == _revision(source)
        assert "No configuration file was changed." in error.unchanged
        # The file was untouched.
        assert _revision(source) == expected
    finally:
        runtime.database.close()


def test_missing_expected_revision_is_rejected(tmp_path) -> None:
    source = _global_source(tmp_path)
    runtime = Runtime(load_config(source))
    try:
        service = runtime.mutations
        document = service.read_document(load_source(source))
        with pytest.raises(ConfigurationMutationError) as raised:
            service.commit_document(document, expected_revision=None)
        assert raised.value.code == "revision_required"
        assert _revision(source) == hashlib.sha256(source.read_bytes()).hexdigest()
    finally:
        runtime.database.close()


def test_external_edit_between_read_and_commit_conflicts(tmp_path) -> None:
    source = _global_source(tmp_path)
    runtime = Runtime(load_config(source))
    try:
        service = runtime.mutations
        expected = service.source_read().revision
        document = service.read_document(load_source(source))
        service.set_target_value(service.find_target(document, "primary"), "model", "a")
        # An external editor changes the file after the document was parsed.
        source.write_bytes(source.read_bytes() + b"\n# external edit\n")

        with pytest.raises(ConfigurationMutationError) as raised:
            service.commit_document(document, expected_revision=expected)

        assert raised.value.code == "configuration_conflict"
        assert source.read_bytes().endswith(b"# external edit\n")
    finally:
        runtime.database.close()


# ---------------------------------------------------------------------------
# Path safety: symlinks, directories, and non-regular paths are rejected.
# ---------------------------------------------------------------------------


def test_reject_symlink_source(tmp_path) -> None:
    real = tmp_path / "real.toml"
    real.write_text("[daemon]\ndefault_profile=\"x\"\n", encoding="utf-8")
    link = tmp_path / "config.toml"
    link.symlink_to(real)
    with pytest.raises(ConfigurationMutationError) as raised:
        commit_bytes(link, b"[daemon]\n", expected_revision=None)
    assert raised.value.code in {"configuration_conflict", "not_found"}
    # The real file was never touched.
    assert real.read_text(encoding="utf-8") == "[daemon]\ndefault_profile=\"x\"\n"


def test_reject_directory_source(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.mkdir()
    with pytest.raises(ConfigurationMutationError) as raised:
        commit_bytes(path, b"[daemon]\n", expected_revision=None)
    assert raised.value.code == "configuration_conflict"


def test_commit_rejects_swapped_symlink(tmp_path) -> None:
    real = tmp_path / "real.toml"
    real.write_text("[daemon]\ndefault_profile=\"x\"\n", encoding="utf-8")
    target = tmp_path / "config.toml"
    target.write_bytes(b"[daemon]\ndefault_profile=\"x\"\n")
    expected = _revision(target)
    target.unlink()
    target.symlink_to(real)
    with pytest.raises(ConfigurationMutationError) as raised:
        commit_bytes(target, b"[daemon]\ndefault_profile=\"y\"\n", expected_revision=expected)
    assert raised.value.code == "configuration_conflict"
    assert real.read_text(encoding="utf-8") == "[daemon]\ndefault_profile=\"x\"\n"


def test_service_rejects_directory_global_source(tmp_path) -> None:
    (tmp_path / "config.toml").mkdir()
    runtime = Runtime(make_config(tmp_path / "home"))
    try:

        class _Fake:
            config = type("C", (), {"config_path": tmp_path / "config.toml"})()

        service = ConfigurationMutationService(_Fake())
        with pytest.raises(ConfigurationMutationError):
            service.source_read()
    finally:
        runtime.database.close()


# ---------------------------------------------------------------------------
# Atomicity: temporary writes in the source directory, mode preservation,
# conflict rechecks, and creation exclusivity.
# ---------------------------------------------------------------------------


def test_temp_files_land_in_source_directory(tmp_path, monkeypatch) -> None:
    source = _global_source(tmp_path)
    runtime = Runtime(load_config(source))
    try:
        service = runtime.mutations
        expected = service.source_read().revision
        document = service.read_document(load_source(source))
        service.set_target_value(service.find_target(document, "primary"), "model", "x")

        import openmcp.config_mutation as module
        observed: list[Path] = []
        real_tempfile = __import__("tempfile").NamedTemporaryFile

        def spy_tempfile(*args, **kwargs):
            handle = real_tempfile(*args, **kwargs)
            observed.append(Path(handle.name).parent)
            return handle

        monkeypatch.setattr(module.tempfile, "NamedTemporaryFile", spy_tempfile)
        service.commit_document(document, expected_revision=expected)

        assert observed and all(directory == source.parent for directory in observed)
    finally:
        runtime.database.close()


def test_commit_preserves_existing_file_mode(tmp_path) -> None:
    source = _global_source(tmp_path)
    os.chmod(source, 0o600)
    runtime = Runtime(load_config(source))
    try:
        service = runtime.mutations
        expected = service.source_read().revision
        document = service.read_document(load_source(source))
        service.set_target_value(service.find_target(document, "primary"), "model", "x")
        service.commit_document(document, expected_revision=expected)

        assert stat.S_IMODE(source.stat().st_mode) == 0o600
    finally:
        runtime.database.close()


def test_commit_rechecks_revision_immediately_before_replace(tmp_path, monkeypatch) -> None:
    source = _global_source(tmp_path)
    runtime = Runtime(load_config(source))
    try:
        service = runtime.mutations
        expected = service.source_read().revision
        document = service.read_document(load_source(source))
        service.set_target_value(service.find_target(document, "primary"), "model", "x")

        real_commit = commit_bytes
        raced = False

        def racing_commit(path, candidate, *, expected_revision, mode=None):
            nonlocal raced
            if not raced:
                raced = True
                path.write_bytes(path.read_bytes() + b"\n# race\n")
            return real_commit(path, candidate, expected_revision=expected_revision, mode=mode)

        monkeypatch.setattr("openmcp.config_mutation.commit_bytes", racing_commit)
        with pytest.raises(ConfigurationMutationError) as raised:
            service.commit_document(document, expected_revision=expected)
        assert raised.value.code == "configuration_conflict"
        assert b"# race\n" in source.read_bytes()
    finally:
        runtime.database.close()


def test_create_bytes_is_exclusive(tmp_path) -> None:
    path = tmp_path / ".openmcp" / "config.toml"
    candidate = b"[profiles.quality]\nconsult = \"primary\"\n"
    created = create_bytes(path, candidate)
    assert path.exists()
    assert created.revision == hashlib.sha256(path.read_bytes()).hexdigest()

    with pytest.raises(ConfigurationMutationError) as raised:
        create_bytes(path, candidate)
    assert raised.value.code == "configuration_conflict"
    assert path.read_bytes() == candidate


def test_commit_leaves_no_temp_litter(tmp_path) -> None:
    source = _global_source(tmp_path)
    runtime = Runtime(load_config(source))
    try:
        service = runtime.mutations
        expected = service.source_read().revision
        document = service.read_document(load_source(source))
        service.set_target_value(service.find_target(document, "primary"), "model", "x")
        service.commit_document(document, expected_revision=expected)
        leftovers = [p for p in source.parent.iterdir() if p.name != source.name]
        assert leftovers == []
    finally:
        runtime.database.close()


# ---------------------------------------------------------------------------
# Validation and publication through the runtime service.
# ---------------------------------------------------------------------------


def test_invalid_candidate_is_rejected_before_replace(tmp_path) -> None:
    source = _global_source(tmp_path)
    runtime = Runtime(load_config(source))
    try:
        service = runtime.mutations
        expected = service.source_read().revision
        document = service.read_document(load_source(source))
        document["daemon"]["default_profile"] = "missing-profile"

        with pytest.raises(ConfigurationMutationError) as raised:
            service.commit_document(document, expected_revision=expected)
        assert raised.value.code == "configuration_invalid"
        assert _revision(source) == expected
    finally:
        runtime.database.close()


def test_valid_commit_publishes_catalog_executor_and_health(tmp_path) -> None:
    source = _global_source(tmp_path)
    runtime = Runtime(load_config(source))
    project_dir = tmp_path / "unused"
    project_dir.mkdir()
    runtime.register_project(str(project_dir), "unused")
    try:
        service = runtime.mutations
        expected = service.source_read().revision
        document = service.read_document(load_source(source))
        service.set_target_value(service.find_target(document, "primary"), "model", "updated")

        result = service.commit_document(document, expected_revision=expected)

        assert result.changed
        assert result.revision == _revision(source)
        assert runtime.catalog.config_revision == result.revision
        assert runtime.catalog.targets[0].model == "updated"
        assert runtime.target_executor.config is runtime.catalog
        health = runtime.configuration_health()
        assert health.valid
        assert health.revision == result.revision
        # Project resolution now sees the new global catalog.
        resolved = runtime.catalog_for_project_cached("unused")
        assert resolved.targets[0].model == "updated"
    finally:
        runtime.database.close()


def test_global_commit_requires_registered_project_compatibility(tmp_path) -> None:
    source = _global_source(tmp_path)
    runtime = Runtime(load_config(source))
    try:
        project_root = tmp_path / "project"
        (project_root / ".openmcp").mkdir(parents=True)
        (project_root / ".openmcp" / "config.toml").write_text(
            """[project]
default_profile = "fast"

[profiles.fast]
implement = "special"
review = "special"
consult = "special"
""",
            encoding="utf-8",
        )
        runtime.register_project(str(project_root), "special-project")

        service = runtime.mutations
        # Adding the missing "special" target makes the project valid again.
        expected = service.source_read().revision
        document = service.read_document(load_source(source))
        table = service.target_table()
        table["id"] = "special"
        table["backend"] = "codex"
        document["targets"].append(table)
        service.commit_document(
            document, expected_revision=expected, validate_registered_projects=True
        )
        resolved = runtime.catalog_for_project_cached("special-project")
        assert "fast" in resolved.profiles

        # Removing it again invalidates the registered project and is rejected.
        expected = service.source_read().revision
        document = service.read_document(load_source(source))
        document["targets"].remove(service.find_target(document, "special"))
        with pytest.raises(ConfigurationMutationError) as raised:
            service.commit_document(
                document, expected_revision=expected, validate_registered_projects=True
            )
        assert raised.value.code == "configuration_invalid"
        assert b'id = "special"' in source.read_bytes()
    finally:
        runtime.database.close()


def test_project_create_minimal_file_is_validated_and_published(tmp_path) -> None:
    runtime, project_root = _runtime_with_project(tmp_path)
    try:
        config_path = project_root / ".openmcp" / "config.toml"
        service = runtime.mutations
        doc = _empty_project_document()

        result = service.create_project_document(doc, project_root=project_root)

        assert config_path.exists()
        text = config_path.read_text(encoding="utf-8")
        assert "[profiles.quality]" in text
        assert 'consult = "primary"' in text
        # Minimal: no unrelated sections or defaults.
        assert "[daemon]" not in text
        assert "default_profile" not in text
        assert result.revision == _revision(config_path)
        resolved = runtime.catalog_for_project_cached("project")
        assert "quality" in resolved.project_profile_declarations
        assert resolved.default_profile == "balanced"
    finally:
        runtime.database.close()


def test_project_create_rejects_invalid_minimal_file(tmp_path) -> None:
    runtime, project_root = _runtime_with_project(tmp_path)
    try:
        service = runtime.mutations
        doc = tomlkit.document()
        profiles = tomlkit.table()
        bad = tomlkit.table()
        bad["unknown_workflow"] = "ghost-target"
        profiles["quality"] = bad
        doc["profiles"] = profiles

        with pytest.raises(ConfigurationMutationError) as raised:
            service.create_project_document(doc, project_root=project_root)
        assert raised.value.code == "configuration_invalid"
        assert not (project_root / ".openmcp" / "config.toml").exists()
    finally:
        runtime.database.close()


def test_project_create_conflicts_when_file_already_exists(tmp_path) -> None:
    runtime, project_root = _runtime_with_project(tmp_path)
    try:
        config_path = project_root / ".openmcp" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            "[profiles.quality]\nconsult = \"primary\"\n", encoding="utf-8"
        )
        service = runtime.mutations
        with pytest.raises(ConfigurationMutationError) as raised:
            service.create_project_document(_empty_project_document(), project_root=project_root)
        assert raised.value.code == "configuration_conflict"
        assert config_path.read_text(encoding="utf-8") == (
            "[profiles.quality]\nconsult = \"primary\"\n"
        )
    finally:
        runtime.database.close()


def test_project_edit_commits_and_publishes(tmp_path) -> None:
    runtime, project_root = _runtime_with_project(tmp_path)
    try:
        config_path = project_root / ".openmcp" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            """[profiles.quality]
consult = "primary"
""",
            encoding="utf-8",
        )
        service = runtime.mutations
        expected = service.source_read(project_root).revision
        document = service.read_document(load_source(config_path))
        profile = service.find_profile(document, "quality")
        service.set_profile_value(profile, "consult", "fallback")

        result = service.commit_document(
            document, project_root=project_root, expected_revision=expected
        )

        assert result.changed
        assert 'consult = "fallback"' in config_path.read_text(encoding="utf-8")
        # Resolve the catalog for the fixture-registered project and then
        # validate against the committed project override.
        resolved = runtime.catalog_for_project_cached("project")
        selection = resolved.profiles["quality"]["consult"]
        assert selection.targets == ("fallback",)
    finally:
        runtime.database.close()


# ---------------------------------------------------------------------------
# Rollback behavior when runtime publication fails.
# ---------------------------------------------------------------------------


def test_publication_failure_restores_exact_bytes_and_catalog(tmp_path, monkeypatch) -> None:
    source = _global_source(tmp_path)
    runtime = Runtime(load_config(source))
    try:
        original = source.read_bytes()
        original_revision = _revision(source)
        service = runtime.mutations
        expected = service.source_read().revision
        document = service.read_document(load_source(source))
        service.set_target_value(service.find_target(document, "primary"), "model", "boom")

        def failing_publish():
            raise RuntimeError("publication exploded")

        monkeypatch.setattr(runtime, "_publish_configuration_locked", failing_publish)

        with pytest.raises(ConfigurationMutationError) as raised:
            service.commit_document(document, expected_revision=expected)

        assert raised.value.code == "configuration_commit_failed"
        assert source.read_bytes() == original
        assert _revision(source) == original_revision
        assert runtime.catalog.config_revision == original_revision
    finally:
        runtime.database.close()


def test_rollback_refuses_to_overwrite_later_external_edit(tmp_path, monkeypatch) -> None:
    source = _global_source(tmp_path)
    runtime = Runtime(load_config(source))
    try:
        service = runtime.mutations
        expected = service.source_read().revision
        document = service.read_document(load_source(source))
        service.set_target_value(service.find_target(document, "primary"), "model", "boom")

        real_commit = commit_bytes
        raced = {"done": False}

        def racing_commit(path, candidate, *, expected_revision, mode=None):
            result = real_commit(path, candidate, expected_revision=expected_revision, mode=mode)
            if not raced["done"]:
                raced["done"] = True
                # External edit lands between our commit and publication.
                path.write_bytes(path.read_bytes() + b"\n# external\n")
            return result

        monkeypatch.setattr("openmcp.config_mutation.commit_bytes", racing_commit)

        def failing_publish():
            raise RuntimeError("publication exploded")

        monkeypatch.setattr(runtime, "_publish_configuration_locked", failing_publish)

        with pytest.raises(ConfigurationMutationError) as raised:
            service.commit_document(document, expected_revision=expected)

        # Rollback must refuse to overwrite the external edit.
        assert raised.value.code == "configuration_commit_failed"
        assert b"# external\n" in source.read_bytes()
    finally:
        runtime.database.close()


def test_project_publication_failure_restores_original(tmp_path, monkeypatch) -> None:
    runtime, project_root = _runtime_with_project(tmp_path)
    try:
        config_path = project_root / ".openmcp" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            "[profiles.fast]\nconsult = \"primary\"\n", encoding="utf-8"
        )
        original = config_path.read_bytes()
        service = runtime.mutations
        expected = service.source_read(project_root).revision
        document = service.read_document(load_source(config_path))
        profile = service.find_profile(document, "fast")
        service.set_profile_value(profile, "consult", "fallback")

        def failing_publish(_root):
            raise RuntimeError("project publication exploded")

        monkeypatch.setattr(runtime, "_publish_project_configuration_locked", failing_publish)

        with pytest.raises(ConfigurationMutationError) as raised:
            service.commit_document(
                document, project_root=project_root, expected_revision=expected
            )
        assert raised.value.code == "configuration_commit_failed"
        assert config_path.read_bytes() == original
    finally:
        runtime.database.close()


def test_project_create_publication_failure_removes_created_file(tmp_path, monkeypatch) -> None:
    runtime, project_root = _runtime_with_project(tmp_path)
    try:
        config_path = project_root / ".openmcp" / "config.toml"
        service = runtime.mutations

        def failing_publish(_root):
            raise RuntimeError("project publication exploded")

        monkeypatch.setattr(runtime, "_publish_project_configuration_locked", failing_publish)

        with pytest.raises(ConfigurationMutationError) as raised:
            service.create_project_document(
                _empty_project_document(), project_root=project_root
            )
        assert raised.value.code == "configuration_commit_failed"
        assert not config_path.exists()
    finally:
        runtime.database.close()


def test_reusable_profile_primitives_expand_and_preserve(tmp_path) -> None:
    """Task-2 primitives: shorthand expansion, array failover, kind probes."""
    path = tmp_path / "config.toml"
    path.write_text(
        """[daemon]
default_profile = "balanced"

[[targets]]
id = "primary"
backend = "codex"

[[targets]]
id = "fallback"
backend = "pi"

[profiles.balanced]
implement = "primary"
review = "primary"
""",
        encoding="utf-8",
    )
    service = ConfigurationMutationService(object())
    document = service.read_document(load_source(path))
    profile = service.find_profile(document, "balanced")
    assert profile is not None
    assert service.workflow_kind(profile, "implement") == "string"
    assert service.workflow_targets(profile, "implement") == ["primary"]

    # Expanding a single-target shorthand into ordered failover.
    service.set_workflow_shorthand(
        profile, "implement", ["primary", "fallback"]
    )
    assert service.workflow_kind(profile, "implement") == "array"
    assert service.workflow_targets(profile, "implement") == ["primary", "fallback"]

    # Removing a declared workflow key leaves it absent.
    service.remove_profile_key(profile, "review")
    assert "review" not in profile

    serialized = service.candidate_bytes(document).decode("utf-8")
    assert 'implement = ["primary", "fallback"]' in serialized
    assert 'review = "primary"' not in serialized


def test_reusable_target_primitives_edit_existing_and_new_tables(tmp_path) -> None:
    """Task-2 primitives: locate, scalar edit, arg ordering, key removal."""
    source = _global_source(tmp_path)
    service = ConfigurationMutationService(object())
    document = service.read_document(load_source(source))
    target = service.find_target(document, "primary")
    assert target is not None
    service.set_target_value(target, "args", ["--strict", "run"])
    service.set_target_argument(target, 1, "deploy")
    service.set_target_value(target, "system_prompt", "multi\nline")
    service.remove_target_key(target, "profile")
    service.remove_target_key(target, "max_concurrency")

    serialized = service.candidate_bytes(document).decode("utf-8")

    assert 'args = ["--strict", "deploy"]' in serialized
    # Removing a key drops the legacy key without normalizing other fields.
    assert "legacy-profile" not in serialized
    assert "system_prompt = \"multi\\nline\"" in serialized or "system_prompt" in serialized


def test_profile_table_creates_missing_declaration(tmp_path) -> None:
    source = _global_source(tmp_path)
    service = ConfigurationMutationService(object())
    document = service.read_document(load_source(source))
    profile = service.profile_table(document, "fast")
    service.set_profile_value(profile, "extends", "balanced")
    service.set_profile_value(profile, "implement", "fallback")

    serialized = service.candidate_bytes(document).decode("utf-8")

    assert "[profiles.fast]" in serialized
    assert 'extends = "balanced"' in serialized
    assert 'implement = "fallback"' in serialized


def test_concurrent_commits_are_serialized_by_the_service_lock(tmp_path) -> None:
    """Two threads committing different models never interleave or lose edits.

    The first commit wins; the second observes the first commit's new revision
    and conflicts instead of silently overwriting. No thread leaves the file
    in a torn state.
    """
    source = _global_source(tmp_path)
    runtime = Runtime(load_config(source))
    try:
        service = runtime.mutations
        errors: list[Exception] = []

        def attempt(model: str) -> None:
            try:
                expected = service.source_read().revision
                document = service.read_document(load_source(source))
                service.set_target_value(
                    service.find_target(document, "primary"), "model", model
                )
                service.commit_document(document, expected_revision=expected)
            except ConfigurationMutationError as exc:
                errors.append(exc)

        first = threading.Thread(target=attempt, args=("from-first",))
        second = threading.Thread(target=attempt, args=("from-second",))
        first.start()
        second.start()
        first.join(timeout=10)
        second.join(timeout=10)

        # Exactly one thread commits; the other reports a conflict or also
        # succeeds only if it serialized behind a fresh read. The file must
        # hold one complete model value, never a torn mixture.
        text = source.read_text(encoding="utf-8")
        committed_models = [m for m in ("from-first", "from-second") if f'model = "{m}"' in text]
        assert len(committed_models) == 1
        assert not (errors and errors[0].code == "configuration_commit_failed")
        # The runtime catalog matches the committed file.
        assert runtime.catalog.config_revision == _revision(source)
    finally:
        runtime.database.close()


def test_commit_rejects_external_edit_injected_after_temp_write(tmp_path, monkeypatch) -> None:
    source = _global_source(tmp_path)
    runtime = Runtime(load_config(source))
    try:
        service = runtime.mutations
        expected = service.source_read().revision
        document = service.read_document(load_source(source))
        service.set_target_value(service.find_target(document, "primary"), "model", "x")

        real_write_temp = openmcp.config_mutation._write_temporary
        raced = False

        def racing_write_temp(directory, candidate, prefix):
            temp = real_write_temp(directory, candidate, prefix)
            nonlocal raced
            if not raced and prefix.startswith(f".{source.name}."):
                raced = True
                source.write_bytes(source.read_bytes() + b"\n# race after temp\n")
            return temp

        monkeypatch.setattr("openmcp.config_mutation._write_temporary", racing_write_temp)
        with pytest.raises(ConfigurationMutationError) as raised:
            service.commit_document(document, expected_revision=expected)
        assert raised.value.code == "configuration_conflict"
        assert b"# race after temp\n" in source.read_bytes()
        leftovers = [p for p in source.parent.iterdir() if p.name != source.name]
        assert leftovers == []
    finally:
        runtime.database.close()


def test_rollback_refuses_to_overwrite_edit_injected_after_temp_write(tmp_path, monkeypatch) -> None:
    source = _global_source(tmp_path)
    runtime = Runtime(load_config(source))
    try:
        service = runtime.mutations
        expected = service.source_read().revision
        document = service.read_document(load_source(source))
        service.set_target_value(service.find_target(document, "primary"), "model", "boom")

        real_write_temp = openmcp.config_mutation._write_temporary
        raced = False

        def failing_publish():
            raise RuntimeError("publication exploded")

        monkeypatch.setattr(runtime, "_publish_configuration_locked", failing_publish)

        def racing_write_temp(directory, candidate, prefix):
            temp = real_write_temp(directory, candidate, prefix)
            nonlocal raced
            if raced:
                source.write_bytes(source.read_bytes() + b"\n# race after rollback temp\n")
            else:
                raced = True
            return temp

        monkeypatch.setattr("openmcp.config_mutation._write_temporary", racing_write_temp)

        with pytest.raises(ConfigurationMutationError) as raised:
            service.commit_document(document, expected_revision=expected)

        assert raised.value.code == "configuration_commit_failed"
        assert b"# race after rollback temp\n" in source.read_bytes()
        leftovers = [p for p in source.parent.iterdir() if p.name != source.name]
        assert leftovers == []
    finally:
        runtime.database.close()


def test_rollback_creation_refuses_deletion_on_external_edit(tmp_path, monkeypatch) -> None:
    runtime, project_root = _runtime_with_project(tmp_path)
    try:
        service = runtime.mutations
        document = _empty_project_document()
        config_path = project_root / ".openmcp" / "config.toml"

        def failing_publish(path):
            raise RuntimeError("publication exploded")

        monkeypatch.setattr(runtime, "_publish_project_configuration_locked", failing_publish)

        real_confirm = service._confirm_current
        confirmed = False

        def racing_confirm(path, candidate_revision):
            nonlocal confirmed
            result = real_confirm(path, candidate_revision)
            if not confirmed:
                confirmed = True
                path.write_bytes(path.read_bytes() + b"\n# race before delete\n")
            return result

        monkeypatch.setattr(service, "_confirm_current", racing_confirm)

        with pytest.raises(ConfigurationMutationError) as raised:
            service.create_project_document(document, project_root=project_root)

        assert raised.value.code == "configuration_commit_failed"
        assert config_path.exists()
        assert b"# race before delete\n" in config_path.read_bytes()
    finally:
        runtime.database.close()


def test_commit_fails_if_mode_preservation_fails(tmp_path, monkeypatch) -> None:
    source = _global_source(tmp_path)
    os.chmod(source, 0o640)
    runtime = Runtime(load_config(source))
    try:
        service = runtime.mutations
        expected = service.source_read().revision
        document = service.read_document(load_source(source))
        service.set_target_value(service.find_target(document, "primary"), "model", "new-model")

        real_chmod = os.chmod

        def failing_chmod(path, mode):
            if Path(path).name.startswith(f".{source.name}."):
                raise OSError("Permission denied")
            return real_chmod(path, mode)

        monkeypatch.setattr(os, "chmod", failing_chmod)

        with pytest.raises(ConfigurationMutationError) as raised:
            service.commit_document(document, expected_revision=expected)

        assert raised.value.code == "configuration_commit_failed"
        assert b"new-model" not in source.read_bytes()
        assert stat.S_IMODE(source.stat().st_mode) == 0o640
        leftovers = [p for p in source.parent.iterdir() if p.name != source.name]
        assert leftovers == []
    finally:
        runtime.database.close()


def test_project_validation_temp_directory_cleaned_up(tmp_path, monkeypatch) -> None:
    runtime, project_root = _runtime_with_project(tmp_path)
    try:
        service = runtime.mutations
        candidate = b"[profiles.quality]\nconsult = \"primary\"\n"
        created_dirs: list[Path] = []
        real_mkdtemp = tempfile.mkdtemp

        def tracking_mkdtemp(*args, **kwargs):
            res = real_mkdtemp(*args, **kwargs)
            created_dirs.append(Path(res))
            return res

        monkeypatch.setattr("tempfile.mkdtemp", tracking_mkdtemp)

        service.resolve_project_catalog(project_root, candidate)
        assert len(created_dirs) == 1
        assert not created_dirs[0].exists()

        with pytest.raises(ConfigurationMutationError):
            service.resolve_project_catalog(project_root, b"invalid toml :::")
        assert len(created_dirs) == 2
        assert not created_dirs[1].exists()
    finally:
        runtime.database.close()


def test_global_commit_always_validates_registered_projects(tmp_path) -> None:
    source = _global_source(tmp_path)
    runtime = Runtime(load_config(source))
    try:
        project_root = tmp_path / "project"
        (project_root / ".openmcp").mkdir(parents=True)
        (project_root / ".openmcp" / "config.toml").write_text(
            """[project]
default_profile = "fast"

[profiles.fast]
implement = "special"
review = "special"
consult = "special"
""",
            encoding="utf-8",
        )
        runtime.register_project(str(project_root), "special-project")

        service = runtime.mutations
        # First add target "special" to make project valid
        expected = service.source_read().revision
        document = service.read_document(load_source(source))
        table = service.target_table()
        table["id"] = "special"
        table["backend"] = "codex"
        document["targets"].append(table)
        service.commit_document(document, expected_revision=expected)

        # Now remove "special" WITHOUT passing validate_registered_projects.
        # Global config is still valid on its own, but project config is invalidated.
        expected = service.source_read().revision
        document = service.read_document(load_source(source))
        document["targets"].remove(service.find_target(document, "special"))

        with pytest.raises(ConfigurationMutationError) as raised:
            service.commit_document(document, expected_revision=expected)
        assert raised.value.code == "configuration_invalid"
        assert b'id = "special"' in source.read_bytes()
    finally:
        runtime.database.close()


def test_commit_rejects_external_edit_injected_in_pre_replace_gap(tmp_path, monkeypatch) -> None:
    source = _global_source(tmp_path)
    runtime = Runtime(load_config(source))
    try:
        service = runtime.mutations
        expected = service.source_read().revision
        document = service.read_document(load_source(source))
        service.set_target_value(service.find_target(document, "primary"), "model", "x")

        real_replace = os.replace
        raced = False

        def racing_replace(src, dst):
            nonlocal raced
            if not raced and Path(dst) == source:
                raced = True
                source.write_bytes(source.read_bytes() + b"\n# gap edit before replace\n")
            return real_replace(src, dst)

        monkeypatch.setattr(os, "replace", racing_replace)
        with pytest.raises(ConfigurationMutationError) as raised:
            service.commit_document(document, expected_revision=expected)
        assert raised.value.code == "configuration_conflict"
        assert b"# gap edit before replace\n" in source.read_bytes()
        leftovers = [p for p in source.parent.iterdir() if p.name != source.name]
        assert leftovers == []
    finally:
        runtime.database.close()


def test_rollback_refuses_to_overwrite_edit_injected_in_pre_restore_gap(tmp_path, monkeypatch) -> None:
    source = _global_source(tmp_path)
    runtime = Runtime(load_config(source))
    try:
        service = runtime.mutations
        expected = service.source_read().revision
        document = service.read_document(load_source(source))
        service.set_target_value(service.find_target(document, "primary"), "model", "boom")

        def failing_publish():
            raise RuntimeError("publication exploded")

        monkeypatch.setattr(runtime, "_publish_configuration_locked", failing_publish)

        commit_done = False
        real_commit = commit_bytes

        def tracking_commit(*args, **kwargs):
            nonlocal commit_done
            res = real_commit(*args, **kwargs)
            commit_done = True
            return res

        monkeypatch.setattr("openmcp.config_mutation.commit_bytes", tracking_commit)

        real_replace = os.replace
        raced = False

        def restore_racing_replace(src, dst):
            nonlocal raced
            if commit_done and not raced and Path(dst) == source:
                raced = True
                source.write_bytes(source.read_bytes() + b"\n# gap edit before restore replace\n")
            return real_replace(src, dst)

        monkeypatch.setattr(os, "replace", restore_racing_replace)

        with pytest.raises(ConfigurationMutationError) as raised:
            service.commit_document(document, expected_revision=expected)

        assert raised.value.code == "configuration_commit_failed"
        assert b"# gap edit before restore replace\n" in source.read_bytes()
        leftovers = [p for p in source.parent.iterdir() if p.name != source.name]
        assert leftovers == []
    finally:
        runtime.database.close()


def test_rollback_creation_refuses_deletion_on_edit_injected_in_pre_unlink_gap(tmp_path, monkeypatch) -> None:
    runtime, project_root = _runtime_with_project(tmp_path)
    try:
        service = runtime.mutations
        document = _empty_project_document()
        config_path = project_root / ".openmcp" / "config.toml"

        def failing_publish(path):
            raise RuntimeError("publication exploded")

        monkeypatch.setattr(runtime, "_publish_project_configuration_locked", failing_publish)

        real_unlink = Path.unlink
        raced = False

        def racing_unlink(p, *args, **kwargs):
            nonlocal raced
            if not raced and p == config_path:
                raced = True
                config_path.write_bytes(config_path.read_bytes() + b"\n# gap edit before unlink\n")
            return real_unlink(p, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", racing_unlink)

        with pytest.raises(ConfigurationMutationError) as raised:
            service.create_project_document(document, project_root=project_root)

        assert raised.value.code == "configuration_commit_failed"
        assert config_path.exists()
        assert b"# gap edit before unlink\n" in config_path.read_bytes()
    finally:
        runtime.database.close()


def test_project_validation_cleanup_failure_not_ignored(tmp_path, monkeypatch) -> None:
    runtime, project_root = _runtime_with_project(tmp_path)
    try:
        service = runtime.mutations
        candidate = b"[profiles.quality]\nconsult = \"primary\"\n"

        def failing_rmtree(path, *args, **kwargs):
            raise OSError("disk cleanup error")

        monkeypatch.setattr(openmcp.config_mutation.shutil, "rmtree", failing_rmtree)

        with pytest.raises(OSError, match="disk cleanup error"):
            service.resolve_project_catalog(project_root, candidate)
    finally:
        runtime.database.close()
