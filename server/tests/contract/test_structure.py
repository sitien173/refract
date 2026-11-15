"""Structural contract tests for the 6 layered packages."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REFRACT_SRC = Path(__file__).resolve().parents[2] / "src" / "refract"
FORBIDDEN_STORE_IMPORTS = (
    "refract.config.load",
    "refract.config.inspection",
    "refract.scheduling",
    "refract.runner",
    "refract.runtime",
    "refract.api",
)
SIX_PACKAGES = (
    REFRACT_SRC / "store",
    REFRACT_SRC / "config",
    REFRACT_SRC / "scheduling",
    REFRACT_SRC / "runner",
    REFRACT_SRC / "api" / "mcp",
    REFRACT_SRC / "api" / "http",
)


def test_store_imports_no_upper_layer() -> None:
    """Modules under refract/store/ import nothing from config loaders, scheduling, runner, runtime, or api."""
    store_dir = REFRACT_SRC / "store"
    assert store_dir.is_dir(), f"{store_dir} does not exist yet"
    py_files = sorted(store_dir.rglob("*.py"))
    assert py_files, "Expected Python modules under refract/store/"

    violations: list[str] = []
    for path in py_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(FORBIDDEN_STORE_IMPORTS):
                        violations.append(f"{path.name}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith(FORBIDDEN_STORE_IMPORTS):
                    violations.append(f"{path.name}: from {node.module} import ...")
    assert not violations, f"Forbidden store imports: {violations}"


def test_six_packages_under_500_lines() -> None:
    """No .py file in the 6 new packages exceeds 500 lines."""
    missing = [str(pkg) for pkg in SIX_PACKAGES if not pkg.is_dir()]
    assert not missing, f"Package directories not yet created: {missing}"

    oversized: list[str] = []
    for pkg in SIX_PACKAGES:
        py_files = sorted(pkg.rglob("*.py"))
        assert py_files, f"Expected Python files under {pkg}"
        for path in py_files:
            line_count = len(path.read_text(encoding="utf-8").splitlines())
            if line_count > 500:
                oversized.append(f"{path.relative_to(REFRACT_SRC)}: {line_count} lines")
    assert not oversized, f"Files exceeding 500 lines: {oversized}"
