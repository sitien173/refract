from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from openmcp.context_files import (
    MANAGED_MARKER,
    cleanup_context_file,
    git_repository_root,
    is_tracked,
    materialize_context_file,
    managed_exclude_block,
    sweep_context_files,
)


def git(path: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def repository(path: Path) -> Path:
    root = path / "project"
    root.mkdir()
    git(root, "init")
    git(root, "config", "user.name", "OpenMCP Tests")
    git(root, "config", "user.email", "openmcp@example.invalid")
    (root / "README.md").write_text("baseline\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-m", "baseline")
    return root


def common_dir(root: Path) -> Path:
    value = git(root, "rev-parse", "--git-common-dir")
    common = Path(value)
    return common if common.is_absolute() else (root / common).resolve()


def exclude_path(root: Path) -> Path:
    return common_dir(root) / "info" / "exclude"


def write_exclude(root: Path, content: str) -> None:
    exclude_path(root).write_text(content, encoding="utf-8")


def read_exclude(root: Path) -> str:
    return exclude_path(root).read_text(encoding="utf-8")


def test_managed_marker_is_a_comment_header() -> None:
    assert MANAGED_MARKER.startswith("<!-- openmcp")
    assert MANAGED_MARKER.endswith("-->")


def test_git_repository_root_resolves_main_checkout(tmp_path) -> None:
    root = repository(tmp_path)
    assert git_repository_root(root) == root


def test_managed_exclude_block_is_delimited_and_anchored() -> None:
    block = managed_exclude_block("AGENTS.override.md")
    assert "BEGIN openmcp" in block and "END openmcp" in block
    assert "/AGENTS.override.md" in block
    assert block.count("AGENTS.override.md") == 2


def test_is_tracked_true_for_index_membership_even_when_deleted(tmp_path) -> None:
    root = repository(tmp_path)
    (root / "AGENTS.override.md").write_text("tracked\n", encoding="utf-8")
    git(root, "add", "AGENTS.override.md")
    git(root, "commit", "-m", "track override")
    (root / "AGENTS.override.md").unlink()

    assert is_tracked(root, root / "AGENTS.override.md")


def test_is_tracked_false_for_untracked_and_excluded(tmp_path) -> None:
    root = repository(tmp_path)
    assert not is_tracked(root, root / "AGENTS.override.md")
    write_exclude(root, "/AGENTS.override.md\n")
    assert not is_tracked(root, root / "AGENTS.override.md")


def test_materialize_composes_instruction_then_root_agents(tmp_path) -> None:
    root = repository(tmp_path)
    (root / "AGENTS.md").write_text("root guidance\n", encoding="utf-8")
    git(root, "add", "AGENTS.md")
    git(root, "commit", "-m", "add agents")

    created = materialize_context_file(root, root / "AGENTS.override.md", "follow the plan")

    assert created == [root / "AGENTS.override.md"]
    content = (root / "AGENTS.override.md").read_bytes()
    assert content.startswith(MANAGED_MARKER.encode())
    assert b"follow the plan" in content
    assert b"root guidance" in content


def test_materialize_without_agents_contains_instruction_only(tmp_path) -> None:
    root = repository(tmp_path)
    created = materialize_context_file(root, root / "AGENTS.override.md", "follow the plan")

    assert created == [root / "AGENTS.override.md"]
    content = (root / "AGENTS.override.md").read_bytes()
    assert b"follow the plan" in content
    assert MANAGED_MARKER.encode() in content


def test_materialize_composes_from_project_root_in_repo_subdirectory(tmp_path) -> None:
    root = repository(tmp_path)
    (root / "AGENTS.md").write_text("repo-level guidance\n", encoding="utf-8")
    git(root, "add", "AGENTS.md")
    git(root, "commit", "-m", "repo agents")
    project = root / "sub" / "project"
    project.mkdir(parents=True)
    (project / "AGENTS.md").write_text("project-level guidance\n", encoding="utf-8")

    created = materialize_context_file(project, project / "AGENTS.override.md", "follow the plan")

    assert created == [project / "AGENTS.override.md"]
    content = (project / "AGENTS.override.md").read_bytes()
    assert MANAGED_MARKER.encode() in content
    assert b"follow the plan" in content
    assert b"project-level guidance" in content
    assert b"repo-level guidance" not in content


def test_materialize_nothing_to_deliver_checks_project_root_in_subdirectory(tmp_path) -> None:
    root = repository(tmp_path)
    (root / "AGENTS.md").write_text("repo-level guidance\n", encoding="utf-8")
    git(root, "add", "AGENTS.md")
    git(root, "commit", "-m", "repo agents")
    project = root / "sub" / "project"
    project.mkdir(parents=True)

    created = materialize_context_file(project, project / "AGENTS.override.md", "")

    # No project-level AGENTS.md and an empty instruction: nothing to deliver.
    assert created == []
    assert not (project / "AGENTS.override.md").exists()


def test_materialize_is_git_invisible_in_main_and_linked_worktree(tmp_path) -> None:
    root = repository(tmp_path)
    linked = tmp_path / "linked"
    git(root, "worktree", "add", "-q", str(linked), "HEAD")

    materialize_context_file(root, root / "AGENTS.override.md", "follow the plan")

    assert git(root, "status", "--porcelain") == ""
    assert git(linked, "status", "--porcelain") == ""
    assert git(root, "check-ignore", "--", "AGENTS.override.md") == "AGENTS.override.md"
    assert git(linked, "check-ignore", "--", "AGENTS.override.md") == "AGENTS.override.md"


def test_exclude_block_written_once_across_repeated_materializations(tmp_path) -> None:
    root = repository(tmp_path)
    materialize_context_file(root, root / "AGENTS.override.md", "one")
    materialize_context_file(root, root / "AGENTS.override.md", "two")

    content = read_exclude(root)
    assert content.count("BEGIN openmcp") == 1
    assert content.count("/AGENTS.override.md") == 1


def test_exclude_block_preserves_unrelated_exclude_content(tmp_path) -> None:
    root = repository(tmp_path)
    write_exclude(root, "# user pattern\n*.tmp\n")

    materialize_context_file(root, root / "AGENTS.override.md", "follow the plan")

    content = read_exclude(root)
    assert content.startswith("# user pattern\n*.tmp\n")
    assert content.count("BEGIN openmcp") == 1


def test_cleanup_removes_regular_marker_file(tmp_path) -> None:
    root = repository(tmp_path)
    materialize_context_file(root, root / "AGENTS.override.md", "follow the plan")
    assert (root / "AGENTS.override.md").exists()

    removed = cleanup_context_file(root, root / "AGENTS.override.md")

    assert removed == [root / "AGENTS.override.md"]
    assert not (root / "AGENTS.override.md").exists()
    assert git(root, "status", "--porcelain") == ""


def test_cleanup_leaves_foreign_file_untouched(tmp_path) -> None:
    root = repository(tmp_path)
    (root / "AGENTS.override.md").write_text("foreign content\n", encoding="utf-8")

    removed = cleanup_context_file(root, root / "AGENTS.override.md")

    assert removed == []
    assert (root / "AGENTS.override.md").read_text(encoding="utf-8") == "foreign content\n"


def test_cleanup_leaves_symlink_untouched(tmp_path) -> None:
    root = repository(tmp_path)
    (root / "target.txt").write_text("target\n", encoding="utf-8")
    (root / "AGENTS.override.md").symlink_to("target.txt")

    removed = cleanup_context_file(root, root / "AGENTS.override.md")

    assert removed == []
    assert (root / "AGENTS.override.md").is_symlink()


def test_materialize_refuses_tracked_file_and_leaves_byte_identical(tmp_path) -> None:
    root = repository(tmp_path)
    original = b"tracked content\n"
    (root / "AGENTS.override.md").write_bytes(original)
    git(root, "add", "AGENTS.override.md")
    git(root, "commit", "-m", "track override")

    with pytest.raises(ValueError, match="tracked"):
        materialize_context_file(root, root / "AGENTS.override.md", "follow the plan")

    assert (root / "AGENTS.override.md").read_bytes() == original


def test_materialize_refuses_untracked_foreign_file(tmp_path) -> None:
    root = repository(tmp_path)
    (root / "AGENTS.override.md").write_text("foreign\n", encoding="utf-8")

    with pytest.raises(ValueError, match="foreign"):
        materialize_context_file(root, root / "AGENTS.override.md", "follow the plan")

    assert (root / "AGENTS.override.md").read_text(encoding="utf-8") == "foreign\n"


def test_non_git_materialize_refuses_foreign_file_and_preserves_it(tmp_path) -> None:
    root = tmp_path / "plain-project"
    root.mkdir()
    (root / "AGENTS.override.md").write_text("foreign\n", encoding="utf-8")

    with pytest.raises(ValueError, match="foreign"):
        materialize_context_file(root, root / "AGENTS.override.md", "follow the plan")

    assert (root / "AGENTS.override.md").read_text(encoding="utf-8") == "foreign\n"


def test_non_git_materialize_refuses_symlink_target(tmp_path) -> None:
    root = tmp_path / "plain-project"
    root.mkdir()
    (root / "target.txt").write_text("target\n", encoding="utf-8")
    (root / "AGENTS.override.md").symlink_to("target.txt")

    with pytest.raises(ValueError, match="symlink"):
        materialize_context_file(root, root / "AGENTS.override.md", "follow the plan")

    assert (root / "AGENTS.override.md").is_symlink()


def test_non_git_materialize_refuses_directory_target(tmp_path) -> None:
    root = tmp_path / "plain-project"
    root.mkdir()
    (root / "AGENTS.override.md").mkdir()

    with pytest.raises(ValueError, match="directory"):
        materialize_context_file(root, root / "AGENTS.override.md", "follow the plan")

    assert (root / "AGENTS.override.md").is_dir()


def test_non_git_materialize_refuses_hardlink_target(tmp_path) -> None:
    root = tmp_path / "plain-project"
    root.mkdir()
    (root / "target.txt").write_text("target\n", encoding="utf-8")
    os.link(root / "target.txt", root / "AGENTS.override.md")

    with pytest.raises(ValueError, match="hardlink|link"):
        materialize_context_file(root, root / "AGENTS.override.md", "follow the plan")

    assert (root / "AGENTS.override.md").exists()


def test_non_git_materialize_overwrites_marker_leftover(tmp_path) -> None:
    root = tmp_path / "plain-project"
    root.mkdir()
    (root / "AGENTS.override.md").write_text(MANAGED_MARKER + "\nstale\n", encoding="utf-8")

    created = materialize_context_file(root, root / "AGENTS.override.md", "fresh")

    assert created == [root / "AGENTS.override.md"]
    assert b"fresh" in (root / "AGENTS.override.md").read_bytes()


def test_non_git_materialize_composes_project_agents(tmp_path) -> None:
    root = tmp_path / "plain-project"
    root.mkdir()
    (root / "AGENTS.md").write_text("plain guidance\n", encoding="utf-8")

    created = materialize_context_file(root, root / "AGENTS.override.md", "follow the plan")

    assert created == [root / "AGENTS.override.md"]
    content = (root / "AGENTS.override.md").read_bytes()
    assert b"follow the plan" in content
    assert b"plain guidance" in content


def test_materialize_refuses_symlink_target(tmp_path) -> None:
    root = repository(tmp_path)
    (root / "target.txt").write_text("target\n", encoding="utf-8")
    (root / "AGENTS.override.md").symlink_to("target.txt")

    with pytest.raises(ValueError, match="symlink"):
        materialize_context_file(root, root / "AGENTS.override.md", "follow the plan")


def test_materialize_refuses_hardlink_target(tmp_path) -> None:
    root = repository(tmp_path)
    (root / "target.txt").write_text("target\n", encoding="utf-8")
    os.link(root / "target.txt", root / "AGENTS.override.md")

    with pytest.raises(ValueError, match="hardlink|link"):
        materialize_context_file(root, root / "AGENTS.override.md", "follow the plan")


def test_materialize_refuses_directory_target(tmp_path) -> None:
    root = repository(tmp_path)
    (root / "AGENTS.override.md").mkdir()

    with pytest.raises(ValueError, match="directory"):
        materialize_context_file(root, root / "AGENTS.override.md", "follow the plan")


def test_materialize_overwrites_leftover_marker_file(tmp_path) -> None:
    root = repository(tmp_path)
    (root / "AGENTS.override.md").write_text(
        MANAGED_MARKER + "\nstale\n", encoding="utf-8"
    )

    created = materialize_context_file(root, root / "AGENTS.override.md", "fresh")

    assert created == [root / "AGENTS.override.md"]
    assert b"stale" not in (root / "AGENTS.override.md").read_bytes()


def test_materialize_creates_with_exclusive_open(tmp_path) -> None:
    root = repository(tmp_path)
    materialize_context_file(root, root / "AGENTS.override.md", "follow the plan")

    # A re-materialization overwrites the managed leftover rather than raising.
    created = materialize_context_file(root, root / "AGENTS.override.md", "again")
    assert created == [root / "AGENTS.override.md"]
    assert b"again" in (root / "AGENTS.override.md").read_bytes()


def test_sweep_removes_only_marker_untracked_files(tmp_path) -> None:
    root = repository(tmp_path)
    (root / "AGENTS.override.md").write_text(
        MANAGED_MARKER + "\nmanaged\n", encoding="utf-8"
    )
    (root / "other.txt").write_text("unrelated\n", encoding="utf-8")
    (root / "AGENTS.md").write_text("real guidance\n", encoding="utf-8")

    removed = sweep_context_files(root, root / "AGENTS.override.md")

    assert removed == [root / "AGENTS.override.md"]
    assert not (root / "AGENTS.override.md").exists()
    assert (root / "other.txt").exists()
    assert (root / "AGENTS.md").exists()


def test_sweep_skips_git_when_no_candidate_exists(tmp_path, monkeypatch) -> None:
    root = repository(tmp_path)
    calls: list[list[str]] = []

    def fake_run(command, *args, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    sweep_context_files(root, root / "AGENTS.override.md")

    assert calls == []
