---
name: verifying-before-completion
description: "Final verification before marking work complete. Use when: finishing a task, completing a plan, or before reporting success. Keywords: verify, check, complete, done, finish"
---

# Verifying Before Completion

## Overview

Never declare work complete without verification. Run tests, check the original requirements, and confirm no regressions.

## Verification Checklist

### 1. Run Integration Checks

- Execute the exact integration checks from the phase or final plan
- All tests must pass
- No new errors or warnings

### 2. Check Original Requirements

- Review the original user request
- Verify each acceptance criterion is met
- Confirm file changes match expected scope

### 3. Run CP4 Phase Review

Apply CP4 to determine:
- `PASS` - Spec fully satisfied
- `PASS_WITH_DEBT` - Usable with explicit non-blocking debt
- `FAIL` - Does not satisfy original request

### 4. Check for Regressions

- Run related test suites
- Verify no unintended side effects
- Check that existing functionality still works

## Completion Report

After verification, report:
- Task completed
- Files changed
- Integration check result
- CP4 status
- Any open follow-ups

## Rule

Do not report final completion until all phases return `PASS` or `PASS_WITH_DEBT` and final integration checks pass. If CP4 returns `FAIL`, address gaps before completion.
