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
2. Fall back to dispatching an Opus subagent using `superpowers-ccg:code-reviewer`
3. Use the same BASE_SHA/HEAD_SHA and task context

**Cursor reviewer returns:** APPROVE, or Issues (Critical/Important/Minor) with suggestions
