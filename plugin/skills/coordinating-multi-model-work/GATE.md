# Multi-Model Gate (Fail-Closed)

Use this gate whenever a skill decides **Routing != CLAUDE** (`CODEX`, `GEMINI`, or `CROSS_VALIDATION`).

## Core Rule

- If `Routing != CLAUDE`, you must obtain external model output via MCP tools (`mcp__codex__codex`, `mcp__gemini__gemini`).
- You must finish with CP4 Final Spec Review per `coordinating-multi-model-work/review-chain.md`.
- If you cannot obtain required external output, stop in `BLOCKED`.

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

```text
[Multi-Model Gate]
Routing: CODEX | GEMINI | CROSS_VALIDATION
Status: BLOCKED
Reason: timeout | tool-unavailable | permission-blocked | other
```
