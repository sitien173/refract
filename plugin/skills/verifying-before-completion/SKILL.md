---
name: verifying-before-completion
description: "Requires running verification commands and confirming output before making success claims. Use when: about to claim work is complete, fixed, or passing, before committing or creating PRs. Keywords: verify, evidence, completion check, test output, proof"
---

# Verification Before Completion

## Overview

Do not claim completion without fresh verification evidence.

**Core principle:** Evidence before claims, always.

## The Iron Law

```
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

If you haven't run the verification command in this message, you cannot claim it passes.

## Protocol Threshold (Required)

Follow `skills/shared/protocol-threshold.md`. The hook injects CP reminders automatically.

## The Gate Function

**CP3 note:** If CP2 produced cross-validation output or other non-trivial external feedback, complete CP3 Reconciliation before making completion claims. CP3 does not replace running verification commands.

**CP4 note:** Always complete CP4 Final Spec Review after verification. CP4 checks spec satisfaction only and does not replace running commands.

```
BEFORE claiming any status or expressing satisfaction:

1. IDENTIFY: What command proves this claim?
2. RUN: Execute the FULL command (fresh, complete)
3. READ: Full output, check exit code, count failures
4. VERIFY: Does output confirm the claim?
   - If NO: State actual status with evidence
   - If YES: State claim WITH evidence
5. ONLY THEN: Make the claim
```

## Minimum Evidence

- Tests pass: fresh test output with zero failures
- Build succeeds: fresh build command with exit code 0
- Bug fixed: reproduction or regression check now passes
- Requirements met: compare the result against the request or plan, not just test output
- Agent completed: inspect the diff and run your own verification

## Red Flags

- Using "should", "probably", "seems to"
- Expressing completion before running the command
- About to commit, open a PR, or move on without verification
- Trusting an agent or prior run instead of fresh output
- Using partial checks to justify a broader claim

## Key Patterns

**Tests:**

```
✅ [Run test command] [See: 34/34 pass] "All tests pass"
❌ "Should pass now" / "Looks correct"
```

**Build:**

```
✅ [Run build] [See: exit 0] "Build passes"
❌ "Linter passed" (linter doesn't check compilation)
```

**Requirements:**

```
✅ Re-read plan → Create checklist → Verify each → Report gaps or completion
❌ "Tests pass, phase complete"
```

**Agent delegation:**

```
✅ Agent reports success → Check VCS diff → Verify changes → Report actual state
❌ Trust agent report
```

## When To Apply

**ALWAYS before:**

- completion claims
- commit or PR messages
- handoffs to the next task
- bug-fix confirmations
- "all good" or equivalent status updates

## Multi-Model Cross-Verification

See `skills/shared/multi-model-integration-section.md` for routing, invocation, and fallback rules.

**CRITICAL:** Cross-model verification is additional to, not a replacement for running actual commands. Never claim success based solely on model confirmation.
