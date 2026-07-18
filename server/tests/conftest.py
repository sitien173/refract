"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_openmcp_home(tmp_path_factory, monkeypatch):
    """Keep daemon state and logs out of the developer's home directory."""
    isolated_home = tmp_path_factory.mktemp("openmcp-home")
    monkeypatch.setattr(Path, "home", lambda: isolated_home)
    yield
