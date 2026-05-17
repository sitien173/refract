---
name: verifying-before-completion
description: "Final verification before marking work complete. Use when finishing a task, completing a plan, or before reporting completion."
---

# Verifying Before Completion

## Use When

- Work appears complete and user expects final status.
- A phase, plan, bug fix, refactor, or implementation is about to be marked done.

## Workflow

1. Run the declared integration checks (build, lint, type-check, tests, smoke commands).
2. Compare results against the original request and acceptance criteria.
3. Confirm file changes match expected scope.
4. Run the Review gate from `coordinating-multi-model-work`: (a) Spec status from integration checks, (b) Quality scan on changed files. Output `# REVIEW` with Spec Status, Quality Findings, Final Status.
5. Check for targeted regressions in the changed area.
6. Report: task status, files changed, integration result, Review status, open follow-ups.

## Hard Rules

- No completion claim until all required checks pass or Review returns `PASS_WITH_DEBT` with explicit non-blocking debt.
- `FAIL` blocks completion — fix the gap or ask user.
- Unrun tests are not passed tests.
- Review stays scoped to spec; broader code-quality review only if listed in the phase checklist.

## References

- `skills/coordinating-multi-model-work/SKILL.md` — Review gate and PASS / PASS_WITH_DEBT / FAIL semantics.
