import importlib.util
import re
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "bump_version.py"

TARGETS = [
    "server/pyproject.toml",
    "server/uv.lock",
    "package.json",
    "plugin/package.json",
    ".claude-plugin/marketplace.json",
    "plugin/.claude-plugin/plugin.json",
    "plugin/.codex-plugin/plugin.json",
    "plugin/.antigravity-plugin/plugin.json",
    "sonar-project.properties",
    "README.md",
    "server/README.md",
    "server/CLI_ARGUMENTS.md",
    "plugin/shared/erp.md",
    "plugin/shared/journal-template.md",
    "plugin/shared/notes-template.md",
    "plugin/shared/worker-contract.md",
    "CHANGELOG.md",
]
TODAY = "2030-01-02"
PLUGIN_README = "plugin/README.md"


def _load():
    spec = importlib.util.spec_from_file_location("bump_version", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def bump():
    return _load()


def _ensure_unreleased_entry(root):
    """Give `## Unreleased` an entry when the copied section is empty, as it is right after a release."""
    path = root / "CHANGELOG.md"
    text = path.read_text(encoding="utf-8")
    match = re.search(r"^## Unreleased\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if match and not match.group(1).strip():
        path.write_text(
            text[: match.start(1)] + "\n- Fixture entry.\n\n" + text[match.end(1) :], encoding="utf-8"
        )


@pytest.fixture
def tree(tmp_path):
    for rel in [*TARGETS, PLUGIN_README]:
        dest = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / rel, dest)
    _ensure_unreleased_entry(tmp_path)
    return tmp_path


@pytest.fixture
def current(tree):
    text = (tree / "server/pyproject.toml").read_text(encoding="utf-8")
    return re.search(r'^version = "([^"]+)"$', text, re.M).group(1)


def _snapshot(root):
    return {rel: (root / rel).read_bytes() for rel in TARGETS}


def _changed_lines(before: bytes, after: bytes):
    old, new = before.decode().splitlines(keepends=True), after.decode().splitlines(keepends=True)
    return [(i, o, n) for i, (o, n) in enumerate(zip(old, new)) if o != n], len(old), len(new)


def _next(version, part):
    major, minor, patch = (int(x) for x in version.split("."))
    return {
        "patch": f"{major}.{minor}.{patch + 1}",
        "minor": f"{major}.{minor + 1}.0",
        "major": f"{major + 1}.0.0",
    }[part]


@pytest.mark.parametrize("part", ["patch", "minor", "major"])
def test_bump_math_and_last_stdout_line(bump, tree, current, part, capsys):
    assert bump.main([part], root=tree, today=TODAY) == 0
    expected = _next(current, part)
    assert capsys.readouterr().out.strip().splitlines()[-1] == expected
    pyproject = (tree / "server/pyproject.toml").read_text(encoding="utf-8")
    assert f'version = "{expected}"' in pyproject


def test_every_target_changes_and_nothing_else(bump, tree, current):
    before = _snapshot(tree)
    assert bump.main(["minor"], root=tree, today=TODAY) == 0
    new = _next(current, "minor")
    for rel in TARGETS:
        after = (tree / rel).read_bytes()
        changed, old_len, new_len = _changed_lines(before[rel], after)
        assert changed, rel
        if rel == "CHANGELOG.md":
            assert new_len == old_len + 2, rel
            continue
        assert old_len == new_len, rel
        assert len(changed) == 1, (rel, changed)
        _, old_line, new_line = changed[0]
        assert current in old_line
        assert new in new_line, rel
        assert old_line.replace(current, new, 1) == new_line, rel


def _released(changelog):
    return next(line.split()[1] for line in changelog if line.endswith(f" - {TODAY}"))


def test_history_lines_unchanged(bump, tree):
    readme_before = (tree / "README.md").read_text(encoding="utf-8").splitlines()
    changelog_before = (tree / "CHANGELOG.md").read_text(encoding="utf-8").splitlines()
    plugin_readme = (tree / PLUGIN_README).read_bytes()
    headings = [line for line in changelog_before if line.startswith("## ") and line != "## Unreleased"]
    assert headings
    assert bump.main(["minor"], root=tree, today=TODAY) == 0
    readme = (tree / "README.md").read_text(encoding="utf-8").splitlines()
    assert readme[0].startswith("# Refract ")
    assert readme[0] != readme_before[0]
    assert readme[1:] == readme_before[1:]
    changelog = (tree / "CHANGELOG.md").read_text(encoding="utf-8").splitlines()
    for heading in headings:
        assert heading in changelog
    remaining = list(changelog)
    for line in changelog_before:
        if line != "## Unreleased":
            remaining.remove(line)
    assert set(remaining) <= {"", "## Unreleased", f"## {_released(changelog)} - {TODAY}"}
    assert (tree / PLUGIN_README).read_bytes() == plugin_readme


def test_changelog_result_with_injected_date(bump, tree, current):
    old = (tree / "CHANGELOG.md").read_text(encoding="utf-8")
    assert bump.main(["patch"], root=tree, today=TODAY) == 0
    new = (tree / "CHANGELOG.md").read_text(encoding="utf-8")
    new_version = _next(current, "patch")
    assert new == old.replace("## Unreleased\n", f"## Unreleased\n\n## {new_version} - {TODAY}\n", 1)
    assert new.startswith(f"# Changelog\n\n## Unreleased\n\n## {new_version} - {TODAY}\n\n- ")


@pytest.mark.parametrize("rel", [t for t in TARGETS if t not in ("server/pyproject.toml", "CHANGELOG.md")])
def test_drift_refused_naming_file_and_writing_nothing(bump, tree, current, rel, capsys):
    path = tree / rel
    text = path.read_text(encoding="utf-8")
    pattern = dict(bump.TARGETS)[rel]
    start, end = re.search(pattern, text, re.M).span("v")
    path.write_text(text[:start] + "0.0.1" + text[end:], encoding="utf-8")
    before = _snapshot(tree)
    assert bump.main(["minor"], root=tree, today=TODAY) != 0
    captured = capsys.readouterr()
    assert rel in captured.err + captured.out
    assert _snapshot(tree) == before


def _set_changelog(tree, text):
    (tree / "CHANGELOG.md").write_text(text, encoding="utf-8")
    return _snapshot(tree)


@pytest.mark.parametrize(
    "text",
    [
        "# Changelog\n\n## 2.5.0 - 2026-11-06\n\n- Added x.\n",
        "# Changelog\n\n## Unreleased\n\n\n## 2.5.0 - 2026-11-06\n\n- Added x.\n",
        "# Changelog\n\n## Unreleased\n",
        "# Changelog\n\n## Unreleased - 2026-11-03\n\n- Added x.\n",
    ],
    ids=["missing", "empty", "empty-at-eof", "dated-only"],
)
def test_changelog_refusals_write_nothing(bump, tree, text, capsys):
    before = _set_changelog(tree, text)
    assert bump.main(["minor"], root=tree, today=TODAY) != 0
    assert "CHANGELOG.md" in capsys.readouterr().err
    assert _snapshot(tree) == before


def test_dry_run_lists_every_change_and_writes_nothing(bump, tree, current, capsys):
    before = _snapshot(tree)
    assert bump.main(["minor", "--dry-run"], root=tree, today=TODAY) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[-1] == _next(current, "minor")
    assert len(lines) - 1 == len(TARGETS)
    for rel in TARGETS:
        assert sum(line.startswith(f"{rel}: ") for line in lines[:-1]) == 1, rel
    assert _snapshot(tree) == before


def test_crlf_line_endings_preserved(bump, tree, current):
    for rel in TARGETS:
        path = tree / rel
        # A Windows checkout may already hold CRLF; normalize first so no line ends in CR CR LF.
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert bump.main(["patch"], root=tree, today=TODAY) == 0
    for rel in TARGETS:
        data = (tree / rel).read_bytes()
        assert data.count(b"\n") == data.count(b"\r\n"), rel


def test_unknown_part_and_bad_usage_exit_nonzero(bump, tree):
    before = _snapshot(tree)
    assert bump.main(["huge"], root=tree, today=TODAY) != 0
    assert bump.main([], root=tree, today=TODAY) != 0
    assert _snapshot(tree) == before


def test_script_imports_neither_subprocess_nor_socket():
    source = SCRIPT.read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|from)\s+(subprocess|socket|urllib)", source, re.M)


def test_notes_prints_section_body_exactly(bump, tree, capsys):
    (tree / "CHANGELOG.md").write_bytes(
        b"# Changelog\n\n## Unreleased\n\n- Pending.\n\n## 2.6.0 - 2030-01-02\n\n\n- First.\n- Second.\n\n\n"
        b"## 2.5.0 - 2026-11-06\n\n- Old.\n"
    )
    assert bump.main(["notes", "2.6.0"], root=tree) == 0
    assert capsys.readouterr().out == "- First.\n- Second.\n"


def test_notes_reads_real_changelog_section(bump, tree, capsys):
    assert bump.main(["notes", "3.0.0"], root=tree) == 0
    out = capsys.readouterr().out
    assert out.startswith("First public release.")
    assert out.rstrip().endswith("Host plugin for Claude Code, Antigravity, Codex, and Pi.")
    assert "## " not in out


def test_notes_reads_crlf_changelog(bump, tree, capsys):
    (tree / "CHANGELOG.md").write_bytes(
        b"# Changelog\r\n\r\n## Unreleased\r\n\r\n- Pending.\r\n\r\n## 2.6.0 - 2030-01-02\r\n\r\n"
        b"- First.\r\n- Second.\r\n\r\n## 2.5.0 - 2026-11-06\r\n\r\n- Old.\r\n"
    )
    assert bump.main(["notes", "2.6.0"], root=tree) == 0
    assert capsys.readouterr().out == "- First.\r\n- Second.\n"


def test_notes_unknown_version_exits_nonzero(bump, tree, capsys):
    assert bump.main(["notes", "9.9.9"], root=tree) != 0
    assert "9.9.9" in capsys.readouterr().err


def test_notes_does_not_match_version_prefix(bump, tree):
    assert bump.main(["notes", "2.5"], root=tree) != 0


def test_notes_empty_section_exits_nonzero(bump, tree, capsys):
    (tree / "CHANGELOG.md").write_text(
        "# Changelog\n\n## 2.6.0 - 2030-01-02\n\n\n## 2.5.0 - 2026-11-06\n\n- Old.\n", encoding="utf-8"
    )
    assert bump.main(["notes", "2.6.0"], root=tree) != 0
    assert "empty" in capsys.readouterr().err


def _holds(root, rel, pattern):
    return re.findall(pattern, (root / rel).read_text(encoding="utf-8"), re.M)


def _assert_all_hold(tree, new):
    json_version = r'^\s*"version": "([^"]+)"'
    expected = {
        "server/pyproject.toml": r'^version = "([^"]+)"$',
        "server/uv.lock": r'^name = "refract"\nversion = "([^"]+)"$',
        "package.json": json_version,
        "plugin/package.json": json_version,
        ".claude-plugin/marketplace.json": json_version,
        "plugin/.claude-plugin/plugin.json": json_version,
        "plugin/.codex-plugin/plugin.json": json_version,
        "plugin/.antigravity-plugin/plugin.json": json_version,
        "sonar-project.properties": r"^sonar\.projectVersion=(.+)$",
        "README.md": r"\A# Refract (.+)$",
        "server/README.md": r"^Version (\S+) ·",
        "server/CLI_ARGUMENTS.md": r"^Refract (\S+) ·",
        "plugin/shared/erp.md": r"^<!-- refract-shared-version: (\S+) -->$",
        "plugin/shared/journal-template.md": r"^<!-- refract-shared-version: (\S+) -->$",
        "plugin/shared/notes-template.md": r"^<!-- refract-shared-version: (\S+) -->$",
        "plugin/shared/worker-contract.md": r"^<!-- refract-shared-version: (\S+) -->$",
    }
    assert set(expected) | {"CHANGELOG.md"} == set(TARGETS)
    for rel, pattern in expected.items():
        assert _holds(tree, rel, pattern) == [new], rel


def test_bump_leaves_every_target_on_the_same_new_version(bump, tree, current):
    assert bump.main(["minor"], root=tree, today=TODAY) == 0
    _assert_all_hold(tree, _next(current, "minor"))


def test_second_bump_after_release_state(bump, tree, current, capsys):
    assert bump.main(["minor"], root=tree, today=TODAY) == 0
    first = _next(current, "minor")
    _assert_all_hold(tree, first)
    # Post-release state: the real tree's `## Unreleased` is empty, so a bump is refused.
    before = _snapshot(tree)
    assert bump.main(["patch"], root=tree, today=TODAY) != 0
    assert _snapshot(tree) == before
    _ensure_unreleased_entry(tree)
    assert bump.main(["patch"], root=tree, today=TODAY) == 0
    second = _next(first, "patch")
    assert capsys.readouterr().out.strip().splitlines()[-1] == second
    _assert_all_hold(tree, second)
