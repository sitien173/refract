---
name: writing-plans
description: Turn a request into a short ordered plan of bounded tasks. Use when implementation spans multiple files, decisions, or verification steps.
---

# Writing Plans

## Requirements

1. Keep the plan short and execution-oriented.
2. Each task must name its likely files or subsystem.
3. Each task must have one owner:
   - Cursor
   - Codex
   - Gemini
4. Each task should include a verification command or validation method.

## Preferred format

1. Goal
2. Constraints
3. Ordered bounded tasks
4. First task to execute now

## Avoid

- vague “investigate everything” steps
- mixing backend and frontend implementation in one bounded task
- plans that require the orchestrator to restate the same context repeatedly
