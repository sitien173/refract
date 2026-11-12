"""Install fake backend CLI executables that the library launches."""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterable
from pathlib import Path

import pytest

from tests.launchers import install_launcher

FAKE_CLI = Path(__file__).parent / "fixtures" / "fake_cli" / "fake_cli.py"


def stub_cli(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    executable: str,
    lines: Iterable[str] = (),
    *,
    exit_code: int = 0,
    sleep_s: float = 0.0,
    record: Path | None = None,
    pid_file: Path | None = None,
    raw_hex: Iterable[str] = (),
    log_text: str | None = None,
    last_message: str | None = None,
) -> None:
    """Make ``executable`` resolve to a launcher that runs ``FAKE_CLI``.

    ``lines`` are printed after ``raw_hex`` entries, which are written as raw bytes.
    ``last_message`` is written to the ``-o`` path when the backend passes one.
    ``shutil.which`` still resolves every other executable name normally.
    """
    bin_dir = tmp_path / f"fake-{executable}-bin"
    bin_dir.mkdir(exist_ok=True)
    config = tmp_path / f"fake-{executable}.json"
    config.write_text(
        json.dumps({
            "name": executable,
            "lines": list(lines),
            "raw_hex": list(raw_hex),
            "exit_code": exit_code,
            "sleep_s": sleep_s,
            "record": None if record is None else str(record),
            "pid_file": None if pid_file is None else str(pid_file),
            "log_text": log_text,
            "last_message": last_message,
        }),
        encoding="utf-8",
    )
    launcher = install_launcher(bin_dir, executable, FAKE_CLI, [str(config)])

    previous = shutil.which
    fake_path = str(launcher)
    monkeypatch.setattr(
        shutil,
        "which",
        lambda name, *args, **kwargs: fake_path if name == executable else previous(name, *args, **kwargs),
    )


__all__ = ["FAKE_CLI", "stub_cli"]
