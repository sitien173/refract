---
name: test-driven-development
description: "Use when implementing any feature or bugfix, before writing implementation code. Covers writing the failing test first, watching it fail, then minimal code to pass."
---

# Test-Driven Development

Write the test first. Watch it fail. Write the minimal code to pass. Refactor.
Routing, gates, and the worker response format live in
`coordinating-multi-model-work` — load it first.

## The Iron Law

```
NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST
```

If you didn't watch the test fail, you don't know it tests the right thing.
Wrote code before the test? Delete it and start over — don't keep it "as
reference", don't "adapt" it while writing the test. **Violating the letter of
this rule violates the spirit of it.**

## Use When

- Implementing a new feature, behaviour change, or refactor.
- Fixing a bug — the failing test reproduces the bug first.
- Exceptions (ask the user): throwaway prototypes, generated code, config files.

## Workflow

1. **RED — write one failing test.** One behaviour, clear name, real code (mocks
   only if unavoidable). It expresses what the code *should* do.
2. **Verify RED — run it, watch it fail.** Mandatory. Confirm it fails for the
   right reason (feature missing), not a typo. Passes already? It tests existing
   behaviour — fix the test.
3. **GREEN — minimal code to pass.** Simplest thing that works. No extra
   features, options, or "while I'm here" changes (YAGNI).
4. **Verify GREEN — run it, watch it pass.** This test passes, others still pass,
   output is clean. Failing? Fix the code, not the test.
5. **REFACTOR — clean up while green.** Remove duplication, improve names. No new
   behaviour. Tests stay green.
6. Repeat for the next behaviour.

## CCG Routing

- **Coordinator (trivial edit):** run the cycle directly; the RED→GREEN run is the evidence.
- **Codex / Gemini phase:** test-first is task-1 of any feature/bugfix; the worker records RED→GREEN per the worker contract.
- **Review gate:** the coordinator FAILs any phase that adds production code without failing-test-first evidence.

(Routing table, gates, and worker mechanics are canonical in `coordinating-multi-model-work`.)

## Hard Rules

- No production code without a failing test that you watched fail first.
- Minimal GREEN code only — simplicity is the goal, not a later cleanup.
- Fix the code to satisfy the test; never weaken the test to pass.
- Bug fix = failing test reproducing the bug, then fix. Never fix without a test.
- User override ("no TDD here") always wins; otherwise the Iron Law holds.

## Red Flags — STOP and start over

- Code written before its test, or test added "later".
- Test passes immediately / you can't explain why it failed.
- "I already manually tested it" · "tests after achieve the same thing".
- "Keep it as reference" · "deleting hours of work is wasteful" (sunk cost).
- "TDD is dogmatic, I'm being pragmatic" · "this case is different".

## Rationalizations

| Excuse | Reality |
|---|---|
| "Too simple to test" | Simple code breaks. The test takes 30 seconds. |
| "I'll test after" | Tests written after pass immediately — they prove nothing. |
| "Tests-after are the same" | After = "what does this do?"; first = "what should it do?" |
| "Already manually tested" | Ad-hoc, no record, can't re-run. Automated is systematic. |
| "Deleting work is wasteful" | Sunk cost. Unverified code is the debt, not the rewrite. |
| "Hard to test" | Hard to test = hard to use. Listen to the test; simplify design. |

## References

- `skills/coordinating-multi-model-work/SKILL.md` — gates, routing, worker response format.
- `skills/systematic-debugging/SKILL.md` — Phase 4 fixes start from a failing test.
- `skills/verifying-before-completion/SKILL.md` — fresh evidence before claiming done.
