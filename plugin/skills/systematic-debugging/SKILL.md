---
name: systematic-debugging
description: "Establishes a reproducible root cause before fixing bugs, failures, regressions, or performance problems."
---

# Systematic Debugging

This skill owns diagnosis. `coordinating-multi-model-work` owns delegation;
`test-driven-development` owns the regression-test cycle.

## Iron Law

```text
NO FIX WITHOUT ROOT-CAUSE EVIDENCE
```

## Workflow

1. **Reproduce.** Capture the full error, exact steps, and expected behavior.
2. **Trace.** Follow bad state backward across component boundaries to the first
   divergence.
3. **Compare.** Read a similar working path and list relevant differences.
4. **Hypothesize.** State one falsifiable cause and test the smallest variable.
5. **Fix.** Pass the reproduction and root cause into a failing regression test,
   then apply the smallest source correction.

## Stop Conditions

- If reproduction fails or evidence contradicts the hypothesis, return to
  tracing.
- After three failed fixes, stop and question the model or architecture.
- Do not proceed without a regression test unless the user explicitly waives it.

## Rules

- Test one hypothesis at a time.
- Fix the source, not a downstream symptom.
- Exclude unrelated refactors and cleanup.
- Record reproduction, root cause, RED → GREEN evidence, and remaining risk.
