from __future__ import annotations

import pytest

from openmcp.repositories import RepositoryError, commit, inspect_repository, reset
from tests.orchestration_helpers import git, repository


def test_inspect_requires_attached_clean_repository(tmp_path) -> None:
    root = repository(tmp_path)
    state = inspect_repository(root)
    assert state.root == root.resolve()
    assert state.branch and state.clean
    git(root, "checkout", "--detach")
    with pytest.raises(RepositoryError, match="attached branch"):
        inspect_repository(root)


def test_commit_writes_directly_to_current_branch(tmp_path) -> None:
    root = repository(tmp_path)
    baseline = git(root, "rev-parse", "HEAD")
    (root / "result.txt").write_text("created\n", encoding="utf-8")
    result = commit(root, "job-1", "feat: direct result")
    assert result != baseline
    assert git(root, "log", "-1", "--format=%s") == "feat: direct result"
    assert git(root, "status", "--porcelain") == ""


def test_commit_without_changes_returns_current_head(tmp_path) -> None:
    root = repository(tmp_path)
    assert commit(root, "job-1") == git(root, "rev-parse", "HEAD")


def test_reset_restores_tracked_and_nonignored_untracked_state(tmp_path) -> None:
    root = repository(tmp_path)
    baseline = git(root, "rev-parse", "HEAD")
    (root / "README.md").write_text("changed\n", encoding="utf-8")
    (root / "new.txt").write_text("new\n", encoding="utf-8")
    reset(root, baseline)
    assert (root / "README.md").read_text(encoding="utf-8") == "baseline\n"
    assert not (root / "new.txt").exists()
    assert git(root, "status", "--porcelain") == ""
