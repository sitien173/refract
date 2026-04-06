# Multi-Model Gate (Fail-Closed)

Use this gate whenever a skill decides **Routing != CLAUDE** (`CODEX`, `GEMINI`, or `CROSS_VALIDATION`).

## Core Rule

- If `Routing != CLAUDE`, you must obtain external model output via MCP tools (`mcp__codex__codex`, `mcp__gemini__gemini`).
- You must finish with CP4 Final Spec Review per `coordinating-multi-model-work/review-chain.md`.
- If an MCP call fails with `timeout` or `tool-unavailable`, retry up to 2 times. If still failing, fall back to a Sonnet subagent (`Agent` tool, `model: "sonnet"`) that implements the task via direct file editing. See `coordinating-multi-model-work/checkpoints.md` CP2 Failure & Fallback.
- If an MCP call fails with `permission-blocked`, stop in `BLOCKED` immediately. Do not retry or fall back.

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
- Status: PASS | PARTIAL | FAIL
- Artifact: <files reviewed>
- Result: <3-6 bullets>
```

## Failure Handling

### Fallback (after 2 retries of timeout or tool-unavailable)

```text
[Multi-Model Gate]
Routing: CODEX | GEMINI
Status: FALLBACK
Reason: tool-unavailable | timeout (after 2 retries)
Fallback: Sonnet subagent (direct file editing)
```

### Blocked (permission-blocked — no retry, no fallback)

```text
[Multi-Model Gate]
Routing: CODEX | GEMINI | CROSS_VALIDATION
Status: BLOCKED
Reason: permission-blocked
```
