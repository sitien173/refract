# Code Review Chain (Cursor Assistant + Opus Final Arbiter)

Use this template when dispatching code review after spec compliance passes.

**Purpose:** Verify implementation is well-built (clean, tested, maintainable) while keeping Opus as the final decision-maker.

**Only dispatch after spec compliance review passes.**

## Review Chain Selection

**Rule:** `ReviewAssistant = (Implementer == Cursor ? None : Cursor); FinalArbiter = Opus`

| Implementer | Review Assistant | Final Arbiter | Rationale |
|-------------|------------------|---------------|-----------|
| Codex (`mcp__codex__codex`) | Cursor (`mcp__cursor__cursor`) | Opus subagent | Cross-model review + consistent final bar |
| Gemini (`mcp__gemini__gemini`) | Cursor (`mcp__cursor__cursor`) | Opus subagent | Cross-model review + consistent final bar |
| Cursor (`mcp__cursor__cursor`) | Skip | Opus subagent | No self-review allowed |

## Invocation (Cursor as Review Assistant)

When Codex or Gemini was the implementer, call `mcp__cursor__cursor`:

```text
## Code Review Assistant

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
- Or list issues with: File, Line, Severity (Critical/Important/Minor), Issue, Suggestion, Confidence
```

### Parameters (Cursor)

```text
Tool: mcp__cursor__cursor
cd: $PWD
sandbox: default
SESSION_ID: <reuse-or-new>
model: claude-4.5-opus-high-thinking

Input variables:
  WHAT_WAS_IMPLEMENTED: [from implementer's report]
  PLAN_OR_REQUIREMENTS: Task N from [plan-file]
  BASE_SHA: [commit before task]
  HEAD_SHA: [current commit]
```

## Invocation (Opus as Final Arbiter)

Dispatch an Opus subagent using `superpowers-cccg:code-reviewer` for every code-changing path. When Cursor assistant feedback exists, include it alongside the diff and task context.

```text
1. Log: `[Final Arbiter] Dispatching Opus reviewer`
2. Dispatch Opus subagent using `superpowers-cccg:code-reviewer`
3. Use the same BASE_SHA/HEAD_SHA and task context
4. Include Cursor assistant findings if present
```

Opus decides whether to accept Cursor findings, dismiss them, add missed issues, or approve.

## Review Loop

- If Opus returns issues: implementer fixes, then re-submit to the review chain
- **Loop limits are risk-tiered:**
  - Trivial tasks: 0 loops (no quality review)
  - Standard tasks: max 3 fix-review loops
  - Critical tasks: max 4 fix-review loops, then escalate to user with full context
- If Opus approves: mark task complete

**Escalation format (when max loops reached):**

```text
⚠️ Review loop limit reached ([N] iterations)
Task complexity: [Standard/Critical]
Remaining issues: [list from last Opus review]
Options: (1) Accept with known issues, (2) User fixes manually, (3) Re-route to different model
```

## Fallback (Cursor Assistant Unavailable)

If `mcp__cursor__cursor` is unavailable when it should be the review assistant (Codex/Gemini implemented):
1. Log: `[Cursor Fallback] Cursor MCP unavailable, using direct Opus final review`
2. Fall back to dispatching the Opus arbiter without assistant feedback
3. Use the same BASE_SHA/HEAD_SHA and task context

## Fallback (Opus Reviewer Unavailable)

If Opus is unavailable when it should be the final arbiter:
- **BLOCKED** — Opus is the only valid final reviewer
- Do NOT let Cursor self-review or replace Opus
- Escalate to user

**Final arbiter returns:** APPROVE, or Issues (Critical/Important/Minor) with suggestions
