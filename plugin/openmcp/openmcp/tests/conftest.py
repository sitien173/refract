"""Test isolation fixtures.

The smoke tests assert how ``server._effective_env()`` resolves backend
defaults. Without isolation, the developer's real ``~/.openmcp/.env``
silently leaks into the test process and changes the resolution order,
masking regressions in the precedence logic.

We patch ``Path.home`` for the duration of every test to a directory that
contains *no* ``.openmcp/.env``, so the dotenv loader always returns an
empty dict unless the test explicitly writes one.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_openmcp_dotenv(tmp_path_factory, monkeypatch):
    """Point ``Path.home()`` at an empty tmp dir so the developer's real
    ``~/.openmcp/.env`` does not leak into the test process.

    Tests that need a specific dotenv content (or specific ``home``)
    can still override via their own ``monkeypatch.setattr(Path, "home", ...)``
    inside the test body — the per-test override wins.
    """
    isolated_home = tmp_path_factory.mktemp("openmcp-home")
    monkeypatch.setattr(Path, "home", lambda: isolated_home)
    yield
