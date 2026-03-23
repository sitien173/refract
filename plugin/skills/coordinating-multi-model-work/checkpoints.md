# Collaboration Checkpoints

## Overview

Checkpoints are used at key stages to decide whether external models are needed, and to enforce a unified evidence protocol (Evidence / BLOCKED).

## Checkpoints

### CP1: Task Analysis (Before starting)

Goal: decide whether external models are needed.

- Collect: task goals, involved files, tech stack, risks/uncertainty
- Use: semantic routing via `coordinating-multi-model-work/routing-decision.md`

**Early exposure:** once you decide `Routing != CLAUDE`, immediately execute `GATE.md` (use MCP tools to obtain Evidence or output BLOCKED). Do not write plans or code first.

### CP2: Mid-Review (Key decision point)

Triggered by:

- Branching approaches (2+ viable paths with different costs/risks)
- Debugging uncertainty (root cause unclear, conflicting evidence)
- Security/performance/data consistency concerns

Action: prefer `CROSS_VALIDATION`, and follow early exposure + evidence.

### CP3: Quality Gate (Before output)

Goal: perform final review before "final output/final conclusion/claiming tests passed/requesting code review".

**Domain Review (unchanged):**
- If `Routing != CLAUDE`: Domain expert Evidence required (Codex/Gemini)
- External failure: must BLOCKED (fail-closed)

**Code Quality Review (Cursor):**
- Evaluate `QualityGateRequired`: did code change in this task?
- If yes: call Cursor (`mcp__cursor__cursor`) in parallel with domain expert
- If no (docs-only): skip Cursor
- Cursor failure at CP3: proceed without (supplementary — see tiered policy in `GATE.md`)

**QualityGateRequired Decision:**

| Routing | Code Changed? | Domain Expert | Cursor |
|---------|--------------|---------------|--------|
| CODEX/GEMINI/CROSS_VALIDATION | Yes | Required | Required (parallel) |
| CODEX/GEMINI/CROSS_VALIDATION | No (docs-only) | Required | Skip |
| CLAUDE | Yes | Skip | Required |
| CLAUDE | No (docs-only) | Skip | Skip |

**Artifact Pinning:** All CP3 reviews must reference the same commit SHA. If fixes from one review invalidate the other, re-run both against the new SHA.

**Conflict Arbitration:**

| Domain Expert | Cursor | Action |
|--------------|--------|--------|
| Pass | Pass | Proceed |
| Pass | Fail | Fix code quality issues, re-review Cursor only |
| Fail | Pass | Fix domain issues, re-review domain expert only |
| Fail | Fail | Fix all issues, re-review both |

## User Override

Users can explicitly override routing:

- "Use Codex" / "Use Gemini" / "Cross-validate" → force corresponding Routing
- "Do not use external models" → force `Routing = CLAUDE`
