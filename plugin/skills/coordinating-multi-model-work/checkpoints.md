# Collaboration Checkpoints

## Overview

Checkpoints are used at key stages to decide whether external models are needed, and to enforce a unified evidence protocol (Evidence / BLOCKED).

**Key principle:** Claude is orchestrator-only — all implementation code must be routed to CODEX, GEMINI, or CURSOR.

## Task Complexity Classification

Before applying checkpoints, classify the task:

| Tier | Criteria | CP Behavior |
|------|----------|-------------|
| **Trivial** | Docs-only, single config line, typo fix, <5 lines changed | Compact one-line CP1/CP3. Skip CP2. Skip quality review. |
| **Standard** | Single-domain task, clear scope, well-defined files | Full CP1/CP3 blocks. CP2 if triggered. Standard quality review. |
| **Critical** | Multi-file, architecture change, security/auth/payment, core logic, multi-domain | Full CP1/CP2/CP3 with cross-validation. Enhanced quality review (4+ loops). |

### Compact CP Format (Trivial tasks only)

```text
[CP1] Routing: CLAUDE | Trivial: docs-only change
[CP3] Verified: [command output or "no code changes"]
```

## Checkpoints

### CP1: Task Analysis (Before starting)

Goal: decide which external model handles this task.

- Collect: task goals, involved files, tech stack, risks/uncertainty
- Use: semantic routing via `coordinating-multi-model-work/routing-decision.md`
- **All tasks requiring code changes MUST route to an external model** (CODEX/GEMINI/CURSOR)

**Early exposure:** once you decide `Routing != CLAUDE`, immediately execute `GATE.md` (use MCP tools to obtain Evidence or output BLOCKED). Do not write plans or code first.

**Enforcement mode:** After routing, determine the enforcement mode per `GATE.md > Enforcement Modes`. Record the mode in the CP1 Assessment block.

### CP2: Mid-Review (Key decision point)

**Objective Triggers** (any one is sufficient):

| Trigger | Threshold | Action |
|---------|-----------|--------|
| Retry count | >= 2 failed attempts at same sub-task | Re-evaluate approach, prefer CROSS_VALIDATION |
| Elapsed time | > 5 minutes on single sub-task without progress | Invoke domain expert for guidance |
| Failing test count | Increasing (more failures than when started) | Stop, investigate root cause before continuing |
| Ambiguity flag | 2+ viable approaches with unclear winner | Invoke CROSS_VALIDATION |
| Debugging stall | Root cause unclear after first investigation pass | Invoke domain expert |

**Subjective Triggers** (use judgment):

- Branching approaches (2+ viable paths with different costs/risks)
- Security/performance/data consistency concerns discovered mid-task
- Unexpected complexity revealed during implementation

Action: prefer `CROSS_VALIDATION`, and follow early exposure + evidence.

**CP2 Assessment Format:**

```text
[CP2 Assessment]
- Trigger: [which objective/subjective trigger fired]
- Current state: [what's been tried, what failed]
- Routing decision: [CLAUDE/CODEX/GEMINI/CURSOR/CROSS_VALIDATION]
- Rationale: ...
```

### CP3: Quality Gate (Before output)

Goal: perform final review before "final output/final conclusion/claiming tests passed/requesting code review".

**Domain Review:**
- If `Routing != CLAUDE`: Domain/implementation Evidence required from the implementing model
- External failure: must BLOCKED (fail-closed), except for partial cross-validation success (see tiered policy in `GATE.md`)

**Code Quality Review:**
- Evaluate `QualityGateRequired`: did code change in this task?
- Apply the review chain per `coordinating-multi-model-work/review-chain.md`
- If no code changed (docs-only): skip quality review

**QualityGateRequired Decision (Risk-Tiered):**

| Task Complexity | Spec Review | Quality Review | Max Fix-Review Loops |
|----------------|-------------|----------------|---------------------|
| **Trivial** (docs, config, <5 lines) | Skip | Skip | 0 |
| **Standard** (single-domain, clear scope) | Full | Full review chain | 3 |
| **Critical** (multi-file, auth/payment/core) | Full + cross-validation | Full review chain + cross-validation | 4+ with user escalation |

> **Note:** `CLAUDE + Code Changed` is not a valid state — if code changes are needed, Claude MUST route to an external model. If this state is detected, re-route to CROSS_VALIDATION.

For the full review chain rule, routing matrix, artifact pinning, and arbitration rules, see `coordinating-multi-model-work/review-chain.md`.

## User Override

Users can explicitly override routing:

- "Use Codex" / "Use Gemini" / "Use Cursor" / "Cross-validate" → force corresponding Routing
- "Do not use external models" → force `Routing = CLAUDE` (docs/coordination only)
