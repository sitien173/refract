---
name: verifying-before-completion
description: "Defines the evidence required before claiming work is complete, fixed, passing, reviewed, or ready to hand off."
---

# Verifying Before Completion

This skill owns evidence and claim discipline. The coordinating skill chooses
the revision, diff ranges, and review sequence.

## Iron Law

```text
NO COMPLETION CLAIM WITHOUT FRESH VERIFICATION EVIDENCE
```

## Method

1. **Identify** what proves each claim.
2. **Run** the complete command or inspection now, at the specified revision.
3. **Read** full output, exit code, and failure count.
4. **Compare** results with every acceptance criterion.
5. **Report** only what the evidence supports.

## Required Evidence

- Applicable build, lint, type, test, and smoke checks.
- Changed paths and diffs match approved scope.
- Acceptance criteria checked individually.
- Bug regression fails without the fix and passes with it.
- Specification and independent quality-review outcomes.
- Explicit debt, skipped checks, and environmental blockers.
- Final revision and repository cleanliness.

## Claim Standard

| Claim | Minimum evidence |
| --- | --- |
| Tests pass | Fresh output with zero failures |
| Build succeeds | Fresh exit code 0 |
| Bug is fixed | Original reproduction or regression test passes |
| Requirements are met | Criterion-by-criterion evidence |
| Worker finished correctly | Verified commit, diff, clean state, and checks |

`FAIL` blocks completion. `PASS_WITH_DEBT` is acceptable only for explicit,
assigned, non-blocking debt. An unrun check is not a passed check; worker
summaries and prior runs are not proof.

## Final Report

State the verified revision, changed files, commands and outcomes, review
results, debt, skipped checks, and follow-ups. Avoid “should,” “probably,” or any
unsupported success claim.
