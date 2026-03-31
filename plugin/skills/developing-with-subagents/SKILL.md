---
name: developing-with-subagents
description: "Executes plans in the current session by dispatching one worker-owned task at a time with spec review and Opus review. Use when: you want same-session execution without turning the main thread into a long narrative log."
---

# Subagent-Driven Development

## Overview

Execute one bounded task at a time by routing it to Codex or Gemini, then review the resulting artifact.

## Process

1. Read the plan once.
2. Extract the current bounded task only.
3. Route that task to one worker.
4. Reuse the same worker session for follow-up fixes on that task.
5. Run spec review.
6. Run Opus quality review.
7. Mark the task complete.
8. Move to the next bounded task.

## Rules

- Keep the controller thread small.
- Do not accumulate rich summaries for every step.
- Do not ask workers for draft-only outputs.
- Ask workers for `diff-or-questions`.
- `CROSS_VALIDATION` is for unresolved design conflicts, not routine implementation.

## Model Strategy

| Role | Model | Selection Rule |
| ---- | ----- | -------------- |
| Backend and systems implementation | Codex MCP (`mcp__codex__codex`) | CODEX routing |
| Frontend implementation | Gemini MCP (`mcp__gemini__gemini`) | GEMINI routing |
| Spec Reviewer | Opus | Always Opus |
| Quality Reviewer | Opus | Always Opus |

## Checkpoints

- CP1 before dispatching the worker
- CP2 only when the current bounded task stalls
- CP3 after implementation, before completion

## Integration

- `superpowers:writing-plans`
- `superpowers:requesting-code-review`
- `superpowers:finishing-development-branches`
- `superpowers:coordinating-multi-model-work`
