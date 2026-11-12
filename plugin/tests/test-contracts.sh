#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if grep -R -n -i -E 'openmcp|superpowers|ccg' \
    commands hooks shared skills .antigravity-plugin plugin.json .claude-plugin .codex-plugin .mcp.json mcp_config.json hooks.json \
    ../.claude-plugin/marketplace.json ../.agents/plugins/marketplace.json; then
    printf 'legacy product name found in plugin surfaces\n' >&2
    exit 1
fi

rc=0; git -c core.excludesFile=/dev/null check-ignore -q --no-index ../.agents/plugins/marketplace.json || rc=$?
[[ "$rc" -eq 1 ]] || { printf 'codex marketplace manifest is git-ignored or not in a git tree\n' >&2; exit 1; }

# Nested `.agents` directories stay ignored.
rc=0; git -c core.excludesFile=/dev/null check-ignore -q ../server/.agents/x || rc=$?
[[ "$rc" -eq 0 ]] || { printf 'nested .agents directory is not git-ignored\n' >&2; exit 1; }

python3 -c "import ast, sys; ast.parse(open(sys.argv[1]).read())" hooks/refract-session-start.py

python3 - <<'PY'
import json
import pathlib
import re

root = pathlib.Path.cwd()
paths = [
    root / ".agents/plugins.json",
    root / ".antigravity-plugin/plugin.json",
    root / "plugin.json",
    root / ".claude-plugin/plugin.json",
    root.parent / ".claude-plugin/marketplace.json",
    root / ".codex-plugin/plugin.json",
    root / "package.json",
    root.parent / "package.json",
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
pi_root_version = documents[root.parent / "package.json"]["version"]
codex_market_path = root.parent / ".agents/plugins/marketplace.json"
assert codex_market_path.is_file(), codex_market_path
codex_market = json.loads(codex_market_path.read_text())
assert codex_market["name"] == "refract"
assert codex_market["plugins"][0]["name"] == "refract"
codex_source = codex_market["plugins"][0]["source"]
assert isinstance(codex_source, dict) and codex_source["path"] == "./plugin"
assert (root.parent / codex_source["path"] / ".codex-plugin/plugin.json").is_file()

assert agy_version == plugin_version == market_version == codex_version == pi_version == pi_root_version

# The repository-root manifest lets `pi install` load the plugin from a git clone.
pi_manifest = documents[root / "package.json"]
pi_root_manifest = documents[root.parent / "package.json"]
assert pi_root_manifest["private"] is True
assert pi_root_manifest["peerDependencies"] == pi_manifest["peerDependencies"]
for kind, paths in pi_manifest["pi"].items():
    assert pi_root_manifest["pi"][kind] == [f"./plugin/{path.removeprefix('./')}" for path in paths], kind
    for path in pi_root_manifest["pi"][kind]:
        assert (root.parent / path).is_dir(), path

contract = (root / "skills/coordinating-multi-model-work/references/tool-contract.md").read_text()
contract_flat = " ".join(contract.split())
tool_table = contract.split("## Nine tools", 1)[1].split("## ", 1)[0]
tool_rows = re.findall(r"^\| `([a-z_]+)` \| (.*?) \| (.*?) \|$", tool_table, re.M)
assert [row[0] for row in tool_rows] == [
    "submit", "wait", "answer", "cancel", "retry", "list",
    "card_create", "card_move", "card_list",
], tool_rows
assert [row[1:] for row in tool_rows] == [
    ("`path`, `workflow`, `prompt`, `profile=\"\"`, `session=\"\"`, `fresh=false`", "`{job}`"),
    ("`job_id`, `timeout_s=3600`", "`{job, result}`"),
    ("`job_id`, `answer`", "`{job}`"),
    ("`job_id`", "`{job}`"),
    ("`job_id`, `target=\"\"`", "`{job}` for a new job with `retry_of` set"),
    ("`path`", "`{active, recent, workflows, profiles, guidance}`"),
    ("`path`, `title`, `body=\"\"`, `job_ids=()`", "`{card}`"),
    ("`card_id`, `state`, `job_ids=()`, `note=\"\"`", "`{card, moved}`"),
    ("`path`", "`{cards, truncated, omitted}`"),
], tool_rows
for detail in (
    "Call only these tools with only these parameters",
    "`job`: `id, project, workflow, profile, target, session, state, retry_of, created_at, updated_at`.",
    "`result`: `text, truncated, result_path, pending_question, failure_kind, next_target, model, duration_ms, tokens`.",
    "`tokens`: `context_used, context_window, input, output, cache_read, cache_write`, each an integer or null.",
    "Unknown tool arguments return `invalid_request`.",
    "`path` is any directory inside the project; Refract resolves its Git root. A path outside Git returns `invalid_path`.",
    "Jobs are admitted FIFO up to the global `max_jobs` capacity, and jobs in the same project may run concurrently. Concurrent jobs share the project checkout and can edit the same files. Jobs that share a project, `session`, workflow, and target run one at a time.",
    "`timeout_s` accepts 0..3600.",
    "`result.pending_question` (`{question_id, text}`)",
    "`answer` without a pending question, after the question expired, or on a terminal job returns `invalid_state`.",
    "Every terminal job writes its full text to `result.result_path`. When `result.truncated` is true, read the full text from that file.",
    "`failure_kind` is null on success, else one of `cancelled`, `circuit_open`, `replay_blocked`, `context_overflow`, `request_fatal`, `target_fatal`, `transient`.",
    "The new job from `retry` keeps the source job's `session` and `fresh` values.",
    "Responses stay below 30,000 characters and 9,000 UTF-8 bytes.",
    "Capture `job.id` from returned envelopes.",
):
    assert detail in contract_flat, detail
for removed in (
    "project_" "resolve", "task_" "guide", "job_" "list", "job_" "report_error",
    "result_" "offset", "next_" "offset", "fresh_" "session", "context_" "key",
    "retry" "able", "project_" "id", "job_" "submit", "job_" "wait", "job_" "answer",
    "job_" "cancel", "job_" "retry", "project_" "register",
):
    assert removed not in contract_flat, removed
approved_errors = {
    "invalid_path", "unknown_job", "unknown_profile", "invalid_state", "config_invalid",
    "daemon_stopping", "invalid_request", "targets_unavailable", "response_too_large", "internal_error",
    "unknown_card",
}
error_section = contract.split("## Errors", 1)[1].split("## ", 1)[0]
error_codes = set(re.findall(r"^\| `([a-z_]+)` \|", error_section, re.M))
assert error_codes == approved_errors, error_codes
for detail in ("isError", "next_action", "request ID", "retry_after_s"):
    assert detail in " ".join(error_section.split()), detail
assert "Honor the applied outcome and job ID" in contract_flat
assert "Never blindly resubmit." in contract_flat
repository = root.parent
server_version = re.search(r'^version = "([^"]+)"', (repository / "server/pyproject.toml").read_text(), re.M).group(1)
sonar_version = re.search(r"^sonar\.projectVersion=(.+)$", (repository / "sonar-project.properties").read_text(), re.M).group(1)
assert server_version == sonar_version == plugin_version, (server_version, sonar_version)
assert (repository / "README.md").read_text().startswith(f"# Refract {plugin_version}\n")
assert f"Refract {plugin_version} ·" in (repository / "server/CLI_ARGUMENTS.md").read_text()
for removed in ("depends_on", "cancelled_dependents", "invalid_dependency", "dependency_failed"):
    assert removed not in contract, removed

coordinator = (root / "skills/coordinating-multi-model-work/SKILL.md").read_text()
setup = coordinator.split("## Setup and Resume", 1)[1].split("### Plan-Artifact Tracking", 1)[0]
assert setup.index("using-git-worktrees") < setup.index("list(path)")
assert "If unavailable, report it once" in setup
assert "planning continues" in setup and "Execute and Review stop" in setup
assert coordinator.index("After submission, do not edit the root") >= 0
assert "temporary checkpoint commit only after it passes" in coordinator
assert "`other` requires an explicit mapping" in contract

agy_description = documents[root / ".antigravity-plugin/plugin.json"]["description"]
plugin_description = documents[root / ".claude-plugin/plugin.json"]["description"]
codex_description = documents[root / ".codex-plugin/plugin.json"]["description"]
pi_description = documents[root / "package.json"]["description"]
pi_root_description = documents[root.parent / "package.json"]["description"]
assert agy_description == plugin_description == codex_description == pi_description == pi_root_description

agy_manifest = documents[root / ".antigravity-plugin/plugin.json"]
# The standalone Antigravity IDE reads only the root plugin.json.
assert documents[root / "plugin.json"] == agy_manifest, "plugin.json must match .antigravity-plugin/plugin.json"
assert agy_manifest.get("displayName"), "antigravity manifest needs a non-empty displayName"
assert (root / agy_manifest.get("logo", "missing-logo")).is_file(), "antigravity manifest logo must name an existing file"
logo = agy_manifest["logo"]
assert not pathlib.Path(logo).is_absolute(), "antigravity manifest logo must be a relative path"
assert (root / logo).resolve().is_relative_to(root.resolve()), "antigravity manifest logo must stay inside the plugin root"

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
                "command": "python3 ./hooks/refract-session-start.py --antigravity",
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
assert "partial local effects" in review
assert "retry(job_id, target=X)" in review
assert "tool-contract.md#recovery" in review

readme = (repository / "server/README.md").read_text()
assert "Nine self-describing MCP tools" in readme
assert "### Recovery and Routing" in readme
assert "### Diagnostic Reporting" not in readme
assert "`result.result_path`" in readme
assert "invalid_request" in readme

for path in (root / "shared").glob("*.md"):
    match = re.search(r"refract-shared-version:\s*([^\s>]+)", path.read_text())
    assert match and match.group(1) == plugin_version, path
PY

workflow_files=(commands hooks shared skills)
public_workflow_files=(commands hooks shared skills)

if grep -R -E --exclude-dir=using-git-worktrees 'git reset --soft|isolated worktree|execution worktree|job_integrate|parent_job_id|include_stage_outputs|from_stage|integration_base|integration_conflict|\.openmcp\.local\.toml|profile="code-review"|\.agents/shared|SESSION_ID|mcp__plugin_superpowers-ccg_openmcp__run|\bConductor\b|\bconductor\b' "${workflow_files[@]}"; then
    printf 'forbidden workflow pattern found\n' >&2
    exit 1
fi
# Only the wave procedure may name `git worktree` outside using-git-worktrees.
waves=skills/coordinating-multi-model-work/references/waves.md
if grep -R -E --exclude-dir=using-git-worktrees 'git worktree' "${workflow_files[@]}" | grep -v -F "${waves}:"; then
    printf 'forbidden workflow pattern found\n' >&2
    exit 1
fi

python3 - "$waves" <<'PY'
import pathlib
import sys

waves = " ".join(pathlib.Path(sys.argv[1]).read_text().split())
for rule in (
    "A single-phase wave runs exactly as today in the main checkout without a worktree.",
    "run the whole wave sequentially in the main checkout. Never share one checkout between wave jobs.",
    "call `wait` round-robin in plan order with `timeout_s=60`.",
    "`git merge --ff-only refract/<slug>/phase-<NN>`",
    "run phase validation plus the plan's baseline commands there.",
    "On a rebase conflict or a step 6.1 check failure, abort the rebase, remove the worktree and branch, and set the state `requeued`.",
    "Never review inside a phase worktree.",
    "Write `phase-<NN>/impl` once.",
):
    assert rule in waves, rule
PY
coordinator_skill=skills/coordinating-multi-model-work/SKILL.md
test "$(grep -c 'Submit sequential jobs one at a time.' "$coordinator_skill")" -eq 1
grep -qF 'Wave implementation jobs in separate worktrees are the sole exception' "$coordinator_skill"
grep -qF '(references/waves.md)' "$coordinator_skill"
grep -qF 'During a wave, you may still edit main-checkout `.handover.md`' "$coordinator_skill"
grep -qF 'waves.md#waiting' skills/coordinating-multi-model-work/references/tool-contract.md
grep -qF 'excludes main-checkout `.handover.md`' skills/coordinating-multi-model-work/references/review.md
grep -qF 'Before the phase lands on the plan branch' skills/coordinating-multi-model-work/references/git-anchors.md

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

v2_tools='project_''resolve|task_''guide|job_''submit|job_''wait|job_''list|job_''cancel|job_''retry|job_''answer|job_''report_error|project_''register|openmcp://'
if grep -R -E "$v2_tools" \
    skills/brainstorming skills/systematic-debugging \
    skills/test-driven-development skills/verifying-before-completion; then
    printf 'Refract mechanics leaked into a policy skill\n' >&2
    exit 1
fi

grep -q 'Every executable plan' skills/writing-plans/SKILL.md
grep -q "Coordinator's plan \`base\` anchor" skills/writing-plans/SKILL.md
grep -q 'Do not hard-code a default profile' skills/writing-plans/SKILL.md
grep -q 'Do not call `list` or `submit` while authoring.' skills/writing-plans/SKILL.md
grep -q 'one Conventional Commit message for the completed plan' skills/writing-plans/SKILL.md
grep -q 'sole branch commit replaces local phase checkpoints' skills/writing-plans/SKILL.md
grep -A1 -F '**Goal:** <one outcome>' skills/writing-plans/SKILL.md | grep -qF '**Depends on:** <Phase N, Phase M | none>'
grep -qF 'A missing `Depends on:` line means the phase depends on the previous phase.' skills/writing-plans/SKILL.md
grep -qF 'only when their `Files:` lists are disjoint' skills/writing-plans/SKILL.md
grep -qF 'neither needs an API, schema, or fixture the other creates' skills/writing-plans/SKILL.md
grep -qF 'lockfiles or `CHANGELOG.md` force a dependency' skills/writing-plans/SKILL.md
grep -qF 'Reject cycles and unknown phase numbers.' skills/writing-plans/SKILL.md

handover=skills/coordinating-multi-model-work/references/handover.md
grep -qF 'wave_base: <commit|null>' "$handover"
grep -qF 'wave: [{ phase, state: implementing|implemented|integrating|integrated|requeued, worktree, branch, implementation_job }, ...]' "$handover"
grep -qF '`wave_base: null`, `wave: []`' "$handover"
grep -qF 'A missing `wave_base` or `wave` key reads as `null` or `[]`.' "$handover"
grep -qF 'Set `implementation_job` immediately after `submit` returns' "$handover"
grep -qF '`current_phase` and `job_refs` describe the phase running gates on the main' "$handover"
grep -qF 'Keep at most one step `doing` per phase.' "$handover"

python3 - "$handover" <<'PY'
import pathlib
import sys

handover = pathlib.Path(sys.argv[1]).read_text()
root = pathlib.Path.cwd()
executing = (root / "skills/executing-plans/SKILL.md").read_text()
autonomous = (root / "skills/executing-plans-autonomously/SKILL.md").read_text()
coordinator = (root / "skills/coordinating-multi-model-work/SKILL.md").read_text()
writing = (root / "skills/writing-plans/SKILL.md").read_text()

assert "board.md" in executing, "skills/executing-plans/SKILL.md missing board.md"
assert "board.md" in autonomous, "skills/executing-plans-autonomously/SKILL.md missing board.md"
assert "board.md" in coordinator, "skills/coordinating-multi-model-work/SKILL.md missing board.md"
assert "card_refs: [{ phase, card_id }, ...]" in handover, "handover missing card_refs schema"
assert "card_refs: []" in handover, "handover missing card_refs initial value"
assert "A missing `card_refs` key reads as `[]`." in handover, "handover missing card_refs rule"
assert "card_refs: []" in writing, "skills/writing-plans/SKILL.md missing card_refs: []"
PY
grep -q 'Do not call `list` for guidance during an active phase' skills/executing-plans/SKILL.md
for skill in skills/executing-plans/SKILL.md skills/executing-plans-autonomously/SKILL.md; do
    grep -qF '(../coordinating-multi-model-work/references/waves.md)' "$skill"
    grep -qF 'single-phase wave runs' "$skill"
done
grep -qF 'Execute folder-layout plans only, one wave per invocation.' skills/executing-plans/SKILL.md
if grep -qF 'one phase per invocation' skills/executing-plans/SKILL.md; then
    printf 'executing-plans still runs one phase per invocation\n' >&2
    exit 1
fi
grep -qF 'emits one phase report per phase' skills/executing-plans/SKILL.md
grep -qF 'sets `BLOCKED` for a failed wave phase after the other phases integrate' skills/executing-plans/SKILL.md
grep -qF 'Loop waves until every phase has its `impl` ref' skills/executing-plans-autonomously/SKILL.md
grep -qF 'set it `requeued` and log the decision to `.handover.md` instead of blocking' skills/executing-plans-autonomously/SKILL.md
implementer=skills/executing-plans/implementer-prompt.md
grep -qF 'Outside a wave, `<code-root>` and `<records-root>` are both `<repo-root>`.' "$implementer"
grep -qF 'submit(path="<code-root>"' "$implementer"
grep -qF 'Read and execute `<records-root>/docs/plans/<slug>/phase-<NN>/prompt.md`' "$implementer"
grep -qF '`<records-root>/docs/plans/<slug>/phase-<NN>/journal.md`' "$implementer"
grep -qF 'Edit code only in `<code-root>`' "$implementer"
grep -qF 'Write phase records only under `<records-root>`.' shared/worker-contract.md
grep -qF 'cannot write under `<records-root>`, return `BLOCKED`' shared/worker-contract.md
grep -qF 'repository-relative paths from both `<code-root>` and `<records-root>`' shared/erp.md
worktrees_skill=skills/using-git-worktrees/SKILL.md
grep -qF '## Wave Mode' "$worktrees_skill"
grep -qF 'refract/<slug>/phase-<NN>' "$worktrees_skill"
grep -qF 'Never fall back to the current directory in wave mode.' "$worktrees_skill"
grep -qF 'Create at most one worktree per request, except in wave mode.' "$worktrees_skill"
grep -qF 'one wave' commands/execute-plan.md
grep -qF 'all waves' commands/execute-plan-all.md

grep -q 'owns routing, admission' skills/coordinating-multi-model-work/SKILL.md
grep -q 'Canonical gates use' skills/coordinating-multi-model-work/SKILL.md
grep -q 'sequential jobs one at a time' skills/coordinating-multi-model-work/SKILL.md
grep -q 'Profiles may be' skills/coordinating-multi-model-work/references/tool-contract.md
grep -q '`list` takes no phase argument' skills/coordinating-multi-model-work/references/tool-contract.md
if grep -R -E '^[[:space:]]*capabilities[[:space:]]*=' \
    commands hooks shared skills; then
    printf 'Removed Refract target capabilities remain documented\n' >&2
    exit 1
fi
grep -qF 'Pass the actual Git root, or any directory inside it, as `path` to' skills/coordinating-multi-model-work/SKILL.md
grep -qF 'Reconcile with `list(path)`' skills/coordinating-multi-model-work/SKILL.md
grep -qF 'Call `list(path)` once per phase.' skills/coordinating-multi-model-work/SKILL.md
grep -q '3600-second default' skills/coordinating-multi-model-work/references/tool-contract.md
grep -q 'You own the entire Git lifecycle' skills/coordinating-multi-model-work/SKILL.md
grep -q 'You are Coordinator' skills/coordinating-multi-model-work/SKILL.md
grep -q 'jobs in the same project may run concurrently' skills/coordinating-multi-model-work/references/tool-contract.md

grep -q 'the newest terminal jobs' skills/coordinating-multi-model-work/references/tool-contract.md
if grep -q -E 'depends_on|cancelled_dependents|invalid_dependency|dependency_failed' skills/coordinating-multi-model-work/references/tool-contract.md; then
    printf 'removed job dependency surface remains in tool contract\n' >&2
    exit 1
fi
grep -qF 'When `result.truncated` is true, read the full text from that file.' skills/coordinating-multi-model-work/references/tool-contract.md
grep -q '`other` requires an explicit mapping' skills/coordinating-multi-model-work/references/tool-contract.md
# Preserve source-freeze and temporary-checkpoint policy guards.
grep -q 'After submission, do not edit the root until that job is terminal.' skills/coordinating-multi-model-work/SKILL.md
grep -q 'Create a temporary checkpoint commit only after it passes.' skills/coordinating-multi-model-work/SKILL.md
grep -qF 'result.failure_kind' skills/coordinating-multi-model-work/SKILL.md
grep -qF 'retry(job_id)' skills/coordinating-multi-model-work/SKILL.md
grep -qF 'result.next_target' skills/coordinating-multi-model-work/SKILL.md
grep -qF 'result.next_target' skills/coordinating-multi-model-work/references/tool-contract.md
if grep -qF 'result.metadata.' skills/coordinating-multi-model-work/SKILL.md skills/coordinating-multi-model-work/references/tool-contract.md; then
    printf 'v2 result.metadata path found in coordinator guidance\n' >&2
    exit 1
fi
grep -qF '`result.tokens.context_used` exceeds 150,000' skills/coordinating-multi-model-work/references/tool-contract.md
grep -q 'Always start every phase with `fresh=true`' skills/coordinating-multi-model-work/references/tool-contract.md
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

board=skills/coordinating-multi-model-work/references/board.md
python3 - "$board" <<'PY'
import pathlib
import sys

board_path = pathlib.Path(sys.argv[1])
assert board_path.is_file(), f"{board_path} missing"
board = " ".join(board_path.read_text().split())
for rule in (
    "This file is the only owner of card rules. The three coordinator skills link here.",
    "Cards carry engineering task text only.",
    "Titles, bodies, and notes never carry personal, beneficiary, or credential data.",
    "Cards are a view. They never replace Git anchors or handover state.",
    "`todo`: TODO.",
    "`in_progress`: IN PROGRESS.",
    "`in_review`: IN REVIEW.",
    "`done`: DONE.",
    "`cancelled`: CANCELLED.",
    "`todo`: `in_progress`, `cancelled`",
    "`in_progress`: `in_review`, `cancelled`",
    "`in_review`: `done`, `in_progress`, `cancelled`",
    "`done`: none",
    "`cancelled`: none",
    "DONE and CANCELLED are final.",
    "A move to the current state is a same-state call.",
    "It links new jobs only. It ignores the note. It writes no move row and leaves `updated_at` unchanged when no link is new.",
    "Title: 1 to 200 characters, not blank after trimming.",
    "Body: at most 4,000 characters.",
    "Note: at most 1,000 characters, so trim findings before the call.",
    "Job IDs: at most 16 job IDs per call, each 1 to 64 characters.",
    "Links: at most 64 links per card.",
    "First Prepare of a plan",
    "`card_list`, then `card_create` for each missing phase in TODO",
    "<slug> · Phase <N>: <phase name>",
    "Write each returned ID to `card_refs` as soon as it returns.",
    "The middle dot is U+00B7.",
    "card_move(in_progress, job_ids=[<implement job>])",
    "card_move(in_review)",
    "link it with a same-state call",
    "card_move(in_progress, note=<findings, up to 1,000 characters>)",
    "card_move(done, note=<Spec and Quality status, debt owner>)",
    "card_move(cancelled, note=<reason>)",
    "A card call is best-effort.",
    "A failed call writes one journal line and one handover `debt` entry owned by `Coordinator`.",
    "A failed card call never sets `BLOCKED` and never changes a gate outcome.",
    "Retry a failed call at most once.",
    "Create and list cards against the `main repo root`, never a worktree.",
    "Pass the main repo root as `path`.",
    "Each phase card moves to IN PROGRESS when its worktree job is submitted.",
    "Review and integration run on the main checkout and follow the card-call table.",
    "A requeued phase keeps its card where it is.",
    "After a lost `card_create` reply, search `card_list` by exact title before creating again.",
    "On resume, reconcile `card_refs` with `card_list`.",
    "Recreate a missing card.",
    "Move a lagging card only along allowed edges.",
    "Journal anything else.",
    "On `response_too_large`, the change was applied.",
    "Record the applied card ID from the error.",
    "Do not create or move again until `card_list` shows the state.",
    "A final-audit regression after DONE goes to handover and the journal.",
    "DONE stays final.",
):
    assert rule in board, rule
PY

if grep -R -F 'phase_base..HEAD' "${workflow_files[@]}"; then
    printf 'unconditional phase_base review range reintroduced\n' >&2
    exit 1
fi

printf 'contract tests passed\n'
