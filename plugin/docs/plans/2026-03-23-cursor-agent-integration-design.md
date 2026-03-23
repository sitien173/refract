# Cursor Agent Integration Design

**Date:** 2026-03-23
**Status:** Approved (pending implementation)
**Validated by:** Codex cross-validation (session 019d1977-3f12-7561-9ad4-9acb46fda5c7)

---

## 1. Summary

Integrate Cursor (`mcp__cursor__cursor`) into the superpowers-ccg multi-model orchestration as a **universal code quality layer**. Cursor is not a routing destination — it activates automatically whenever code changes need review, replacing the Opus code quality reviewer in the subagent workflow and augmenting CP3 with parallel code quality validation.

**Mental model:**
> Codex/Gemini answer "is this the right thing?" — Cursor answers "is this thing built well?"

---

## 2. Design Decisions

| Decision | Choice | Alternatives Rejected |
|----------|--------|-----------------------|
| Cursor's role | Validation/code quality layer (Option C) | Replaces Codex/Gemini for implementation (A), Peer with own routing (B) |
| Workflow position | Post-implementation review (Option A) | Pre-commit gate (B), Continuous companion (C) |
| Review stage | Replaces Opus quality reviewer in stage 2 (Option A) | Third stage after both (B), Parallel with Opus (C) |
| CP3 participation | Joins CP3 alongside Codex/Gemini in parallel (Option A) | Limited to subagent stage only (B), Replaces domain experts for CLAUDE routing (C) |
| Routing label | No label — implicit activation (Option A) | Explicit `CURSOR` routing label (B) |

---

## 3. Architecture

### 3.1 Cursor's Position in the System

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CLAUDE (Orchestrator)                        │
│                                                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐               │
│  │ Codex MCP   │  │ Gemini MCP  │  │ Cursor MCP   │               │
│  │ (Backend)   │  │ (Frontend)  │  │ (Code Quality)│               │
│  │             │  │             │  │              │               │
│  │ APIs, DB,   │  │ UI, styles, │  │ Bugs, edge   │               │
│  │ auth, algo  │  │ components  │  │ cases, DRY,  │               │
│  │             │  │             │  │ readability  │               │
│  └──────┬──────┘  └──────┬──────┘  └──────┬───────┘               │
│         │                │                │                        │
│    Domain routing    Domain routing    Implicit activation          │
│    (CP1/CP2/CP3)     (CP1/CP2/CP3)    (code changes exist)        │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 What Cursor Does

- Reviews code for: bugs, edge cases, readability, maintainability, performance anti-patterns
- Replaces Opus code quality reviewer in subagent stage 2
- Runs in parallel with domain experts at CP3

### 3.3 What Cursor Does NOT Do

- No routing label — never appears in `[CP1 Assessment]` routing decisions
- No involvement in CP1 or CP2 — those remain domain-routing decisions
- No spec compliance review — stays with Opus subagent
- No domain analysis — stays with Codex/Gemini
- No docs-only review — exempt from Cursor (no code changed)

---

## 4. Integration Point 1: Subagent Stage 2

### Before (current)

```
Implementer (sonnet) → Spec Reviewer (Opus) → Code Quality Reviewer (Opus)
```

### After

```
Implementer (sonnet) → Spec Reviewer (Opus) → Cursor MCP (mcp__cursor__cursor)
```

### Flow

1. Spec compliance reviewer (Opus) approves — no change
2. Claude calls `mcp__cursor__cursor` with:
   - The diff/changes (pinned to commit SHA)
   - The original task spec for context
   - Prompt focused on code quality (not spec compliance)
3. If Cursor flags issues → implementer subagent fixes → re-submit to Cursor
4. If Cursor approves → mark task complete
5. **Max 3 fix loops** — after 3 iterations, escalate to user for decision

### Fail-Closed with Fallback

- If `mcp__cursor__cursor` is unavailable: **fall back to Opus code quality reviewer** (the previous behavior)
- Log a warning: `[Cursor Fallback] Cursor MCP unavailable, using Opus quality reviewer`
- This prevents Cursor outages from blocking all work

### Updated Model Strategy Table

| Subagent              | Model                              | Freedom                              |
| --------------------- | ---------------------------------- | ------------------------------------ |
| Implementer           | `model: sonnet`                    | Low - always use Sonnet for code     |
| Spec Reviewer         | Opus (default)                     | Low - always use Opus for review     |
| Code Quality Reviewer | Cursor MCP (`mcp__cursor__cursor`) | Low - always use Cursor; Opus fallback |
| Exploration           | `model: haiku`                     | Medium - prefer Haiku, flexible      |

---

## 5. Integration Point 2: CP3 Quality Gate

### Before (current)

```
CP3 fires → call Codex OR Gemini → record evidence → proceed or BLOCKED
```

### After

```
CP3 fires → QualityGateRequired? → call (Codex OR Gemini) AND Cursor in parallel
           → reconcile → record evidence → proceed or BLOCKED
```

### QualityGateRequired Check

CP3 now evaluates whether code changed (not just routing):

| Condition | Domain Expert | Cursor |
|-----------|--------------|--------|
| `Routing != CLAUDE` + code changed | Yes (per routing) | Yes (parallel) |
| `Routing != CLAUDE` + docs only | Yes (per routing) | No (exempt) |
| `Routing == CLAUDE` + code changed | No | Yes (new coverage) |
| `Routing == CLAUDE` + docs only | No | No |

This closes the gap Codex identified: CLAUDE-routed code changes now get quality review.

### Artifact Pinning

All CP3 reviews must reference the same artifact:
- Pin to **commit SHA** before dispatching parallel reviews
- Both domain expert and Cursor must review against the same SHA
- If fixes are applied from one review, re-run both against the new SHA

### Conflict Arbitration

| Domain Expert | Cursor | Action |
|--------------|--------|--------|
| Pass | Pass | Proceed |
| Pass | Fail | Fix code quality issues, re-review with Cursor only |
| Fail | Pass | Fix domain issues, re-review with domain expert only |
| Fail | Fail | Fix all issues, re-review both |
| Disagree on same code | — | Claude arbitrates, user escalation if unresolvable |

### Fail-Closed Rules

- If domain expert unavailable → BLOCKED (unchanged)
- If Cursor unavailable at CP3 → **proceed without Cursor** (CP3 domain review is primary; Cursor is supplementary here since code was already reviewed in subagent stage 2)
- This differs from stage 2 where Cursor is primary (with Opus fallback)

### Updated Evidence Block Format

```text
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
```

When `Routing == CLAUDE` but code changed:

```text
[Quality Gate]
Routing: CLAUDE (code quality review only)

Evidence (Code Quality):
- Tool: mcp__cursor__cursor
- Artifact: <commit SHA>
- Result: <3-6 bullets>

Integration: <what was accepted/rejected>
```

---

## 6. Cursor MCP Invocation Template

To be added to `INTEGRATION.md`:

```json
{
  "tool": "mcp__cursor__cursor",
  "params": {
    "PROMPT": "## Code Quality Review\n\n### Task Context\n[Original task spec — what was being built and why]\n\n### Changes to Review\n[Diff or file paths with line ranges]\nCommit: [SHA]\n\n### Review Focus\n1. Correctness: bugs, edge cases, off-by-one errors, null handling\n2. Readability: naming, structure, comments where non-obvious\n3. Maintainability: DRY, coupling, separation of concerns\n4. Performance: anti-patterns, unnecessary allocations, N+1 queries\n\n### Important\n- Spec compliance has already been verified — focus only on code quality\n- Do NOT suggest feature additions or scope changes\n\n### Output Format\n- APPROVE if no issues found\n- Or list issues as:\n  - File: [path]\n  - Line: [number]\n  - Severity: Critical | Important | Minor\n  - Issue: [description]\n  - Suggestion: [fix]",
    "cd": "$PWD",
    "sandbox": "default",
    "SESSION_ID": "<reuse-or-new>"
  }
}
```

### Key Rules (same as Codex/Gemini)

- Prompts to Cursor MUST be in English
- Cursor output is reference only — Claude makes final decisions
- Think independently — question Cursor's suggestions, don't blindly apply
- Always pin review to a specific commit SHA

---

## 7. Consistency Fix: Fail-Closed vs Timeout Fallback

**Issue found during Codex review:** `GATE.md` enforces strict fail-closed (BLOCKED), but `cross-validation.md` lines 243-244 allow Claude fallback on timeout. This must be unified.

**Resolution:** Adopt a two-tier policy:

| Context | On Failure |
|---------|-----------|
| Subagent stage 2 (Cursor) | Fall back to Opus quality reviewer |
| CP3 domain expert (Codex/Gemini) | BLOCKED — strict fail-closed |
| CP3 Cursor (supplementary) | Proceed without — domain review is primary |
| Cross-validation (both models) | If one times out: use completed result + Claude supplement. If both timeout: BLOCKED |

Update `cross-validation.md` lines 243-244 and `GATE.md` to document this tiered policy.

---

## 8. Files to Modify

| # | File | Change |
|---|------|--------|
| 1 | `skills/coordinating-multi-model-work/SKILL.md` | Add Cursor to overview, add step 3.5 "use Cursor for code quality review" to core instructions |
| 2 | `skills/coordinating-multi-model-work/INTEGRATION.md` | Add Cursor invocation template (Section 6), add to Quick Reference tree |
| 3 | `skills/coordinating-multi-model-work/GATE.md` | Add `Evidence (Code Quality)` block format, document tiered fail-closed policy |
| 4 | `skills/coordinating-multi-model-work/checkpoints.md` | Update CP3 to include QualityGateRequired check and parallel Cursor invocation |
| 5 | `skills/coordinating-multi-model-work/cross-validation.md` | Update timeout handling (lines 243-244) to match tiered policy, mention Cursor at CP3 |
| 6 | `skills/developing-with-subagents/SKILL.md` | Replace Opus quality reviewer with Cursor MCP in stage 2, update model strategy table, add max 3 fix loops, add Opus fallback |
| 7 | `skills/developing-with-subagents/code-quality-reviewer-prompt.md` | Rewrite as Cursor MCP invocation (instead of Opus subagent dispatch) |
| 8 | `superpowers-ccg.md` | Add Cursor to multi-model coordination section, update review workflow description |
| 9 | `CLAUDE.md` | Add Cursor to architecture documentation |

### Files NOT Changed

- `routing-decision.md` / `routing-rules.md` — no routing label added
- `hooks/` — hook enforcement unchanged
- `skills/dispatching-parallel-agents/` — Cursor is not a parallel dispatch target
- `lib/skills-core.js` — skill resolution unaffected

---

## 9. Codex Review Findings (Incorporated)

The following issues from Codex review have been addressed in this design:

| # | Finding | Severity | Resolution |
|---|---------|----------|------------|
| 1 | Uncovered paths when `Routing == CLAUDE` + code changes | Blocker | Added `QualityGateRequired` check at CP3 (Section 5) |
| 2 | Fail-closed inconsistency between GATE.md and cross-validation.md | Blocker | Tiered fail-closed policy (Section 7) |
| 3 | Race condition from parallel reviewers seeing different snapshots | Major | Artifact pinning to commit SHA (Section 5) |
| 4 | Single point of failure if Cursor unavailable | Major | Opus fallback at stage 2, proceed-without at CP3 (Sections 4, 5) |
| 5 | Need second decision axis beyond domain routing | Major | `QualityGateRequired` flag (Section 5) |
| 6 | Missing max review loops | Major | Cap at 3 iterations, then escalate (Section 4) |
| 7 | Conflict arbitration rule needed | Codex suggestion | Arbitration table added (Section 5) |
| 8 | Exempt docs-only changes | Codex suggestion | QualityGateRequired table excludes docs-only (Section 5) |

---

## 10. Implementation Order

Recommended sequence for implementing these changes:

1. **INTEGRATION.md** — Add Cursor template (independent, no dependencies)
2. **GATE.md** — Update evidence format and tiered policy
3. **cross-validation.md** — Fix timeout handling consistency
4. **checkpoints.md** — Add QualityGateRequired and parallel Cursor at CP3
5. **SKILL.md** (coordinating) — Add Cursor to overview and core instructions
6. **code-quality-reviewer-prompt.md** — Rewrite as Cursor invocation
7. **SKILL.md** (developing-with-subagents) — Replace quality reviewer, add fallback
8. **superpowers-ccg.md** — Update documentation
9. **CLAUDE.md** — Update architecture docs
