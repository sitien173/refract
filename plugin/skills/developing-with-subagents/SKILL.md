---
name: developing-with-subagents
description: "Executes plans in the current session by dispatching one worker-owned task at a time and ending each task with Claude CP4 final spec review. Use when: you want same-session execution without turning the main thread into a long narrative log."
---

# Subagent-Driven Development

## Overview

Execute one bounded task at a time by routing it to Codex or Gemini, then end with CP4 final spec review.

## Process

1. Read the plan once.
2. Extract the current bounded task only.
3. Build a task-scoped context bundle for that task.
4. Route that task to one worker.
5. Reuse the same worker session for follow-up fixes on that task, and send deltas only.
6. If CP3 is triggered, reconcile external responses before final review.
7. Run CP4 Final Spec Review in Claude.
8. Mark the task complete only if CP4 returns `PASS`.
9. If CP4 returns `PARTIAL` or `FAIL`, loop back with a bounded follow-up.
10. Move to the next bounded task only after `PASS`.

## Rules

- Keep the controller thread small.
- Do not accumulate rich summaries for every step.
- Do not repaste full CP0 discovery output into each worker prompt.
- Do not ask workers for draft-only outputs.
- Ask workers for External Response Protocol v1.1 with full file content first and unified diff second.
- `CROSS_VALIDATION` is for unresolved design conflicts, not routine implementation.
- CP4 is spec-only. Do not treat it as a code quality review pass.

## Model Strategy

| Role | Model | Selection Rule |
| ---- | ----- | -------------- |
| Backend and systems implementation | Codex MCP (`mcp__codex__codex`) | CODEX routing |
| Frontend implementation | Gemini MCP (`mcp__gemini__gemini`) | GEMINI routing |
| Final Spec Reviewer | Claude main thread | Always CP4 |

## Checkpoints

- CP1 before dispatching the worker
- CP2 when CP1 routes the current bounded task to an external model
- CP3 after CP2 only when reconciliation is needed
- CP4 as the final step on every task

## Integration

- `superpowers:writing-plans`
- `superpowers:verifying-before-completion`
- `superpowers:coordinating-multi-model-work`
