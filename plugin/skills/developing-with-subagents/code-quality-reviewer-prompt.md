# Code Quality Review (Opus)

Use this template when dispatching code review after spec compliance passes.

**Purpose:** Verify implementation is well-built (clean, tested, maintainable) via Opus review.

**Only dispatch after spec compliance review passes.**

## Review Selection

**Rule:** `Reviewer = Opus` (for all implementers)

| Implementer | Reviewer |
|-------------|----------|
| Codex (`mcp__codex__codex`) | Opus subagent |
| Gemini (`mcp__gemini__gemini`) | Opus subagent |
| Cursor (`mcp__cursor__cursor`) | Opus subagent |

## Invocation (Opus Reviewer)

Dispatch an Opus subagent using `superpowers-cccg:code-reviewer` for every code-changing path.

```text
1. Log: `[Quality Review] Dispatching Opus reviewer`
2. Dispatch Opus subagent using `superpowers-cccg:code-reviewer`
3. Use BASE_SHA/HEAD_SHA and task context
4. Include diff and original task spec
```

### Review Focus

1. Correctness: bugs, edge cases, off-by-one errors, null handling
2. Readability: naming, structure, comments where non-obvious
3. Maintainability: DRY, coupling, separation of concerns
4. Performance: anti-patterns, unnecessary allocations, N+1 queries

### Important

- Spec compliance has already been verified — focus only on code quality
- Do NOT suggest feature additions or scope changes

## Review Loop

- If Opus returns issues: implementer fixes, then re-submit to Opus
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

## Fallback (Opus Reviewer Unavailable)

If Opus is unavailable:
- **BLOCKED** — Opus is the only valid reviewer
- Escalate to user

**Opus returns:** APPROVE, or Issues (Critical/Important/Minor) with suggestions
