"""Transaction-boundary tests for safe TOML configuration mutation."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import threading
from pathlib import Path

import pytest
import tomlkit

import refract.config_mutation

from refract.config import load_config
from refract.config_mutation import (
    ConfigurationMutationError,
    ConfigurationMutationService,
    commit_bytes,
    create_bytes,
    load_source,
    target_to_editor_data,
)
from refract.models import TargetEditorData, TargetReference
from refract.runtime import OrchestrationError, Runtime
from tests.orchestration_helpers import config as make_config
from tests.orchestration_helpers import register_project

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
    register_project(runtime, str(project_root), "project")
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
        timeout_s=90,
    )

    serialized = service.candidate_bytes(document).decode("utf-8")

    # Untouched single-quoted shorthand keeps its literal style.
    assert "implement = 'primary'" in serialized
    # Untouched array shorthand keeps its form.
    assert 'review = ["primary", "fallback"]' in serialized
    # The edited inline policy remains a single-line inline table.
    assert "consult = { targets = [\"fallback\", \"primary\"], max_attempts = 2, timeout_s = 90 }" in serialized


def test_new_timeout_policy_omits_max_attempts(tmp_path) -> None:
    from refract.config_mutation import _apply_workflow_policy
    from refract.models import WorkflowPolicyData

    path = tmp_path / "config.toml"
    path.write_text(
        """[daemon]
default_profile = "balanced"

[[targets]]
id = "primary"
backend = "codex"

[profiles.balanced]
review = "primary"
""",
        encoding="utf-8",
    )
    service = ConfigurationMutationService(object())
    document = service.read_document(load_source(path))
    profile = service.find_profile(document, "balanced")
    assert profile is not None

    _apply_workflow_policy(
        service,
        profile,
        "implement",
        WorkflowPolicyData(targets=["primary"], timeout_s=45),
    )
    implement_policy = profile["implement"]
    assert list(implement_policy["targets"]) == ["primary"]
    assert implement_policy["timeout_s"] == 45
    assert "max_attempts" not in implement_policy

    _apply_workflow_policy(
        service,
        profile,
        "review",
        WorkflowPolicyData(targets=["primary"], timeout_s=30),
    )
    review_policy = profile["review"]
    assert list(review_policy["targets"]) == ["primary"]
    assert review_policy["timeout_s"] == 30
    assert "max_attempts" not in review_policy


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
    # Zero timeout keeps the edited shorthand; the untouched review shorthand remains a string.
    from refract.config_mutation import _apply_workflow_policy
    from refract.models import WorkflowPolicyData

    _apply_workflow_policy(
        service, profile, "implement",
        WorkflowPolicyData(targets=["primary"], timeout_s=0),
    )

    serialized = service.candidate_bytes(document).decode("utf-8")

    assert 'implement = "primary"' in serialized
    assert 'review = "primary"' in serialized
    assert 'implement = {targets = ["primary"], max_attempts' not in serialized


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

        import refract.config_mutation as module
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

        monkeypatch.setattr("refract.config_mutation.commit_bytes", racing_commit)
        with pytest.raises(ConfigurationMutationError) as raised:
            service.commit_document(document, expected_revision=expected)
        assert raised.value.code == "configuration_conflict"
        assert b"# race\n" in source.read_bytes()
    finally:
        runtime.database.close()


@pytest.mark.skipif(os.name == "nt", reason="uses fcntl")
def test_commit_holds_sibling_lock_across_replace(tmp_path, monkeypatch) -> None:
    import fcntl

    path = tmp_path / "config.toml"
    path.write_bytes(b"[daemon]\n")
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    real_replace = os.replace
    observed: list[bool] = []

    def probing_replace(src, dst):
        with open(path.parent / f".{path.name}.lock", "a+b") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                observed.append(True)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                observed.append(False)
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", probing_replace)
    commit_bytes(path, b"[daemon]\nmax_jobs = 2\n", expected_revision=expected)

    assert observed == [True]
    assert path.read_bytes() == b"[daemon]\nmax_jobs = 2\n"


def test_create_bytes_is_exclusive(tmp_path) -> None:
    path = tmp_path / ".refract" / "config.toml"
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
        leftovers = [p for p in source.parent.iterdir() if p.name not in (source.name, f".{source.name}.lock")]
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
    register_project(runtime, str(project_dir), "unused")
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
        health = runtime.config_health
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
        (project_root / ".refract").mkdir(parents=True)
        (project_root / ".refract" / "config.toml").write_text(
            """[project]
default_profile = "fast"

[profiles.fast]
implement = "special"
review = "special"
consult = "special"
""",
            encoding="utf-8",
        )
        register_project(runtime, str(project_root), "special-project")

        service = runtime.mutations
        # Adding the missing "special" target makes the project valid again.
        expected = service.source_read().revision
        document = service.read_document(load_source(source))
        table = service.target_table()
        table["id"] = "special"
        table["backend"] = "codex"
        document["targets"].append(table)
        service.commit_document(
            document, expected_revision=expected
        )
        resolved = runtime.catalog_for_project_cached("special-project")
        assert "fast" in resolved.profiles

        # Removing it again invalidates the registered project and is rejected.
        expected = service.source_read().revision
        document = service.read_document(load_source(source))
        document["targets"].remove(service.find_target(document, "special"))
        with pytest.raises(ConfigurationMutationError) as raised:
            service.commit_document(
                document, expected_revision=expected
            )
        assert raised.value.code == "configuration_invalid"
        assert b'id = "special"' in source.read_bytes()
    finally:
        runtime.database.close()


def test_project_create_minimal_file_is_validated_and_published(tmp_path) -> None:
    runtime, project_root = _runtime_with_project(tmp_path)
    try:
        config_path = project_root / ".refract" / "config.toml"
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
        assert not (project_root / ".refract" / "config.toml").exists()
    finally:
        runtime.database.close()


def test_project_create_conflicts_when_file_already_exists(tmp_path) -> None:
    runtime, project_root = _runtime_with_project(tmp_path)
    try:
        config_path = project_root / ".refract" / "config.toml"
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
        config_path = project_root / ".refract" / "config.toml"
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

        monkeypatch.setattr("refract.config_mutation.commit_bytes", racing_commit)

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
        config_path = project_root / ".refract" / "config.toml"
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
        config_path = project_root / ".refract" / "config.toml"
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

    # Expanding a single-target shorthand into ordered failover.
    service.set_workflow_shorthand(
        profile, "implement", ["primary", "fallback"]
    )
    assert service.workflow_kind(profile, "implement") == "array"

    # Removing a declared workflow key leaves it absent.
    service.remove_profile_key(profile, "review")
    assert "review" not in profile

    serialized = service.candidate_bytes(document).decode("utf-8")
    assert 'implement = ["primary", "fallback"]' in serialized
    assert 'review = "primary"' not in serialized


def test_reusable_target_primitives_edit_existing_and_new_tables(tmp_path) -> None:
    """Task-2 primitives: locate, scalar edit, arg ordering."""
    source = _global_source(tmp_path)
    service = ConfigurationMutationService(object())
    document = service.read_document(load_source(source))
    target = service.find_target(document, "primary")
    assert target is not None
    service.set_target_value(target, "args", ["--strict", "deploy"])
    service.set_target_value(target, "system_prompt", "multi\nline")

    serialized = service.candidate_bytes(document).decode("utf-8")

    assert 'args = ["--strict", "deploy"]' in serialized
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

        real_write_temp = refract.config_mutation._write_temporary
        raced = False

        def racing_write_temp(directory, candidate, prefix):
            temp = real_write_temp(directory, candidate, prefix)
            nonlocal raced
            if not raced and prefix.startswith(f".{source.name}."):
                raced = True
                source.write_bytes(source.read_bytes() + b"\n# race after temp\n")
            return temp

        monkeypatch.setattr("refract.config_mutation._write_temporary", racing_write_temp)
        with pytest.raises(ConfigurationMutationError) as raised:
            service.commit_document(document, expected_revision=expected)
        assert raised.value.code == "configuration_conflict"
        assert b"# race after temp\n" in source.read_bytes()
        leftovers = [p for p in source.parent.iterdir() if p.name not in (source.name, f".{source.name}.lock")]
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

        real_write_temp = refract.config_mutation._write_temporary
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

        monkeypatch.setattr("refract.config_mutation._write_temporary", racing_write_temp)

        with pytest.raises(ConfigurationMutationError) as raised:
            service.commit_document(document, expected_revision=expected)

        assert raised.value.code == "configuration_commit_failed"
        assert b"# race after rollback temp\n" in source.read_bytes()
        leftovers = [p for p in source.parent.iterdir() if p.name not in (source.name, f".{source.name}.lock")]
        assert leftovers == []
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
        leftovers = [p for p in source.parent.iterdir() if p.name not in (source.name, f".{source.name}.lock")]
        assert leftovers == []
    finally:
        runtime.database.close()


def test_project_validation_writes_no_files(tmp_path) -> None:
    runtime, project_root = _runtime_with_project(tmp_path)
    try:
        service = runtime.mutations
        before = sorted(tmp_path.rglob("*"))
        service.resolve_project_catalog(
            project_root, b"[profiles.quality]\nconsult = \"primary\"\n"
        )
        with pytest.raises(ConfigurationMutationError):
            service.resolve_project_catalog(project_root, b"invalid toml :::")
        assert sorted(tmp_path.rglob("*")) == before
    finally:
        runtime.database.close()


def test_global_commit_always_validates_registered_projects(tmp_path) -> None:
    source = _global_source(tmp_path)
    runtime = Runtime(load_config(source))
    try:
        project_root = tmp_path / "project"
        (project_root / ".refract").mkdir(parents=True)
        (project_root / ".refract" / "config.toml").write_text(
            """[project]
default_profile = "fast"

[profiles.fast]
implement = "special"
review = "special"
consult = "special"
""",
            encoding="utf-8",
        )
        register_project(runtime, str(project_root), "special-project")

        service = runtime.mutations
        # First add target "special" to make project valid
        expected = service.source_read().revision
        document = service.read_document(load_source(source))
        table = service.target_table()
        table["id"] = "special"
        table["backend"] = "codex"
        document["targets"].append(table)
        service.commit_document(document, expected_revision=expected)

        # Now remove "special".
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



# ---------------------------------------------------------------------------
# Phase 2: Target configuration CRUD and reference checks
# ---------------------------------------------------------------------------


def test_read_targets_and_get_target_expose_all_fields(tmp_path) -> None:
    source = _global_source(tmp_path)
    text = source.read_text(encoding="utf-8")
    text = text.replace(
        'max_concurrency = 2',
        'max_concurrency = 2\nmodel = "gpt-4"\nreasoning = "deep"\nsystem_prompt = "act safe"\nisolated = true\nread_only = true\nargs = ["--verbose"]',
    )
    source.write_text(text, encoding="utf-8")
    runtime = Runtime(load_config(source))
    try:
        service = runtime.mutations
        source_read, targets = service.read_targets()
        assert source_read.revision == _revision(source)
        assert len(targets) == 2
        primary = next(t for t in targets if t.id == "primary")
        assert primary.backend == "codex"
        assert primary.model == "gpt-4"
        assert primary.backend_profile == "legacy-profile"
        assert primary.reasoning == "deep"
        assert primary.system_prompt == "act safe"
        assert primary.isolated is True
        assert primary.read_only is True
        assert primary.args == ["--verbose"]
        assert primary.max_concurrency == 2

        _, retrieved = service.get_target("primary")
        assert retrieved == primary

        with pytest.raises(ConfigurationMutationError) as raised:
            service.get_target("nonexistent")
        assert raised.value.code == "not_found"
    finally:
        runtime.database.close()


def test_create_target_emits_backend_profile_only_and_preserves_unrelated(tmp_path) -> None:
    source = _global_source(tmp_path)
    runtime = Runtime(load_config(source))
    try:
        service = runtime.mutations
        expected = service.source_read().revision
        data = TargetEditorData(
            id="tertiary",
            backend="codex",
            backend_profile="balanced",
            args=["--flag"],
            max_concurrency=3,
        )
        result, created = service.create_target(data, expected_revision=expected)
        assert created.id == "tertiary"
        assert created.backend_profile == "balanced"
        assert result.changed is True

        new_text = source.read_text(encoding="utf-8")
        assert '# operator comment' in new_text
        assert 'profile = "legacy-profile"' in new_text
        assert 'backend_profile = "balanced"' in new_text
        tertiary_block = new_text.split('id = "tertiary"')[1]
        assert '\nprofile = ' not in tertiary_block

        assert "tertiary" in [t.id for t in runtime.catalog.targets]
    finally:
        runtime.database.close()


def test_create_target_appends_inline_table_to_inline_targets(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = home / "config.toml"
    source.write_text(
        'targets = [{ id = "primary", backend = "codex" }]\n\n'
        '[profiles.balanced]\nimplement = "primary"\nreview = "primary"\n'
        'consult = "primary"\n\n[daemon]\ndefault_profile = "balanced"\n',
        encoding="utf-8",
    )
    runtime = Runtime(load_config(source))
    try:
        service = runtime.mutations
        service.create_target(
            TargetEditorData(id="extra", backend="pi", args=["--x"]),
            expected_revision=service.source_read().revision,
        )
        assert [t.id for t in load_config(source).targets] == ["primary", "extra"]
    finally:
        runtime.database.close()


def test_missing_global_source_is_not_found(tmp_path) -> None:
    source = _global_source(tmp_path)
    runtime = Runtime(load_config(source))
    try:
        source.unlink()
        with pytest.raises(ConfigurationMutationError) as raised:
            runtime.mutations.delete_target("fallback", expected_revision="abc")
        assert raised.value.code == "not_found"
    finally:
        runtime.database.close()


def test_project_root_holding_global_config_is_rejected(tmp_path) -> None:
    root = tmp_path / "user"
    (root / ".refract").mkdir(parents=True)
    source = root / ".refract" / "config.toml"
    source.write_text(_global_text(), encoding="utf-8")
    runtime = Runtime(load_config(source))
    try:
        with pytest.raises(OrchestrationError) as raised:
            runtime.resolve_project(str(root))
        assert raised.value.code == "invalid_path"
    finally:
        runtime.database.close()


def test_create_target_rejects_duplicate_or_empty_id(tmp_path) -> None:
    source = _global_source(tmp_path)
    runtime = Runtime(load_config(source))
    try:
        service = runtime.mutations
        expected = service.source_read().revision

        with pytest.raises(ConfigurationMutationError) as raised_dup:
            service.create_target(
                TargetEditorData(id="primary", backend="codex"),
                expected_revision=expected,
            )
        assert raised_dup.value.code == "configuration_invalid"

        with pytest.raises(ConfigurationMutationError) as raised_empty:
            service.create_target(
                TargetEditorData(id="   ", backend="codex"),
                expected_revision=expected,
            )
        assert raised_empty.value.code == "configuration_invalid"
    finally:
        runtime.database.close()


def test_create_target_rejects_invalid_candidate(tmp_path) -> None:
    source = _global_source(tmp_path)
    runtime = Runtime(load_config(source))
    try:
        service = runtime.mutations
        expected = service.source_read().revision

        with pytest.raises(ConfigurationMutationError) as raised:
            service.create_target(
                TargetEditorData(id="bad", backend="codex", args=["--"]),
                expected_revision=expected,
            )
        assert raised.value.code == "configuration_invalid"
        assert b'id = "bad"' not in source.read_bytes()
    finally:
        runtime.database.close()


def test_update_target_preserves_legacy_profile_key(tmp_path) -> None:
    source = _global_source(tmp_path)
    runtime = Runtime(load_config(source))
    try:
        service = runtime.mutations
        expected = service.source_read().revision
        data = TargetEditorData(
            id="primary",
            backend="codex",
            backend_profile="updated-profile",
            model="new-model",
            max_concurrency=4,
        )
        result, updated = service.update_target("primary", data, expected_revision=expected)
        assert updated.backend_profile == "updated-profile"
        assert updated.model == "new-model"

        file_text = source.read_text(encoding="utf-8")
        assert 'profile = "updated-profile"' in file_text
        assert 'backend_profile' not in file_text
        assert 'model = "new-model"' in file_text
    finally:
        runtime.database.close()


def test_update_target_rejects_rename_and_unknown_target(tmp_path) -> None:
    source = _global_source(tmp_path)
    runtime = Runtime(load_config(source))
    try:
        service = runtime.mutations
        expected = service.source_read().revision

        with pytest.raises(ConfigurationMutationError) as raised_rename:
            service.update_target(
                "primary",
                TargetEditorData(id="renamed", backend="codex"),
                expected_revision=expected,
            )
        assert raised_rename.value.code == "configuration_invalid"

        with pytest.raises(ConfigurationMutationError) as raised_missing:
            service.update_target(
                "missing",
                TargetEditorData(id="missing", backend="codex"),
                expected_revision=expected,
            )
        assert raised_missing.value.code == "not_found"
    finally:
        runtime.database.close()


def test_update_target_concurrency_conflict(tmp_path) -> None:
    source = _global_source(tmp_path)
    runtime = Runtime(load_config(source))
    try:
        service = runtime.mutations
        stale_revision = "0" * 64
        with pytest.raises(ConfigurationMutationError) as raised:
            service.update_target(
                "primary",
                TargetEditorData(id="primary", backend="codex"),
                expected_revision=stale_revision,
            )
        assert raised.value.code == "configuration_conflict"
        assert raised.value.current_revision == _revision(source)
    finally:
        runtime.database.close()


def test_delete_target_unreferenced_succeeds(tmp_path) -> None:
    source = _global_source(tmp_path)
    runtime = Runtime(load_config(source))
    try:
        service = runtime.mutations
        expected = service.source_read().revision
        data = TargetEditorData(id="standalone", backend="pi")
        res, _ = service.create_target(data, expected_revision=expected)

        del_res, deleted_id = service.delete_target("standalone", expected_revision=res.revision)
        assert deleted_id == "standalone"
        assert b"standalone" not in source.read_bytes()
        assert "standalone" not in [t.id for t in runtime.catalog.targets]
    finally:
        runtime.database.close()


def test_delete_target_blocked_by_global_and_project_declarations_ignores_jobs(tmp_path) -> None:
    runtime, project_root = _runtime_with_project(tmp_path)
    try:
        service = runtime.mutations
        source = service._resolve_source(None)

        proj_config = project_root / ".refract" / "config.toml"
        proj_config.parent.mkdir(parents=True, exist_ok=True)
        proj_config.write_text(
            """[profiles.quality]
consult = "primary"
review = "primary"
""",
            encoding="utf-8",
        )

        project = runtime.database.projects()[0]
        runtime.database.create_job(
            job_id="test-job-1",
            project_id=project.id,
            workflow="consult",
            profile="quality",
            prompt="test prompt",
            execution_plan_json=json.dumps({"targets": ["primary"]}),
            context_key="test-key",
            config_revision=service.source_read().revision,
        )

        expected = service.source_read().revision
        with pytest.raises(ConfigurationMutationError) as raised:
            service.delete_target("primary", expected_revision=expected)

        assert raised.value.code == "referenced"
        refs = raised.value.references
        assert refs is not None
        assert len(refs) > 0

        global_refs = [r for r in refs if r["scope"] == "global"]
        assert any(r["profile_id"] == "balanced" and r["workflow"] == "consult" for r in global_refs)

        project_refs = [r for r in refs if r["scope"] == "project"]
        assert any(r["project_id"] == project.id and r["profile_id"] == "quality" and r["workflow"] == "consult" for r in project_refs)

        assert all("job_id" not in r for r in refs)
    finally:
        runtime.database.close()


def test_reference_scanning_uses_declarations_not_effective_values(tmp_path) -> None:
    source = _global_source(tmp_path)
    runtime = Runtime(load_config(source))
    try:
        service = runtime.mutations
        refs = service.find_target_references("fallback")
        assert refs == []
    finally:
        runtime.database.close()


def test_read_targets_and_get_target_single_source_read(tmp_path, monkeypatch) -> None:
    source = _global_source(tmp_path)
    runtime = Runtime(load_config(source))
    try:
        service = runtime.mutations
        import refract.config_mutation as cm

        read_count = 0
        original_regular_source = cm._regular_source

        def counting_regular_source(path):
            nonlocal read_count
            read_count += 1
            return original_regular_source(path)

        monkeypatch.setattr(cm, "_regular_source", counting_regular_source)

        read_count = 0
        source_read, targets = service.read_targets()
        assert read_count == 1
        assert not source_read.absent
        assert source_read.revision == _revision(source)
        assert len(targets) == 2

        read_count = 0
        source_read, target = service.get_target("primary")
        assert read_count == 1
        assert not source_read.absent
        assert source_read.revision == _revision(source)
        assert target.id == "primary"
    finally:
        runtime.database.close()


def test_delete_target_scans_current_parsed_global_declarations(tmp_path) -> None:
    source = _global_source(tmp_path)
    runtime = Runtime(load_config(source))
    try:
        service = runtime.mutations
        assert not any(
            "fallback" in selection.targets
            for decl in runtime.catalog.profile_declarations.values()
            for selection in decl.workflows.values()
        )

        updated_text = source.read_text(encoding="utf-8") + 'other = "fallback"\n'
        source.write_text(updated_text, encoding="utf-8")
        current_rev = _revision(source)

        with pytest.raises(ConfigurationMutationError) as raised:
            service.delete_target("fallback", expected_revision=current_rev)

        assert raised.value.code == "referenced"
        refs = raised.value.references
        assert refs is not None
        assert any(
            r["scope"] == "global"
            and r["profile_id"] == "balanced"
            and r["workflow"] == "other"
            for r in refs
        )
    finally:
        runtime.database.close()


def test_delete_target_unreferenced_in_current_document_succeeds_even_if_stale_catalog_had_reference(
    tmp_path,
) -> None:
    source = _global_source(tmp_path)
    runtime = Runtime(load_config(source))
    try:
        service = runtime.mutations
        assert any(
            "primary" in selection.targets
            for decl in runtime.catalog.profile_declarations.values()
            for selection in decl.workflows.values()
        )

        new_text = """[daemon]
default_profile = "balanced"

[[targets]]
id = "primary"
backend = "codex"

[[targets]]
id = "fallback"
backend = "pi"

[profiles.balanced]
implement = "fallback"
review = "fallback"
consult = "fallback"
"""
        source.write_text(new_text, encoding="utf-8")
        current_rev = _revision(source)

        result, deleted_id = service.delete_target("primary", expected_revision=current_rev)
        assert deleted_id == "primary"
        assert result.changed
        _, remaining = service.read_targets()
        assert [t.id for t in remaining] == ["fallback"]
    finally:
        runtime.database.close()


def test_find_target_references_with_explicit_document(tmp_path) -> None:
    source = _global_source(tmp_path)
    runtime = Runtime(load_config(source))
    try:
        service = runtime.mutations
        doc = tomlkit.parse("""
[profiles.alpha]
fast = "target_x"
quality = ["target_y", "target_x"]
other = { targets = ["target_z"] }
extends = "target_x"
""")
        refs_x = service.find_target_references("target_x", document=doc)
        assert len(refs_x) == 2
        assert {r.workflow for r in refs_x} == {"fast", "quality"}
        assert all(r.scope == "global" and r.profile_id == "alpha" for r in refs_x)

        refs_z = service.find_target_references("target_z", document=doc)
        assert len(refs_z) == 1
        assert refs_z[0].workflow == "other"
    finally:
        runtime.database.close()


def test_phase3_profile_editor_models() -> None:
    from pydantic import ValidationError
    from refract.models import (
        ProfileEditorData,
        ProfileEditorResponse,
        ProfileReference,
        ProjectOverrideDeleteResponse,
        WorkflowPolicyData,
    )

    policy = WorkflowPolicyData(targets=["primary"])
    assert policy.targets == ["primary"]
    assert policy.timeout_s == 0

    with pytest.raises(ValidationError):
        WorkflowPolicyData(targets=["primary"], unknown_field="invalid")

    profile_data = ProfileEditorData(
        id="balanced",
        extends="  ",
        workflows={
            "consult": None,
            "implement": WorkflowPolicyData(targets=["primary", "fallback"], timeout_s=900),
        },
    )
    assert profile_data.id == "balanced"
    assert profile_data.extends is None
    assert profile_data.workflows["consult"] is None
    assert profile_data.workflows["implement"].timeout_s == 900

    with pytest.raises(ValidationError):
        ProfileEditorData(id="balanced", extra="disallowed")

    resp = ProfileEditorResponse(
        id="balanced",
        declared={"consult": None, "implement": policy},
        inherited={"consult": policy, "implement": None},
        effective={"consult": policy, "implement": policy},
        sources={"consult": "global", "implement": "declared"},
    )
    assert resp.declared["consult"] is None
    assert resp.inherited["consult"].targets == ["primary"]

    ref = ProfileReference(scope="project", project_id="p1", profile_id="child", relationship="extends")
    assert ref.relationship == "extends"

    del_resp = ProjectOverrideDeleteResponse(
        revision="rev1",
        source_path="/path/to/config.toml",
        deleted="balanced",
        fallback=resp,
    )
    assert del_resp.deleted == "balanced"
    assert del_resp.fallback.id == "balanced"


def test_global_profile_crud_and_references(tmp_path) -> None:
    source = _global_source(tmp_path)
    runtime = Runtime(load_config(source))
    try:
        service = runtime.mutations

        # 1. Read profiles
        source_read, profiles, default_prof, targets = service.read_profiles()
        assert not source_read.absent
        assert default_prof == "balanced"
        assert len(profiles) >= 1
        assert any(p.id == "balanced" for p in profiles)
        assert "primary" in targets

        # 2. Try to delete balanced (which is global default_profile) -> blocked with code='referenced'
        with pytest.raises(ConfigurationMutationError) as raised:
            service.delete_profile("balanced", expected_revision=source_read.revision)
        assert raised.value.code == "referenced"
        assert any(r["relationship"] == "default_profile" for r in raised.value.references)

        # 3. Create new profile 'custom' with shorthand workflow
        from refract.models import ProfileEditorData, WorkflowPolicyData
        new_prof = ProfileEditorData(
            id="custom",
            extends=None,
            workflows={
                "implement": WorkflowPolicyData(targets=["primary"]),
                "review": None,
            },
        )
        result, created = service.create_profile(new_prof, expected_revision=source_read.revision)
        assert created.id == "custom"
        assert created.declared["implement"].targets == ["primary"]
        assert created.declared["review"] is None
        # Shorthand check in TOML on disk: should be implement = "primary"
        doc = service.read_document(load_source(source))
        assert doc["profiles"]["custom"]["implement"] == "primary"

        # 4. Create child extending custom -> blocks deleting custom
        child_prof = ProfileEditorData(
            id="child",
            extends="custom",
            workflows={
                "review": WorkflowPolicyData(targets=["primary"]),
            },
        )
        result2, created_child = service.create_profile(child_prof, expected_revision=result.revision)
        assert created_child.extends == "custom"
        assert created_child.inherited["implement"].targets == ["primary"]

        # Attempt delete custom -> blocked by extends
        with pytest.raises(ConfigurationMutationError) as raised2:
            service.delete_profile("custom", expected_revision=result2.revision)
        assert raised2.value.code == "referenced"
        assert any(r["relationship"] == "extends" and r["profile_id"] == "child" for r in raised2.value.references)

        # 5. Update custom with timeout_s -> requires expansion to inline table
        update_data = ProfileEditorData(
            id="custom",
            extends=None,
            workflows={
                "implement": WorkflowPolicyData(targets=["primary"], timeout_s=120),
            },
        )
        # First delete child so we can test clean deletion later
        result3, _ = service.delete_profile("child", expected_revision=result2.revision)
        result4, updated = service.update_profile("custom", update_data, expected_revision=result3.revision)
        assert updated.declared["implement"].timeout_s == 120
        doc2 = service.read_document(load_source(source))
        val = doc2["profiles"]["custom"]["implement"]
        assert isinstance(val, (dict, tomlkit.items.InlineTable))
        assert val["timeout_s"] == 120

        # 6. Delete custom now succeeds
        result5, deleted_id = service.delete_profile("custom", expected_revision=result4.revision)
        assert deleted_id == "custom"
    finally:
        runtime.database.close()


def test_project_override_crud_and_missing_file_creation(tmp_path) -> None:
    runtime, project_root = _runtime_with_project(tmp_path)
    try:
        service = runtime.mutations
        proj_cfg_path = project_root / ".refract" / "config.toml"
        assert not proj_cfg_path.exists()

        # 1. Read overrides when absent
        source_read, overrides, g_def, p_def, targets = service.read_project_overrides(project_root)
        assert source_read.absent
        assert overrides == []
        assert g_def == "balanced"
        assert p_def == "balanced"

        # 2. Create override when file absent -> creates minimal file
        from refract.models import ProfileEditorData, WorkflowPolicyData
        override_data = ProfileEditorData(
            id="balanced",
            extends=None,
            workflows={
                "implement": WorkflowPolicyData(targets=["primary"]),
            },
        )
        result, created = service.create_project_override(
            project_root, override_data, expected_revision=""
        )
        assert created.id == "balanced"
        assert created.declared["implement"].targets == ["primary"]
        assert proj_cfg_path.exists()

        # Confirm minimal file creation (no unrelated sections)
        raw_text = proj_cfg_path.read_text(encoding="utf-8")
        assert "daemon" not in raw_text
        assert "project" not in raw_text
        assert "[profiles.balanced]" in raw_text

        # 3. Read again -> present
        source_read2, overrides2, _, _, _ = service.read_project_overrides(project_root)
        assert not source_read2.absent
        assert len(overrides2) == 1
        assert overrides2[0].id == "balanced"

        # 4. Update override
        update_data = ProfileEditorData(
            id="balanced",
            extends=None,
            workflows={
                "implement": WorkflowPolicyData(targets=["primary"], timeout_s=300),
            },
        )
        result2, updated = service.update_project_override(
            project_root, "balanced", update_data, expected_revision=result.revision
        )
        assert updated.declared["implement"].timeout_s == 300

        # 5. Delete override -> returns resulting global fallback
        result3, deleted_id, fallback = service.delete_project_override(
            project_root, "balanced", expected_revision=result2.revision
        )
        assert deleted_id == "balanced"
        assert fallback is not None
        assert fallback.id == "balanced"
        assert fallback.declared["implement"] is None  # undeclared in project scope now
        assert fallback.effective["implement"] is not None  # effective from global

        # A project-only profile has no global fallback after removal.
        local_data = ProfileEditorData(
            id="project-only",
            workflows={"implement": WorkflowPolicyData(targets=["primary"])},
        )
        local_result, local_profile = service.create_project_override(
            project_root, local_data, expected_revision=result3.revision,
        )
        assert local_profile.id == "project-only"
        _, deleted_id, fallback = service.delete_project_override(
            project_root, "project-only", expected_revision=local_result.revision,
        )
        assert deleted_id == "project-only"
        assert fallback is None
    finally:
        runtime.database.close()
