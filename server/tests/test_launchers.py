"""The shared launcher forwards arguments and exit codes through the product launch path."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

from refract.backends._process import run_process

from tests.launchers import install_launcher

SCRIPT = """\
import json
import sys

code, record, *rest = sys.argv[1:]
with open(record, "w", encoding="utf-8") as handle:
    json.dump(rest, handle)
sys.exit(int(code))
"""

ARGS = ["a&b", "100%", '"quoted"', "with space", "café"]


def test_launcher_preserves_arguments_and_exit_code(tmp_path: Path) -> None:
    script = tmp_path / "record_argv.py"
    script.write_text(SCRIPT, encoding="utf-8")
    record = tmp_path / "argv.json"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    install_launcher(bin_dir, "fakecli", script, ["3", str(record)])

    resolved = shutil.which("fakecli", path=str(bin_dir))
    assert resolved is not None

    async def noop(_line: str) -> None:
        return None

    outcome = asyncio.run(run_process([resolved, *ARGS], None, None, str(tmp_path), None, None, noop))

    assert outcome.returncode == 3
    assert json.loads(record.read_text(encoding="utf-8")) == ARGS


STDIN_SCRIPT = """\
import json
import sys

record = sys.argv[1]
raw = sys.stdin.buffer.read()
with open(record, "w", encoding="utf-8") as handle:
    json.dump({"hex": raw.hex(), "text": raw.decode("utf-8")}, handle)
"""


def test_launcher_delivers_stdin_unchanged(tmp_path: Path) -> None:
    script = tmp_path / "record_stdin.py"
    script.write_text(STDIN_SCRIPT, encoding="utf-8")
    record = tmp_path / "stdin.json"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    install_launcher(bin_dir, "fakecli", script, [str(record)])
    resolved = shutil.which("fakecli", path=str(bin_dir))
    assert resolved is not None
    payload = "the prompt café"

    async def noop(_line: str) -> None:
        return None

    outcome = asyncio.run(run_process([resolved], payload, None, str(tmp_path), None, None, noop))

    assert outcome.returncode == 0
    assert json.loads(record.read_text(encoding="utf-8")) == {
        "hex": payload.encode("utf-8").hex(),
        "text": payload,
    }
