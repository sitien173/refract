"""Resolve a path to its registered project by canonical Git root."""

from __future__ import annotations

import sqlite3
import subprocess
import uuid
from pathlib import Path

from refract.config.models import DaemonConfig
from refract.models import OrchestrationError, ProjectView
from refract.store.database import Database


def resolve_project(database: Database, config: DaemonConfig, path: str) -> ProjectView:
    """Resolve the canonical Git root idempotently."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(Path(path).expanduser()), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        completed = None
    if completed is None or completed.returncode != 0 or not completed.stdout.strip():
        raise OrchestrationError(
            "Project path is not inside a Git repository.",
            code="invalid_path",
            next_action="Pass a path inside the project's Git repository.",
        )
    resolved = Path(completed.stdout.strip()).resolve()
    config_path = getattr(config, "config_path", None)
    if config_path is not None and (
        resolved / ".refract" / "config.toml"
    ).resolve() == Path(config_path).resolve():
        raise OrchestrationError(
            "Project path holds the global Refract configuration.",
            code="invalid_path",
            next_action="Register the project's own directory instead.",
        )
    root = resolved.as_posix()
    existing = next((project for project in database.projects() if project.root == root), None)
    if existing is not None:
        return existing
    try:
        return database.upsert_project(project_id=str(uuid.uuid4()), root=root)
    except sqlite3.IntegrityError:
        existing = next((project for project in database.projects() if project.root == root), None)
        if existing is None:
            raise
        return existing
