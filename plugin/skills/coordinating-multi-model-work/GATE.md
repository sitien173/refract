# Multi-Model Gate (Fail-Closed)

Use this gate whenever a skill decides **Routing != CLAUDE** (CODEX/GEMINI/CURSOR/CROSS_VALIDATION).

**Claude is orchestrator-only** — all implementation code must go through external models. If all external models are unavailable, the task is BLOCKED by design.

## Core Rule

- If Routing != CLAUDE, you MUST obtain external model output via MCP tools (`mcp__codex__codex`, `mcp__gemini__gemini`, `mcp__cursor__cursor`).
- If code changed, you MUST obtain quality review from the appropriate reviewer (see Deterministic Reviewer Rule).
- If you cannot obtain required external output (timeout, tool unavailable, permission blocked), follow the **Tiered Failure Policy** below.
- Do NOT provide a final conclusion, final patch, or "best effort" solution without required evidence, unless the Tiered Failure Policy explicitly permits proceeding.

**Deterministic Reviewer Rule:** `Reviewer = (Implementer == Cursor ? Opus : Cursor)`

**Early exposure:** If you decide `Routing != CLAUDE`, run the external invocation immediately (before doing real work). Do not defer the gate until the end.

## Invocation

Use the templates in `INTEGRATION.md`.

Timeout policy:
- Use the existing timeout configuration in your environment (e.g. `CODEX_TIMEOUT`).
- Do NOT invent new timeout constants in the skill.
- If the first attempt times out, retry at most once after applying your existing timeout escalation procedure.

## Evidence Requirement

Before continuing past a checkpoint (or producing final output), include an Evidence block:

### Standard Evidence (CODEX/GEMINI routing)

```text
[Multi-Model Gate]
Routing: CODEX | GEMINI
Why: <one sentence>

Evidence:
- Tool: mcp__codex__codex | mcp__gemini__gemini
- Params: <key MCP parameters used (PROMPT, cd, SESSION_ID, sandbox, model, etc.)>
- Result: <3-6 bullets of what the external model said>
- Integration: <what you accepted/rejected and why>
```

### CURSOR Routing Evidence

```text
[Multi-Model Gate]
Routing: CURSOR
Why: <one sentence>

Evidence (Implementation):
- Tool: mcp__cursor__cursor
- Params: <key MCP parameters used>
- Result: <3-6 bullets of what Cursor implemented>

Evidence (Quality Review):
- Reviewer: Opus (deterministic — Cursor cannot self-review)
- Artifact: <commit SHA>
- Result: <3-6 bullets>

Integration: <what was accepted/rejected from each>
```

### Extended Evidence (with Quality Review)

When quality reviewer participates alongside domain expert at CP3:

```text
[Multi-Model Gate]
Routing: CODEX | GEMINI | CROSS_VALIDATION
Why: <one sentence>

Evidence (Domain):
- Tool: mcp__codex__codex | mcp__gemini__gemini
- Artifact: <commit SHA>
- Result: <3-6 bullets>

Evidence (Code Quality):
- Reviewer: Cursor | Opus (per deterministic reviewer rule)
- Artifact: <commit SHA>
- Result: <3-6 bullets>

Integration: <what was accepted/rejected from each>
```

## Failure Handling (Fail-Closed)

If the external call fails:

```text
[Multi-Model Gate]
Routing: CODEX | GEMINI | CURSOR | CROSS_VALIDATION
Status: BLOCKED
Reason: timeout | tool-unavailable | permission-blocked | other

Next action:
- Provide the exact rerun MCP tool call (tool + params) for the user.
- Ask the user to re-run after fixing the blocker.

Stop here. Do not proceed.
```

## Tiered Failure Policy

Not all external calls have the same failure severity. Use this matrix:

| Call Context | On Failure | Rationale |
|-------------|-----------|-----------|
| CURSOR routing (implementation) | BLOCKED — strict fail-closed | Primary implementer, no substitute |
| Domain expert at CP3 (Codex/Gemini) | BLOCKED — strict fail-closed | Primary validation, no substitute |
| Quality reviewer (Cursor reviewing Codex/Gemini work) at subagent stage 2 | Fall back to Opus quality reviewer | Cursor is primary but Opus can substitute |
| Quality reviewer (Cursor) at CP3 (supplementary) | Proceed without — log warning | Domain review is primary; code was already reviewed in stage 2 |
| Quality reviewer (Opus reviewing Cursor work) | BLOCKED — Opus must review | No self-review allowed, Opus is the only reviewer |
| Cross-validation: one model times out | Use completed result + Claude supplement | Partial evidence better than none |
| Cross-validation: all timeout | BLOCKED | No evidence available |

## Pre-Output Self-Check (Mandatory)

- If Routing != CLAUDE: do I have Implementation Evidence from the external model?
- If code changed: do I have Quality Review Evidence (or valid exemption)?
- Was the correct reviewer used? (Cursor implemented → Opus reviewed, not Cursor)
- If not: did I stop in BLOCKED state (no final answer)?
- Exemption: docs-only changes do not require Quality Review Evidence
