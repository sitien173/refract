# Multi-Model Gate (Fail-Closed)

Use this gate whenever a skill decides **Routing != CLAUDE** (CODEX/GEMINI/CROSS_VALIDATION), or whenever code changes require quality review via Cursor.

## Core Rule

- If Routing != CLAUDE, you MUST obtain external model output via the Codex/Gemini MCP tools (`mcp__codex__codex`, `mcp__gemini__gemini`).
- If code changed, you MUST obtain Cursor (`mcp__cursor__cursor`) code quality review (see Tiered Failure Policy for fallback behavior).
- If you cannot obtain required external output (timeout, tool unavailable, permission blocked), follow the **Tiered Failure Policy** below — different call contexts have different failure severity.
- Do NOT provide a final conclusion, final patch, or “best effort” solution without required evidence, unless the Tiered Failure Policy explicitly permits proceeding.

**Early exposure:** If you decide `Routing != CLAUDE`, run the external invocation immediately (before doing real work). Do not defer the gate until the end.

## Invocation

Use the templates in `INTEGRATION.md`.

Timeout policy:
- Use the existing timeout configuration in your environment (e.g. `CODEX_TIMEOUT`).
- Do NOT invent new timeout constants in the skill.
- If the first attempt times out, retry at most once after applying your existing timeout escalation procedure.

## Evidence Requirement

Before continuing past a checkpoint (or producing final output), include an Evidence block:

```text
[Multi-Model Gate]
Routing: CODEX | GEMINI | CROSS_VALIDATION
Why: <one sentence>

Evidence:
- Tool: mcp__codex__codex | mcp__gemini__gemini
- Params: <key MCP parameters used (PROMPT, cd, SESSION_ID, sandbox, model, etc.)>
- Result: <3-6 bullets of what the external model said>
- Integration: <what you accepted/rejected and why>
```

### Extended Evidence Format (with Code Quality)

When Cursor participates in the quality gate alongside a domain expert:

```text
[Multi-Model Gate]
Routing: CODEX | GEMINI | CROSS_VALIDATION
Why: <one sentence>

Evidence (Domain):
- Tool: mcp__codex__codex | mcp__gemini__gemini
- Artifact: <commit SHA>
- Result: <3-6 bullets>

Evidence (Code Quality):
- Tool: mcp__cursor__cursor
- Artifact: <commit SHA>
- Result: <3-6 bullets>

Integration: <what was accepted/rejected from each>
```

When only Cursor reviews (Routing == CLAUDE but code changed):

```text
[Quality Gate]
Routing: CLAUDE (code quality review only)

Evidence (Code Quality):
- Tool: mcp__cursor__cursor
- Artifact: <commit SHA>
- Result: <3-6 bullets>

Integration: <what was accepted/rejected>
```

## Failure Handling (Fail-Closed)

If the external call fails:

```text
[Multi-Model Gate]
Routing: CODEX | GEMINI | CROSS_VALIDATION
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
| Domain expert at CP3 (Codex/Gemini) | BLOCKED — strict fail-closed | Primary validation, no substitute |
| Cursor at subagent stage 2 | Fall back to Opus code quality reviewer | Cursor is primary but Opus can substitute |
| Cursor at CP3 (supplementary) | Proceed without — log warning | Domain review is primary; code was already reviewed in stage 2 |
| Cross-validation: one model times out | Use completed result + Claude supplement | Partial evidence better than none |
| Cross-validation: both timeout | BLOCKED | No evidence available |

## Pre-Output Self-Check (Mandatory)

- If Routing != CLAUDE: do I have Domain Evidence?
- If code changed: do I have Code Quality Evidence (or valid exemption)?
- If not: did I stop in BLOCKED state (no final answer)?
- Exemption: docs-only changes do not require Code Quality Evidence
