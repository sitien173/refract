---
name: executing-plans
description: "Executes written implementation plans task-by-task with review checkpoints between batches. Use when: having a plan document to execute in a dedicated session. Keywords: execute plan, implementation, batch execution, checkpoints"
---

# Executing Plans

## Overview

Load plan, review critically, execute tasks in batches, report for review between batches.

**Core principle:** Batch execution with checkpoints for architect review.

**Announce at start:** "I'm using the executing-plans skill to implement this plan."

## Protocol Threshold (Required)

Follow `skills/shared/protocol-threshold.md`. The hook injects CP reminders automatically.

## The Process

### Step 0: Load Persisted Tasks

1. Call `TaskList` to check for existing native tasks in this session
2. **Locate tasks file:** Look for `<plan-path>.tasks.json` (same directory as the plan `.md`)
3. **If tasks file exists AND native tasks are empty** (fresh session): recreate from JSON using TaskCreate:
   - Include full `description` from `.tasks.json` (not just subject — it contains the `json:metadata` fence)
   - Restore `blockedBy` relationships with `TaskUpdate` after all tasks are created
4. **If native tasks already exist:** verify they match the plan, then resume from the first `pending` or `in_progress` task
5. **If neither tasks file nor native tasks exist:** proceed to Step 1b after reviewing the plan

Update `.tasks.json` after every task status change (see Step 2).

### Step 1: Load and Review Plan

1. Read plan file
2. Review critically - identify any questions or concerns about the plan
3. If concerns: Raise them with your human partner before starting
4. If no concerns: Create TodoWrite and proceed

### Step 1b: Bootstrap Tasks from Plan (if needed)

Only run this step if TaskList returned no tasks AND no `.tasks.json` file was found.

1. Parse the plan document for `## Task N:` or `### Task N:` headers
2. For each task found, use TaskCreate with:
   - `subject`: the task title from the plan (e.g. `"Task 1: [Component Name]"`)
   - `description`: full structured content (Goal, Files, Acceptance Criteria, Verify, Steps) with `json:metadata` code fence at the end
   - `activeForm`: present tense action (e.g. `"Implementing X"`)
3. **CRITICAL — Dependencies:** For each task that has `blockedBy` in the plan, call `TaskUpdate` with `addBlockedBy`. Do NOT skip this — dependencies enforce correct execution order.
4. Call `TaskList` to verify `blockedBy` relationships are correctly shown (e.g. "blocked by #1, #2")

### Step 2: Execute Batch

**Default: First 3 tasks**

**Claude Model Selection:** When dispatching Claude subagents for task execution, use `model: sonnet` for implementation work. Sonnet excels at code writing and is more cost-effective than Opus for execution tasks.

Copy this checklist template for each batch:

```
Batch Progress:
- [ ] Task N: [description] - in_progress
- [ ] Task N+1: [description] - pending
- [ ] Task N+2: [description] - pending

Current Task:
- [ ] Checkpoint 1 (Task Analysis) applied
- [ ] All steps followed exactly
- [ ] Checkpoint 2 (Mid-Review) if needed
- [ ] Verifications run
- [ ] Checkpoint 3 (Quality Gate) applied
- [ ] Task marked complete
```

For each task:

1. Mark as `in_progress` (`TaskUpdate status: in_progress`); sync `.tasks.json` (update `"status"` to `"in_progress"`, set `"lastUpdated"` to current ISO timestamp)
2. **Parse task metadata:** Extract the `json:metadata` code fence from the task description to get `verifyCommand` and `acceptanceCriteria`
3. **► CP1 (Task Analysis):** Apply `coordinating-multi-model-work/checkpoints.md`
4. Follow each step exactly (plan has bite-sized steps)
5. **► CP2 (Mid-Review):** If blocked or uncertain, apply `coordinating-multi-model-work/checkpoints.md`
7. **Run verification using metadata:** Execute `verifyCommand` from the parsed metadata. Check each item in `acceptanceCriteria` before proceeding. If verification fails, stop and report — do NOT mark as completed.
8. **► CP3 (Quality Gate):** Before marking complete, run the review chain per `coordinating-multi-model-work/review-chain.md`
9. Mark as `completed` (`TaskUpdate status: completed`); sync `.tasks.json` (update `"status"` to `"completed"`, set `"lastUpdated"` to current ISO timestamp)

### Step 3: Report

When batch complete:

- Show what was implemented
- Show verification output
- Say: "Ready for feedback."

### Step 4: Continue

Based on feedback:

- Apply changes if needed
- Execute next batch
- Repeat until complete

### Step 5: Complete Development

After all tasks complete and verified:

- Announce: "I'm using the finishing-development-branches skill to complete this work."
- **REQUIRED SUB-SKILL:** Use superpowers:finishing-development-branches
- Follow that skill to verify tests, present options, execute choice

## When to Stop and Ask for Help

**STOP executing immediately when:**

- Hit a blocker mid-batch (missing dependency, test fails, instruction unclear)
- Plan has critical gaps preventing starting
- You don't understand an instruction
- Verification fails repeatedly

**Ask for clarification rather than guessing.**

## When to Revisit Earlier Steps

**Return to Review (Step 1) when:**

- Partner updates the plan based on your feedback
- Fundamental approach needs rethinking

**Don't force through blockers** - stop and ask.

## Remember

- Review plan critically first
- Follow plan steps exactly
- Don't skip verifications
- Reference skills when plan says to
- Between batches: just report and wait
- Stop when blocked, don't guess

## Multi-Model Task Execution

See `skills/shared/multi-model-integration-section.md` for routing, invocation, and fallback rules.

Additional notes for plan execution:
- **Check for Model Hint:** If plan includes `Model hint`, respect explicit hints
- **Post-implementation:** Opus reviews per `coordinating-multi-model-work/review-chain.md`

## Supplementary Tools (Optional)

These tools enhance plan execution when available. See `skills/shared/supplementary-tools.md`.

- **Morphllm Fast-Apply:** For tasks involving repeated edits across multiple files (pattern migrations, style enforcement), use Morphllm for token-efficient bulk edits.
- **Serena:** For tasks modifying existing code in large codebases, use Serena to verify symbol references and dependencies before and after changes.
- **Sequential-Thinking:** When a task stalls at CP2 (2+ failed attempts, ambiguous approach), use Sequential-Thinking to systematically decompose the problem.
