"""Contract tests for pydantic config validation, schema_version, and retry.codes.

Phase 3 contract for the structured failure surface: when the config is invalid,
`refract doctor` exits non-zero and writes to stderr one JSON object as its last
non-empty line:

    {"error": {"code": "config_invalid",
               "errors": [{"loc": [<str|int>, ...], "msg": str, "hint": str}, ...]}}

`loc` is the pydantic-style path of the offending key, for example
["schema_version"] or ["targets", 5, "retry", "codes", 0]. Each test config carries
exactly one fault, so `errors` must hold exactly one entry with the exact `loc`.
"""

from __future__ import annotations

import json
import os
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pytest

from tests.contract.conftest import SERVER_DIR, doctor_command, write_config


def _run_doctor(home: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["REFRACT_HOME"] = str(home)
    env["DO_NOT_TRACK"] = "1"
    return subprocess.run(
        doctor_command(),
        cwd=SERVER_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _config_error(proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    assert proc.returncode != 0
    lines = [line for line in proc.stderr.splitlines() if line.strip()]
    assert lines, "doctor wrote nothing to stderr"
    error = json.loads(lines[-1])["error"]
    assert error["code"] == "config_invalid"
    assert all(isinstance(entry.get("hint"), str) and entry["hint"] for entry in error["errors"])
    assert all(isinstance(entry.get("msg"), str) and entry["msg"] for entry in error["errors"])
    return error


def _assert_single_loc(proc: subprocess.CompletedProcess[str], loc: list[str | int]) -> None:
    error = _config_error(proc)
    assert [entry["loc"] for entry in error["errors"]] == [loc]


def test_config_missing_schema_version_fails_with_loc(tmp_path: Path) -> None:
    """Config without schema_version fails with config_invalid and loc ["schema_version"]."""
    home = tmp_path / "home dir"
    home.mkdir()
    write_config(home, port=8765, with_schema_version=False)

    _assert_single_loc(_run_doctor(home), ["schema_version"])


def test_config_unknown_key_fails(tmp_path: Path) -> None:
    """Config with an unknown section fails with config_invalid and loc ["unknown_section"]."""
    home = tmp_path / "home dir"
    home.mkdir()
    write_config(home, port=8765, extra_toml='[unknown_section]\nfoo = "bar"\n')

    _assert_single_loc(_run_doctor(home), ["unknown_section"])


def test_config_unknown_retry_code_fails_with_loc(tmp_path: Path) -> None:
    """An unknown retry.codes entry fails with config_invalid at its exact loc."""
    home = tmp_path / "home dir"
    home.mkdir()
    config_path = write_config(
        home,
        port=8765,
        extra_toml=(
            '[[targets]]\nid = "bad-retry"\nbackend = "claude"\nmodel = "fake-claude"\n'
            'retry = { attempts = 2, codes = ["not_a_real_code"] }\n'
        ),
    )
    bad_index = len(tomllib.loads(config_path.read_text(encoding="utf-8"))["targets"]) - 1

    _assert_single_loc(_run_doctor(home), ["targets", bad_index, "retry", "codes", 0])
