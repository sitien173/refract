"""Claude helper: a fake ``claude`` stub the library launches."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pytest

from tests.cli_stub import stub_cli


def stub_claude(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    lines: Iterable[str] = (),
    *,
    exit_code: int = 0,
    sleep_s: float = 0.0,
    record: Path | None = None,
    pid_file: Path | None = None,
) -> None:
    """Make ``claude`` resolve to a launcher that prints ``lines`` and exits with ``exit_code``."""
    stub_cli(
        monkeypatch,
        tmp_path,
        "claude",
        lines,
        exit_code=exit_code,
        sleep_s=sleep_s,
        record=record,
        pid_file=pid_file,
    )


__all__ = ["stub_claude"]
