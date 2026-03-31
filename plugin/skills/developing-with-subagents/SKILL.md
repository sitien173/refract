---
name: developing-with-subagents
description: "Executes plans by dispatching a fresh subagent per task with spec review and quality review. Use when: executing implementation plans in the current session with independent tasks."
---

# Subagent-Driven Development

## Overview

Execute a plan by routing each task to the appropriate external model (Codex or Gemini based on domain), with spec compliance review first (Opus), then Opus code quality review on every code-changing path.

## When to Use

- You already have an implementation plan
- Tasks are mostly independent
- You want to stay in the current session

## The Process

```text
Read plan → extract tasks → create TodoWrite
For each task:
  Route to external model (Codex/Gemini)
  Answer questions if needed
  External model implements, tests, commits
  Spec reviewer checks compliance
  Opus performs quality review
  Mark task complete
Finish with final review and finishing-development-branches
```

## Model Strategy

| Role | Model | Selection Rule |
| ---- | ----- | -------------- |
| Backend and systems implementation | Codex MCP (`mcp__codex__codex`) | CODEX routing |
| Frontend implementation | Gemini MCP (`mcp__gemini__gemini`) | GEMINI routing |
| Spec Reviewer | Opus | Always Opus |
| Quality Reviewer | Opus | Always Opus |

## Collaboration Checkpoints

- **CP1** before dispatching the implementer
- **CP2** during execution if stalled or uncertain
- **CP3** after implementation, before completion

## Integration

- `superpowers:writing-plans`
- `superpowers:requesting-code-review`
- `superpowers:finishing-development-branches`
- `superpowers:coordinating-multi-model-work`
