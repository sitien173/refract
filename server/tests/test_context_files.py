from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from openmcp.context_files import (
    MANAGED_MARKER,
    _open_managed_for_replacement,
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


def test_replacement_race_swapped_foreign_path_is_neither_modified_nor_deleted(tmp_path, monkeypatch) -> None:
    """A foreign file swapped in after validation is refused through the
    descriptor and is neither truncated nor unlinked.

    The race is simulated by swapping the target pathname to a foreign file
    immediately before the inode-safe descriptor open. Because replacement
    opens with O_NOFOLLOW, re-validates the marker through the descriptor, and
    never unlinks the pathname, the foreign file survives byte-identical.
    """
    import openmcp.context_files as context_files

    root = repository(tmp_path)
    target = root / "AGENTS.override.md"
    # Start with a managed leftover so the pre-check passes.
    target.write_text(MANAGED_MARKER + "\nstale\n", encoding="utf-8")
    foreign = b"foreign content that must survive\n"

    original_open = context_files._open_managed_for_replacement

    def racing_open(path, *args, **kwargs):
        # Simulate the attacker swapping the path to a foreign file between the
        # pre-check and the descriptor open.
        target.write_bytes(foreign)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(context_files, "_open_managed_for_replacement", racing_open)

    with pytest.raises(ValueError, match="foreign"):
        materialize_context_file(root, target, "follow the plan")

    assert target.read_bytes() == foreign
    assert target.exists()


def test_replacement_race_swapped_tracked_path_is_neither_modified_nor_deleted(tmp_path, monkeypatch) -> None:
    """A tracked file swapped in after validation is refused and survives."""
    import openmcp.context_files as context_files

    root = repository(tmp_path)
    target = root / "AGENTS.override.md"
    target.write_text(MANAGED_MARKER + "\nstale\n", encoding="utf-8")

    original_open = context_files._open_managed_for_replacement

    def racing_open(path, *args, **kwargs):
        # Swap in a file that is also tracked by Git.
        tracked = b"tracked content\n"
        target.write_bytes(tracked)
        git(root, "add", "-f", "AGENTS.override.md")
        git(root, "commit", "-m", "track override")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(context_files, "_open_managed_for_replacement", racing_open)

    with pytest.raises(ValueError, match="foreign"):
        materialize_context_file(root, target, "follow the plan")

    assert target.read_bytes() == b"tracked content\n"
    assert target.exists()
    assert git(root, "status", "--porcelain") == ""


def test_replacement_race_swapped_tracked_marker_file_fails_closed(tmp_path, monkeypatch) -> None:
    """A tracked marker-bearing file swapped in after the index check is
    refused: the exact-inode identity check fails closed before mutation, and
    the tracked file survives."""
    import openmcp.context_files as context_files

    root = repository(tmp_path)
    target = root / "AGENTS.override.md"
    # Pre-validated managed leftover.
    target.write_text(MANAGED_MARKER + "\nstale\n", encoding="utf-8")
    tracked = MANAGED_MARKER.encode() + b"\ntracked content\n"

    original_open = context_files._open_managed_for_replacement

    def racing_open(path, expected, *args, **kwargs):
        # Swap the path to a DIFFERENT inode that carries the marker and is
        # also tracked by Git. The old inode is replaced in the index.
        target.write_bytes(tracked)
        git(root, "add", "-f", "AGENTS.override.md")
        git(root, "commit", "-m", "track override")
        return original_open(path, expected, *args, **kwargs)

    monkeypatch.setattr(context_files, "_open_managed_for_replacement", racing_open)

    with pytest.raises(ValueError, match="identity|tracked"):
        materialize_context_file(root, target, "follow the plan")

    assert target.read_bytes() == tracked
    assert git(root, "status", "--porcelain") == ""


def test_replacement_rechecks_tracking_on_same_inode_before_mutation(tmp_path, monkeypatch) -> None:
    """If the prevalidated managed inode's path becomes Git-tracked while the
    descriptor is open (same inode, marker intact), the tracking recheck fails
    closed before any truncation, and the inode survives byte-identical."""
    import openmcp.context_files as context_files

    root = repository(tmp_path)
    target = root / "AGENTS.override.md"
    original = MANAGED_MARKER.encode() + b"\nmanaged\n"
    target.write_bytes(original)
    original_identity = (target.stat().st_dev, target.stat().st_ino)

    original_replace = context_files._replace_managed_file

    def racing_replace(path, content, expected, repo_root):
        # Same inode: rewrite in place, then stage it so the tracking recheck
        # inside _replace_managed_file (after open, before truncate) fails.
        target.write_bytes(original)
        git(root, "add", "-f", "AGENTS.override.md")
        return original_replace(path, content, expected, repo_root)

    monkeypatch.setattr(context_files, "_replace_managed_file", racing_replace)

    with pytest.raises(ValueError, match="tracked"):
        materialize_context_file(root, target, "follow the plan")

    # The inode identity is unchanged and the content is untouched.
    assert (target.stat().st_dev, target.stat().st_ino) == original_identity
    assert target.read_bytes() == original


def test_cleanup_race_swapped_foreign_path_is_restored(tmp_path, monkeypatch) -> None:
    """A foreign file swapped in at the path is quarantined, fails marker
    validation, and is restored to the original path untouched."""
    import openmcp.context_files as context_files

    root = repository(tmp_path)
    target = root / "AGENTS.override.md"
    target.write_text(MANAGED_MARKER + "\nmanaged\n", encoding="utf-8")
    foreign = b"foreign content that must survive\n"

    original_quarantine = context_files._quarantine_candidate

    def racing_quarantine(path):
        # Swap the path to a foreign file immediately before quarantine.
        path.write_bytes(foreign)
        return original_quarantine(path)

    monkeypatch.setattr(context_files, "_quarantine_candidate", racing_quarantine)

    removed = cleanup_context_file(root, target)

    assert removed == []
    assert target.read_bytes() == foreign
    assert not list(root.glob("*.openmcp-quarantine-*"))


def test_cleanup_race_swapped_tracked_path_is_restored(tmp_path, monkeypatch) -> None:
    """A tracked file swapped in at the path is quarantined, fails tracking
    validation, and is restored to the original path untouched."""
    import openmcp.context_files as context_files

    root = repository(tmp_path)
    target = root / "AGENTS.override.md"
    target.write_text(MANAGED_MARKER + "\nmanaged\n", encoding="utf-8")
    tracked = b"tracked content\n"

    original_quarantine = context_files._quarantine_candidate

    def racing_quarantine(path):
        # Swap in a tracked file before quarantine.
        path.write_bytes(tracked)
        git(root, "add", "-f", "AGENTS.override.md")
        git(root, "commit", "-m", "track override")
        return original_quarantine(path)

    monkeypatch.setattr(context_files, "_quarantine_candidate", racing_quarantine)

    removed = cleanup_context_file(root, target)

    assert removed == []
    assert target.read_bytes() == tracked
    assert git(root, "status", "--porcelain") == ""
    assert not list(root.glob("*.openmcp-quarantine-*"))


def test_sweep_race_swapped_foreign_path_is_restored(tmp_path, monkeypatch) -> None:
    """The sweep applies the same quarantine safety to a foreign swap."""
    import openmcp.context_files as context_files

    root = repository(tmp_path)
    target = root / "AGENTS.override.md"
    target.write_text(MANAGED_MARKER + "\nmanaged\n", encoding="utf-8")
    foreign = b"foreign content that must survive\n"

    original_quarantine = context_files._quarantine_candidate

    def racing_quarantine(path):
        path.write_bytes(foreign)
        return original_quarantine(path)

    monkeypatch.setattr(context_files, "_quarantine_candidate", racing_quarantine)

    removed = sweep_context_files(root, target)

    assert removed == []
    assert target.read_bytes() == foreign
    assert not list(root.glob("*.openmcp-quarantine-*"))


def test_cleanup_restore_preserves_quarantined_bytes_when_target_replaced(tmp_path, monkeypatch) -> None:
    """If the original path is concurrently claimed while a non-managed
    candidate is quarantined, restoration refuses to overwrite it and preserves
    the quarantined bytes, reporting failure rather than deleting data."""
    import openmcp.context_files as context_files

    root = repository(tmp_path)
    target = root / "AGENTS.override.md"
    target.write_text(MANAGED_MARKER + "\nmanaged\n", encoding="utf-8")
    foreign = b"foreign\n"
    replacement = b"concurrent writer\n"

    original_quarantine = context_files._quarantine_candidate
    original_restore = context_files._restore_quarantined

    def racing_quarantine(path):
        path.write_bytes(foreign)
        return original_quarantine(path)

    def racing_restore(target_path, quarantine_path):
        # A concurrent writer claims the original path before restore.
        target_path.write_bytes(replacement)
        return original_restore(target_path, quarantine_path)

    monkeypatch.setattr(context_files, "_quarantine_candidate", racing_quarantine)
    monkeypatch.setattr(context_files, "_restore_quarantined", racing_restore)

    with pytest.raises(ValueError, match="preserved"):
        cleanup_context_file(root, target)

    # The concurrent writer's file is untouched and the quarantined bytes are
    # preserved at the quarantine path, not deleted.
    assert target.read_bytes() == replacement
    quarantined = list(root.glob("*.openmcp-quarantine-*"))
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == foreign
