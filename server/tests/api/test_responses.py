"""Byte limit, byte-safe truncation and on-demand result files of the MCP API."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from refract.api.mcp import responses
from refract.api.mcp.responses import MAX_RESPONSE_BYTES, RefractError, envelope_bytes, render_result


def _payload(text: str) -> dict:
    return {"job": {"id": "job-1"}, "result": text, "truncated": False, "result_path": None}


def test_short_result_is_returned_whole(tmp_path: Path) -> None:
    text = render_result(_payload("done"), "done", tmp_path / "results", "job-1")
    body = json.loads(text)
    assert body["result"] == "done" and body["truncated"] is False and body["result_path"] is None
    assert not (tmp_path / "results").exists()


def test_100_kb_result_is_truncated_and_materialized(tmp_path: Path) -> None:
    full = "X" * 100 * 1024
    text = render_result(_payload(full), full, tmp_path / "results", "job-1")
    body = json.loads(text)
    assert body["truncated"] is True
    assert 0 < len(body["result"]) < len(full)
    assert envelope_bytes(text) < MAX_RESPONSE_BYTES
    path = Path(body["result_path"])
    assert path.read_text(encoding="utf-8") == full
    assert path.parent == (tmp_path / "results")
    assert not list(path.parent.glob("*.tmp"))


@pytest.mark.parametrize("char", ["é", "€", "𝄞", "\n", '"'])
def test_truncation_never_splits_a_character(tmp_path: Path, char: str) -> None:
    full = char * 20_000
    text = render_result(_payload(full), full, tmp_path / "results", "job-2")
    body = json.loads(text)
    assert body["truncated"] is True
    assert set(body["result"]) == {char}
    assert envelope_bytes(text) < MAX_RESPONSE_BYTES
    assert "�" not in text


def test_metadata_alone_over_the_limit_is_response_too_large(tmp_path: Path) -> None:
    payload = _payload("")
    payload["job"] = {"id": "j" * (MAX_RESPONSE_BYTES + 1)}
    with pytest.raises(RefractError) as error:
        render_result(payload, "text", tmp_path / "results", "job-3")
    assert error.value.code == "response_too_large"


def test_result_file_write_is_atomic_and_stays_in_results_dir(tmp_path: Path, monkeypatch) -> None:
    results = tmp_path / "results"
    replaced: list[tuple[str, str]] = []
    real = os.replace
    monkeypatch.setattr(responses.os, "replace", lambda src, dst: (replaced.append((str(src), str(dst))), real(src, dst))[1])
    path = responses.materialize_result(results, "job-4", "one")
    assert path == results / "job-4.md"
    assert replaced and replaced[0][0] != replaced[0][1] and Path(replaced[0][0]).parent == results
    assert responses.materialize_result(results, "job-4", "two").read_text(encoding="utf-8") == "two"


@pytest.mark.parametrize("job_id", ["../escape", "a/b", "", ".."])
def test_result_file_rejects_job_ids_outside_the_results_dir(tmp_path: Path, job_id: str) -> None:
    with pytest.raises(ValueError):
        responses.materialize_result(tmp_path / "results", job_id, "x")
    assert not (tmp_path / "escape.md").exists()


def test_truncated_response_with_result_path_never_exceeds_the_cap(tmp_path: Path) -> None:
    full = "X" * 100 * 1024
    results = tmp_path / ("r" * 200)
    for pad in range(MAX_RESPONSE_BYTES - 700, MAX_RESPONSE_BYTES - 100, 37):
        payload = _payload(full)
        payload["job"] = {"id": "job-1", "note": "n" * pad}
        try:
            text = render_result(payload, full, results, "job-1")
        except RefractError as error:
            assert error.code == "response_too_large"
            continue
        assert envelope_bytes(text) <= MAX_RESPONSE_BYTES
        assert json.loads(text)["result_path"] == str(results / "job-1.md")


def test_metadata_that_fits_only_without_result_path_is_response_too_large(tmp_path: Path) -> None:
    results = tmp_path / "/".join(["r" * 50] * 6)
    full = "Y" * 100 * 1024

    def metadata(size: int, path: str | None) -> str:
        return json.dumps(
            {"job": {"id": "x" * size}, "result": "", "truncated": True, "result_path": path},
            ensure_ascii=False, separators=(",", ":"),
        )

    size = MAX_RESPONSE_BYTES - 1000
    while envelope_bytes(metadata(size, None)) < MAX_RESPONSE_BYTES - 1:
        size += 1
    assert envelope_bytes(metadata(size, None)) < MAX_RESPONSE_BYTES
    assert envelope_bytes(metadata(size, str(results / "job-1.md"))) >= MAX_RESPONSE_BYTES
    payload = {"job": {"id": "x" * size}, "result": full, "truncated": False, "result_path": None}
    with pytest.raises(RefractError) as error:
        render_result(payload, full, results, "job-1")
    assert error.value.code == "response_too_large"
    assert not results.exists()
