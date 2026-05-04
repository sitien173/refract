---
name: verifying-before-completion
description: "Final verification before marking work complete. Use when finishing a task, completing a plan, checking done status, validating success, or before reporting completion."
---

# Verifying Before Completion

## Use When

- Work appears complete and the user expects a final status.
- A phase, plan, bug fix, refactor, or implementation is about to be marked done.
- Tests or acceptance criteria need final confirmation.

## Workflow

1. Run declared integration checks for the phase or final plan.
2. Compare results against the original user request and acceptance criteria.
3. Confirm file changes match expected scope.
4. Run CP4 Phase Review and return `PASS`, `PASS_WITH_DEBT`, or `FAIL`.
5. Check for targeted regressions relevant to the changed area.
6. Report task status, files changed, integration result, CP4 status, and open follow-ups.

## Hard Rules

- Do not report final completion until all required checks pass or CP4 returns `PASS_WITH_DEBT` with explicit non-blocking debt.
- If CP4 returns `FAIL`, address the gap before completion.
- Do not treat unrun tests as passed.
- Do not broaden CP4 into general style or best-practice review unless the phase checklist requires it.

## References

- `skills/shared/protocol-threshold.md` — exact CP4 response block.
- `skills/coordinating-multi-model-work/review-chain.md` — canonical phase review outcomes.
- `skills/coordinating-multi-model-work/checkpoints.md` — CP3.5 integration checks and CP4 rules.
