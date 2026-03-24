# CCCG Workflow Optimizations Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers-cccg:executing-plans to implement this plan task-by-task.

**Goal:** Implement the 6 optimization priorities identified by 3-way CROSS_VALIDATION (Codex + Gemini + Cursor) and arbitrated by Opus.

**Architecture:** Incremental improvements to the existing skills-as-markdown framework. Each task modifies specific files with exact changes. No new skill directories needed. One new CI workflow and one new test file.

**Tech Stack:** Markdown, Bash (hooks/tests), YAML (GitHub Actions)

**Cross-Validation Source:** Session from 2026-03-24 — Codex (architecture), Gemini (DX), Cursor (systems) independently analyzed all workflows and converged on these priorities.

---

## Task 1: Namespace Unification — Fix `superpowers-ccg:` → `superpowers-cccg:`

**Model hint:** `auto`

> **IMPORTANT:** Only change `superpowers-ccg:` (two C's) references to `superpowers-cccg:` (three C's). Do NOT change `superpowers:` (no suffix) references — those are intentional and handled by `lib/skills-core.js` prefix-stripping logic.

**Files:**

- Modify: `CLAUDE.md:38` — namespace declaration
- Modify: `CLAUDE.md:90` — skill authoring reference
- Modify: `commands/brainstorm.md:6` — skill invocation
- Modify: `commands/write-plan.md:6` — skill invocation
- Modify: `commands/execute-plan.md:6` — skill invocation
- Modify: `skills/coordinating-multi-model-work/INTEGRATION.md:31` — related skill reference
- Modify: `skills/coordinating-multi-model-work/INTEGRATION.md:147` — code-reviewer reference
- Modify: `skills/developing-with-subagents/code-quality-reviewer-prompt.md:66` — code-reviewer reference
- Modify: `skills/developing-with-subagents/code-quality-reviewer-prompt.md:72` — code-reviewer reference
- Modify: `skills/developing-with-subagents/code-quality-reviewer-prompt.md:86` — fallback reference
- Modify: `skills/developing-with-subagents/SKILL.md:344` — related skill reference

**Step 1: Fix CLAUDE.md**

Replace on line 38:
```
All skills are exposed under the `superpowers-ccg:` namespace.
```
with:
```
All skills are exposed under the `superpowers-cccg:` namespace.
```

Replace on line 90:
```
When creating or editing skills, use `superpowers-ccg:writing-skills`.
```
with:
```
When creating or editing skills, use `superpowers-cccg:writing-skills`.
```

**Step 2: Fix command files**

In `commands/brainstorm.md` line 6, replace:
```
Invoke the superpowers-ccg:brainstorming skill and follow it exactly as presented to you
```
with:
```
Invoke the superpowers-cccg:brainstorming skill and follow it exactly as presented to you
```

In `commands/write-plan.md` line 6, replace:
```
Invoke the superpowers-ccg:writing-plans skill and follow it exactly as presented to you
```
with:
```
Invoke the superpowers-cccg:writing-plans skill and follow it exactly as presented to you
```

In `commands/execute-plan.md` line 6, replace:
```
Invoke the superpowers-ccg:executing-plans skill and follow it exactly as presented to you
```
with:
```
Invoke the superpowers-cccg:executing-plans skill and follow it exactly as presented to you
```

**Step 3: Fix INTEGRATION.md**

In `skills/coordinating-multi-model-work/INTEGRATION.md` line 31, replace:
```
**Related skill:** superpowers-ccg:coordinating-multi-model-work
```
with:
```
**Related skill:** superpowers-cccg:coordinating-multi-model-work
```

In the same file line 147, replace:
```
superpowers-ccg:code-reviewer
```
with:
```
superpowers-cccg:code-reviewer
```

**Step 4: Fix code-quality-reviewer-prompt.md**

In `skills/developing-with-subagents/code-quality-reviewer-prompt.md`, replace all three occurrences of `superpowers-ccg:code-reviewer` (lines 66, 72, 86) with `superpowers-cccg:code-reviewer`.

**Step 5: Fix developing-with-subagents/SKILL.md**

On line 344, replace:
```
**Related skill:** superpowers-ccg:coordinating-multi-model-work
```
with:
```
**Related skill:** superpowers-cccg:coordinating-multi-model-work
```

**Step 6: Verify no remaining `superpowers-ccg:` references (except filename `superpowers-ccg.md`)**

Run:
```bash
grep -rn "superpowers-ccg:" --include="*.md" --include="*.sh" --include="*.json" --include="*.js" . | grep -v "superpowers-cccg:" | grep -v "superpowers-ccg.md" | grep -v "node_modules" | grep -v "docs/plans/"
```
Expected: No matches (zero lines)

**Step 7: Commit**

```bash
git add CLAUDE.md commands/ skills/coordinating-multi-model-work/INTEGRATION.md skills/developing-with-subagents/code-quality-reviewer-prompt.md skills/developing-with-subagents/SKILL.md
git commit -m "fix: unify namespace to superpowers-cccg: across all files"
```

---

## Task 2: Tiered Enforcement Model — Add strict/degraded/incident modes to GATE.md

**Model hint:** `auto`

**Files:**

- Modify: `skills/coordinating-multi-model-work/GATE.md` — add Enforcement Modes section
- Modify: `skills/coordinating-multi-model-work/checkpoints.md` — reference enforcement modes

**Step 1: Add Enforcement Modes section to GATE.md**

After the existing "## Tiered Failure Policy" section (after line 117), add a new section:

```markdown
## Enforcement Modes

Tasks are classified into enforcement tiers based on complexity and risk. The tier determines how strictly the fail-closed rule applies.

| Mode | Trigger | Behavior | BLOCKED on failure? |
|------|---------|----------|---------------------|
| **Strict** | Implementation tasks, critical path changes (auth/payment/data), multi-file code changes | Full fail-closed. No exceptions. | Yes — always |
| **Degraded** | Non-critical single-file changes, config edits, documentation with code snippets | Allow "unverified proposal" clearly marked with `⚠️ UNVERIFIED — external model unavailable`. User must approve before proceeding. | No — but must warn |
| **Incident** | 3+ consecutive external model failures in same session | Notify user: "External models repeatedly unavailable. Options: (1) retry, (2) manual override, (3) pause and troubleshoot MCP connection." Log for post-mortem. | Pauses for user decision |

### Mode Selection

```text
IF task modifies auth, payment, security, data models, or core business logic:
    mode = strict
ELSE IF task is single-file, non-critical, or config/docs-with-code:
    mode = degraded
IF consecutive_failures >= 3 in session:
    mode = incident (overrides above)
```

### Unverified Proposal Format (Degraded Mode Only)

```text
⚠️ UNVERIFIED PROPOSAL — External model unavailable
Routing: [CODEX/GEMINI/CURSOR]
Failure reason: [timeout/tool-unavailable/permission-blocked]

Proposed change (generated by Claude as orchestrator, NOT validated by domain expert):
[proposed changes]

To proceed: User must explicitly approve this unverified proposal.
To retry: [exact MCP tool call to retry]
```
```

**Step 2: Reference enforcement modes in checkpoints.md**

At the end of the CP1 section (after line 19), add:

```markdown
**Enforcement mode:** After routing, determine the enforcement mode per `GATE.md > Enforcement Modes`. Record the mode in the CP1 Assessment block.
```

Update the CP1 Assessment template to include mode. In `hooks/user-prompt-submit.sh`, the template already exists — we'll update it in Task 3.

**Step 3: Commit**

```bash
git add skills/coordinating-multi-model-work/GATE.md skills/coordinating-multi-model-work/checkpoints.md
git commit -m "feat: add tiered enforcement modes (strict/degraded/incident) to GATE.md"
```

---

## Task 3: Adaptive CP Depth — Add task complexity tiers and CP2 objective triggers

**Model hint:** `auto`

**Files:**

- Modify: `skills/coordinating-multi-model-work/checkpoints.md` — add complexity tiers, CP2 objective triggers
- Modify: `hooks/user-prompt-submit.sh` — update CP template with complexity tier and enforcement mode

**Step 1: Add Task Complexity Classification to checkpoints.md**

Before the "## Checkpoints" heading (before line 9), add a new section:

```markdown
## Task Complexity Classification

Before applying checkpoints, classify the task:

| Tier | Criteria | CP Behavior |
|------|----------|-------------|
| **Trivial** | Docs-only, single config line, typo fix, <5 lines changed | Compact one-line CP1/CP3. Skip CP2. Skip quality review. |
| **Standard** | Single-domain task, clear scope, well-defined files | Full CP1/CP3 blocks. CP2 if triggered. Standard quality review. |
| **Critical** | Multi-file, architecture change, security/auth/payment, core logic, multi-domain | Full CP1/CP2/CP3 with cross-validation. Enhanced quality review (4+ loops). |

### Compact CP Format (Trivial tasks only)

```text
[CP1] Routing: CLAUDE | Trivial: docs-only change
[CP3] Verified: [command output or "no code changes"]
```
```

**Step 2: Add CP2 Objective Triggers to checkpoints.md**

Replace the existing CP2 section (lines 21-29) with:

```markdown
### CP2: Mid-Review (Key decision point)

**Objective Triggers** (any one is sufficient):

| Trigger | Threshold | Action |
|---------|-----------|--------|
| Retry count | >= 2 failed attempts at same sub-task | Re-evaluate approach, prefer CROSS_VALIDATION |
| Elapsed time | > 5 minutes on single sub-task without progress | Invoke domain expert for guidance |
| Failing test count | Increasing (more failures than when started) | Stop, investigate root cause before continuing |
| Ambiguity flag | 2+ viable approaches with unclear winner | Invoke CROSS_VALIDATION |
| Debugging stall | Root cause unclear after first investigation pass | Invoke domain expert |

**Subjective Triggers** (use judgment):

- Branching approaches (2+ viable paths with different costs/risks)
- Security/performance/data consistency concerns discovered mid-task
- Unexpected complexity revealed during implementation

Action: prefer `CROSS_VALIDATION`, and follow early exposure + evidence.

**CP2 Assessment Format:**

```text
[CP2 Assessment]
- Trigger: [which objective/subjective trigger fired]
- Current state: [what's been tried, what failed]
- Routing decision: [CLAUDE/CODEX/GEMINI/CROSS_VALIDATION]
- Rationale: ...
```
```

**Step 3: Update hooks/user-prompt-submit.sh**

Replace the `REMINDER_TEXT` variable content to include complexity tier, enforcement mode, and compact format:

```bash
REMINDER_TEXT="[CP Protocol Threshold (Required)]

1) Before the first Task call: output a standalone [CP1 Assessment] block (the block itself must not include tool calls)
2) Before claiming completion / requesting review / claiming verification passed: output a standalone [CP3 Assessment] block (the block itself must not include tool calls)

Note: Put the CP block first; tool calls may follow in the same assistant reply.

[CP1 Assessment]
- Task type: [Frontend/Backend/Full-stack/Other]
- Complexity: [Trivial/Standard/Critical]
- Enforcement mode: [Strict/Degraded/Incident]
- Routing decision: [CLAUDE/CODEX/GEMINI/CURSOR/CROSS_VALIDATION]
- Rationale: ...

Compact format (Trivial tasks only):
[CP1] Routing: CLAUDE | Trivial: <reason>

[CP3 Assessment]
- Task type: [Frontend/Backend/Full-stack/Other]
- Routing decision: [CLAUDE/CODEX/GEMINI/CURSOR/CROSS_VALIDATION]
- Rationale: ...

Compact format (Trivial tasks only):
[CP3] Verified: <evidence>

If unmet -> immediately perform the CP assessment, then continue the flow right away; do not stop or interrupt.
"
```

**Step 4: Commit**

```bash
git add skills/coordinating-multi-model-work/checkpoints.md hooks/user-prompt-submit.sh
git commit -m "feat: add adaptive CP depth (trivial/standard/critical) and CP2 objective triggers"
```

---

## Task 4: Risk-Tiered Quality Review

**Model hint:** `auto`

**Files:**

- Modify: `skills/coordinating-multi-model-work/checkpoints.md` — add risk tiers to QualityGateRequired
- Modify: `skills/developing-with-subagents/code-quality-reviewer-prompt.md` — add risk-aware loop limits
- Modify: `skills/coordinating-multi-model-work/cross-validation.md` — add divergence-only report format

**Step 1: Add risk tiers to QualityGateRequired in checkpoints.md**

Replace the existing QualityGateRequired Decision table (lines 47-58) with:

```markdown
**QualityGateRequired Decision (Risk-Tiered):**

| Task Complexity | Spec Review | Quality Review | Max Fix-Review Loops | Notes |
|----------------|-------------|----------------|---------------------|-------|
| **Trivial** (docs, config, <5 lines) | Skip | Skip | 0 | No code review needed |
| **Standard** (single-domain, clear scope) | Full | Full | 3 | Current default behavior |
| **Critical** (multi-file, auth/payment/core) | Full + cross-validation | Full + cross-validation | 4+ with user escalation | Enhanced scrutiny |

**Routing × Code Changed Matrix** (unchanged):

| Routing | Code Changed? | Implementation By | Quality Reviewed By |
|---------|--------------|-------------------|-------------------|
| CODEX | Yes | Codex | Cursor (parallel) |
| CODEX | No (docs-only) | Codex | Skip |
| GEMINI | Yes | Gemini | Cursor (parallel) |
| GEMINI | No (docs-only) | Gemini | Skip |
| CURSOR | Yes | Cursor | Opus (no self-review) |
| CURSOR | No (docs-only) | Cursor | Skip |
| CROSS_VALIDATION | Yes | Multiple | Depends on implementer |
| CLAUDE | No (docs-only) | N/A (orchestrator) | Skip |
```

**Step 2: Add risk-aware loop limits to code-quality-reviewer-prompt.md**

Replace the Review Loop section (lines 76-80) with:

```markdown
## Review Loop

- If reviewer returns issues: implementer fixes, then re-submit to reviewer
- **Loop limits are risk-tiered:**
  - Trivial tasks: 0 loops (no quality review)
  - Standard tasks: max 3 fix-review loops
  - Critical tasks: max 4 fix-review loops, then escalate to user with full context
- If reviewer approves: mark task complete

**Escalation format (when max loops reached):**
```text
⚠️ Review loop limit reached ([N] iterations)
Task complexity: [Standard/Critical]
Remaining issues: [list from last review]
Options: (1) Accept with known issues, (2) User fixes manually, (3) Re-route to different model
```
```

**Step 3: Add divergence-only report format to cross-validation.md**

After the existing "### Standard Cross-Validation Report" section (after line 208), add:

```markdown
### Divergence-Only Report (Default for Standard tasks)

For standard-complexity tasks, use this compact format that highlights only where models disagreed:

```markdown
## Cross-Validation Summary

**Agreement:** [1-2 sentence summary of shared conclusions]

**Divergences:**
| Aspect | Codex | Gemini | Resolution |
|--------|-------|--------|------------|
| [Only divergent points] | [View] | [View] | [Decision + rationale] |

**Action:** [What to do next based on resolution]
```

Use the full Standard Report format for Critical-complexity tasks or when divergences are extensive (3+ divergence rows).
```

**Step 4: Commit**

```bash
git add skills/coordinating-multi-model-work/checkpoints.md skills/developing-with-subagents/code-quality-reviewer-prompt.md skills/coordinating-multi-model-work/cross-validation.md
git commit -m "feat: add risk-tiered quality review and divergence-only cross-validation reports"
```

---

## Task 5: Testing & CI

**Model hint:** `auto`

**Files:**

- Create: `.github/workflows/test.yml` — CI workflow for fast tests
- Create: `tests/claude-code/test-namespace-consistency.sh` — namespace lint test
- Modify: `tests/claude-code/run-skill-tests.sh` — add namespace test to fast suite

**Step 1: Create namespace consistency test**

Create `tests/claude-code/test-namespace-consistency.sh`:

```bash
#!/usr/bin/env bash
# Test: Verify no stale superpowers-ccg: (2-C) namespace references remain
# All references should use superpowers-cccg: (3-C) or superpowers: (no suffix)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$SCRIPT_DIR/test-helpers.sh"

echo "=== Test: namespace consistency ==="
echo ""

# Search for superpowers-ccg: (exactly 2 C's, not 3) in all relevant files
# Exclude: superpowers-ccg.md filename itself, node_modules, docs/plans (archived), .git
echo "Test 1: No stale superpowers-ccg: references..."
STALE_REFS=$(grep -rn "superpowers-ccg:" \
  --include="*.md" --include="*.sh" --include="*.json" --include="*.js" \
  "$REPO_ROOT" 2>/dev/null \
  | grep -v "superpowers-cccg:" \
  | grep -v "superpowers-ccg\.md" \
  | grep -v "node_modules" \
  | grep -v "docs/plans/" \
  | grep -v "\.git/" \
  || true)

if [ -n "$STALE_REFS" ]; then
  echo "  [FAIL] Found stale superpowers-ccg: references (should be superpowers-cccg:):"
  echo "$STALE_REFS" | sed 's/^/    /'
  exit 1
fi

echo "  [PASS] All namespace references are consistent"
echo ""
```

> **Note:** Archived plan files in `docs/plans/` are intentionally excluded from namespace consistency checks. They are historical records and not expected to match the current namespace.

**Step 2: Add namespace test to fast test suite**

In `tests/claude-code/run-skill-tests.sh`, add `test-namespace-consistency.sh` to the default fast test list (alongside `test-subagent-driven-development.sh`).

**Step 3: Create GitHub Actions CI workflow**

Create `.github/workflows/test.yml`:

```yaml
name: Fast Tests

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  fast-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run fast test suite
        run: |
          chmod +x tests/claude-code/run-skill-tests.sh
          chmod +x tests/claude-code/test-*.sh
          ./tests/claude-code/run-skill-tests.sh
```

**Step 4: Run the namespace test locally to verify it passes**

Run from repo root:
```bash
chmod +x tests/claude-code/test-namespace-consistency.sh
./tests/claude-code/test-namespace-consistency.sh
```
Expected: `[PASS] All namespace references are consistent` (only after Task 1 is complete)

**Step 5: Commit**

```bash
git add .github/workflows/test.yml tests/claude-code/test-namespace-consistency.sh tests/claude-code/run-skill-tests.sh
git commit -m "feat: add namespace consistency test and GitHub Actions CI workflow"
```

---

## Task 6: Context Efficiency — Compact session-start injection

**Model hint:** `auto`

**Files:**

- Modify: `hooks/session-start.sh` — inject compact summary instead of full skill content

**Step 1: Refactor session-start.sh to inject compact summary**

Replace the full skill content injection approach. Instead of reading and injecting the entire `using-superpowers/SKILL.md` and `coordinating-multi-model-work/SKILL.md` content, inject a compact summary with pointers to load full skills on demand.

Replace the content injection in `session-start.sh` (the `additionalContext` value in the JSON output) with a compact version:

```bash
# Instead of reading full skill files, inject compact summary
COMPACT_CONTEXT="You have superpowers.

**Core Rules:**
1. **1% Rule:** If there is even a 1% chance a skill applies, use the Skill tool to load it before responding.
2. **Claude is orchestrator-only:** All implementation code goes through external models (Codex/Gemini/Cursor MCP).
3. **Checkpoint Protocol:** CP1 before first Task call, CP3 before claiming completion.
4. **Fail-Closed:** If Routing != CLAUDE and MCP call fails, output BLOCKED (see GATE.md for tiered policy).

**Multi-Model Routing:**
- Backend (API, DB, auth) → CODEX (\`mcp__codex__codex\`)
- Frontend (UI, styles) → GEMINI (\`mcp__gemini__gemini\`)
- General (debug, refactor, DevOps) → CURSOR (\`mcp__cursor__cursor\`)
- Full-stack/uncertain → CROSS_VALIDATION (multiple)
- Docs/coordination only → CLAUDE

**Skill Namespace:** \`superpowers-cccg:\` — use Skill tool to load any skill by name.

**To learn more:** Load \`superpowers-cccg:using-superpowers\` or \`superpowers-cccg:coordinating-multi-model-work\` for full instructions."
```

This reduces the injected context from ~3000 tokens to ~300 tokens while preserving all critical rules. Full skill content is loaded on-demand via the Skill tool.

**Step 2: Verify hooks still work**

Run:
```bash
bash hooks/session-start.sh
```
Expected: Valid JSON output with compact `additionalContext` field

**Step 3: Commit**

```bash
git add hooks/session-start.sh
git commit -m "perf: reduce session-start context injection from ~3000 to ~300 tokens"
```

---

## Execution Dependencies

```
Task 1 (Namespace) ← no dependencies, do first
Task 2 (Tiered Enforcement) ← no dependencies, can parallel with Task 1
Task 3 (Adaptive CP) ← depends on Task 2 (references enforcement modes)
Task 4 (Risk-Tiered Review) ← depends on Task 3 (references complexity tiers)
Task 5 (Testing & CI) ← depends on Task 1 (namespace test validates Task 1)
Task 6 (Context Efficiency) ← depends on Task 1 (uses correct namespace)
```

**Recommended execution order:** Task 1 → Task 2 → Task 3 → Task 4 → Task 5 → Task 6

**Batch 1:** Tasks 1 + 2 (independent, can run in parallel — no dependencies)
**Batch 2:** Tasks 3 + 5 in parallel (requires Batch 1 complete: Task 3 depends on Task 2, Task 5 depends on Task 1)
**Batch 3:** Tasks 4 + 6 in parallel (requires Batch 2 complete: Task 4 depends on Task 3, Task 6 depends on Task 1)

> **Note on `lib/skills-core.js`:** This file only strips the `superpowers:` prefix (no suffix). Claude Code resolves plugin skills via the registered plugin namespace (`superpowers-cccg`), not through this file. No changes needed to `skills-core.js`.
