---
name: systematic-debugging
description: "Use when something is broken or behaves unexpectedly: a bug, error, crash, failing or flaky test, regression, or slowdown, even when the user only asks for a quick fix. Establishes a reproducible root cause before any change."
---

# Systematic Debugging

## Role

This skill owns diagnosis. `coordinating-multi-model-work` owns delegation;
`test-driven-development` owns the regression-test cycle.

## Iron Law

Change code only after evidence confirms the root cause. A fix without one
hides the defect instead of removing it.

## Workflow

1. **Reproduce.** Capture the full error, exact steps, environment, and
   expected versus actual behavior. For performance, record a baseline: the
   command and its numbers. Done when the failure occurs on demand.
2. **Trace.** Follow bad state backward across component boundaries to the
   first divergence, the earliest point where actual state differs from
   expected. Add temporary logging or assertions where reading is not enough,
   and remove them before the fix.
3. **Compare.** Read a similar working path and list the relevant differences.
4. **Hypothesize.** Log one falsifiable hypothesis with its predicted
   observation. Change one variable to test it.
5. **Confirm.** A hypothesis is confirmed only when the prediction holds and
   reverting the change brings the failure back.
6. **Fix.** Hand the reproduction and root cause to `test-driven-development`:
   a regression test that goes RED for the diagnosed reason, then the smallest
   source correction.

## Hypothesis Log

Keep one line per hypothesis visible while working:

```text
H<n>: <cause> | Predict: <observation> | Test: <one change> | Result: confirmed | refuted
```

## Stop Conditions

- Evidence contradicts the hypothesis: mark it refuted and return to Trace.
- Three refuted hypotheses or three failed fixes: stop, show the log, and
  question the model or architecture with the user.
- No reproduction after three attempts: report what was tried, propose
  instrumentation, and ask before changing code.
- A regression test is required unless the user explicitly waives it.

## Rules

- Fix the source, not a downstream symptom.
- Keep the change to the fix; leave unrelated refactors and cleanup out.

## Output Format

```text
# DIAGNOSIS
- Reproduction: <command or steps> -> <observed failure>
- Root cause: <file:line> <mechanism>
- Evidence: <confirmed hypothesis and observation>
- Regression: <test> RED -> GREEN
- Remaining risk: <item> | none
```
