"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_refract_home(tmp_path_factory, monkeypatch):
    """Keep daemon state and logs out of the developer's home directory."""
    isolated_home = tmp_path_factory.mktemp("refract-home")
    monkeypatch.setattr(Path, "home", lambda: isolated_home)
    monkeypatch.setenv("DO_NOT_TRACK", "1")
    monkeypatch.setenv("REFRACT_HOME", str(isolated_home / ".refract"))
    monkeypatch.delenv("REFRACT_TELEMETRY", raising=False)

    import urllib.request

    def reject_telemetry(*_args, **_kwargs):
        raise AssertionError("Telemetry network access is forbidden in tests")

    monkeypatch.setattr(urllib.request, "urlopen", reject_telemetry)
    from refract import product_telemetry

    monkeypatch.setattr(product_telemetry.TELEMETRY_OPENER, "open", reject_telemetry)

    from refract import pricing

    def reject_pricing_fetch(*_args, **_kwargs):
        raise pricing.PricingError("http")

    monkeypatch.setattr(pricing, "fetch_pricing", reject_pricing_fetch)
