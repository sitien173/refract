# Collaboration Checkpoints

## Overview

Checkpoints are used at key stages to decide whether external models are needed, and to enforce a unified evidence protocol (Evidence / BLOCKED).

**Key principle:** Claude is orchestrator-only — all implementation code must be routed to CODEX, GEMINI, or CURSOR.

## Checkpoints

### CP1: Task Analysis (Before starting)

Goal: decide which external model handles this task.

- Collect: task goals, involved files, tech stack, risks/uncertainty
- Use: semantic routing via `coordinating-multi-model-work/routing-decision.md`
- **All tasks requiring code changes MUST route to an external model** (CODEX/GEMINI/CURSOR)

**Early exposure:** once you decide `Routing != CLAUDE`, immediately execute `GATE.md` (use MCP tools to obtain Evidence or output BLOCKED). Do not write plans or code first.

### CP2: Mid-Review (Key decision point)

Triggered by:

- Branching approaches (2+ viable paths with different costs/risks)
- Debugging uncertainty (root cause unclear, conflicting evidence)
- Security/performance/data consistency concerns

Action: prefer `CROSS_VALIDATION`, and follow early exposure + evidence.

### CP3: Quality Gate (Before output)

Goal: perform final review before "final output/final conclusion/claiming tests passed/requesting code review".

**Domain Review:**
- If `Routing != CLAUDE`: Domain/implementation Evidence required from the implementing model
- External failure: must BLOCKED (fail-closed), except for partial cross-validation success (see tiered policy in `GATE.md`)

**Code Quality Review:**
- Evaluate `QualityGateRequired`: did code change in this task?
- **Deterministic Reviewer Rule:** `Reviewer = (Implementer == Cursor ? Opus : Cursor)`
- When Codex/Gemini implements: Cursor reviews quality (in parallel with domain expert)
- When Cursor implements: Opus reviews quality (no self-review)
- If no code changed (docs-only): skip quality review
- Quality reviewer failure at CP3: see tiered policy in `GATE.md`

**QualityGateRequired Decision:**

| Routing | Code Changed? | Implementation By | Quality Reviewed By |
|---------|--------------|-------------------|-------------------|
| CODEX | Yes | Codex | Cursor (parallel) |
| CODEX | No (docs-only) | Codex | Skip |
| GEMINI | Yes | Gemini | Cursor (parallel) |
| GEMINI | No (docs-only) | Gemini | Skip |
| CURSOR | Yes | Cursor | Opus (no self-review) |
| CURSOR | No (docs-only) | Cursor | Skip |
| CROSS_VALIDATION | Yes | Multiple | Depends on implementer |
| CLAUDE | No (docs-only) | N/A (orchestrator) | Skip |

> **Note:** `CLAUDE + Code Changed` is not a valid state — if code changes are needed, Claude MUST route to an external model. If this state is detected, re-route to CURSOR.

**Artifact Pinning:** All CP3 reviews must reference the same commit SHA. If fixes from one review invalidate the other, re-run both against the new SHA.

**Conflict Arbitration:**

| Domain Expert | Quality Reviewer | Action |
|--------------|-----------------|--------|
| Pass | Pass | Proceed |
| Pass | Fail | Fix quality issues, re-review quality only |
| Fail | Pass | Fix domain issues, re-review domain expert only |
| Fail | Fail | Fix all issues, re-review both |

## User Override

Users can explicitly override routing:

- "Use Codex" / "Use Gemini" / "Use Cursor" / "Cross-validate" → force corresponding Routing
- "Do not use external models" → force `Routing = CLAUDE` (docs/coordination only)
