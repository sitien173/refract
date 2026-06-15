---
name: systematic-debugging
description: "Use when encountering any bug, test failure, or unexpected behaviour, before proposing fixes. Covers root-cause investigation, hypothesis testing, and fixing at the source."
---

# Systematic Debugging

Find the root cause before touching anything. Random fixes waste time and create
new bugs; symptom patches mask the real defect. Routing and gates live in
`coordinating-multi-model-work` — load it first.

## The Iron Law

```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
```

You cannot propose a fix until Phase 1 is complete. **Violating the letter of
this process violates the spirit of debugging.** Systematic is *faster* than
guess-and-check thrashing — especially under time pressure.

## Use When

- Any test failure, bug, crash, unexpected behaviour, build/integration failure,
  or performance problem.
- *Especially* when: under time pressure, a fix seems "obvious", you've already
  tried multiple fixes, or the last fix didn't work.

## Workflow — Four Phases (complete each before the next)

1. **Root cause.** Read the full error/stack trace. Reproduce reliably. Check
   recent changes (`git diff`, new deps, config). In multi-component systems, add
   diagnostic logging at each boundary and run once to see *where* it breaks.
   Trace the bad value backward to its source.
2. **Pattern analysis.** Find similar working code. Read any reference
   implementation completely. List every difference between working and broken —
   "that can't matter" is how bugs hide.
3. **Hypothesis & test.** State one hypothesis: "X is the root cause because Y."
   Make the smallest change that tests it — one variable at a time. Wrong? Form a
   new hypothesis; don't stack fixes.
4. **Fix the root cause.** Start with a failing test that reproduces the bug
   (`test-driven-development`). Apply one fix. Verify the test passes and nothing
   else broke. No bundled "while I'm here" changes.

**3+ failed fixes ⇒ STOP.** Each fix revealing a new problem elsewhere means the
architecture is wrong, not the hypothesis. Question fundamentals and ask the user
before attempting fix #4.

## CCG Routing

- Route the bug by side per `coordinating-multi-model-work`; unclear or full-stack failure → Cross-Validation to localise the failing layer first.
- The dispatch prompt must require a root-cause hypothesis **with evidence** (boundary logs / failing test) before any fix commit.
- **Review gate:** the coordinator FAILs a fix lacking root-cause evidence or a failing-test-first reproduction.

## Hard Rules

- No fix before Phase 1 is complete — investigation precedes proposals.
- One hypothesis, one change at a time; never bundle fixes or refactors.
- Every bug fix begins with a failing test reproducing it.
- 3+ failed fixes → stop and question the architecture with the user.

## Red Flags — STOP, return to Phase 1

- "Quick fix now, investigate later" · "just try changing X and see".
- Proposing solutions before tracing the data flow.
- "Skip the test, I'll verify manually" · "it's probably X, let me fix that".
- "One more fix attempt" after 2+ failures · each fix breaks something new.

## Rationalizations

| Excuse | Reality |
|---|---|
| "Issue is simple, skip the process" | Simple bugs have root causes too; the process is fast for them. |
| "Emergency, no time" | Systematic is faster than thrashing — 95% vs 40% first-fix rate. |
| "Try this first, investigate later" | The first fix sets the pattern. Do it right from the start. |
| "Multiple fixes at once saves time" | Can't isolate what worked; causes new bugs. |
| "Reference too long, I'll adapt it" | Partial understanding guarantees bugs. Read it fully. |
| "I see the problem" | Seeing the symptom ≠ understanding the root cause. |

## References

- `skills/coordinating-multi-model-work/SKILL.md` — routing, Cross-Validation, gates.
- `skills/test-driven-development/SKILL.md` — Phase 4: failing test before the fix.
- `skills/verifying-before-completion/SKILL.md` — verify the fix with fresh evidence.
