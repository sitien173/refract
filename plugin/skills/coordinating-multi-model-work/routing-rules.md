# Routing Quick Heuristics (Non-Normative)

This file is a lightweight cheat sheet. It is **not** the routing decision algorithm.

Prefer semantic routing via `coordinating-multi-model-work/routing-decision.md` and invoke the MCP tools (`mcp__codex__codex`, `mcp__gemini__gemini`, `mcp__cursor__cursor`) accordingly.

## High-signal defaults

- APIs/databases/security/performance/concurrency → **CODEX**
- UI/components/styles/interactions → **GEMINI**
- Debugging/refactoring/DevOps/CI-CD/scripts/general implementation → **CURSOR**
- Full-stack changes or uncertain cross-domain debugging → **CROSS_VALIDATION**
- Documentation-only edits / pure coordination (no code) → **CLAUDE**

## Common file hints (examples)

- `**/*.go`, `**/*.py`, `**/*.sql` → CODEX
- `**/*.tsx`, `**/*.css`, `**/*.html` → GEMINI
- `**/*.sh`, `**/*.yml`, `Dockerfile`, `Makefile` → CURSOR
- Mixed set across frontend + backend → CROSS_VALIDATION
- `**/*.md` (docs only, no code) → CLAUDE
- Design docs, implementation docs, requirements specs, architecture docs → CROSS_VALIDATION

## Cursor (Implementation + Quality Review)

Cursor (`mcp__cursor__cursor`) has a **dual role**:

### As Implementation Agent (CURSOR routing)
- Debugging, refactoring, DevOps, scripts, general implementation
- Catches all tasks that don't clearly fit CODEX or GEMINI
- Fail-closed: BLOCKED if unavailable (same as CODEX/GEMINI)

### As Quality Reviewer (automatic, orthogonal to routing)
- Reviews code quality when Codex or Gemini implements
- Does NOT self-review when Cursor implements — Opus reviews instead
- See `checkpoints.md` for `QualityGateRequired` decision table

**Deterministic reviewer:** `Reviewer = (Implementer == Cursor ? Opus : Cursor)`

## Claude (Orchestrator Only)

Claude does **NOT** write implementation code. Claude's role:
- Route tasks to CODEX, GEMINI, or CURSOR
- Coordinate between models
- Edit documentation (no code changes)
- If a task requires code and all external models are unavailable → **BLOCKED**

## Reminder

If you choose `Routing != CLAUDE`, apply `coordinating-multi-model-work/GATE.md` immediately (evidence or BLOCKED).
