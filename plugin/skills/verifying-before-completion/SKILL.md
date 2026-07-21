---
name: verifying-before-completion
description: "Requires fresh evidence before claiming work is complete, fixed, passing, ready to integrate, or ready to hand off."
---

# Verifying Before Completion

Load `coordinating-multi-model-work` first for delegated work. Its Gate 3 owns
independent review and integration; this skill owns evidence discipline.

## Iron Law

```text
NO COMPLETION CLAIM WITHOUT FRESH VERIFICATION EVIDENCE
```

## Gate Function

Before any success claim:

1. **Identify** the command or inspection that proves the claim.
2. **Run** it fresh and completely in the correct revision.
3. **Read** the full output, exit code, and failure count.
4. **Compare** the evidence with every acceptance criterion.
5. **Report** only what the evidence supports.

For an OpenMCP implementation, verify in a disposable detached worktree at the
result commit. Never assume a terminal execution worktree still exists.

## Required Evidence

- Declared build, lint, type, test, and smoke commands as applicable.
- Changed paths and diff match the approved scope.
- Acceptance criteria checked line by line.
- Bug fixes show the regression test failing without the fix and passing with it.
- Specification and independent quality review status.
- Explicit debt, skipped checks, or environmental blockers.

## Claim Standard

| Claim | Minimum evidence |
| --- | --- |
| Tests pass | Fresh test output with zero failures |
| Build succeeds | Fresh build exit code 0 |
| Bug is fixed | Original reproduction or regression test now passes |
| Requirements are met | Criterion-by-criterion evidence |
| Worker finished correctly | Verified commit, diff, and checks |

`FAIL` blocks completion. `PASS_WITH_DEBT` permits completion only when the debt
is non-blocking, explicit, and assigned. An unrun check is not a passed check.
Worker summaries and previous runs are not proof.

## Final Report

State:

- status and revision verified,
- files changed,
- commands and outcomes,
- specification and quality review results,
- debt, skipped checks, and follow-ups.

Avoid “should,” “probably,” or any implied success not backed by the evidence in
this run.

## References

- `skills/coordinating-multi-model-work/SKILL.md` — Gate 3 and integration.
- `skills/test-driven-development/SKILL.md` — RED → GREEN evidence.
- `skills/systematic-debugging/SKILL.md` — root-cause verification.
