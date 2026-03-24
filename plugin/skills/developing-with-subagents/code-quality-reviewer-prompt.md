# Code Quality Review (Deterministic Reviewer)

Use this template when dispatching code quality review after spec compliance passes.

**Purpose:** Verify implementation is well-built (clean, tested, maintainable)

**Only dispatch after spec compliance review passes.**

## Reviewer Selection (Deterministic)

**Rule:** `Reviewer = (Implementer == Cursor ? Opus : Cursor)`

| Implementer | Quality Reviewer | Rationale |
|-------------|-----------------|-----------|
| Codex (`mcp__codex__codex`) | Cursor (`mcp__cursor__cursor`) | Cross-model review |
| Gemini (`mcp__gemini__gemini`) | Cursor (`mcp__cursor__cursor`) | Cross-model review |
| Cursor (`mcp__cursor__cursor`) | Opus subagent | No self-review allowed |

## Invocation (Cursor as Reviewer)

When Codex or Gemini was the implementer, call `mcp__cursor__cursor`:

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

### Parameters (Cursor)

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

## Invocation (Opus as Reviewer)

When Cursor was the implementer, dispatch an Opus subagent using `superpowers-ccg:code-reviewer` with the same review focus and BASE_SHA/HEAD_SHA context.

**This is NOT a fallback** — it is the deterministic choice when Cursor implements.

```
1. Log: `[Quality Review] Cursor implemented — dispatching Opus reviewer (no self-review)`
2. Dispatch Opus subagent using `superpowers-ccg:code-reviewer`
3. Use the same BASE_SHA/HEAD_SHA and task context
```

## Review Loop

- If reviewer returns issues: implementer fixes, then re-submit to reviewer
- **Max 3 fix-review loops** — after 3 iterations, escalate to user
- If reviewer approves: mark task complete

## Fallback (Cursor Reviewer Unavailable)

If `mcp__cursor__cursor` is unavailable when it should be the reviewer (Codex/Gemini implemented):
1. Log: `[Cursor Fallback] Cursor MCP unavailable, using Opus quality reviewer`
2. Fall back to dispatching an Opus subagent using `superpowers-ccg:code-reviewer`
3. Use the same BASE_SHA/HEAD_SHA and task context

## Fallback (Opus Reviewer Unavailable)

If Opus is unavailable when it should be the reviewer (Cursor implemented):
- **BLOCKED** — Opus is the only valid reviewer for Cursor-implemented code
- Do NOT let Cursor self-review
- Escalate to user

**Reviewer returns:** APPROVE, or Issues (Critical/Important/Minor) with suggestions
