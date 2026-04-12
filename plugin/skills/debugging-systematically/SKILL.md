---
name: debugging-systematically
description: "Systematic debugging with evidence-based root cause analysis. Use when: fixing bugs, investigating failures, diagnosing test failures, or tracing unexpected behavior. Keywords: debug, fix, error, failing, broken, investigate"
---

# Debugging Systematically

## Overview

Debug with evidence, not guesses. Gather facts, form hypotheses, test them, and trace to root cause.

## Process

### Step 1: Reproduce

- Get exact reproduction steps
- Capture error messages, stack traces, logs
- Identify minimal reproduction case

### Step 2: Gather Evidence

- Read relevant code paths
- Check test outputs and CI logs
- Use Auggie for broader context if needed

### Step 3: Form Hypotheses

- List 2-3 possible causes ranked by likelihood
- Each hypothesis must be testable
- Start with the most likely

### Step 4: Test Hypotheses

- Add diagnostic logging or assertions
- Run targeted tests
- Eliminate hypotheses with evidence

### Step 5: Fix and Verify

- Fix the root cause, not symptoms
- Run verification command
- Confirm no regressions

## Multi-Model Integration

For complex debugging:
- Route to **Codex** for backend/systems issues
- Use **cross-validation** only if failure mode stays ambiguous after one pass
- Apply CP workflow: CP0 context → CP1 routing → CP2 execution → CP4 verification

## Key Principles

- Evidence over intuition
- Smallest possible fix
- Verify before declaring done
- Document root cause for future reference
