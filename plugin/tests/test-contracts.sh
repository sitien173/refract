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
assert mcp == {
    "type": "http",
    "url": "http://127.0.0.1:8765/mcp",
}
assert "/home/" not in json.dumps(mcp)

for path in (root / "shared").glob("*.md"):
    match = re.search(r"ccg-shared-version:\s*([^\s>]+)", path.read_text())
    assert match and match.group(1) == plugin_version, path
PY

workflow_files=(commands hooks shared skills)
public_workflow_files=(commands hooks shared skills)

if grep -R -E 'git reset --soft|git worktree|isolated worktree|execution worktree|job_integrate|parent_job_id|include_stage_outputs|from_stage|integration_base|integration_conflict|\.openmcp\.local\.toml|profile="code-review"|\.agents/shared|SESSION_ID|mcp__plugin_superpowers-ccg_openmcp__run|\bConductor\b|\bconductor\b' "${workflow_files[@]}"; then
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

if grep -R -E 'commit_message|base_commit|result_commit|result\.commit|head_commit|workflow\.writes|\.writes|project\.clean' "${workflow_files[@]}"; then
    printf 'stale Git-lifecycle field found\n' >&2
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

for status in inbox ready in-plan done declined; do
    grep -q "\`${status}\`" shared/backlog-contract.md
done
grep -q '<!-- next id: B-001 -->' shared/backlog-contract.md
grep -q 'in the same edit that appends the row' shared/backlog-contract.md
grep -q 'No column alignment' shared/backlog-contract.md
grep -q 'only when no project job is active' shared/backlog-contract.md
grep -q 'docs/plans/BACKLOG.md' shared/backlog-contract.md
grep -q 'shared/backlog-contract.md' hooks/superpowers-ccg-session-start.sh
grep -q 'shared/backlog-contract.md' commands/backlog.md
for verb in 'add <text>' 'triage'; do
    grep -q "${verb}" commands/backlog.md
done

for skill in skills/*/SKILL.md; do
    grep -qi 'owns' "$skill"
    if [[ "$skill" != "skills/coordinating-multi-model-work/SKILL.md" ]]; then
        test "$(wc -l < "$skill")" -le 90
    fi
done
test "$(wc -l < skills/coordinating-multi-model-work/SKILL.md)" -le 265
test "$(wc -l < skills/coordinating-multi-model-work/references/tool-contract.md)" -le 90
test "$(wc -l < skills/executing-plans/implementer-prompt.md)" -le 100

if grep -R -E 'job_submit|job_wait|job_retry|job_cancel|project_register|openmcp://' \
    skills/brainstorming skills/systematic-debugging \
    skills/test-driven-development skills/verifying-before-completion; then
    printf 'OpenMCP mechanics leaked into a policy skill\n' >&2
    exit 1
fi

grep -q 'Every executable plan' skills/writing-plans/SKILL.md
grep -q 'Do not hard-code a default profile' skills/writing-plans/SKILL.md
grep -q 'Do not call `task_guide`, register a project, or submit jobs' skills/writing-plans/SKILL.md
grep -q 'Do not re-run `task_guide` for an' skills/executing-plans/SKILL.md

grep -q 'OpenMCP provides four fixed workflows' skills/coordinating-multi-model-work/SKILL.md
grep -q '`consult`, `implement`, `other`, and' skills/coordinating-multi-model-work/SKILL.md
grep -q '^`review`\. Canonical gates' skills/coordinating-multi-model-work/SKILL.md
grep -q 'Profiles may be partial' skills/coordinating-multi-model-work/references/tool-contract.md
grep -q '`other` requires an explicit mapping' skills/coordinating-multi-model-work/references/tool-contract.md
if grep -R -E '^[[:space:]]*capabilities[[:space:]]*=' \
    commands hooks shared skills; then
    printf 'Removed OpenMCP target capabilities remain documented\n' >&2
    exit 1
fi
grep -q 'openmcp://workflows/<project_id>' skills/coordinating-multi-model-work/SKILL.md
grep -q 'After submission, do not edit the root' skills/coordinating-multi-model-work/SKILL.md
grep -q 'Call `status`; require' skills/coordinating-multi-model-work/SKILL.md
grep -q 'project_register' skills/coordinating-multi-model-work/SKILL.md
grep -q 'task_guide' skills/coordinating-multi-model-work/SKILL.md
grep -q 'result.text' skills/coordinating-multi-model-work/SKILL.md
grep -q 'commit the reconciled diff' skills/coordinating-multi-model-work/SKILL.md
grep -q 'You own the entire Git lifecycle' skills/coordinating-multi-model-work/SKILL.md
grep -q 'openmcp://projects/<project_id>/jobs' skills/coordinating-multi-model-work/SKILL.md
grep -q 'openmcp://projects/<project_id>/profiles' skills/coordinating-multi-model-work/SKILL.md
grep -q 'You are Coordinator' skills/coordinating-multi-model-work/SKILL.md
grep -q 'Same-project jobs run FIFO' skills/coordinating-multi-model-work/SKILL.md

grep -q 'workflow: implement' skills/executing-plans/implementer-prompt.md
grep -q 'job_submit' skills/executing-plans/implementer-prompt.md
grep -q '^  prompt: |$' skills/executing-plans/implementer-prompt.md
grep -q 'A review fix is a resumed `implement` job' skills/executing-plans/implementer-prompt.md
grep -q '^  profile: <phase implementation profile>$' skills/executing-plans/implementer-prompt.md

printf 'contract tests passed\n'
