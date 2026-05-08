# Multi-Model Gate (Fail-Closed)

Use this gate whenever a skill decides **Routing != CLAUDE** (`CODEX`, `GEMINI`, or `CROSS_VALIDATION`).

## Core Rule

- If `Routing != CLAUDE`, you must obtain external model output via MCP tools (`mcp__codex__codex`, `mcp__gemini__gemini`).
- You must finish the phase with CP4 Phase Review per `coordinating-multi-model-work/review-chain.md` when MCP output exists.
- If any Codex or Gemini MCP call fails with `timeout`, `tool-unavailable`, `session-failed`, session instability, model error, or `permission-blocked`, stop in `BLOCKED` immediately and ask the human to retry or explicitly consent to an alternate route.
- Do not retry, switch executors, spawn subagents/Task/Agent fallback, or handle implementation directly after executor MCP failure without explicit human consent after the block.

## Evidence Requirement

```text
[Multi-Model Gate]
Routing: CODEX | GEMINI | CROSS_VALIDATION
Why: <one sentence>

Evidence (Implementation):
- Tool: mcp__codex__codex | mcp__gemini__gemini
- Params: <key MCP parameters used>
- Result: <3-6 bullets>

Evidence (CP4 Spec Review):
- Reviewer: Claude
- Status: PASS | PASS_WITH_DEBT | FAIL
- Artifact: <files reviewed>
- Result: <3-6 bullets>
```

## Failure Handling

```text
[Multi-Model Gate]
Routing: CODEX | GEMINI | CROSS_VALIDATION
Status: BLOCKED
Reason: permission-blocked | tool-unavailable | timeout | session-failed
Next action: ask human to retry or consent to alternate route
```
