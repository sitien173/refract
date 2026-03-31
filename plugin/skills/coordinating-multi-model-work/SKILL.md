---
name: coordinating-multi-model-work
description: "Routes bounded implementation tasks to Codex (backend and systems) or Gemini (frontend) via MCP tools. Claude is orchestrator-only and should stay out of the implementation hot path. Use when: implementation, debugging, refactoring, UI work, APIs, databases, scripts, CI/CD, or cross-model arbitration."
---

# Coordinating Multi-Model Work

## Overview

Claude is the orchestrator. It routes tasks, coordinates workers, and integrates results, but never writes implementation code.

Use this module to route one bounded task at a time:
- **Codex** — backend and systems
- **Gemini** — frontend

## Core Rules

1. Reduce the current work to one bounded task with a clear file set and verification command.
2. Route that bounded task to exactly one worker unless there is real architectural uncertainty.
3. Reuse the same worker `SESSION_ID` for follow-up fixes on that task.
4. Ask for `diff-or-questions`, not prototypes, essays, or full rewrites.
5. After the worker completes, review the artifact with Opus.

## Cross-Validation

`CROSS_VALIDATION` is rare. Use it only when:
- the task genuinely spans frontend and backend at the same time, or
- two viable designs remain after scope reduction, or
- the failure mode is still ambiguous after one worker pass.

Do not use cross-validation as the default for ordinary implementation work.

## Checkpoint Workflow

At CP1, CP2, and CP3:
1. Decide routing
2. Apply `GATE.md`
3. Continue only with evidence

## Response Protocol

All external model prompts must reference Serena memory `global/response_protocol`.

## Reference Files

- `coordinating-multi-model-work/checkpoints.md`
- `coordinating-multi-model-work/routing-decision.md`
- `coordinating-multi-model-work/GATE.md`
- `coordinating-multi-model-work/INTEGRATION.md`
- `coordinating-multi-model-work/review-chain.md`
- `coordinating-multi-model-work/cross-validation.md`
