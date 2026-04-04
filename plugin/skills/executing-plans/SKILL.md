---
name: executing-plans
description: "Executes written implementation plans one bounded task at a time with checkpoint and review gates. Use when: executing a plan in a dedicated session without letting the main thread accumulate unnecessary context."
---

# Executing Plans

## Overview

Load the plan, then execute exactly one active task at a time.

**Core principle:** one bounded task, one worker owner, one artifact, one review.

## Process

### Step 0: Load Persisted Tasks

1. Call `TaskList`.
2. Load `<plan-path>.tasks.json` if present.
3. Resume from the first `pending` or `in_progress` task.

### Step 1: Read the Plan Once

1. Read the plan file once.
2. Validate the next task only.
3. Do not keep a running narrative for completed tasks in the main thread.

### Step 2: Execute One Task

For the current task only:

1. Mark it `in_progress`.
2. Extract `verifyCommand`, `acceptanceCriteria`, and file set.
3. Apply CP1 and build one task-scoped context bundle.
4. If routing is not `CLAUDE`, apply CP2 and route to one worker.
5. Reuse that worker `SESSION_ID` only for fixes on the same task, and send deltas only.
6. Require External Response Protocol v1.1 with final file content preferred and unified diff fallback.
7. If CP3 is triggered, reconcile external responses and decide whether to proceed, retry, continue, or ask the user.
8. Run verification.
9. Run CP4 Final Spec Review.
10. Mark the task `completed` only if CP4 returns `PASS`.
11. Persist a tiny handoff summary to `.tasks.json` or project memory:
    - task id
    - worker used
    - context refs used
    - files changed
    - verify command result
    - CP4 status
    - open follow-ups

### Step 3: Report Briefly

After each completed task:
- what changed
- verification result
- next task

Do not dump prior task history back into the session.

## Rules

- Default to one active task, not batches of three.
- Do not ask a worker for a prototype that Claude will later rewrite.
- Do not re-explain the whole plan to the worker. Send only the current bounded task.
- Do not send the full CP0 discovery blob when a task-scoped context bundle will do.
- Use `CROSS_VALIDATION` only when the current task cannot be narrowed to one owner.

## Completion

After all tasks complete:
- use `superpowers:verifying-before-completion`
