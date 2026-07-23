from __future__ import annotations

import json

import pytest

from openmcp.config import TargetConfig, load_config, load_project_config, load_task_guide, validate_target_args
from openmcp.planning import resolve_execution_plan
from openmcp.workflows import get_workflow
from tests.orchestration_helpers import config


def _explicit_config() -> str:
    return """[daemon]
default_profile = "balanced"

[[targets]]
id = "primary"
backend = "codex"
capabilities = ["code", "review", "consult"]

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
"""


def test_task_guide_prefers_project_then_global(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "task_guide.json").write_text(json.dumps({"scope": "global"}), encoding="utf-8")
    root = tmp_path / "project"
    (root / ".openmcp").mkdir(parents=True)
    (root / ".openmcp" / "task_guide.json").write_text(json.dumps({"scope": "project"}), encoding="utf-8")
    assert load_task_guide(home, root) == {"scope": "project"}
    assert load_task_guide(home) == {"scope": "global"}


def test_default_builtins_resolve_capable_targets(tmp_path) -> None:
    catalog = config(tmp_path / "home")
    for name in ("implement", "review", "consult"):
        assert resolve_execution_plan(get_workflow(name), catalog, "balanced").selection.targets == ("primary",)


def test_missing_config_file_is_rejected(tmp_path) -> None:
    with pytest.raises(ValueError, match="Missing config file"):
        load_config(tmp_path / "config.toml")


@pytest.mark.parametrize(
    ("section", "config"),
    [
        ("targets", '[daemon]\ndefault_profile = "balanced"\n[profiles.balanced]\nimplement = "primary"\nreview = "primary"\nconsult = "primary"\n'),
        ("profiles", '[daemon]\ndefault_profile = "balanced"\n[[targets]]\nid = "primary"\nbackend = "codex"\n'),
    ],
)
def test_required_config_sections_must_be_present(tmp_path, section, config) -> None:
    path = tmp_path / "config.toml"
    path.write_text(config, encoding="utf-8")

    with pytest.raises(ValueError, match=section):
        load_config(path)


@pytest.mark.parametrize(
    ("section", "config"),
    [
        (
            "targets",
            '[daemon]\ndefault_profile = "balanced"\n[targets]\n[profiles.balanced]\nimplement = "primary"\nreview = "primary"\nconsult = "primary"\n',
        ),
        (
            "profiles",
            '[daemon]\ndefault_profile = "balanced"\n[[targets]]\nid = "primary"\nbackend = "codex"\n[profiles]\n',
        ),
    ],
)
def test_required_config_sections_must_not_be_empty(tmp_path, section, config) -> None:
    path = tmp_path / "config.toml"
    path.write_text(config, encoding="utf-8")

    with pytest.raises(ValueError, match=section):
        load_config(path)


@pytest.mark.parametrize(
    "daemon", ["[daemon]", '[daemon]\ndefault_profile = "missing"'],
)
def test_default_profile_must_be_explicit_and_known(tmp_path, daemon) -> None:
    path = tmp_path / "config.toml"
    path.write_text(_explicit_config().replace('[daemon]\ndefault_profile = "balanced"', daemon), encoding="utf-8")

    with pytest.raises(ValueError, match="default_profile"):
        load_config(path)


def test_removed_global_profile_aliases_are_rejected(tmp_path) -> None:
    legacy_profiles = "routing_" + "profiles"
    legacy_default = "default_" + "routing_" + "profile"
    path = tmp_path / "config.toml"
    path.write_text(
        f"[{legacy_profiles}.balanced]\n"
        f"{legacy_default} = \"balanced\"\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unsupported"):
        load_config(path)


def test_removed_project_profile_aliases_are_rejected(tmp_path) -> None:
    root = tmp_path / "project"
    (root / ".openmcp").mkdir(parents=True)
    legacy_profiles = "routing_" + "profiles"
    (root / ".openmcp" / "config.toml").write_text(
        f"[{legacy_profiles}.quality]\nimplement = \"primary\"\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unsupported"):
        load_project_config(root, config(tmp_path / "home"))


def test_project_config_overlays_profiles(tmp_path) -> None:
    root = tmp_path / "project"
    (root / ".openmcp").mkdir(parents=True)
    (root / ".openmcp" / "config.toml").write_text("""[project]
default_profile = "quality"
[profiles.quality]
implement = "primary"
review = "primary"
consult = "primary"
""", encoding="utf-8")
    catalog = config(tmp_path / "home")
    resolved = load_project_config(root, catalog)
    assert resolved.default_profile == "quality"
    assert resolve_execution_plan(get_workflow("implement"), resolved, "quality").selection.targets == ("primary",)


@pytest.mark.parametrize("backend,args", [("agy", ("--",)), ("codex", ("--cd", "/other")), ("pi", ("--extension", "unsafe.ts"))])
def test_config_rejects_reserved_target_args(backend, args) -> None:
    with pytest.raises(ValueError):
        validate_target_args("unsafe", backend, args, isolated=backend == "pi")


def test_custom_target_defaults_support_all_semantic_workflows(tmp_path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text("""[[targets]]
id = "primary"
backend = "codex"
[daemon]
default_profile = "balanced"
[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
""", encoding="utf-8")
    monkeypatch.setenv("OPENMCP_HOME", str(home))
    catalog = load_config(home / "config.toml")
    assert TargetConfig(id="primary", backend="codex").capabilities == ("code", "reasoning", "review", "consult")
    assert all(resolve_execution_plan(get_workflow(name), catalog, "balanced").selection.targets == ("primary",) for name in ("implement", "review", "consult"))
