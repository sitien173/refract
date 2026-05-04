---
name: debugging-systematically
description: "Systematic debugging with evidence-based root cause analysis. Use when fixing bugs, investigating failures, diagnosing test failures, tracing unexpected behavior, or handling debug, fix, error, failing, broken, and investigate requests."
---

# Debugging Systematically

## Use When

- User reports a bug, failure, broken behavior, or test failure.
- Root cause is unknown.
- A fix needs evidence rather than guessing.

## Workflow

1. Reproduce: collect exact steps, error messages, stack traces, logs, and minimal failing case.
2. Gather evidence: read relevant paths, test outputs, CI logs, and Auggie context when scope is broad.
3. Form 2-3 ranked, testable hypotheses.
4. Test the most likely hypothesis first with targeted checks, assertions, logs, or focused tests.
5. Fix the root cause with the smallest safe change.
6. Verify with the failing repro, targeted tests, and regression checks.

## Hard Rules

- Evidence over intuition.
- Fix root cause, not symptoms.
- Do not make broad refactors while debugging unless required by the root cause.
- For complex debugging, route through CP0-CP4 and use Codex by default.
- Use cross-validation only if the failure mode stays ambiguous after one pass.
- Do not report completion before verification.

## References

- `skills/shared/protocol-threshold.md` — CP0-CP4 routing and review gates.
- `skills/shared/supplementary-tools.md` — Auggie and Grok Search for broad context or external issue research.
- `skills/verifying-before-completion/SKILL.md` — final verification rules.
