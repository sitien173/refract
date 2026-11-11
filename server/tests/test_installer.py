"""Installer tests. Stub host CLIs record argv; every path stays under tmp_path."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from refract import cli, installer, updater
from refract.config import refract_home
from tests.host_stubs import GIT_ENV, Env

DEFAULT = installer.DEFAULT_SOURCE
REPO = installer.MARKETPLACE_REPO
GITHUB_MARKET = [{"name": "refract", "repo": REPO}]


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
    return e


def stub_host(
    env: Env, name: str, *, plugins: list | None = None, markets: list | None = None, fail: str = ""
) -> None:
    """Stub a host: ``list --json`` answers from the data, a command containing ``fail`` exits 1."""
    body = (
        "if args[-2:] == ['list', '--json']:\n"
        "    out = MARKETS if 'marketplace' in args else PLUGINS\n"
        "    sys.stdout.write(out)\n"
        "    sys.exit(0)\n"
        f"sys.exit(1 if {fail!r} and {fail!r} in joined else 0)\n"
    )
    header = f"PLUGINS = {json.dumps(plugins or [])!r}\nMARKETS = {json.dumps(markets or [])!r}\n"
    env.stub(name, body=header + body)


def mutating(env: Env) -> list[str]:
    return [line for line in env.call_log() if not line.endswith("list --json")]


def run(
    action: str,
    hosts: list[str],
    *,
    scope: str = "user",
    source: str | None = None,
    dry_run: bool = False,
) -> tuple[int, list[str]]:
    lines: list[str] = []
    code = installer.run(
        action, hosts, scope=scope, source=source, dry_run=dry_run, out=lines.append
    )
    return code, lines


def refract_plugin(scope: str = "user") -> dict[str, str]:
    return {"id": "refract@refract", "scope": scope}


# --- 1. exact argv per host and scope ----------------------------------------


@pytest.mark.parametrize("scope", ["user", "project", "local"])
def test_claude_install_argv_per_scope(env: Env, scope: str) -> None:
    stub_host(env, "claude")
    code, _ = run("install", ["claude"], scope=scope)
    assert code == 0
    assert mutating(env) == [
        f"claude plugin marketplace add {REPO} --scope {scope}",
        f"claude plugin install refract@refract -s {scope}",
    ]


@pytest.mark.parametrize("scope", ["user", "project", "local"])
def test_claude_uninstall_argv_per_scope(env: Env, scope: str) -> None:
    stub_host(env, "claude", plugins=[refract_plugin(scope)], markets=GITHUB_MARKET)
    code, lines = run("uninstall", ["claude"], scope=scope)
    assert code == 0
    assert mutating(env) == [
        f"claude plugin uninstall refract@refract -s {scope}",
        f"claude plugin marketplace remove refract --scope {scope}",
    ]
    assert "claude: removed" in lines


def test_claude_install_with_local_source_uses_resolved_path(env: Env, tmp_path: Path) -> None:
    stub_host(env, "claude")
    clone = tmp_path / "clone"
    clone.mkdir()
    code, _ = run("install", ["claude"], source=str(clone))
    assert code == 0
    assert mutating(env)[0] == f"claude plugin marketplace add {clone.resolve()} --scope user"


def test_codex_install_and_uninstall_argv(env: Env) -> None:
    stub_host(env, "codex")
    assert run("install", ["codex"])[0] == 0
    assert mutating(env) == [
        f"codex plugin marketplace add {REPO}",
        "codex plugin add refract@refract",
    ]
    env.calls.unlink()
    stub_host(env, "codex", plugins=[{"id": "refract@refract"}], markets=GITHUB_MARKET)
    assert run("uninstall", ["codex"])[0] == 0
    assert mutating(env) == [
        "codex plugin remove refract@refract",
        "codex plugin marketplace remove refract",
    ]


def test_agy_install_and_uninstall_argv(env: Env) -> None:
    stub_host(env, "agy")
    assert run("install", ["agy"])[0] == 0
    assert mutating(env) == [f"agy plugin install {DEFAULT}"]
    env.calls.unlink()
    stub_host(env, "agy", plugins=[{"id": "refract"}])
    assert run("uninstall", ["agy"])[0] == 0
    assert mutating(env) == ["agy plugin uninstall refract"]
    assert not any("--help" in line for line in env.call_log())


@pytest.mark.parametrize(("scope", "flag"), [("user", ""), ("project", " -l")])
def test_pi_install_argv_per_scope(env: Env, scope: str, flag: str) -> None:
    stub_host(env, "pi")
    assert run("install", ["pi"], scope=scope)[0] == 0
    assert mutating(env) == [f"pi install {DEFAULT}{flag}"]


# --- 2. -p parsing ------------------------------------------------------------


def test_host_list_accepts_commas_repeats_and_dedupes(env: Env) -> None:
    for name in ("claude", "pi", "agy"):
        stub_host(env, name)
    code, lines = run("install", ["claude,pi", "pi", "agy,claude"], dry_run=True)
    assert code == 0
    assert lines[0] == "hosts: claude, pi, agy"


def test_all_resolves_to_hosts_on_path(env: Env) -> None:
    stub_host(env, "claude")
    stub_host(env, "pi")
    code, lines = run("install", ["all"], dry_run=True)
    assert code == 0
    assert lines[0] == "hosts: claude, pi"
    assert not any(line.startswith(("codex", "agy")) for line in lines)


def test_all_with_no_host_on_path_exits_1(env: Env) -> None:
    code, lines = run("install", ["all"])
    assert code == 1
    assert env.call_log() == []
    assert lines


def test_unknown_host_is_a_usage_error(env: Env) -> None:
    stub_host(env, "claude")
    assert run("install", ["claude,bogus"])[0] == 2
    assert env.call_log() == []


# --- 3. named host missing ----------------------------------------------------


def test_named_host_missing_exits_1(env: Env) -> None:
    code, lines = run("install", ["codex"])
    assert code == 1
    assert "codex: failed: not on PATH" in lines


# --- 4. dry run ---------------------------------------------------------------


def test_dry_run_prints_commands_and_makes_no_mutating_call(env: Env) -> None:
    stub_host(env, "claude")
    stub_host(env, "pi")
    code, lines = run("install", ["claude", "pi"], dry_run=True)
    assert code == 0
    assert mutating(env) == []
    assert f"claude: would run: claude plugin marketplace add {REPO} --scope user" in lines
    assert "claude: would run: claude plugin install refract@refract -s user" in lines
    assert f"pi: would run: pi install {DEFAULT}" in lines


def test_dry_run_uninstall_makes_no_mutating_call(env: Env) -> None:
    stub_host(env, "claude", plugins=[refract_plugin()], markets=GITHUB_MARKET)
    code, lines = run("uninstall", ["claude"], dry_run=True)
    assert code == 0
    assert mutating(env) == []
    assert "claude: would run: claude plugin uninstall refract@refract -s user" in lines


# --- 5. already in the requested state -----------------------------------------


def test_install_is_noop_when_claude_already_installed(env: Env) -> None:
    stub_host(env, "claude", plugins=[refract_plugin()], markets=GITHUB_MARKET)
    code, lines = run("install", ["claude"])
    assert code == 0
    assert mutating(env) == []
    assert "claude: already installed" in lines


def test_install_is_noop_when_pi_already_installed(env: Env) -> None:
    stub_host(env, "pi")
    env.pi_dir.mkdir()
    (env.pi_dir / "settings.json").write_text(json.dumps({"packages": [DEFAULT]}))
    code, lines = run("install", ["pi"])
    assert code == 0
    assert mutating(env) == []
    assert "pi: already installed" in lines


@pytest.mark.parametrize("host", ["claude", "codex", "agy", "pi"])
def test_uninstall_is_noop_when_not_installed(env: Env, host: str) -> None:
    stub_host(env, host)
    code, lines = run("uninstall", [host])
    assert code == 0
    assert mutating(env) == []
    assert f"{host}: not installed" in lines


# --- 6. Claude marketplace name clash -------------------------------------------


def test_claude_marketplace_with_other_source_fails_without_add(env: Env, tmp_path: Path) -> None:
    other = str(tmp_path / "local-clone")
    stub_host(env, "claude", markets=[{"name": "refract", "path": other}])
    code, lines = run("install", ["claude"])
    assert code == 1
    assert mutating(env) == []
    failure = next(line for line in lines if line.startswith("claude: failed"))
    assert other in failure
    assert REPO in failure


def test_claude_marketplace_with_same_source_skips_add(env: Env) -> None:
    stub_host(env, "claude", markets=GITHUB_MARKET)
    code, _ = run("install", ["claude"])
    assert code == 0
    assert mutating(env) == ["claude plugin install refract@refract -s user"]


# --- 7. partial failure ----------------------------------------------------------


def test_claude_failure_does_not_stop_pi_and_prints_undo(env: Env) -> None:
    stub_host(env, "claude", fail="plugin install")
    stub_host(env, "pi")
    code, lines = run("install", ["claude", "pi"])
    assert code == 1
    assert any(line.startswith("claude: failed") for line in lines)
    assert f"claude: applied: claude plugin marketplace add {REPO} --scope user" in lines
    assert "claude: undo: claude plugin marketplace remove refract --scope user" in lines
    assert "pi: installed" in lines
    assert f"pi install {DEFAULT}" in mutating(env)


# --- 8. Pi removal ---------------------------------------------------------------


@pytest.mark.parametrize(
    "stored",
    [DEFAULT, "git+https://github.com/sitien173/refract.git", "github.com/sitien173/refract/"],
)
def test_pi_remove_passes_stored_source_unchanged(env: Env, stored: str) -> None:
    stub_host(env, "pi")
    env.pi_dir.mkdir()
    (env.pi_dir / "settings.json").write_text(json.dumps({"packages": [{"source": stored}]}))
    code, lines = run("uninstall", ["pi"])
    assert code == 0
    assert mutating(env) == [f"pi remove {stored}"]
    assert "pi: removed" in lines


def test_pi_remove_passes_relative_source_unchanged(env: Env, tmp_path: Path) -> None:
    stub_host(env, "pi")
    clone = tmp_path / "relative" / "refract"
    clone.mkdir(parents=True)
    (clone / "package.json").write_text(json.dumps({"name": "refract"}))
    env.pi_dir.mkdir()
    (env.pi_dir / "settings.json").write_text(json.dumps({"packages": ["../relative/refract"]}))
    assert run("uninstall", ["pi"])[0] == 0
    assert mutating(env) == ["pi remove ../relative/refract"]


def test_pi_project_scope_reads_project_settings(
    env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_host(env, "pi")
    project = tmp_path / "project"
    (project / ".pi").mkdir(parents=True)
    stored = "git+https://github.com/sitien173/refract.git"
    (project / ".pi" / "settings.json").write_text(json.dumps({"packages": [stored]}))
    env.pi_dir.mkdir()
    (env.pi_dir / "settings.json").write_text(json.dumps({"packages": [DEFAULT]}))
    monkeypatch.chdir(project)
    code, lines = run("uninstall", ["pi"], scope="project")
    assert code == 0
    assert mutating(env) == [f"pi remove {stored} -l"]
    assert f"directory: {project.resolve()}" in lines or f"directory: {project}" in lines


# --- 9. unsupported scope ---------------------------------------------------------


@pytest.mark.parametrize(
    ("hosts", "scope"),
    [
        (["codex"], "project"),
        (["codex"], "local"),
        (["agy"], "project"),
        (["agy"], "local"),
        (["pi"], "local"),
    ],
    ids=["codex-project", "codex-local", "agy-project", "agy-local", "pi-local"],
)
@pytest.mark.parametrize("action", ["install", "uninstall"])
def test_unsupported_scope_exits_2_with_no_calls(
    env: Env, action: str, hosts: list[str], scope: str
) -> None:
    for name in ("claude", "codex", "agy", "pi"):
        stub_host(env, name)
    code, _ = run(action, ["claude", *hosts], scope=scope, dry_run=True)
    assert code == 2
    assert env.call_log() == []


def test_cli_rejects_bogus_host_and_unsupported_scope(env: Env) -> None:
    stub_host(env, "codex")
    for argv in (
        ["install", "-p", "bogus"],
        ["install", "-p", "codex", "--scope", "project", "--dry-run"],
    ):
        with pytest.raises(SystemExit) as raised:
            cli.main(argv)
        assert raised.value.code == 2
    assert env.call_log() == []


def test_cli_install_dry_run_exits_0(env: Env, capsys: pytest.CaptureFixture[str]) -> None:
    stub_host(env, "claude")
    with pytest.raises(SystemExit) as raised:
        cli.main(["install", "-p", "claude", "--dry-run"])
    assert raised.value.code == 0
    assert "claude plugin install refract@refract -s user" in capsys.readouterr().out


# --- 10. marketplace removal safety -------------------------------------------------


@pytest.mark.parametrize("host", ["claude", "codex"])
def test_marketplace_kept_when_another_plugin_still_installed(env: Env, host: str) -> None:
    other = {"id": "other@refract", "marketplace": "refract", "scope": "user"}
    stub_host(env, host, plugins=[refract_plugin(), other], markets=GITHUB_MARKET)
    code, lines = run("uninstall", [host])
    assert code == 0
    assert not any("marketplace remove" in line for line in mutating(env))
    assert any("marketplace refract kept" in line for line in lines)


def test_marketplace_kept_when_source_is_not_a_refract_source(env: Env) -> None:
    foreign = [{"name": "refract", "repo": "someone/else"}]
    stub_host(env, "claude", plugins=[refract_plugin()], markets=foreign)
    code, lines = run("uninstall", ["claude"])
    assert code == 0
    assert mutating(env) == ["claude plugin uninstall refract@refract -s user"]
    assert any("marketplace refract kept" in line for line in lines)


# --- 11. source strings round-trip through the updater --------------------------------


def test_default_sources_are_trusted_by_the_updater(tmp_path: Path) -> None:
    assert updater._parse_source(installer.resolve_source(None), None) == ("github", None)
    market = {"repo": installer.marketplace_arg(DEFAULT)}
    assert updater._marketplace_source(market) == ("github", None)
    local = installer.resolve_source(str(tmp_path))
    assert updater._parse_source(local, None) == ("clone", tmp_path.resolve())
    assert installer.marketplace_arg(local) == local


# --- lock ----------------------------------------------------------------------------


def test_busy_update_lock_exits_1_without_calls(env: Env) -> None:
    stub_host(env, "claude")
    with updater._file_lock(refract_home() / "update.lock") as held:
        assert held
        code, lines = run("install", ["claude"])
    assert code == 1
    assert env.call_log() == []
    assert lines


# --- fix cycle 1 ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("host", "action"),
    [("claude", "install"), ("codex", "uninstall"), ("agy", "install"), ("pi", "install")],
)
def test_launch_failure_reports_cannot_run(
    env: Env, monkeypatch: pytest.MonkeyPatch, host: str, action: str
) -> None:
    stub_host(env, host)

    def refuse(_args: list[str]) -> list[str]:
        raise OSError("no launcher")

    monkeypatch.setattr(updater, "prepare_command", refuse)
    code, lines = run(action, [host])
    assert code == 1
    assert f"{host}: failed: cannot run {host}" in lines


@pytest.mark.parametrize("host", ["claude", "codex"])
def test_marketplace_list_failure_blocks_add(env: Env, host: str) -> None:
    body = (
        "if 'marketplace' in args and args[-2:] == ['list', '--json']:\n    sys.exit(1)\n"
        "if args[-2:] == ['list', '--json']:\n    sys.stdout.write('[]')\n    sys.exit(0)\n"
    )
    env.stub(host, body=body)
    code, lines = run("install", [host])
    assert code == 1
    assert f"{host}: failed: cannot list marketplaces" in lines
    assert not any("marketplace add" in line for line in env.call_log())


@pytest.mark.parametrize("host", ["agy", "codex"])
def test_plugin_list_failure_has_single_prefix(env: Env, host: str) -> None:
    env.stub(host, code=1)
    code, lines = run("install", [host])
    assert code == 1
    assert f"{host}: failed: cannot list plugins: exit 1" in lines


def test_marketplace_kept_when_local_path_is_not_a_refract_package(
    env: Env, tmp_path: Path
) -> None:
    other = tmp_path / "not-refract"
    other.mkdir()
    stub_host(
        env,
        "claude",
        plugins=[refract_plugin()],
        markets=[{"name": "refract", "path": str(other)}],
    )
    code, lines = run("uninstall", ["claude"])
    assert code == 0
    assert mutating(env) == ["claude plugin uninstall refract@refract -s user"]
    assert any("not a Refract source" in line for line in lines)


@pytest.mark.parametrize(
    ("host", "reinstall"),
    [
        ("claude", "claude plugin install refract@refract -s user"),
        ("codex", "codex plugin add refract@refract"),
    ],
)
def test_failed_marketplace_removal_prints_reinstall_undo(
    env: Env, host: str, reinstall: str
) -> None:
    stub_host(
        env, host, plugins=[{"id": "refract@refract"}], markets=GITHUB_MARKET, fail="marketplace remove"
    )
    code, lines = run("uninstall", [host])
    assert code == 1
    assert any(line.startswith(f"{host}: applied: {host} plugin ") for line in lines)
    assert f"{host}: undo: {reinstall}" in lines


def test_other_marketplace_plugin_does_not_count_as_installed(env: Env) -> None:
    other = {"id": "refract@other", "marketplace": "other", "scope": "user"}
    stub_host(env, "claude", plugins=[other], markets=GITHUB_MARKET)
    code, lines = run("install", ["claude"])
    assert code == 0
    assert mutating(env) == ["claude plugin install refract@refract -s user"]
    env.calls.unlink()
    code, lines = run("uninstall", ["claude"])
    assert code == 0
    assert mutating(env) == []
    assert "claude: not installed" in lines


CODEX_INSTALLED = [
    [{"id": "refract@other"}, {"id": "refract@refract"}],
    [{"name": "refract", "marketplace": "refract"}],
    [{"name": "refract"}],
]


@pytest.mark.parametrize("plugins", CODEX_INSTALLED, ids=["after-other", "name-and-market", "bare-name"])
def test_codex_raw_list_items_count_as_installed(env: Env, plugins: list) -> None:
    stub_host(env, "codex", plugins=plugins, markets=GITHUB_MARKET)
    code, lines = run("install", ["codex"])
    assert code == 0
    assert "codex: already installed" in lines
    assert mutating(env) == []
    code, lines = run("uninstall", ["codex"], dry_run=True)
    assert code == 0
    assert "codex: would run: codex plugin remove refract@refract" in lines


def test_codex_other_marketplace_alone_is_not_installed(env: Env) -> None:
    stub_host(env, "codex", plugins=[{"id": "refract@other"}], markets=GITHUB_MARKET)
    code, lines = run("uninstall", ["codex"])
    assert code == 0
    assert "codex: not installed" in lines
    assert mutating(env) == []
