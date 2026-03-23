# Routing Quick Heuristics (Non-Normative)

This file is a lightweight cheat sheet. It is **not** the routing decision algorithm.

Prefer semantic routing via `coordinating-multi-model-work/routing-decision.md` and invoke the MCP tools (`mcp__codex__codex`, `mcp__gemini__gemini`) accordingly.

## High-signal defaults

- UI/components/styles/interactions → **GEMINI**
- APIs/databases/security/performance/concurrency → **CODEX**
- Full-stack changes or uncertain debugging → **CROSS_VALIDATION**
- Simple documentation edits / trivial edits → **CLAUDE**

## Common file hints (examples)

- `**/*.tsx`, `**/*.css` → GEMINI
- `**/*.go`, `**/*.py`, `**/*.sql`, `**/*.sh` → CODEX
- Mixed set across frontend + backend → CROSS_VALIDATION
- Design docs, implementation docs, requirements specs, architecture docs, and other critical documentation → CROSS_VALIDATION

## Cursor (Not a Routing Target)

Cursor (`mcp__cursor__cursor`) is a **code quality layer**, not a routing destination. Do not create a `CURSOR` routing label. Cursor activates automatically at:
- Subagent stage 2 (replaces Opus quality reviewer)
- CP3 when code changed (parallel with domain expert)

See `checkpoints.md` for `QualityGateRequired` decision table.

## Reminder

If you choose `Routing != CLAUDE`, apply `coordinating-multi-model-work/GATE.md` immediately (evidence or BLOCKED).
