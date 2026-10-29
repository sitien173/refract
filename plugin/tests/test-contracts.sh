#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if grep -R -n -i -E 'openmcp|superpowers|ccg' \
    commands hooks shared skills .antigravity-plugin .claude-plugin .codex-plugin .mcp.json mcp_config.json hooks.json \
    ../.claude-plugin/marketplace.json; then
    printf 'legacy product name found in plugin surfaces\n' >&2
    exit 1
fi

bash -n hooks/refract-session-start.sh

python3 - <<'PY'
import json
import pathlib
import re

root = pathlib.Path.cwd()
paths = [
    root / ".agents/plugins.json",
    root / ".antigravity-plugin/plugin.json",
    root / ".claude-plugin/plugin.json",
    root.parent / ".claude-plugin/marketplace.json",
    root / ".codex-plugin/plugin.json",
    root / "package.json",
    root / ".mcp.json",
    root / "mcp_config.json",
    root / "hooks/hooks.json",
    root / "hooks.json",
]
documents = {path: json.loads(path.read_text()) for path in paths}
assert documents[root / ".agents/plugins.json"] == {
    "entries": [{"path": "..", "include_only": ["plugin"]}]
}

agy_version = documents[root / ".antigravity-plugin/plugin.json"]["version"]
plugin_version = documents[root / ".claude-plugin/plugin.json"]["version"]
market_version = documents[root.parent / ".claude-plugin/marketplace.json"]["plugins"][0]["version"]
codex_version = documents[root / ".codex-plugin/plugin.json"]["version"]
pi_version = documents[root / "package.json"]["version"]
assert agy_version == plugin_version == market_version == codex_version == pi_version

contract = (root / "skills/coordinating-multi-model-work/references/tool-contract.md").read_text()
contract_flat = " ".join(contract.split())
tool_table = contract.split("## Nine tools", 1)[1].split("## ", 1)[0]
tools = re.findall(r"^\| `([a-z_]+)` \|", tool_table, re.M)
assert tools == ["project_resolve", "task_guide", "job_submit", "job_wait", "job_list", "job_cancel", "job_retry", "job_answer", "job_report_error"]
for detail in (
    "`path`, `alias=\"\"`", "{project:{id, alias, path}}",
    "{workflows, profiles:{default, available}, guidance}",
    "{job:summary}", "{job:summary, result:{text, error, next_offset, metadata}}",
    "{active, recent, more_recent}", "{job:summary}",
    "`job_id`, `answer`",
    "`job_id`, `category`, `expected`, `observed`, `report_key`",
    "{report:{id, job_id, category, created_at}, duplicate}",
    "pending_question",
    "Summary fields are exactly `id, project_id, workflow, profile, state, context_key, attempts, created_at, updated_at`.",
    "Unknown tool arguments return `invalid_request`.",
    "At most one job per project runs at a time. Jobs within each project are admitted FIFO, bounded by the global `max_jobs` capacity; jobs in different projects may run concurrently up to that capacity.",
    "`timeout_s=3600`", "`result_offset=0`", "0..3600",
    "Capture `project.id` and `job.id` from returned envelopes.",
):
    assert detail in contract_flat, detail
approved_errors = {
    "unknown_project", "invalid_path", "alias_taken", "unknown_job",
    "unknown_profile",
    "invalid_state", "config_invalid", "daemon_stopping", "invalid_request",
    "targets_unavailable", "response_too_large", "internal_error",
}
error_section = contract.split("## Errors", 1)[1].split("## ", 1)[0]
error_codes = set(re.findall(r"^\| `([a-z_]+)` \|", error_section, re.M))
assert error_codes == approved_errors, error_codes
for detail in ("isError", "retryable", "next_action", "request ID"):
    assert detail in " ".join(error_section.split()), detail
assert "root job or project ID" in contract_flat
assert "project_register" not in contract
assert plugin_version == market_version == codex_version == "2.1.0"
repository = root.parent
server_version = re.search(r'^version = "([^"]+)"', (repository / "server/pyproject.toml").read_text(), re.M).group(1)
web_version = json.loads((repository / "server/web/package.json").read_text())["version"]
sonar_version = re.search(r"^sonar\.projectVersion=(.+)$", (repository / "sonar-project.properties").read_text(), re.M).group(1)
assert server_version == web_version == sonar_version == plugin_version, (server_version, web_version, sonar_version)
assert (repository / "README.md").read_text().startswith(f"# Refract {plugin_version}\n")
assert f"Refract {plugin_version} ·" in (repository / "server/CLI_ARGUMENTS.md").read_text()
for removed in ("depends_on", "cancelled_dependents", "invalid_dependency", "dependency_failed"):
    assert removed not in contract, removed

coordinator = (root / "skills/coordinating-multi-model-work/SKILL.md").read_text()
setup = coordinator.split("## Setup and Resume", 1)[1].split("### Plan-Artifact Tracking", 1)[0]
assert setup.index("using-git-worktrees") < setup.index("project_resolve")
assert "If unavailable, report it once" in setup
assert "planning continues" in setup and "Execute and Review stop" in setup
assert coordinator.index("After submission, do not edit the root") >= 0
assert "temporary checkpoint commit only after it passes" in coordinator
assert "`other` requires an explicit mapping" in contract

agy_description = documents[root / ".antigravity-plugin/plugin.json"]["description"]
plugin_description = documents[root / ".claude-plugin/plugin.json"]["description"]
codex_description = documents[root / ".codex-plugin/plugin.json"]["description"]
pi_description = documents[root / "package.json"]["description"]
assert agy_description == plugin_description == codex_description == pi_description

mcp = documents[root / ".mcp.json"]["mcpServers"]["refract"]
assert mcp == {
    "type": "http",
    "url": "${REFRACT_URL:-http://127.0.0.1:8765/mcp}",
}
assert "/home/" not in json.dumps(mcp)
default_port = int(re.search(
    r"^DEFAULT_PORT = (\d+)$",
    (repository / "server/src/refract/config.py").read_text(),
    re.M,
).group(1))
default_endpoint = f"http://127.0.0.1:{default_port}/mcp"
assert default_endpoint in mcp["url"]
assert documents[root / "mcp_config.json"]["mcpServers"]["refract"] == {
    "url": default_endpoint,
}
assert documents[root / "hooks.json"] == {
    "refract-session-start": {
        "SessionStart": [
            {
                "type": "command",
                "command": "./hooks/refract-session-start.sh --antigravity",
                "timeout": 10,
            }
        ]
    }
}
assert default_endpoint in contract
assert f'"{default_endpoint}"' in (root / "pi/extensions/refract.ts").read_text()
assert "dependent jobs" not in coordinator
assert "consolidation procedure" in (root / "skills/executing-plans/SKILL.md").read_text()
assert "consolidation procedure" in (root / "skills/coordinating-multi-model-work/references/review.md").read_text()

review = (root / "skills/coordinating-multi-model-work/references/review.md").read_text()
assert "job_report_error" in review
assert "recursive reporting" in review
assert "safe reconciliation" in review

for diag_detail in (
    "Database.prune_history",
    "client observations",
    "complete terminal pagination",
    "Generic worker error text",
):
    assert diag_detail in contract, diag_detail

readme = (repository / "server/README.md").read_text()
assert "Nine self-describing MCP tools" in readme
assert "job_report_error" in readme
assert "### Diagnostic Reporting" in readme
assert "correlation metadata" in readme
assert "2048 characters" in readme
assert "invalid_request" in readme

for path in (root / "shared").glob("*.md"):
    match = re.search(r"refract-shared-version:\s*([^\s>]+)", path.read_text())
    assert match and match.group(1) == plugin_version, path
PY

workflow_files=(commands hooks shared skills)
public_workflow_files=(commands hooks shared skills)

if grep -R -E --exclude-dir=using-git-worktrees 'git reset --soft|git worktree|isolated worktree|execution worktree|job_integrate|parent_job_id|include_stage_outputs|from_stage|integration_base|integration_conflict|\.openmcp\.local\.toml|profile="code-review"|\.agents/shared|SESSION_ID|mcp__plugin_superpowers-ccg_openmcp__run|\bConductor\b|\bconductor\b' "${workflow_files[@]}"; then
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
    printf 'obsolete Refract contract found\n' >&2
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
grep -q '^## Final Checkpoint$' shared/journal-template.md

for skill in skills/*/SKILL.md; do
    if [[ "$skill" != "skills/using-refract/SKILL.md" ]]; then
        grep -qi 'owns' "$skill"
    fi
    if [[ "$skill" != "skills/coordinating-multi-model-work/SKILL.md" && "$skill" != "skills/using-git-worktrees/SKILL.md" ]]; then
        test "$(wc -l < "$skill")" -le 90
    fi
done
test "$(wc -l < skills/coordinating-multi-model-work/SKILL.md)" -le 265
test "$(wc -l < skills/using-git-worktrees/SKILL.md)" -le 180
test "$(wc -l < skills/coordinating-multi-model-work/references/tool-contract.md)" -le 90
test "$(wc -l < skills/coordinating-multi-model-work/references/review.md)" -le 100
test "$(wc -l < skills/executing-plans/implementer-prompt.md)" -le 100

if grep -R -E 'project_resolve|task_guide|job_submit|job_wait|job_list|job_cancel|job_retry|job_answer|project_register|openmcp://' \
    skills/brainstorming skills/systematic-debugging \
    skills/test-driven-development skills/verifying-before-completion; then
    printf 'Refract mechanics leaked into a policy skill\n' >&2
    exit 1
fi

grep -q 'Every executable plan' skills/writing-plans/SKILL.md
grep -q "Coordinator's plan \`base\` anchor" skills/writing-plans/SKILL.md
grep -q 'Do not hard-code a default profile' skills/writing-plans/SKILL.md
grep -q 'Do not call `task_guide`, register a project, or submit jobs' skills/writing-plans/SKILL.md
grep -q 'one Conventional Commit message for the completed plan' skills/writing-plans/SKILL.md
grep -q 'sole branch commit replaces local phase checkpoints' skills/writing-plans/SKILL.md
grep -q 'Do not re-run `task_guide` for an' skills/executing-plans/SKILL.md

grep -q 'owns routing, admission' skills/coordinating-multi-model-work/SKILL.md
grep -q 'Canonical gates use' skills/coordinating-multi-model-work/SKILL.md
grep -q 'sequential jobs one at a time' skills/coordinating-multi-model-work/SKILL.md
grep -q 'Profiles may be' skills/coordinating-multi-model-work/references/tool-contract.md
grep -q 'task_guide' skills/coordinating-multi-model-work/references/tool-contract.md
if grep -R -E '^[[:space:]]*capabilities[[:space:]]*=' \
    commands hooks shared skills; then
    printf 'Removed Refract target capabilities remain documented\n' >&2
    exit 1
fi
grep -q 'project_resolve' skills/coordinating-multi-model-work/SKILL.md
grep -q 'job_list(project_id)' skills/coordinating-multi-model-work/SKILL.md
grep -q 'task_guide(project_id)' skills/coordinating-multi-model-work/SKILL.md
grep -q '3600-second heartbeat' skills/coordinating-multi-model-work/references/tool-contract.md
grep -q 'You own the entire Git lifecycle' skills/coordinating-multi-model-work/SKILL.md
grep -q 'You are Coordinator' skills/coordinating-multi-model-work/SKILL.md
grep -q 'At most one job per project runs at a time' skills/coordinating-multi-model-work/references/tool-contract.md

grep -q 'more_recent' skills/coordinating-multi-model-work/references/tool-contract.md
if grep -q -E 'depends_on|cancelled_dependents|invalid_dependency|dependency_failed' skills/coordinating-multi-model-work/references/tool-contract.md; then
    printf 'removed job dependency surface remains in tool contract\n' >&2
    exit 1
fi
grep -q 'result_offset' skills/coordinating-multi-model-work/references/tool-contract.md
grep -q '`other` requires an explicit mapping' skills/coordinating-multi-model-work/references/tool-contract.md
# Preserve source-freeze and temporary-checkpoint policy guards.
grep -q 'After submission, do not edit the root until that job is terminal.' skills/coordinating-multi-model-work/SKILL.md
grep -q 'Create a temporary checkpoint commit only after it passes.' skills/coordinating-multi-model-work/SKILL.md
grep -qF 'result.metadata.failure.kind' skills/coordinating-multi-model-work/SKILL.md
grep -qF 'result.metadata.retry.retryable' skills/coordinating-multi-model-work/SKILL.md
grep -qF 'result.metadata.retry.next_target' skills/coordinating-multi-model-work/SKILL.md
grep -qF 'result.metadata.retry.next_target' skills/coordinating-multi-model-work/references/tool-contract.md
if grep -qF '`result.metadata.telemetry.context_used_tokens` exceeds' skills/coordinating-multi-model-work/references/tool-contract.md; then
    printf 'context_used_tokens object compared directly to threshold\n' >&2
    exit 1
fi
grep -qF 'result.metadata.telemetry.context_used_tokens.value' skills/coordinating-multi-model-work/references/tool-contract.md
grep -q 'Always start every phase with `fresh_session=true`' skills/coordinating-multi-model-work/references/tool-contract.md
grep -qF 'For follow-up jobs within the same phase' skills/coordinating-multi-model-work/references/tool-contract.md
if grep -q -E 'result\.metadata\.failure_kind|result\.metadata\.context_window_used' skills/coordinating-multi-model-work/SKILL.md skills/coordinating-multi-model-work/references/tool-contract.md; then
    printf 'removed legacy metadata field found in coordinator guidance\n' >&2
    exit 1
fi

anchors=skills/coordinating-multi-model-work/references/git-anchors.md
grep -qF 'refs/plans/<slug>/base' "$anchors"
grep -qF 'refs/plans/<slug>/impl' "$anchors"
grep -qF 'refs/plans/<slug>/phase-<NN>/base' "$anchors"
grep -qF 'refs/plans/<slug>/phase-<NN>/impl' "$anchors"
grep -q 'Create one replacement commit from the final checkpoint tree' "$anchors"
grep -q 'Atomically move the attached branch' "$anchors"
grep -q 'sole plan commit' "$anchors"
grep -qF 'git cat-file -e <sha>^{commit}' "$anchors"
grep -qF 'git merge-base --is-ancestor <sha> HEAD' "$anchors"
grep -q 'STALE_ANCHOR' "$anchors"
grep -q 'STALE_ANCHOR' skills/coordinating-multi-model-work/SKILL.md
grep -qF 'refract.plans.tracking' skills/coordinating-multi-model-work/SKILL.md
grep -q 'git ls-files docs/plans' skills/coordinating-multi-model-work/SKILL.md
grep -q 'git check-ignore -q docs/plans' skills/coordinating-multi-model-work/SKILL.md
test "$(wc -l < "$anchors")" -le 120

if grep -R -F 'phase_base..HEAD' "${workflow_files[@]}"; then
    printf 'unconditional phase_base review range reintroduced\n' >&2
    exit 1
fi

printf 'contract tests passed\n'
