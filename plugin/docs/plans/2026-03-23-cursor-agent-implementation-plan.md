# Cursor Agent Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate Cursor (`mcp__cursor__cursor`) as a universal code quality layer into the multi-model orchestration framework.

**Architecture:** Cursor replaces the Opus code quality reviewer in subagent stage 2 and joins CP3 as a parallel quality reviewer alongside domain experts. No routing label — implicit activation when code changes exist. Tiered fail-closed policy with Opus fallback at stage 2.

**Tech Stack:** Markdown skill files, Bash hooks (no compiled code)

**Design doc:** `docs/plans/2026-03-23-cursor-agent-integration-design.md`

---

### Task 1: Update GATE.md — Tiered fail-closed policy and evidence format

**Model hint:** `auto`

**Files:**
- Modify: `skills/coordinating-multi-model-work/GATE.md`

**Step 1: Add tiered fail-closed policy**

After the existing "Failure Handling" section (line 38), add a new section:

```markdown
## Tiered Failure Policy

Not all external calls have the same failure severity. Use this matrix:

| Call Context | On Failure | Rationale |
|-------------|-----------|-----------|
| Domain expert at CP3 (Codex/Gemini) | BLOCKED — strict fail-closed | Primary validation, no substitute |
| Cursor at subagent stage 2 | Fall back to Opus code quality reviewer | Cursor is primary but Opus can substitute |
| Cursor at CP3 (supplementary) | Proceed without — log warning | Domain review is primary; code was already reviewed in stage 2 |
| Cross-validation: one model times out | Use completed result + Claude supplement | Partial evidence better than none |
| Cross-validation: both timeout | BLOCKED | No evidence available |
```

**Step 2: Update evidence format**

After the existing evidence block template (line 36), add the extended format:

```markdown
### Extended Evidence Format (with Code Quality)

When Cursor participates in the quality gate alongside a domain expert:

\```text
[Multi-Model Gate]
Routing: CODEX | GEMINI | CROSS_VALIDATION
Why: <one sentence>

Evidence (Domain):
- Tool: mcp__codex__codex | mcp__gemini__gemini
- Artifact: <commit SHA>
- Result: <3-6 bullets>

Evidence (Code Quality):
- Tool: mcp__cursor__cursor
- Artifact: <commit SHA>
- Result: <3-6 bullets>

Integration: <what was accepted/rejected from each>
\```

When only Cursor reviews (Routing == CLAUDE but code changed):

\```text
[Quality Gate]
Routing: CLAUDE (code quality review only)

Evidence (Code Quality):
- Tool: mcp__cursor__cursor
- Artifact: <commit SHA>
- Result: <3-6 bullets>

Integration: <what was accepted/rejected>
\```
```

**Step 3: Update pre-output self-check**

Update the self-check at the end to include Cursor awareness:

```markdown
## Pre-Output Self-Check (Mandatory)

- If Routing != CLAUDE: do I have Domain Evidence?
- If code changed: do I have Code Quality Evidence (or valid exemption)?
- If not: did I stop in BLOCKED state (no final answer)?
- Exemption: docs-only changes do not require Code Quality Evidence
```

**Step 4: Verify changes**

Run: `grep -n "Cursor\|Quality Gate\|Tiered" skills/coordinating-multi-model-work/GATE.md`
Expected: Multiple matches confirming all sections added

**Step 5: Commit**

```bash
git add skills/coordinating-multi-model-work/GATE.md
git commit -m "feat: add tiered fail-closed policy and Cursor evidence format to GATE.md"
```

---

### Task 2: Fix cross-validation.md — Timeout handling consistency

**Model hint:** `auto`

**Files:**
- Modify: `skills/coordinating-multi-model-work/cross-validation.md:234-250`

**Step 1: Update timeout handling section**

Replace lines 241-244 in cross-validation.md:

```markdown
### Timeout Handling

- Single model call timeout: use completed result + Claude supplement
- Both timeout: fallback to Claude independent analysis
```

With:

```markdown
### Timeout Handling

- Single model call timeout: use completed result + Claude supplement (log which model timed out)
- Both timeout: BLOCKED — follow `GATE.md` fail-closed procedure (do not fall back to Claude independent analysis)

> **Note:** This aligns with the tiered failure policy in `GATE.md`. Cross-validation requires at least one external perspective to be meaningful.
```

**Step 2: Verify changes**

Run: `grep -n "BLOCKED\|tiered\|GATE" skills/coordinating-multi-model-work/cross-validation.md`
Expected: Matches on the updated timeout section

**Step 3: Commit**

```bash
git add skills/coordinating-multi-model-work/cross-validation.md
git commit -m "fix: align cross-validation timeout handling with fail-closed gate policy"
```

---

### Task 3: Update checkpoints.md — QualityGateRequired and parallel Cursor at CP3

**Model hint:** `auto`

**Files:**
- Modify: `skills/coordinating-multi-model-work/checkpoints.md`

**Step 1: Update CP3 section**

Replace the existing CP3 section (lines 29-33) with:

```markdown
### CP3: Quality Gate (Before output)

Goal: perform final review before "final output/final conclusion/claiming tests passed/requesting code review".

**Domain Review (unchanged):**
- If `Routing != CLAUDE`: Domain expert Evidence required (Codex/Gemini)
- External failure: must BLOCKED (fail-closed)

**Code Quality Review (Cursor):**
- Evaluate `QualityGateRequired`: did code change in this task?
- If yes: call Cursor (`mcp__cursor__cursor`) in parallel with domain expert
- If no (docs-only): skip Cursor
- Cursor failure at CP3: proceed without (supplementary — see tiered policy in `GATE.md`)

**QualityGateRequired Decision:**

| Routing | Code Changed? | Domain Expert | Cursor |
|---------|--------------|---------------|--------|
| CODEX/GEMINI/CROSS_VALIDATION | Yes | Required | Required (parallel) |
| CODEX/GEMINI/CROSS_VALIDATION | No (docs-only) | Required | Skip |
| CLAUDE | Yes | Skip | Required |
| CLAUDE | No (docs-only) | Skip | Skip |

**Artifact Pinning:** All CP3 reviews must reference the same commit SHA. If fixes from one review invalidate the other, re-run both against the new SHA.

**Conflict Arbitration:**

| Domain Expert | Cursor | Action |
|--------------|--------|--------|
| Pass | Pass | Proceed |
| Pass | Fail | Fix code quality issues, re-review Cursor only |
| Fail | Pass | Fix domain issues, re-review domain expert only |
| Fail | Fail | Fix all issues, re-review both |
```

**Step 2: Verify changes**

Run: `grep -n "QualityGateRequired\|Cursor\|Artifact Pinning" skills/coordinating-multi-model-work/checkpoints.md`
Expected: Multiple matches confirming all sections added

**Step 3: Commit**

```bash
git add skills/coordinating-multi-model-work/checkpoints.md
git commit -m "feat: add QualityGateRequired check and parallel Cursor invocation to CP3"
```

---

### Task 4: Update routing-decision.md — Add QualityGateRequired and Cursor note

**Model hint:** `auto`

**Files:**
- Modify: `skills/coordinating-multi-model-work/routing-decision.md`

**Step 1: Add QualityGateRequired section after Decision Output (line 73)**

```markdown
## Quality Gate Decision (Orthogonal to Routing)

In addition to domain routing, CP3 evaluates whether code quality review is needed:

```
**QualityGateRequired:** [Yes | No]
**Rationale:** [Code changed / docs-only]
```

This is independent of the routing decision:
- Cursor (`mcp__cursor__cursor`) is NOT a routing destination
- It activates automatically when code changed, regardless of routing label
- See `checkpoints.md` for the full QualityGateRequired decision table
```

**Step 2: Add note to Routing Targets (after line 82)**

Add after the CLAUDE bullet:

```markdown
> **Note:** Cursor (`mcp__cursor__cursor`) is intentionally absent from routing targets. It is a universal code quality layer that activates based on whether code changed, not based on task domain. See `checkpoints.md` for details.
```

**Step 3: Verify changes**

Run: `grep -n "Cursor\|QualityGateRequired" skills/coordinating-multi-model-work/routing-decision.md`
Expected: Matches in both new sections

**Step 4: Commit**

```bash
git add skills/coordinating-multi-model-work/routing-decision.md
git commit -m "feat: add QualityGateRequired decision and Cursor exclusion note to routing framework"
```

---

### Task 5: Update routing-rules.md — Add Cursor clarification

**Model hint:** `auto`

**Files:**
- Modify: `skills/coordinating-multi-model-work/routing-rules.md`

**Step 1: Add Cursor note after the Reminder section (line 23)**

```markdown
## Cursor (Not a Routing Target)

Cursor (`mcp__cursor__cursor`) is a **code quality layer**, not a routing destination. Do not create a `CURSOR` routing label. Cursor activates automatically at:
- Subagent stage 2 (replaces Opus quality reviewer)
- CP3 when code changed (parallel with domain expert)

See `checkpoints.md` for `QualityGateRequired` decision table.
```

**Step 2: Commit**

```bash
git add skills/coordinating-multi-model-work/routing-rules.md
git commit -m "docs: clarify Cursor is not a routing target in quick heuristics"
```

---

### Task 6: Update INTEGRATION.md — Add Cursor invocation template

**Model hint:** `auto`

**Files:**
- Modify: `skills/coordinating-multi-model-work/INTEGRATION.md`

**Step 1: Add Cursor to Quick Reference (after line 13)**

Update the Quick Reference tree to include Cursor:

```
Task Type → Model Selection:
├─ Frontend (UI, components, styles) → GEMINI
├─ Backend (API, database, logic) → CODEX
├─ Full-stack or uncertain → CROSS_VALIDATION
├─ Design docs, implementation docs, requirements specs, architecture docs, and other critical documentation → CROSS_VALIDATION
├─ Simple (docs, configs) → CLAUDE (no external model needed)
└─ Code quality review (automatic) → CURSOR (not a routing target — see below)
```

**Step 2: Add Cursor invocation template (after Cross-Validation section, before Important Rules)**

Add before line 88:

```markdown
### Code Quality Review (Cursor MCP)

Cursor is invoked automatically for code quality review — it is NOT a routing target. Use this template when code changes need quality validation (subagent stage 2, CP3 with code changes).

\```json
{
  "tool": "mcp__cursor__cursor",
  "params": {
    "PROMPT": "## Code Quality Review\n\n### Task Context\n[Original task spec — what was being built and why]\n\n### Changes to Review\n[Diff or file paths with line ranges]\nCommit: [SHA]\n\n### Review Focus\n1. Correctness: bugs, edge cases, off-by-one errors, null handling\n2. Readability: naming, structure, comments where non-obvious\n3. Maintainability: DRY, coupling, separation of concerns\n4. Performance: anti-patterns, unnecessary allocations, N+1 queries\n\n### Important\n- Spec compliance has already been verified — focus only on code quality\n- Do NOT suggest feature additions or scope changes\n\n### Output Format\n- APPROVE if no issues found\n- Or list issues as:\n  - File: [path]\n  - Line: [number]\n  - Severity: Critical | Important | Minor\n  - Issue: [description]\n  - Suggestion: [fix]",
    "cd": "$PWD",
    "sandbox": "default",
    "SESSION_ID": "<reuse-or-new>"
  }
}
\```

**Cursor-specific rules:**
- Pin review to a specific commit SHA (artifact pinning)
- Max 3 fix-review loops before escalating to user
- If Cursor unavailable at subagent stage 2: fall back to Opus quality reviewer
- If Cursor unavailable at CP3: proceed without (supplementary)
```

**Step 3: Verify changes**

Run: `grep -n "Cursor\|cursor\|mcp__cursor" skills/coordinating-multi-model-work/INTEGRATION.md`
Expected: Multiple matches for template and rules

**Step 4: Commit**

```bash
git add skills/coordinating-multi-model-work/INTEGRATION.md
git commit -m "feat: add Cursor MCP invocation template to integration guide"
```

---

### Task 7: Update coordinating SKILL.md — Add Cursor to overview and core instructions

**Model hint:** `auto`

**Files:**
- Modify: `skills/coordinating-multi-model-work/SKILL.md`

**Step 1: Update description frontmatter (line 3)**

Update the description to mention Cursor:

```yaml
description: "Routes work to Codex (backend) and Gemini (frontend) via MCP tools, with Cursor for code quality review and cross-validation for full-stack/uncertain tasks. Use when: UI/components/styles, APIs/databases/auth/security/performance, debugging, code review, or tasks mentioning Codex/Gemini/Cursor/CCG/multi-model. Keywords: codex mcp, gemini mcp, cursor mcp, cross-validation, code quality, api, database, auth, security, performance, ui, component"
```

**Step 2: Update Overview (line 21)**

Replace line 21 with:

```markdown
Use this module to decide whether to call **Codex** (backend), **Gemini** (frontend), and/or **Cursor** (code quality) via MCP tools, and to enforce a consistent evidence protocol.
```

**Step 3: Add Cursor to Core Instructions (after step 3, line 31)**

Add between steps 3 and 4:

```markdown
**3.5** Whenever code changes are complete, **use Cursor (`mcp__cursor__cursor`) for code quality review**. Cursor reviews for bugs, edge cases, readability, maintainability, and performance. This is automatic — Cursor is not a routing target but a universal quality layer. See `coordinating-multi-model-work/INTEGRATION.md` for the invocation template.
```

**Step 4: Update Reference Files (after line 54)**

Add:

```markdown
- **Cross-validation mechanism:** `coordinating-multi-model-work/cross-validation.md`
```

**Step 5: Commit**

```bash
git add skills/coordinating-multi-model-work/SKILL.md
git commit -m "feat: add Cursor as code quality layer to coordinating multi-model work skill"
```

---

### Task 8: Rewrite code-quality-reviewer-prompt.md — Cursor MCP invocation

**Model hint:** `auto`

**Files:**
- Modify: `skills/developing-with-subagents/code-quality-reviewer-prompt.md`

**Step 1: Rewrite the file**

Replace entire contents with:

```markdown
# Code Quality Review via Cursor MCP

Use this template when dispatching code quality review after spec compliance passes.

**Purpose:** Verify implementation is well-built (clean, tested, maintainable)

**Only dispatch after spec compliance review passes.**

## Invocation

Call `mcp__cursor__cursor` with the following prompt structure:

```text
## Code Quality Review

### Task Context
[WHAT_WAS_IMPLEMENTED — from implementer's report]
[PLAN_OR_REQUIREMENTS — Task N from plan-file]

### Changes to Review
[Diff between BASE_SHA and HEAD_SHA]
Commit: [HEAD_SHA]

### Review Focus
1. Correctness: bugs, edge cases, off-by-one errors, null handling
2. Readability: naming, structure, comments where non-obvious
3. Maintainability: DRY, coupling, separation of concerns
4. Performance: anti-patterns, unnecessary allocations, N+1 queries

### Important
- Spec compliance has already been verified — focus only on code quality
- Do NOT suggest feature additions or scope changes

### Output Format
- APPROVE if no issues found
- Or list issues with: File, Line, Severity (Critical/Important/Minor), Issue, Suggestion
```

## Parameters

```
Tool: mcp__cursor__cursor
cd: $PWD
sandbox: default
SESSION_ID: <reuse-or-new>

Input variables:
  WHAT_WAS_IMPLEMENTED: [from implementer's report]
  PLAN_OR_REQUIREMENTS: Task N from [plan-file]
  BASE_SHA: [commit before task]
  HEAD_SHA: [current commit]
```

## Review Loop

- If Cursor returns issues: implementer fixes, then re-submit to Cursor
- **Max 3 fix-review loops** — after 3 iterations, escalate to user
- If Cursor approves: mark task complete

## Fallback

If `mcp__cursor__cursor` is unavailable:
1. Log: `[Cursor Fallback] Cursor MCP unavailable, using Opus quality reviewer`
2. Fall back to dispatching an Opus subagent using `superpowers:code-reviewer`
3. Use the same BASE_SHA/HEAD_SHA and task context

**Cursor reviewer returns:** APPROVE, or Issues (Critical/Important/Minor) with suggestions
```

**Step 2: Verify changes**

Run: `grep -n "mcp__cursor\|Fallback\|Max 3" skills/developing-with-subagents/code-quality-reviewer-prompt.md`
Expected: Matches confirming Cursor invocation, fallback, and loop cap

**Step 3: Commit**

```bash
git add skills/developing-with-subagents/code-quality-reviewer-prompt.md
git commit -m "feat: rewrite code quality reviewer to use Cursor MCP with Opus fallback"
```

---

### Task 9: Update developing-with-subagents SKILL.md — Replace quality reviewer, update model table

**Model hint:** `auto`

**Files:**
- Modify: `skills/developing-with-subagents/SKILL.md`

**Step 1: Update overview (line 18)**

Replace:
```markdown
Execute plan by dispatching fresh subagent per task, with two-stage review after each: spec compliance review first, then code quality review.
```

With:
```markdown
Execute plan by dispatching fresh subagent per task, with two-stage review after each: spec compliance review first (Opus), then code quality review (Cursor MCP, with Opus fallback).
```

**Step 2: Update core principle (line 20)**

Replace:
```markdown
**Core principle:** Fresh subagent per task + two-stage review (spec then quality) = high quality, fast iteration
```

With:
```markdown
**Core principle:** Fresh subagent per task + two-stage review (spec via Opus, then quality via Cursor MCP) = high quality, fast iteration
```

**Step 3: Update process diagram references (lines 98-100)**

Replace:
```
"Dispatch code quality reviewer subagent (./code-quality-reviewer-prompt.md)" [shape=box];
"Code quality reviewer subagent approves?" [shape=diamond];
"Implementer subagent fixes quality issues" [shape=box];
```

With:
```
"Call Cursor MCP for code quality review (./code-quality-reviewer-prompt.md)" [shape=box];
"Cursor approves?" [shape=diamond];
"Implementer subagent fixes quality issues (max 3 loops)" [shape=box];
```

Update the corresponding edge labels similarly (lines 118-121).

**Step 4: Update model strategy table (lines 140-144)**

Replace:
```markdown
| Subagent              | Model           | Freedom                          |
| --------------------- | --------------- | -------------------------------- |
| Implementer           | `model: sonnet` | Low - always use Sonnet for code |
| Spec/Quality Reviewer | Opus (default)  | Low - always use Opus for review |
| Exploration           | `model: haiku`  | Medium - prefer Haiku, flexible  |
```

With:
```markdown
| Subagent              | Model                              | Freedom                              |
| --------------------- | ---------------------------------- | ------------------------------------ |
| Implementer           | `model: sonnet`                    | Low - always use Sonnet for code     |
| Spec Reviewer         | Opus (default)                     | Low - always use Opus for review     |
| Code Quality Reviewer | Cursor MCP (`mcp__cursor__cursor`) | Low - always use Cursor; Opus fallback |
| Exploration           | `model: haiku`                     | Medium - prefer Haiku, flexible      |
```

**Step 5: Update CP3 checkpoint description (line 162-163)**

Replace:
```markdown
**► Checkpoint 3 (Quality Gate):** After subagent completes, before spec review:

- Implementation complete → invoke domain expert for pre-review assessment
```

With:
```markdown
**► Checkpoint 3 (Quality Gate):** After subagent completes implementation:

- Implementation complete → invoke domain expert for pre-review assessment
- Code quality review via Cursor runs after spec compliance passes (see `code-quality-reviewer-prompt.md`)
- If Cursor unavailable: fall back to Opus code quality reviewer
- Max 3 fix-review loops with Cursor before escalating to user
```

**Step 6: Update example workflow (lines 193-194)**

Replace code quality reviewer references in the example:
```
[Get git SHAs, dispatch code quality reviewer]
Code reviewer: Strengths: Good test coverage, clean. Issues: None. Approved.
```

With:
```
[Get git SHAs, call Cursor MCP for code quality review]
Cursor: APPROVE — Good test coverage, clean implementation. No issues found.
```

And similarly for the second example block (around line 222-229).

**Step 7: Update red flags section**

Add to the "Never" list:
```markdown
- Skip Cursor fallback to Opus when Cursor is unavailable (don't just skip quality review)
- Exceed 3 fix-review loops with Cursor without escalating to user
```

**Step 8: Commit**

```bash
git add skills/developing-with-subagents/SKILL.md
git commit -m "feat: replace Opus code quality reviewer with Cursor MCP in subagent workflow"
```

---

### Task 10: Update superpowers-ccg.md — Multi-model coordination docs

**Model hint:** `auto`

**Files:**
- Modify: `superpowers-ccg.md`

**Step 1: Update Multi-Model Coordination section (around line 172-198)**

Add Cursor to the routing labels table:

```markdown
### Routing Labels

| Label | When to Use | MCP Tool |
|-------|-------------|----------|
| `CODEX` | Backend: API, database, algorithms, auth, security | `mcp__codex__codex` |
| `GEMINI` | Frontend: UI, components, styles, interactions | `mcp__gemini__gemini` |
| `CROSS_VALIDATION` | Full-stack, uncertain, critical tasks | Both MCP tools |
| `CLAUDE` | Simple tasks, general work | No MCP call |

> **Note:** Cursor (`mcp__cursor__cursor`) is NOT a routing label. It is a universal code quality layer that activates automatically when code changes need review. See below.

### Cursor (Code Quality Layer)

Cursor reviews code for quality (bugs, edge cases, readability, maintainability, performance). It operates in two places:

1. **Subagent stage 2:** Replaces Opus code quality reviewer. Falls back to Opus if unavailable.
2. **CP3 quality gate:** Runs in parallel with domain expert when code changed. Proceeds without if unavailable.

Max 3 fix-review loops before escalating to user. Docs-only changes are exempt.
```

**Step 2: Update Core Instructions (around line 185-189)**

Add step 3.5:
```markdown
3.5. **Quality review** - After coding, use Cursor (`mcp__cursor__cursor`) for code quality review. Cursor is automatic, not a routing decision.
```

**Step 3: Update review workflow in Workflow 3 (around line 103-107)**

```markdown
### Workflow 3: Code Review

```
superpowers-ccg:requesting-code-review → [reviewer subagent] → superpowers-ccg:receiving-code-review → [implement fixes]
```

Note: Code quality review via Cursor MCP is built into the subagent workflow (stage 2) and does not need separate invocation.
```

**Step 4: Update Model Selection table (around line 307-312)**

```markdown
| Task Type | Model |
|-----------|-------|
| Code writing, implementation | `model: sonnet` |
| Review, architecture, complex reasoning | Opus (default) |
| Exploration, search, quick lookups | `model: haiku` |
| Code quality review | Cursor MCP (`mcp__cursor__cursor`); Opus fallback |
```

**Step 5: Commit**

```bash
git add superpowers-ccg.md
git commit -m "docs: add Cursor code quality layer to agent rules documentation"
```

---

### Task 11: Update CLAUDE.md — Architecture docs

**Model hint:** `auto`

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Update multi-model routing table**

Add Cursor row and note:

```markdown
| Routing | When | MCP Tool |
|---------|------|----------|
| `CODEX` | Backend: API, DB, auth, algorithms | `mcp__codex__codex` |
| `GEMINI` | Frontend: UI, components, styles | `mcp__gemini__gemini` |
| `CROSS_VALIDATION` | Full-stack, architectural, uncertain | Both |
| `CLAUDE` | Docs, simple config, general tasks | None |

Cursor (`mcp__cursor__cursor`) is not a routing target — it is a universal code quality layer that activates automatically when code changes exist, operating in subagent stage 2 (replacing Opus quality reviewer) and at CP3 (parallel with domain expert).
```

**Step 2: Update subagent workflow description**

In the Skills section, update the `developing-with-subagents` description:

```markdown
- `developing-with-subagents/` — Dispatches fresh subagents per task with two-stage review (spec via Opus, quality via Cursor MCP)
```

**Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add Cursor code quality layer to CLAUDE.md architecture docs"
```
