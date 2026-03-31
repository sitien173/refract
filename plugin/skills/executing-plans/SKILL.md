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
3. Apply CP1.
4. Route to one worker.
5. Reuse that worker `SESSION_ID` only for fixes on the same task.
6. Apply CP2 only if the task stalls.
7. Run verification.
8. Apply CP3 and run Opus review.
9. Mark the task `completed`.
10. Persist a tiny handoff summary to `.tasks.json` or project memory:
    - task id
    - worker used
    - files changed
    - verify command result
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
- Use `CROSS_VALIDATION` only when the current task cannot be narrowed to one owner.

## Completion

After all tasks complete:
- use `superpowers:finishing-development-branches`
