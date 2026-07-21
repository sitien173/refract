---
name: systematic-debugging
description: "Finds root causes before fixes. Use for bugs, test failures, crashes, regressions, performance issues, or unexpected behavior."
---

# Systematic Debugging

Load `coordinating-multi-model-work` first when the investigation may lead to
repository changes.

## Iron Law

```text
NO FIX WITHOUT ROOT-CAUSE EVIDENCE
```

## Workflow

1. **Reproduce.** Read the full error and stack trace. Record an exact, reliable
   reproduction and the expected behavior.
2. **Trace.** Inspect recent changes and follow the bad state backward to its
   source. At component boundaries, capture inputs and outputs to locate the
   first divergence.
3. **Compare.** Find similar working code, read it completely, and list every
   relevant difference from the failing path.
4. **Hypothesize.** State one falsifiable claim: “X causes the failure because
   Y.” Test the smallest possible variable; do not stack speculative changes.
5. **Fix.** Add a failing regression test, confirm it fails for the diagnosed
   reason, apply the smallest source fix, then run focused and broader checks.

For unclear, cross-component, or architecture-sensitive failures, use Gate 1
consultation. The implementation prompt must carry the reproduction and
root-cause evidence; the Review gate rejects symptom-only fixes.

## Stop Conditions

- Three failed fix attempts: stop, question the model or architecture, and ask
  the user before another attempt.
- The issue cannot be reproduced or evidence contradicts the hypothesis: return
  to tracing, not implementation.
- A proposed fix lacks a regression test: do not submit it unless the user
  explicitly waives testing.

## Rules

- One hypothesis and one experimental change at a time.
- Fix the source, not a downstream symptom.
- Do not bundle refactors or unrelated cleanup with a fix.
- Record reproduction, root cause, RED → GREEN evidence, and remaining risk.

## References

- `skills/test-driven-development/SKILL.md` — regression-test cycle.
- `skills/verifying-before-completion/SKILL.md` — fresh completion evidence.
