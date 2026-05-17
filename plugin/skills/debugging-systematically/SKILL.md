---
name: debugging-systematically
description: "Evidence-based root-cause debugging. Use for bugs, test failures, regressions, unexpected behaviour, or any debug/fix/error/broken/investigate request."
---

# Debugging Systematically

## Use When

- User reports a bug, failure, broken behaviour, or test failure.
- Root cause is unknown.
- Fix needs evidence, not guessing.

## Workflow

1. **Reproduce.** Collect exact steps, error messages, stack traces, logs, minimal failing case.
2. **Gather evidence.** Read relevant paths, test output, CI logs. Use Grep/Glob/Read freely.
3. **Hypothesise.** Form 2–3 ranked, testable hypotheses.
4. **Test the top hypothesis.** Targeted assertions, logs, or focused tests confirm or eliminate it.
5. **Fix root cause.** Smallest safe change. Route by side via `coordinating-multi-model-work`:
   - Claude — single-file or trivial fix.
   - Codex — back-side bug (logic, database, system, infra).
   - Gemini — front-side bug (UI, CSS, layout, interaction).
6. **Verify.** Failing repro now passes; targeted tests + regression checks pass.

## Hard Rules

- Evidence over intuition.
- Fix root cause, not symptoms.
- No broad refactor while debugging unless the root cause demands it.
- No completion claim before verification.

## References

- `skills/coordinating-multi-model-work/SKILL.md` — routing and Review gate.
- `skills/debugging-systematically/root-cause-tracing.md` — root-cause technique.
- `skills/debugging-systematically/condition-based-waiting.md` — flake debugging.
- `skills/debugging-systematically/defense-in-depth.md` — guard layers.
- `skills/verifying-before-completion/SKILL.md` — final verification.
