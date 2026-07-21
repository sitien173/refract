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

readme = (root / "README.md").read_text()
for block in re.findall(r"```toml\n(.*?)```", readme, re.S):
    tomllib.loads(block)

json_documents = [
    json.loads(block)
    for block in re.findall(r"```json\n(.*?)```", readme, re.S)
]
guide = next(document for document in json_documents if "recommendations" in document)
assert guide["version"] == 1
assert guide["recommendations"]
assert all(item.get("use_case") and item.get("workflow") for item in guide["recommendations"])
assert all("routing_profile" not in item for item in guide["recommendations"])
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
    printf 'configured target label leaked into public workflow\n' >&2
    exit 1
fi

if grep -R -E 'task_route|routing_profile|routing-profile|routing profile|execution_role|setup_instruction|openmcp://models|openmcp://routing-profiles|\.openmcp/workflows' "${workflow_files[@]}"; then
    printf 'obsolete OpenMCP contract found\n' >&2
    exit 1
fi

if grep -R -E '`(quality|balanced|cost)`' skills; then
    printf 'profile preset hard-coded in skill\n' >&2
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
grep -q 'Do not call `task_guide` during plan authoring' skills/writing-plans/SKILL.md
grep -q 're-run `task_guide` for an active phase chain' skills/executing-plans/SKILL.md
grep -q 'OpenMCP supports exactly three workflows' skills/coordinating-multi-model-work/SKILL.md
grep -q 'Project custom workflow files are unsupported' skills/coordinating-multi-model-work/SKILL.md
grep -q 'openmcp://workflows/<project_id>' skills/coordinating-multi-model-work/SKILL.md
grep -q 'Never mutate the root while an isolated chain is active' skills/coordinating-multi-model-work/SKILL.md
grep -q 'Call `status` and require `running`' skills/coordinating-multi-model-work/SKILL.md
grep -q 'project_register' skills/coordinating-multi-model-work/SKILL.md
grep -q 'task_guide' skills/coordinating-multi-model-work/SKILL.md
grep -q 'job.result.text' skills/coordinating-multi-model-work/SKILL.md
grep -q 'job_integrate' skills/coordinating-multi-model-work/SKILL.md
grep -q 'openmcp://projects/<project_id>/jobs' skills/coordinating-multi-model-work/SKILL.md
grep -q 'openmcp://projects/<project_id>/profiles' skills/coordinating-multi-model-work/SKILL.md
grep -q 'You are Coordinator while this skill is active' skills/coordinating-multi-model-work/SKILL.md
grep -q 'Terminal jobs release their OpenMCP worktrees' skills/coordinating-multi-model-work/SKILL.md

grep -q 'workflow: implement' skills/executing-plans/implementer-prompt.md
grep -q 'job_submit' skills/executing-plans/implementer-prompt.md
grep -q 'job_wait' skills/executing-plans/implementer-prompt.md
grep -q 'timeout_s: 30' skills/executing-plans/implementer-prompt.md
grep -q 'include_stage_outputs: false' skills/executing-plans/implementer-prompt.md
grep -q '^  profile: <phase implementation profile>$' skills/executing-plans/implementer-prompt.md
grep -q 'latest successful implementation job' skills/executing-plans/implementer-prompt.md

printf 'contract tests passed\n'
