#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

bash -n hooks/superpowers-ccg-session-start.sh

python3 - <<'PY'
import json
import pathlib
import re

root = pathlib.Path.cwd()
paths = [
    root / ".claude-plugin/plugin.json",
    root / ".claude-plugin/marketplace.json",
    root / ".mcp.json",
    root / "hooks/hooks.json",
]
documents = {path: json.loads(path.read_text()) for path in paths}

plugin_version = documents[root / ".claude-plugin/plugin.json"]["version"]
market_version = documents[root / ".claude-plugin/marketplace.json"]["plugins"][0]["version"]
assert plugin_version == market_version

mcp = documents[root / ".mcp.json"]["mcpServers"]["openmcp"]
assert mcp["command"] == "uvx"
source = mcp["args"][1]
assert re.search(r"openmcp@[0-9a-f]{40}$", source)
assert "/home/" not in json.dumps(mcp)

for path in (root / "shared").glob("*.md"):
    match = re.search(r"ccg-shared-version:\s*([^\s>]+)", path.read_text())
    assert match and match.group(1) == plugin_version, path
PY

workflow_files=(README.md CLAUDE.md commands hooks shared skills)

if grep -R -E 'git reset --soft|profile="code-review"|\.agents/shared' "${workflow_files[@]}"; then
    printf 'forbidden workflow pattern found\n' >&2
    exit 1
fi

grep -q 'TASK_COMPLETE | BLOCKED | CONTINUE_SESSION' shared/erp.md
grep -q 'Use `completed` only with `TASK_COMPLETE`' shared/erp.md
grep -q '^## Implementation Response$' shared/journal-template.md
grep -q '^## Quality Review$' shared/journal-template.md
grep -q '^## Review Result$' shared/journal-template.md
grep -q '^## Final Commit$' shared/journal-template.md
grep -q 'Every executable plan' skills/writing-plans/SKILL.md
grep -q 'Workers never change repository history' skills/coordinating-multi-model-work/SKILL.md

printf 'contract tests passed\n'
