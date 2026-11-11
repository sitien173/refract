"""Installer tests. Stub host CLIs record argv; every path stays under tmp_path."""

from __future__ import annotations

import json
import shutil
import sys
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


# --- agy-ide: destination, source, probe, and dry-run file plan -----------------


def make_plugin_root(root: Path) -> Path:
    manifest = root / ".antigravity-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"name": "refract"}))
    return root


IDE_MARKER = ".refract-agy-ide-install.json"


def own_ide_copy(dst: Path) -> Path:
    """Mark ``dst`` as a copy Refract made, the way an install does."""
    (dst / IDE_MARKER).write_text(json.dumps({"owner": "refract", "path": str(dst.resolve())}))
    return dst


def mark_ide_present(env: Env) -> None:
    (env.home / ".gemini" / "config").mkdir(parents=True)


def snapshot(root: Path) -> list[Path]:
    return sorted(root.rglob("*"))


def test_agy_ide_is_a_host_with_user_and_project_scopes() -> None:
    assert "agy-ide" in installer.HOSTS
    assert installer._SCOPES_BY_HOST["agy-ide"] == ("user", "project")


def test_agy_ide_scope_local_is_rejected_with_exit_2(
    env: Env, capsys: pytest.CaptureFixture[str]
) -> None:
    mark_ide_present(env)
    code, lines = run("install", ["agy-ide"], scope="local")
    assert code == 2
    assert lines == []
    assert "--scope local is not supported for agy-ide" in capsys.readouterr().err


def test_agy_ide_destination_per_scope(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    cwd = env.home / "work"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    assert installer._agy_ide_destination("user") == (
        env.home / ".gemini" / "config" / "plugins" / "refract"
    )
    assert installer._agy_ide_destination("project") == (
        cwd.resolve() / ".agents" / "plugins" / "refract"
    )


def test_agy_ide_rejects_url_source(env: Env) -> None:
    mark_ide_present(env)
    code, lines = run("install", ["agy-ide"], dry_run=True)
    assert code == 1
    assert any("agy-ide: failed:" in line and "local path" in line for line in lines)
    code, lines = run("install", ["agy-ide"], source="git@github.com:o/r.git", dry_run=True)
    assert code == 1
    assert any("local path" in line for line in lines)


def test_agy_ide_plugin_root_from_repository_path(env: Env, tmp_path: Path) -> None:
    mark_ide_present(env)
    repo = tmp_path / "repo"
    plugin = make_plugin_root(repo / "plugin")
    assert installer._agy_ide_plugin_root(str(repo)) == plugin
    code, lines = run("install", ["agy-ide"], source=str(repo), dry_run=True)
    dst = env.home / ".gemini" / "config" / "plugins" / "refract"
    assert code == 0
    assert lines[0] == "hosts: agy-ide"
    assert f"agy-ide: would copy {plugin} -> {dst}" in lines
    assert lines[-1] == "agy-ide: skipped (dry run)"


def test_agy_ide_plugin_root_from_plugin_path(env: Env, tmp_path: Path) -> None:
    mark_ide_present(env)
    plugin = make_plugin_root(tmp_path / "plugin")
    assert installer._agy_ide_plugin_root(str(plugin)) == plugin
    code, lines = run("install", ["agy-ide"], source=str(plugin), dry_run=True)
    assert code == 0
    assert any(line.startswith(f"agy-ide: would copy {plugin} -> ") for line in lines)


def test_agy_ide_fails_without_manifest(env: Env, tmp_path: Path) -> None:
    mark_ide_present(env)
    (tmp_path / "empty" / "plugin").mkdir(parents=True)
    code, lines = run("install", ["agy-ide"], source=str(tmp_path / "empty"), dry_run=True)
    assert code == 1
    assert any("agy-ide: failed:" in line and "plugin.json" in line for line in lines)


@pytest.mark.parametrize("marker", [".gemini/antigravity-ide", ".gemini/config"])
def test_agy_ide_probe_present(env: Env, marker: str) -> None:
    (env.home / marker).mkdir(parents=True)
    assert installer._agy_ide_present() is True


def test_agy_ide_probe_absent_reports_failure(env: Env, tmp_path: Path) -> None:
    plugin = make_plugin_root(tmp_path / "plugin")
    assert installer._agy_ide_present() is False
    code, lines = run("install", ["agy-ide"], source=str(plugin), dry_run=True)
    assert code == 1
    assert "agy-ide: failed: Antigravity IDE not found" in lines


def test_all_includes_agy_ide_only_when_probe_succeeds(env: Env) -> None:
    assert installer._expand_hosts(["all"]) == []
    mark_ide_present(env)
    assert installer._expand_hosts(["all"]) == ["agy-ide"]


def test_agy_ide_install_dry_run_lines_and_no_writes(env: Env, tmp_path: Path) -> None:
    mark_ide_present(env)
    plugin = make_plugin_root(tmp_path / "plugin")
    before = snapshot(env.home)
    code, lines = run("install", ["agy-ide"], source=str(plugin), dry_run=True)
    dst = env.home / ".gemini" / "config" / "plugins" / "refract"
    assert code == 0
    assert lines == [
        "hosts: agy-ide",
        f"agy-ide: would copy {plugin} -> {dst}",
        "agy-ide: skipped (dry run)",
    ]
    assert snapshot(env.home) == before


def test_agy_ide_installed_detection_and_uninstall_dry_run(env: Env, tmp_path: Path) -> None:
    mark_ide_present(env)
    plugin = make_plugin_root(tmp_path / "plugin")
    dst = env.home / ".gemini" / "config" / "plugins" / "refract"
    code, lines = run("uninstall", ["agy-ide"], dry_run=True)
    assert (code, lines) == (0, ["hosts: agy-ide", "agy-ide: not installed"])
    own_ide_copy(make_plugin_root(dst))
    before = snapshot(env.home)
    assert run("install", ["agy-ide"], source=str(plugin), dry_run=True)[1][-1] == (
        "agy-ide: already installed"
    )
    code, lines = run("uninstall", ["agy-ide"], dry_run=True)
    assert code == 0
    assert lines == [
        "hosts: agy-ide",
        f"agy-ide: would remove {dst}",
        "agy-ide: skipped (dry run)",
    ]
    assert snapshot(env.home) == before


def test_agy_ide_detects_root_plugin_json(env: Env) -> None:
    mark_ide_present(env)
    dst = env.home / ".gemini" / "config" / "plugins" / "refract"
    dst.mkdir(parents=True)
    (dst / "plugin.json").write_text(json.dumps({"name": "refract"}))
    own_ide_copy(dst)
    assert run("uninstall", ["agy-ide"], dry_run=True)[1][1] == f"agy-ide: would remove {dst}"
    (dst / "plugin.json").write_text(json.dumps({"name": "other"}))
    failure = run("uninstall", ["agy-ide"], dry_run=True)[1][1]
    assert failure.startswith("agy-ide: failed:")
    assert "not a Refract plugin" in failure


def test_agy_ide_project_scope_dry_run(
    env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mark_ide_present(env)
    plugin = make_plugin_root(tmp_path / "plugin")
    cwd = tmp_path / "proj"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    code, lines = run("install", ["agy-ide"], scope="project", source=str(plugin), dry_run=True)
    dst = cwd.resolve() / ".agents" / "plugins" / "refract"
    assert code == 0
    assert f"agy-ide: would copy {plugin} -> {dst}" in lines
    assert not (cwd / ".agents").exists()


def test_all_with_default_source_skips_agy_ide_and_exits_0(env: Env) -> None:
    mark_ide_present(env)
    for dry_run in (True, False):
        code, lines = run("install", ["all"], dry_run=dry_run)
        assert code == 0
        assert lines == ["hosts: agy-ide", "agy-ide: skipped: needs --source <local path>"]


def test_all_uninstall_with_agy_ide_not_installed_exits_0(env: Env) -> None:
    mark_ide_present(env)
    code, lines = run("uninstall", ["all"])
    assert (code, lines) == (0, ["hosts: agy-ide", "agy-ide: not installed"])


def test_named_agy_ide_with_default_source_still_fails(env: Env) -> None:
    mark_ide_present(env)
    code, lines = run("install", ["agy-ide"])
    assert code == 1
    assert "agy-ide: failed: agy-ide needs a local path source; pass --source <path>" in lines


def tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def fake_plugin(root: Path) -> Path:
    make_plugin_root(root)
    (root / "skills" / "one").mkdir(parents=True)
    (root / "skills" / "one" / "SKILL.md").write_bytes(b"# one\r\n\x00\xff")
    (root / "hooks.json").write_text("{}")
    return root


def test_agy_ide_install_copies_the_tree_and_uninstall_removes_it(
    env: Env, tmp_path: Path
) -> None:
    mark_ide_present(env)
    plugin = fake_plugin(tmp_path / "plugin")
    dst = env.home / ".gemini" / "config" / "plugins" / "refract"
    code, lines = run("install", ["agy-ide"], source=str(plugin))
    assert (code, lines) == (0, ["hosts: agy-ide", "agy-ide: installed"])
    copied = tree(dst)
    assert {k: v for k, v in copied.items() if k != IDE_MARKER} == tree(plugin)
    assert IDE_MARKER in copied
    assert not [p for p in dst.parent.iterdir() if p != dst]
    code, lines = run("uninstall", ["agy-ide"])
    assert (code, lines) == (0, ["hosts: agy-ide", "agy-ide: removed"])
    assert not dst.exists()
    assert (dst.parent).is_dir()
    assert run("uninstall", ["agy-ide"]) == (0, ["hosts: agy-ide", "agy-ide: not installed"])


def test_agy_ide_reinstall_is_a_noop(env: Env, tmp_path: Path) -> None:
    mark_ide_present(env)
    plugin = fake_plugin(tmp_path / "plugin")
    assert run("install", ["agy-ide"], source=str(plugin))[0] == 0
    dst = env.home / ".gemini" / "config" / "plugins" / "refract"
    (dst / "skills" / "one" / "SKILL.md").write_text("edited")
    before = tree(dst)
    code, lines = run("install", ["agy-ide"], source=str(plugin))
    assert (code, lines) == (0, ["hosts: agy-ide", "agy-ide: already installed"])
    assert tree(dst) == before


def test_agy_ide_project_scope_install_and_uninstall(
    env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mark_ide_present(env)
    plugin = fake_plugin(tmp_path / "plugin")
    cwd = tmp_path / "proj"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    assert run("install", ["agy-ide"], scope="project", source=str(plugin))[0] == 0
    dst = cwd / ".agents" / "plugins" / "refract"
    assert (dst / ".antigravity-plugin" / "plugin.json").is_file()
    assert run("uninstall", ["agy-ide"], scope="project")[1][-1] == "agy-ide: removed"
    assert not dst.exists()


def test_agy_ide_uninstall_refuses_another_plugin(env: Env) -> None:
    mark_ide_present(env)
    dst = env.home / ".gemini" / "config" / "plugins" / "refract"
    make_plugin_root(dst)
    (dst / ".antigravity-plugin" / "plugin.json").write_text(json.dumps({"name": "other"}))
    own_ide_copy(dst)
    before = tree(dst)
    code, lines = run("uninstall", ["agy-ide"])
    assert code == 1
    assert lines[-1].startswith("agy-ide: failed:")
    assert "not a Refract plugin" in lines[-1]
    assert tree(dst) == before


def test_agy_ide_uninstall_refuses_a_directory_without_a_manifest(env: Env) -> None:
    mark_ide_present(env)
    dst = env.home / ".gemini" / "config" / "plugins" / "refract"
    dst.mkdir(parents=True)
    (dst / "notes.txt").write_text("keep")
    code, lines = run("uninstall", ["agy-ide"])
    assert code == 1
    assert "not a Refract plugin" in lines[-1]
    assert (dst / "notes.txt").read_text() == "keep"


def test_agy_ide_uninstall_refuses_a_refract_manifest_without_the_marker(env: Env) -> None:
    """The agy CLI stages its own refract manifest at this path; it must survive."""
    mark_ide_present(env)
    dst = env.home / ".gemini" / "config" / "plugins" / "refract"
    make_plugin_root(dst)
    before = tree(dst)
    for dry_run in (True, False):
        code, lines = run("uninstall", ["agy-ide"], dry_run=dry_run)
        assert code == 1
        assert lines[-1].startswith("agy-ide: failed:")
        assert "another tool" in lines[-1]
        assert tree(dst) == before


def test_agy_ide_uninstall_of_a_missing_destination_is_not_installed(env: Env) -> None:
    mark_ide_present(env)
    assert run("uninstall", ["agy-ide"]) == (0, ["hosts: agy-ide", "agy-ide: not installed"])


def test_agy_ide_failed_copy_leaves_no_destination_or_temp_dir(
    env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mark_ide_present(env)
    plugin = fake_plugin(tmp_path / "plugin")
    parent = env.home / ".gemini" / "config" / "plugins"

    def half_copy(src: Path, dst: Path, **kwargs: object) -> Path:
        (dst / "hooks.json").write_text("{}")
        raise OSError("disk full")

    monkeypatch.setattr(installer.shutil, "copytree", half_copy)
    code, lines = run("install", ["agy-ide"], source=str(plugin))
    assert code == 1
    assert lines[1].startswith("agy-ide: failed:")
    assert "disk full" in lines[1]
    assert not (parent / "refract").exists()
    assert list(parent.iterdir()) == []


def test_agy_ide_install_into_an_existing_foreign_directory_fails_and_keeps_it(
    env: Env, tmp_path: Path
) -> None:
    mark_ide_present(env)
    plugin = fake_plugin(tmp_path / "plugin")
    dst = env.home / ".gemini" / "config" / "plugins" / "refract"
    dst.mkdir(parents=True)
    (dst / "notes.txt").write_text("keep")
    code, lines = run("install", ["agy-ide"], source=str(plugin))
    assert code == 1
    assert lines[-1].startswith("agy-ide: failed:")
    assert tree(dst) == {"notes.txt": b"keep"}
    assert [p.name for p in dst.parent.iterdir()] == ["refract"]


def ide_dst(env: Env) -> Path:
    return env.home / ".gemini" / "config" / "plugins" / "refract"


def staging_leftovers(parent: Path) -> list[str]:
    return sorted(p.name for p in parent.iterdir() if p.name.startswith(".refract-"))


def test_apply_file_rechecks_the_marker_before_removing(env: Env) -> None:
    dst = make_plugin_root(ide_dst(env))
    before = tree(dst)
    reason = installer._apply_file(installer._FileStep("remove", None, dst))
    assert reason is not None
    assert "no Refract install marker" in reason
    assert tree(dst) == before


@pytest.mark.skipif(sys.platform == "win32", reason="needs symlinks")
def test_agy_ide_symlinked_destination_is_refused_at_plan_and_execute_time(
    env: Env, tmp_path: Path
) -> None:
    mark_ide_present(env)
    target = own_ide_copy(make_plugin_root(tmp_path / "elsewhere"))
    dst = ide_dst(env)
    dst.parent.mkdir(parents=True)
    dst.symlink_to(target, target_is_directory=True)
    before = tree(target)
    for dry_run in (True, False):
        code, lines = run("uninstall", ["agy-ide"], dry_run=dry_run)
        assert code == 1
        assert lines[-1] == f"agy-ide: failed: {dst} is a link; not removing it"
    reason = installer._apply_file(installer._FileStep("remove", None, dst))
    assert reason == f"{dst} is a link; not removing it"
    assert dst.is_symlink()
    assert tree(target) == before


@pytest.mark.skipif(sys.platform == "win32", reason="needs symlinks")
def test_agy_ide_symlinked_marker_is_not_ownership(env: Env, tmp_path: Path) -> None:
    mark_ide_present(env)
    dst = make_plugin_root(ide_dst(env))
    real = own_ide_copy(make_plugin_root(tmp_path / "real"))
    (dst / IDE_MARKER).symlink_to(real / IDE_MARKER)
    # Even with a path that matches, a linked marker proves nothing.
    (real / IDE_MARKER).write_text(json.dumps({"owner": "refract", "path": str(dst.resolve())}))
    assert installer._agy_ide_owned(dst) is False
    code, lines = run("uninstall", ["agy-ide"])
    assert code == 1
    assert "another tool" in lines[-1]
    assert dst.is_dir()


@pytest.mark.parametrize(
    "content",
    ["not json", "[]", '{"owner": "other"}', '{"owner": "refract"}', '{"owner": "refract", "path": 3}'],
    ids=["malformed", "not-object", "wrong-owner", "no-path-legacy", "bad-path"],
)
def test_agy_ide_unusable_marker_is_not_ownership(env: Env, content: str) -> None:
    mark_ide_present(env)
    dst = make_plugin_root(ide_dst(env))
    (dst / IDE_MARKER).write_text(content)
    before = tree(dst)
    code, lines = run("uninstall", ["agy-ide"])
    assert code == 1
    assert "another tool" in lines[-1]
    assert tree(dst) == before


def test_agy_ide_marker_that_is_a_directory_is_not_ownership(env: Env) -> None:
    mark_ide_present(env)
    dst = make_plugin_root(ide_dst(env))
    (dst / IDE_MARKER).mkdir()
    assert run("uninstall", ["agy-ide"])[0] == 1
    assert dst.is_dir()


def test_agy_ide_marker_naming_another_location_is_not_ownership(
    env: Env, tmp_path: Path
) -> None:
    mark_ide_present(env)
    plugin = fake_plugin(tmp_path / "plugin")
    assert run("install", ["agy-ide"], source=str(plugin))[0] == 0
    dst = ide_dst(env)
    elsewhere = tmp_path / "copy" / "refract"
    shutil.copytree(dst, elsewhere)
    assert json.loads((elsewhere / IDE_MARKER).read_text())["path"] == str(dst.resolve())
    assert installer._agy_ide_owned(elsewhere) is False
    reason = installer._apply_file(installer._FileStep("remove", None, elsewhere))
    assert reason is not None
    assert elsewhere.is_dir()
    assert installer._agy_ide_owned(dst) is True


def test_agy_ide_failed_rename_leaves_no_staging_directory(
    env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mark_ide_present(env)
    plugin = fake_plugin(tmp_path / "plugin")

    def refuse(self: Path, target: object) -> Path:
        raise PermissionError("busy")

    monkeypatch.setattr(Path, "rename", refuse)
    code, lines = run("install", ["agy-ide"], source=str(plugin))
    assert code == 1
    assert "busy" in lines[-1]
    assert not ide_dst(env).exists()
    assert staging_leftovers(ide_dst(env).parent) == []


def test_agy_ide_interrupt_during_copy_removes_staging(
    env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mark_ide_present(env)
    plugin = fake_plugin(tmp_path / "plugin")

    def interrupt(src: Path, dst: Path, **kwargs: object) -> Path:
        (dst / "hooks.json").write_text("{}")
        raise KeyboardInterrupt

    monkeypatch.setattr(installer.shutil, "copytree", interrupt)
    with pytest.raises(KeyboardInterrupt):
        run("install", ["agy-ide"], source=str(plugin))
    assert staging_leftovers(ide_dst(env).parent) == []
    assert not ide_dst(env).exists()


@pytest.mark.skipif(sys.platform == "win32", reason="needs POSIX permission bits")
def test_agy_ide_read_only_source_installs_or_fails_cleanly(env: Env, tmp_path: Path) -> None:
    """No copytree patch: the real copystat path makes staging read-only."""
    mark_ide_present(env)
    plugin = fake_plugin(tmp_path / "plugin")
    (plugin / "hooks.json").chmod(0o444)
    plugin.chmod(0o555)
    try:
        code, lines = run("install", ["agy-ide"], source=str(plugin))
        parent = ide_dst(env).parent
        assert staging_leftovers(parent) == []
        assert (code, lines[-1]) == (0, "agy-ide: installed")
        assert run("uninstall", ["agy-ide"])[1][-1] == "agy-ide: removed"
        assert list(parent.iterdir()) == []
    finally:
        plugin.chmod(0o755)
        (plugin / "hooks.json").chmod(0o644)


@pytest.mark.skipif(sys.platform == "win32", reason="needs POSIX permission bits")
def test_agy_ide_read_only_source_with_failing_marker_write_leaves_no_staging(
    env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mark_ide_present(env)
    plugin = fake_plugin(tmp_path / "plugin")
    (plugin / "skills" / "one" / "SKILL.md").chmod(0o444)
    (plugin / "skills" / "one").chmod(0o555)
    real_write = Path.write_text

    def deny_marker(self: Path, *args: object, **kwargs: object) -> int:
        if self.name == IDE_MARKER:
            raise PermissionError(13, "denied")
        return real_write(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "write_text", deny_marker)
    try:
        code, lines = run("install", ["agy-ide"], source=str(plugin))
        assert code == 1
        assert "denied" in lines[-1]
        assert staging_leftovers(ide_dst(env).parent) == []
    finally:
        (plugin / "skills" / "one").chmod(0o755)


@pytest.mark.skipif(sys.platform == "win32", reason="needs POSIX permission bits")
def test_agy_ide_uninstall_deletes_read_only_files(env: Env, tmp_path: Path) -> None:
    mark_ide_present(env)
    plugin = fake_plugin(tmp_path / "plugin")
    assert run("install", ["agy-ide"], source=str(plugin))[0] == 0
    dst = ide_dst(env)
    (dst / "skills" / "one" / "SKILL.md").chmod(0o444)
    (dst / "skills" / "one").chmod(0o555)
    assert run("uninstall", ["agy-ide"])[1][-1] == "agy-ide: removed"
    assert list(dst.parent.iterdir()) == []


def test_agy_ide_failed_delete_leaves_no_broken_destination(
    env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mark_ide_present(env)
    plugin = fake_plugin(tmp_path / "plugin")
    assert run("install", ["agy-ide"], source=str(plugin))[0] == 0
    dst = ide_dst(env)

    def fail(path: Path) -> None:
        raise OSError("file in use")

    monkeypatch.setattr(installer, "_rmtree", fail)
    code, lines = run("uninstall", ["agy-ide"])
    assert code == 1
    assert "file in use" in lines[-1]
    assert ".refract-removing-" in lines[-1]
    assert not dst.exists()
    # The leftover is named in the report; a later uninstall sees no destination.
    assert run("uninstall", ["agy-ide"]) == (0, ["hosts: agy-ide", "agy-ide: not installed"])


def test_agy_ide_failed_rename_aside_keeps_the_destination(
    env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mark_ide_present(env)
    plugin = fake_plugin(tmp_path / "plugin")
    assert run("install", ["agy-ide"], source=str(plugin))[0] == 0
    dst = ide_dst(env)
    before = tree(dst)

    def refuse(self: Path, target: object) -> Path:
        raise PermissionError("busy")

    monkeypatch.setattr(Path, "rename", refuse)
    code, lines = run("uninstall", ["agy-ide"])
    assert code == 1
    assert "busy" in lines[-1]
    assert tree(dst) == before
    assert run("uninstall", ["agy-ide"], dry_run=True)[1][1] == f"agy-ide: would remove {dst}"


def test_agy_ide_destination_inside_the_source_is_refused(
    env: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mark_ide_present(env)
    plugin = fake_plugin(tmp_path / "plugin")
    (plugin / ".agents").mkdir()
    monkeypatch.chdir(plugin)
    for dry_run in (True, False):
        code, lines = run(
            "install", ["agy-ide"], scope="project", source=str(plugin), dry_run=dry_run
        )
        assert code == 1
        assert "inside the source" in lines[-1]
    assert list((plugin / ".agents").iterdir()) == []


def test_all_with_local_source_runs_every_host_including_agy_ide(
    env: Env, tmp_path: Path
) -> None:
    mark_ide_present(env)
    for host in ("claude", "codex", "agy", "pi"):
        stub_host(env, host)
    plugin = fake_plugin(tmp_path / "plugin")
    code, lines = run("install", ["all"], source=str(plugin))
    assert code == 0
    assert lines[0] == "hosts: claude, codex, agy, agy-ide, pi"
    for host in ("claude", "codex", "agy", "agy-ide", "pi"):
        assert f"{host}: installed" in lines
    assert any(call.startswith("pi install") for call in mutating(env))
    dst = env.home / ".gemini" / "config" / "plugins" / "refract"
    assert (dst / ".antigravity-plugin" / "plugin.json").is_file()


def test_agy_ide_failure_does_not_stop_later_hosts(env: Env, tmp_path: Path) -> None:
    mark_ide_present(env)
    stub_host(env, "claude")
    plugin = fake_plugin(tmp_path / "plugin")
    dst = env.home / ".gemini" / "config" / "plugins" / "refract"
    dst.mkdir(parents=True)
    code, lines = run("install", ["agy-ide", "claude"], source=str(plugin))
    assert code == 1
    assert lines[1].startswith("agy-ide: failed:")
    assert lines[-1] == "claude: installed"


def test_report_failure_renders_file_steps() -> None:
    lines: list[str] = []
    step = installer._FileStep("copy", Path("src"), Path("dst"))
    installer._report_failure("agy-ide", "boom", [step], lines.append)
    assert lines == ["agy-ide: failed: boom", "agy-ide: applied: copy src -> dst"]
