# Routing Quick Heuristics (Non-Normative)

This file is a lightweight cheat sheet. It is **not** the routing decision algorithm.

Prefer semantic routing via `coordinating-multi-model-work/routing-decision.md` and invoke the MCP tools (`mcp__codex__codex`, `mcp__gemini__gemini`) accordingly.

## High-signal defaults

- UI/components/styles/interactions → **GEMINI**
- APIs/databases/security/performance/concurrency → **CODEX**
- Full-stack changes or uncertain debugging → **CROSS_VALIDATION**
- Pure docs / trivial edits → **CLAUDE**

## Common file hints (examples)

- `**/*.tsx`, `**/*.css` → GEMINI
- `**/*.go`, `**/*.py`, `**/*.sql`, `**/*.sh` → CODEX
- Mixed set across frontend + backend → CROSS_VALIDATION

## Reminder

If you choose `Routing != CLAUDE`, apply `coordinating-multi-model-work/GATE.md` immediately (evidence or BLOCKED).