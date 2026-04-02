---
name: using-superpowers
description: Establish how to operate Superpowers CCG inside Cursor. Use when starting work, deciding which skill to apply, or setting the orchestration model for a task.
---

# Using Superpowers In Cursor

## Core behavior

1. If there is even a small chance that a skill applies, use the skill before proceeding.
2. Keep Cursor in the orchestrator role for anything beyond trivial local edits or documentation.
3. Break work into bounded tasks with a file set and a verification command.
4. Route implementation to one worker at a time:
   - `codex` for backend and systems
   - `gemini` for frontend and styling
5. Only use cross-validation when a single worker cannot safely own the decision.

## Standard flow

1. Use `brainstorming` before open-ended feature design.
2. Use `writing-plans` to produce bounded execution tasks.
3. Use `executing-plans` to run the work one task at a time.
4. Use `verifying-before-completion` before reporting completion.

## Commands

- `/brainstorm` for discovery and design
- `/write-plan` for turning scope into bounded tasks
- `/execute-plan` for worker-driven execution
