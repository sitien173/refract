# Multi-Model Gate (Fail-Closed)

Use this gate whenever a skill decides **Routing != CLAUDE** (CODEX/GEMINI/CURSOR/CROSS_VALIDATION).

**Claude is orchestrator-only** — all implementation code must go through external models. If all external models are unavailable, the task is BLOCKED by design.

## Core Rule

- If Routing != CLAUDE, you MUST obtain external model output via MCP tools (`mcp__codex__codex`, `mcp__gemini__gemini`, `mcp__cursor__cursor`).
- If code changed, you MUST run the review chain per `coordinating-multi-model-work/review-chain.md`.
- If you cannot obtain required external output (timeout, tool unavailable, permission blocked), follow the **Tiered Failure Policy** and **Enforcement Modes** below.
- Do NOT provide a final conclusion, final patch, or "best effort" solution without required evidence, unless the **Tiered Failure Policy** or **Enforcement Modes** explicitly permits proceeding (for example, a user-approved unverified proposal in **Degraded** mode only).

**Early exposure:** If you decide `Routing != CLAUDE`, run the external invocation immediately (before doing real work). Do not defer the gate until the end.

## Invocation

Use the templates in `INTEGRATION.md`.

Timeout policy:
- Use the existing timeout configuration in your environment (e.g. `CODEX_TIMEOUT`).
- Do NOT invent new timeout constants in the skill.
- If the first attempt times out, retry at most once after applying your existing timeout escalation procedure.

## Evidence Requirement

Before continuing past a checkpoint (or producing final output), include an Evidence block:

### Standard Evidence (CODEX/GEMINI/CURSOR routing)

```text
[Multi-Model Gate]
Routing: CODEX | GEMINI | CURSOR
Why: <one sentence>

Evidence (Implementation):
- Tool: mcp__codex__codex | mcp__gemini__gemini | mcp__cursor__cursor
- Params: <key MCP parameters used (PROMPT, cd, SESSION_ID, sandbox, model, etc.)>
- Result: <3-6 bullets of what the external model said>

Evidence (Opus Review):
- Reviewer: Opus
- Artifact: <commit SHA>
- Result: <3-6 bullets of Opus's judgment>

Integration: <what you accepted/rejected and why>
```

### Extended Evidence (CROSS_VALIDATION)

When multiple models participate at CP3:

```text
[Multi-Model Gate]
Routing: CROSS_VALIDATION
Why: <one sentence>

Evidence (Domain 1):
- Tool: mcp__codex__codex | mcp__gemini__gemini | mcp__cursor__cursor
- Artifact: <commit SHA>
- Result: <3-6 bullets>

Evidence (Domain 2):
- Tool: mcp__codex__codex | mcp__gemini__gemini | mcp__cursor__cursor
- Artifact: <commit SHA>
- Result: <3-6 bullets>

Evidence (Opus Review):
- Reviewer: Opus
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
| Opus reviewer (any code-changing path) | BLOCKED — Opus must review | Opus is the only reviewer |
| Cross-validation: one model times out | Use completed result + Claude supplement | Partial evidence better than none |
| Cross-validation: all timeout | BLOCKED | No evidence available |

## Enforcement Modes

Tasks are classified into enforcement tiers based on complexity and risk. The tier determines how strictly the fail-closed rule applies.

| Mode | Trigger | Behavior | BLOCKED on failure? |
|------|---------|----------|---------------------|
| **Strict** | Implementation tasks, critical path changes (auth/payment/data), multi-file code changes | Full fail-closed. No exceptions. | Yes — always |
| **Degraded** | Non-critical single-file changes, config edits, documentation with code snippets | Allow "unverified proposal" clearly marked with `⚠️ UNVERIFIED — external model unavailable`. User must approve before proceeding. | No — but must warn |
| **Incident** | 3+ consecutive external model failures in same session | Notify user: "External models repeatedly unavailable. Options: (1) retry, (2) manual override, (3) pause and troubleshoot MCP connection." Log for post-mortem. | Pauses for user decision |

### Mode Selection

```text
IF task modifies auth, payment, security, data models, or core business logic:
    mode = strict
ELSE IF task is single-file, non-critical, or config/docs-with-code:
    mode = degraded
IF consecutive_failures >= 3 in session:
    mode = incident (overrides above)
```

### Unverified Proposal Format (Degraded Mode Only)

```text
⚠️ UNVERIFIED PROPOSAL — External model unavailable
Routing: [CODEX/GEMINI/CURSOR]
Failure reason: [timeout/tool-unavailable/permission-blocked]

Proposed change (generated by Claude as orchestrator, NOT validated by domain expert):
[proposed changes]

To proceed: User must explicitly approve this unverified proposal.
To retry: [exact MCP tool call to retry]
```

## Pre-Output Self-Check (Mandatory)

- If Routing != CLAUDE: do I have Implementation Evidence from the external model?
- If code changed: do I have Quality Review Evidence per `review-chain.md` (or valid exemption)?
- If not: did I stop in BLOCKED state (no final answer)?
- Exemption: docs-only changes do not require Quality Review Evidence
