# Collaboration Checkpoints

## Overview

Checkpoints are used at key stages to decide whether external models are needed and to enforce the evidence protocol.

**Key principle:** Claude is orchestrator-only — all implementation code must be routed to `CODEX` or `GEMINI`.

## CP1: Task Analysis

- Collect task goals, involved files, tech stack, and uncertainty.
- Use `coordinating-multi-model-work/routing-decision.md`.
- All tasks requiring code changes must route to an external model.

## CP2: Mid-Review

Trigger when:
- 2 or more failed attempts occur
- Progress stalls
- Ambiguity remains
- New security, performance, or data consistency risks appear

Prefer `CROSS_VALIDATION` when CP2 fires.

## CP3: Quality Gate

- If `Routing != CLAUDE`, domain evidence is required from the implementing model.
- If code changed, apply the review chain.
- If no code changed, skip quality review.

## User Override

- "Use Codex" / "Use Gemini" / "Cross-validate" force corresponding routing.
- "Do not use external models" forces `CLAUDE` for docs/coordination only.
