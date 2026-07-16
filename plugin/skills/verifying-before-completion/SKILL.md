---
name: verifying-before-completion
description: "Use when about to claim work is complete, fixed, or passing — before committing, creating PRs, or reporting done. Requires running verification and confirming output before any success claim."
---

# Verifying Before Completion

Claiming work is complete without verification is dishonesty, not efficiency.
Evidence before claims, always. The Review gate semantics live in
`coordinating-multi-model-work` — load it first.

## The Iron Law

```
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

If you haven't run the verification command *in this message*, you cannot claim
it passes. **Violating the letter of this rule violates the spirit of it** —
paraphrases, synonyms, and implied success all count as claims.

## Use When

- Work appears complete and the user expects a final status.
- A phase, plan, bug fix, or refactor is about to be marked done.
- Before ANY commit, push, PR, task hand-off, or expression of satisfaction
  ("Great!", "Done!", "should work now").

## The Gate Function

```
Before claiming any status:
1. IDENTIFY  — which command proves this claim?
2. RUN       — execute the full command, fresh and complete
3. READ      — full output, exit code, failure count
4. VERIFY    — does the output actually confirm the claim?
5. ONLY THEN — state the claim WITH its evidence
Skip a step = guessing, not verifying.
```

## Workflow

1. Run the declared integration checks (build, lint, type-check, tests, smoke)
   fresh — never reuse a previous run.
   For external jobs, use a disposable detached worktree at
   `job.result.commit`. Terminal execution worktrees are already released.
2. Read full output and exit codes; compare against the original request and
   acceptance criteria, line by line.
3. Confirm changed files match the expected scope.
4. Run the Review gate from `coordinating-multi-model-work`.
5. For bug fixes, verify the red→green cycle: the regression test fails without
   the fix and passes with it (don't trust a test that only passed once).
6. Report: task status, files changed, integration result with evidence, Review
   status, open follow-ups.

## Common Failures

| Claim | Requires | Not sufficient |
|---|---|---|
| Tests pass | Test output: 0 failures | A previous run, "should pass" |
| Build succeeds | Build command: exit 0 | Linter passed, "logs look fine" |
| Bug fixed | Original-symptom test passes | Code changed, assumed fixed |
| Regression test works | Red→green cycle verified | Test passed once |
| Worker completed | Diff shows requested changes | Worker reported "success" |
| Requirements met | Line-by-line checklist | Tests passing |

## Hard Rules

- No completion claim until required checks pass, or Review returns
  `PASS_WITH_DEBT` with explicit non-blocking debt. `FAIL` blocks completion.
- Unrun tests are not passed tests. Partial checks prove nothing.
- Trust no worker/agent success report — verify the VCS diff directly.
- Review stays scoped to spec + changed files; broader audit only if the phase
  checklist asks for it.
- For external code changes, submit the derived reviewer read workflow with the
  latest write job as parent. Pass the stored routing profile. Use a unique
  reviewer context. Fold findings into Review status before `job_integrate`.

## Red Flags — STOP

- "should", "probably", "seems to" · satisfaction before evidence.
- About to commit/push/PR without having run verification.
- Trusting a worker's success report · relying on a partial check.
- "Just this once" · "I'm tired and want this done".

## Rationalizations

| Excuse | Reality |
|---|---|
| "Should work now" | Run the verification. |
| "I'm confident" | Confidence ≠ evidence. |
| "Linter passed" | Linter ≠ compiler ≠ tests. |
| "Worker said success" | Verify independently via the diff. |
| "Partial check is enough" | Partial proves nothing. |
| "Different words, rule doesn't apply" | Spirit over letter. |

## References

- `skills/coordinating-multi-model-work/SKILL.md` — Review gate, PASS / PASS_WITH_DEBT / FAIL semantics.
- `skills/test-driven-development/SKILL.md` — red→green evidence for regression tests.
- `skills/systematic-debugging/SKILL.md` — verify a fix resolved the root cause.
