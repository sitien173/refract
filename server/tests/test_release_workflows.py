import re
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
RUN = re.compile(r"^(\s*(?:-\s+)?)run:\s*(.*)$")


def read(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def run_blocks(text: str) -> list[str]:
    """Return the shell text of every `run:` step, single-line and block forms."""
    lines = text.splitlines()
    blocks = []
    for i, line in enumerate(lines):
        m = RUN.match(line)
        if not m:
            continue
        key_indent = len(m.group(1))
        body = [m.group(2)]
        if re.fullmatch(r"[|>][+-]?", m.group(2).strip()):
            body = []
            for nxt in lines[i + 1 :]:
                if nxt.strip() and len(nxt) - len(nxt.lstrip()) <= key_indent:
                    break
                body.append(nxt)
        blocks.append("\n".join(body))
    return blocks


def test_run_blocks_helper_covers_both_forms():
    text = "steps:\n  - run: echo ${{ a }}\n  - name: x\n    run: |\n      echo hi\n      echo ${{ b }}\n    env:\n      V: ${{ c }}\n"
    blocks = run_blocks(text)
    assert len(blocks) == 2
    assert "${{ a }}" in blocks[0]
    assert "${{ b }}" in blocks[1] and "${{ c }}" not in blocks[1]


def test_no_expression_inside_run_blocks():
    for name in ("bump.yml", "release.yml"):
        blocks = run_blocks(read(name))
        if name == "bump.yml":
            assert blocks, "bump.yml has no run steps"
        for block in blocks:
            assert "${{" not in block, f"{name}: expression inside run: {block!r}"


def test_bump_dispatch_input():
    text = read("bump.yml")
    assert "workflow_dispatch:" in text
    assert re.search(r"level:\n(?:\s+.*\n)*?\s+type: choice", text)
    assert re.search(r"options:\n\s+- patch\n\s+- minor\n\s+- major\n", text)
    assert re.search(r"default: patch\b", text)


def test_bump_permissions_and_concurrency():
    text = read("bump.yml")
    assert re.search(r"permissions:\n\s+contents: write\n\s+actions: write\n", text)
    assert "concurrency:" in text
    assert "group:" in text
    assert "cancel-in-progress: false" in text


def test_bump_main_branch_guard_comes_first():
    text = read("bump.yml")
    assert "refs/heads/main" in text
    assert text.index("refs/heads/main") < text.index("actions/checkout")


def test_bump_pins_uv():
    text = read("bump.yml")
    assert 'version: "0.11.26"' in text
    assert 'python-version: "3.12"' in text


def test_bump_atomic_push_and_dispatch():
    text = read("bump.yml")
    assert re.search(r'git push --atomic origin HEAD:main "refs/tags/v\$VERSION"', text)
    assert 'gh workflow run release.yml --ref "v$VERSION"' in text
    assert "GH_TOKEN: ${{ github.token }}" in text
    assert "--force" not in text and "push -f" not in text


def test_bump_guards_precede_commit():
    text = read("bump.yml")
    commit = text.index("git commit")
    assert text.index("uv lock --check") < commit
    assert text.index("plugin/tests/run.sh") < commit
    assert text.index("git ls-remote") < commit
    assert text.index("scripts/bump_version.py") < commit


def test_release_dispatch_and_notes():
    text = read("release.yml")
    assert "workflow_dispatch:" in text
    assert 'tags: ["v*"]' in text
    assert "--notes-file notes.md" in text
    assert "--verify-tag" in text
    assert "--generate-notes" not in text
    assert 'bump_version.py notes "$version" > notes.md' in text
    assert not re.search(r"^\s+if:", text, re.M)


def test_release_permissions():
    text = read("release.yml")
    assert re.search(r"^permissions:\n  contents: read\n", text, re.M)
    assert re.search(r"release:\n(?:.*\n)*?    permissions:\n      contents: write\n", text)


def bump_step_block() -> str:
    blocks = [b for b in run_blocks(read("bump.yml")) if "bump_version.py" in b]
    assert len(blocks) == 1
    return blocks[0]


def test_bump_step_cannot_hide_script_exit_status():
    text = read("bump.yml")
    block = bump_step_block()
    piped = any("bump_version.py" in line and "|" in line for line in block.splitlines())
    assert not piped or "pipefail" in block or "shell: bash" in text


def test_bump_step_checks_version_format_before_export():
    block = bump_step_block()
    guard = "^[0-9]+\\.[0-9]+\\.[0-9]+$"
    assert guard in block
    assert block.index(guard) < block.index("GITHUB_ENV")


def steps(text: str) -> list[str]:
    """Split a workflow into step texts at each `      - ` list item."""
    return re.split(r"(?m)^(?=      - )", text)[1:]


def step_with(text: str, needle: str) -> str:
    found = [st for st in steps(text) if needle in st]
    assert len(found) == 1, f"{needle!r} found in {len(found)} steps"
    return found[0]


def test_bump_checkout_fetches_full_history():
    step = step_with(read("bump.yml"), "actions/checkout@v4")
    assert "fetch-depth: 0" in step


def test_bump_committer_identity():
    step = step_with(read("bump.yml"), "git commit")
    assert 'git config user.name "github-actions[bot]"' in step
    assert 'git config user.email "41898282+github-actions[bot]@users.noreply.github.com"' in step
    assert step.index("git config user.email") < step.index("git commit")


def test_bump_commit_message_and_annotated_tag():
    step = step_with(read("bump.yml"), "git commit")
    assert '"chore(release): v$VERSION"' in step
    assert 'git tag -a "v$VERSION" -m "v$VERSION"' in step
    assert step.index("git commit") < step.index("git tag -a")


def test_bump_summary_always_runs_and_names_recovery():
    step = step_with(read("bump.yml"), "GITHUB_STEP_SUMMARY")
    assert "if: always()" in step
    assert '>> "$GITHUB_STEP_SUMMARY"' in step
    assert "Run Release on tag v$VERSION" in step
    assert "Do not rerun Bump version" in step
    assert "DISPATCH_OUTCOME: ${{ steps.dispatch.outcome }}" in step


def test_release_check_requires_tag_ref_type():
    step = step_with(read("release.yml"), "Check tag matches package version")
    assert '"$GITHUB_REF_TYPE" != "tag"' in step
    assert '"$GITHUB_REF_NAME" != "v$version"' in step
    assert "${{" not in step
