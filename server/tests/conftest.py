"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_refract_home(tmp_path_factory, monkeypatch):
    """Keep daemon state and logs out of the developer's home directory."""
    isolated_home = tmp_path_factory.mktemp("refract-home")
    monkeypatch.setattr(Path, "home", lambda: isolated_home)
    yield
