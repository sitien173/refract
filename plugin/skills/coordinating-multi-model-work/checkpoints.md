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
- **Review Chain Rule:** `ReviewAssistant = (Implementer == Cursor ? None : Cursor); FinalArbiter = Opus`
- When Codex/Gemini implement: Cursor review assistant runs first, then Opus makes the final decision
- When Cursor implements: Opus reviews directly (no self-review)
- If no code changed (docs-only): skip quality review
- If Cursor review assistant is unavailable for a Codex/Gemini path: Opus reviews directly
- If Opus is unavailable for any code-changing path: BLOCKED

**QualityGateRequired Decision (Risk-Tiered):**

| Task Complexity | Spec Review | Quality Review | Max Fix-Review Loops | Notes |
|----------------|-------------|----------------|---------------------|-------|
| **Trivial** (docs, config, <5 lines) | Skip | Skip | 0 | No code review needed |
| **Standard** (single-domain, clear scope) | Full | Full review chain | 3 | Cursor assists only when implementer is not Cursor |
| **Critical** (multi-file, auth/payment/core) | Full + cross-validation | Full review chain + cross-validation | 4+ with user escalation | Enhanced scrutiny |

**Routing × Code Changed Matrix**:

| Routing | Code Changed? | Implementation By | Review Assistant | Final Arbiter |
|---------|--------------|-------------------|------------------|---------------|
| CODEX | Yes | Codex | Cursor | Opus |
| CODEX | No (docs-only) | Codex | Skip | Skip |
| GEMINI | Yes | Gemini | Cursor | Opus |
| GEMINI | No (docs-only) | Gemini | Skip | Skip |
| CURSOR | Yes | Cursor | Skip | Opus |
| CURSOR | No (docs-only) | Cursor | Skip | Skip |
| CROSS_VALIDATION | Yes | Multiple | Depends on final implementer | Opus |
| CLAUDE | No (docs-only) | N/A (orchestrator) | Skip | Skip |

> **Note:** `CLAUDE + Code Changed` is not a valid state — if code changes are needed, Claude MUST route to an external model. If this state is detected, re-route to CURSOR.

**Artifact Pinning:** All CP3 reviews must reference the same commit SHA. If fixes invalidate an earlier assistant review or Opus judgment, re-run the applicable review chain against the new SHA.

**Review Chain Arbitration:**

- Cursor assistant findings are advisory. Opus decides whether they stand.
- If Cursor assistant approves but Opus finds issues, fix Opus issues and re-run Opus.
- If Cursor assistant finds issues that Opus dismisses, proceed with Opus's judgment and record the dismissal.
- After substantive fixes on a Codex/Gemini path, re-run Cursor assistant and Opus. After fixes on a Cursor path, re-run Opus.

## User Override

Users can explicitly override routing:

- "Use Codex" / "Use Gemini" / "Use Cursor" / "Cross-validate" → force corresponding Routing
- "Do not use external models" → force `Routing = CLAUDE` (docs/coordination only)
