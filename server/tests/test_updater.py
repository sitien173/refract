"""Updater version-check, cache, and CLI tests. Every path stays under tmp_path."""

from __future__ import annotations

import http.client
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from refract import cli, installer, updater
from tests.host_stubs import Env


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    e = Env(tmp_path)
    monkeypatch.setenv("REFRACT_HOME", str(e.refract_home))
    monkeypatch.setenv("HOME", str(e.home))
    monkeypatch.setattr(Path, "home", lambda: e.home)
    monkeypatch.setattr(updater.metadata, "version", lambda _name: "2.5.0")
    return e


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_a: Any, **_k: Any):
        raise AssertionError("unexpected network call")

    monkeypatch.setattr(updater, "_open_release", refuse)
    monkeypatch.setattr(cli, "urlopen", refuse)


# --- release check ------------------------------------------------------


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self, size: int = -1) -> bytes:
        return self.body if size < 0 else self.body[:size]

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_a: object) -> None:
        return None


def release(monkeypatch: pytest.MonkeyPatch, body: Any = None, exc: Exception | None = None) -> list[Request]:
    seen: list[Request] = []

    def fake(request: Request, timeout: float):
        seen.append(request)
        if exc is not None:
            raise exc
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        return FakeResponse(raw)

    monkeypatch.setattr(updater, "_open_release", fake)
    return seen


def test_release_newer_with_v_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = release(monkeypatch, {"tag_name": "v2.6.0"})
    result = updater.check_release("2.5.0")
    assert (result.state, result.version) == ("update", "2.6.0")
    assert seen[0].full_url == updater.RELEASE_URL


def test_release_newer_without_prefix_compares_integers(monkeypatch: pytest.MonkeyPatch) -> None:
    release(monkeypatch, {"tag_name": "2.10.0"})
    assert updater.check_release("2.9.0").state == "update"


def test_release_equal(monkeypatch: pytest.MonkeyPatch) -> None:
    release(monkeypatch, {"tag_name": "v2.5.0"})
    assert updater.check_release("2.5.0").state == "current"


def test_release_older(monkeypatch: pytest.MonkeyPatch) -> None:
    release(monkeypatch, {"tag_name": "v2.4.9"})
    assert updater.check_release("2.5.0").state == "current"


@pytest.mark.parametrize("flag", ["draft", "prerelease"])
def test_release_draft_and_prerelease_ignored(monkeypatch: pytest.MonkeyPatch, flag: str) -> None:
    release(monkeypatch, {"tag_name": "v9.0.0", flag: True})
    result = updater.check_release("2.5.0")
    assert (result.state, result.version) == ("current", None)


@pytest.mark.parametrize("tag", ["v2.6", "v1.2.3-rc1", "latest", "v1.2.3\n", "v1.2.3; rm -rf /", "", "V1.2.3"])
def test_release_invalid_tag_is_failed(monkeypatch: pytest.MonkeyPatch, tag: str) -> None:
    release(monkeypatch, {"tag_name": tag})
    result = updater.check_release("2.5.0")
    assert (result.state, result.detail, result.version) == ("failed", "cannot check", None)


def test_release_404_is_current(monkeypatch: pytest.MonkeyPatch) -> None:
    release(monkeypatch, exc=HTTPError(updater.RELEASE_URL, 404, "nf", {}, None))  # type: ignore[arg-type]
    assert updater.check_release("2.5.0").state == "current"


@pytest.mark.parametrize("code", [403, 429, 500])
def test_release_http_errors_fail(monkeypatch: pytest.MonkeyPatch, code: int) -> None:
    release(monkeypatch, exc=HTTPError(updater.RELEASE_URL, code, "x", {}, None))  # type: ignore[arg-type]
    result = updater.check_release("2.5.0")
    assert (result.state, result.detail) == ("failed", "cannot check")


def test_release_url_error_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    release(monkeypatch, exc=URLError("offline"))
    assert updater.check_release("2.5.0").state == "failed"


@pytest.mark.parametrize("body", [b"{not json", b"[]", b'{"tag_name": 5}', b"null"])
def test_release_malformed_body_fails(monkeypatch: pytest.MonkeyPatch, body: bytes) -> None:
    release(monkeypatch, body=body)
    assert updater.check_release("2.5.0").state == "failed"


def test_release_oversized_body_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    padding = " " * (updater.MAX_RELEASE_BYTES + 1)
    response = FakeResponse((json.dumps({"tag_name": "v9.9.9"}) + padding).encode())
    sizes: list[int] = []
    read = response.read
    response.read = lambda size=-1: (sizes.append(size), read(size))[1]  # type: ignore[method-assign]
    monkeypatch.setattr(updater, "_open_release", lambda _request, _timeout: response)
    assert updater.check_release("2.5.0").state == "failed"
    assert sizes == [updater.MAX_RELEASE_BYTES + 1]


def test_release_body_at_limit_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = json.dumps({"tag_name": "v9.9.9"}).encode()
    release(monkeypatch, body=raw + b" " * (updater.MAX_RELEASE_BYTES - len(raw)))
    assert updater.check_release("2.5.0").state == "update"


def test_release_unknown_installed_version_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    release(monkeypatch, {"tag_name": "v9.9.9"})
    assert updater.check_release(None).state == "failed"


@pytest.mark.parametrize("target", ["https://evil.example/x", "http://api.github.com/x", "https://api.github.com.evil.example/x"])
def test_redirect_handler_refuses_other_hosts(target: str) -> None:
    handler = updater._SameHostRedirect()
    request = Request(updater.RELEASE_URL)
    with pytest.raises(URLError):
        handler.redirect_request(request, None, 302, "Found", {}, target)


def test_redirect_handler_allows_same_host() -> None:
    handler = updater._SameHostRedirect()
    new = handler.redirect_request(
        Request(updater.RELEASE_URL), None, 302, "Found", {}, "https://api.github.com/repos/other"
    )
    assert new is not None
    assert new.full_url == "https://api.github.com/repos/other"


def test_release_cross_host_redirect_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    release(monkeypatch, exc=URLError("cross-host redirect refused"))
    assert updater.check_release("2.5.0").state == "failed"


# --- update CLI & check behavior ---------------------------------------


EXPECTED_COMMANDS = [
    'server: uv tool install --force "refract @ git+https://github.com/sitien173/refract#subdirectory=server"',
    "claude: claude plugin marketplace update refract && claude plugin update refract@refract",
    "codex: codex plugin marketplace upgrade && codex plugin add refract@refract",
    "agy: agy plugin install https://github.com/sitien173/refract",
    "agy-ide: refract uninstall -p agy-ide && refract install -p agy-ide",
    "pi: pi update https://github.com/sitien173/refract",
]


def _run_cli(argv: list[str]) -> int:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(argv)
    assert isinstance(exc_info.value.code, int)
    return exc_info.value.code


def test_update_prints_status_line_and_six_commands(
    env: Env, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen = release(monkeypatch, {"tag_name": "v2.6.0"})
    code = _run_cli(["update"])
    assert code == 0
    assert len(seen) == 1
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 7
    assert "2.6.0" in lines[0]
    assert lines[1:] == EXPECTED_COMMANDS
    cache = json.loads((env.refract_home / updater.CACHE_NAME).read_text())
    assert set(cache.keys()) == {"schema", "checked_at", "latest_version", "update_available"}
    assert cache["schema"] == 1
    assert cache["latest_version"] == "2.6.0"
    assert cache["update_available"] is True


def test_update_check_failed_still_prints_six_commands_and_exits_0(
    env: Env, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    release(monkeypatch, exc=URLError("offline"))
    code = _run_cli(["update"])
    assert code == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 7
    assert "failed" in lines[0].lower()
    assert lines[1:] == EXPECTED_COMMANDS


def test_update_check_writes_schema_1_cache_and_prints_nothing(
    env: Env, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen = release(monkeypatch, {"tag_name": "v2.5.0"})
    code = _run_cli(["update", "--check"])
    assert code == 0
    assert len(seen) == 1
    assert capsys.readouterr().out == ""
    cache = json.loads((env.refract_home / updater.CACHE_NAME).read_text())
    assert set(cache.keys()) == {"schema", "checked_at", "latest_version", "update_available"}
    assert cache["schema"] == 1
    assert isinstance(cache["checked_at"], (int, float))
    assert cache["latest_version"] == "2.5.0"
    assert cache["update_available"] is False


def test_update_check_within_24h_makes_no_request_and_prints_nothing(
    env: Env, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen = release(monkeypatch, {"tag_name": "v9.9.9"})
    now = 1_700_000_000.0
    updater.write_cache(
        env.refract_home / updater.CACHE_NAME,
        {"schema": 1, "checked_at": now - 3600, "latest_version": "2.5.0", "update_available": False},
    )
    monkeypatch.setattr(updater.time, "time", lambda: now)
    code = _run_cli(["update", "--check"])
    assert code == 0
    assert seen == []
    assert capsys.readouterr().out == ""


def test_update_check_after_24h_refreshes_cache(
    env: Env, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen = release(monkeypatch, {"tag_name": "v2.7.0"})
    now = 1_700_000_000.0
    updater.write_cache(
        env.refract_home / updater.CACHE_NAME,
        {"schema": 1, "checked_at": now - updater.CHECK_TTL_S - 1, "latest_version": "2.5.0", "update_available": False},
    )
    monkeypatch.setattr(updater.time, "time", lambda: now)
    code = _run_cli(["update", "--check"])
    assert code == 0
    assert len(seen) == 1
    assert capsys.readouterr().out == ""
    cache = json.loads((env.refract_home / updater.CACHE_NAME).read_text())
    assert cache["latest_version"] == "2.7.0"
    assert cache["update_available"] is True


def test_update_check_with_held_lock_exits_0_without_request(
    env: Env, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen = release(monkeypatch, {"tag_name": "v9.9.9"})
    with installer._file_lock(env.refract_home / "update-check.lock") as held:
        assert held
        code = _run_cli(["update", "--check"])
    assert code == 0
    assert seen == []
    assert capsys.readouterr().out == ""


def test_update_force_exits_2_with_argument_error(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["update", "--force"])
    assert exc_info.value.code == 2
    assert "--force" in capsys.readouterr().err


def test_incomplete_read_returns_failed_and_keeps_check_silent(
    env: Env, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class BrokenResponse:
        def read(self, _size: int = -1) -> bytes:
            raise http.client.IncompleteRead(b'{"tag_name":')

        def __enter__(self) -> BrokenResponse:
            return self

        def __exit__(self, *_a: object) -> None:
            return None

    monkeypatch.setattr(updater, "_open_release", lambda _req, _timeout: BrokenResponse())
    assert _run_cli(["update"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 7
    assert "failed" in lines[0].lower()
    assert lines[1:] == EXPECTED_COMMANDS

    assert _run_cli(["update", "--check"]) == 0
    assert capsys.readouterr().out == ""


def test_oversized_tag_component_is_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    release(monkeypatch, {"tag_name": f"v{'9' * 5000}.0.0"})
    result = updater.check_release("2.5.0")
    assert (result.state, result.detail, result.version) == ("failed", "cannot check", None)
