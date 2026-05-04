---
name: executing-plans
description: "Executes written implementation plans one phase at a time with executor, reviewer, and integrator gates. Use when: executing a plan in a dedicated session without letting the main thread accumulate unnecessary context."
---

# Executing Plans

## Overview

Load the plan, then execute exactly one active phase at a time.

**Core principle:** one phase, one primary executor, one Claude review, one integration gate.

## Process

### Step 0: Load the Plan

1. Read the plan file once.
2. Identify the single active phase to execute in this session.
3. Prefer an explicitly requested phase; otherwise use the next phase that is not already reflected in the repo state.
4. Confirm the phase contains 2-4 related tasks. If it is too small or too broad, re-scope before dispatch.

### Step 1: Prepare The Phase

1. Validate the active phase only.
2. Extract its owner, task list, file set, acceptance criteria, reviewer checklist, and integration checks.
3. Do not keep a running narrative for completed phases in the main thread.

### Step 2: Executor

For the current phase only:

1. Apply CP1 and build one phase-scoped context bundle.
2. If routing is not `CLAUDE`, apply CP2 and route to one worker.
3. Route to `Codex` first for most implementation.
4. Route to `Gemini` only when the phase is UI-heavy: visual layout, components, styling, interactions, or animation dominate the work.
5. If any Codex or Gemini MCP call fails, output `BLOCKED`; do not retry or switch executors.
6. Reuse the worker `SESSION_ID` only for fixes on the same phase, and send deltas only.
7. Workers edit files directly via MCP write tools and respond using External Response Protocol v1.1; the response lists `## FILES MODIFIED` without duplicating file content.

### Step 3: Reviewer

Claude reviews the executor output against the phase reviewer checklist.

1. Check spec satisfaction and regressions called out by the phase.
2. Run or inspect the phase verification result.
3. Return exactly one status:
   - `PASS` - phase fully satisfies the checklist
   - `PASS_WITH_DEBT` - phase is usable, integration can continue, and debt is explicit
   - `FAIL` - phase has a blocking gap that must be fixed before integration
4. If status is `FAIL`, send one bounded follow-up to the same executor session.

### Step 4: Integrator

Run integration after each reviewed phase:

1. Run the phase integration checks.
2. Check that the repo still builds or tests at the level required by the phase.
3. Capture a brief phase handoff note:
   - phase completed
   - worker used
   - files changed
   - review status
   - integration check result
   - debt or follow-ups
4. Move to the next phase only after the integration gate returns `PASS` or `PASS_WITH_DEBT`.

### Step 5: Final Summary

Only after all phases finish:

1. Run the final integration section from the plan.
2. Produce the final summary.
3. Include remaining debt only if a phase returned `PASS_WITH_DEBT`.

## Legacy CP Compatibility

When a plan still uses CP language:

1. CP1 routes the active phase.
2. CP2 is the executor step.
3. CP3 is used only for reconciliation when external output is conflicting or incomplete.
4. CP4 is the reviewer step and returns `PASS`, `PASS_WITH_DEBT`, or `FAIL`.

## Rules

- Default to one active phase, not one tiny task.
- Do not ask a worker for a prototype that Claude will later rewrite.
- Do not re-explain the whole plan to the worker. Send only the current phase.
- Do not send the full CP0 discovery blob when a phase-scoped context bundle will do.
- Use `CROSS_VALIDATION` only when the current phase cannot be narrowed to one owner.
- Do not produce a project final summary until all phases complete.

## Completion

After all phases complete:
- use `superpowers:verifying-before-completion`
