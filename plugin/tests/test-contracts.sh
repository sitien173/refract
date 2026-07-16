#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

bash -n hooks/superpowers-ccg-session-start.sh

python3 - <<'PY'
import json
import pathlib
import re
import tomllib

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
assert mcp == {
    "type": "http",
    "url": "http://127.0.0.1:8765/mcp",
}
assert "/home/" not in json.dumps(mcp)

for path in (root / "shared").glob("*.md"):
    match = re.search(r"ccg-shared-version:\s*([^\s>]+)", path.read_text())
    assert match and match.group(1) == plugin_version, path

toml_blocks = re.findall(r"```toml\n(.*?)```", (root / "README.md").read_text(), re.S)
assert toml_blocks
for block in toml_blocks:
    tomllib.loads(block)

json_blocks = re.findall(r"```json\n(.*?)```", (root / "README.md").read_text(), re.S)
assert json_blocks
json_documents = [json.loads(block) for block in json_blocks]
route_template = next(document for document in json_documents if "routes" in document)
delegated_routes = [route for route in route_template["routes"] if route["role"] != "coordinator"]
assert delegated_routes
assert all(route.get("execution_role") for route in delegated_routes)
PY

workflow_files=(README.md CLAUDE.md commands hooks shared skills)
public_workflow_files=(CLAUDE.md commands hooks shared skills)

if grep -R -E 'git reset --soft|git worktree list --porcelain|inside its isolated worktree|profile="code-review"|\.agents/shared|SESSION_ID|mcp__plugin_superpowers-ccg_openmcp__run|\bConductor\b|\bconductor\b' "${workflow_files[@]}"; then
    printf 'forbidden workflow pattern found\n' >&2
    exit 1
fi

if grep -R -E '\bcodex\b|\bagy\b|backend-write|frontend-write|review-read|backend-read|frontend-read|Cross-Validation' "${public_workflow_files[@]}"; then
    printf 'provider identity leaked into public workflow\n' >&2
    exit 1
fi

if grep -R -E '\b(Forge|Canvas|Sage|Sentinel)\b|forge-write|canvas-write|sage-read|sentinel-read' "${public_workflow_files[@]}"; then
    printf 'configured agent nickname hard-coded in public workflow\n' >&2
    exit 1
fi

if grep -R -E '`(quality|balanced|cost)`' skills; then
    printf 'routing profile preset hard-coded in skill\n' >&2
    exit 1
fi

grep -q 'TASK_COMPLETE | BLOCKED | CONTINUE_CONTEXT' shared/erp.md
grep -q 'Use `completed` only with `TASK_COMPLETE`' shared/erp.md
grep -q '^## Implementation Response$' shared/journal-template.md
grep -q '^## Quality Review$' shared/journal-template.md
grep -q '^## Review Result$' shared/journal-template.md
grep -q '^## Final Commit$' shared/journal-template.md
grep -q 'Every executable plan' skills/writing-plans/SKILL.md
grep -q 'Resolve at execution' skills/writing-plans/SKILL.md
grep -q 'Do not call `task_route` during plan authoring' skills/writing-plans/SKILL.md
grep -q 'Validate user-pinned nicknames' skills/executing-plans/SKILL.md
grep -q 'Otherwise select the returned default' skills/executing-plans/SKILL.md
grep -q 'execution_role' skills/coordinating-multi-model-work/SKILL.md
grep -q 'openmcp://workflows/<project_id>' skills/coordinating-multi-model-work/SKILL.md
grep -q 'Do not reroute an existing phase chain' skills/coordinating-multi-model-work/SKILL.md
grep -q 'Existing phase chains keep stored routing decisions' skills/executing-plans/SKILL.md
grep -q '<owner_execution_role>-write' skills/executing-plans/implementer-prompt.md
grep -q 'Never mutate the root during isolated chains' skills/coordinating-multi-model-work/SKILL.md
grep -q 'project_init' skills/executing-plans/implementer-prompt.md
grep -q 'project_register' skills/executing-plans/implementer-prompt.md
grep -q 'task_route' skills/coordinating-multi-model-work/SKILL.md
grep -q 'job_submit' skills/executing-plans/implementer-prompt.md
grep -q 'job_wait' skills/executing-plans/implementer-prompt.md
grep -q 'include_stage_outputs: false' skills/executing-plans/implementer-prompt.md
grep -q 'job.result.text' skills/coordinating-multi-model-work/SKILL.md
grep -q 'job_integrate' skills/executing-plans/SKILL.md
grep -q 'parent_job_id' skills/executing-plans/implementer-prompt.md
grep -q 'openmcp://projects/<project_id>/jobs' skills/coordinating-multi-model-work/SKILL.md
grep -q 'openmcp://routing-profiles' skills/coordinating-multi-model-work/SKILL.md
grep -q 'openmcp://projects/<project_id>/routing-profiles' skills/coordinating-multi-model-work/SKILL.md
grep -q 'routing_profile' skills/executing-plans/implementer-prompt.md
grep -q 'You are Coordinator while this skill is active' skills/coordinating-multi-model-work/SKILL.md
grep -q 'Terminal jobs release their OpenMCP worktrees' skills/coordinating-multi-model-work/SKILL.md

printf 'contract tests passed\n'
