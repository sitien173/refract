# Multi-Model Integration Guide

This file provides standard integration patterns for other skills to use multi-model capabilities.

**Claude is orchestrator-only** — all implementation code goes through external models.

## Quick Reference

See `coordinating-multi-model-work/routing-decision.md` for routing rules and `coordinating-multi-model-work/review-chain.md` for the review chain.

## Standard Integration Section

```markdown
## Multi-Model Integration

**Related skill:** superpowers-ccg:coordinating-multi-model-work

For tasks requiring implementation, apply semantic routing:

1. Analyze task domain using `coordinating-multi-model-work/routing-decision.md`
2. Notify user: "I will use [model] to [task purpose]"
3. Invoke model via MCP tools (`mcp__codex__codex` for backend and systems, `mcp__gemini__gemini` for frontend)
4. Run the review chain before completion claims
5. Integrate results before proceeding

**Fallback (Fail-Closed):** If the MCP tool call fails or times out, stop and follow `coordinating-multi-model-work/GATE.md`.
```

## Response Protocol

All prompts to external models must include the response protocol from Serena memory `global/response_protocol`.

## Invocation Templates

### Backend and Systems Implementation (Codex MCP)

```json
{
  "tool": "mcp__codex__codex",
  "params": {
    "PROMPT": "## Context\n[Problem/task description]\n\n## Code Location\nFile: [file_path]\nLines: [start_line]-[end_line]\n\nNote: Use your CLI tools to read the file at the specified location.\n\n## Analysis Focus\n1. API, backend, or systems implementation\n2. Data flow and state management\n3. Performance, security, and operational considerations\n\n## Response Protocol\nFIRST: Read Serena memory 'global/response_protocol' for full format rules.\nFALLBACK: You respond to an orchestrator agent, NOT a human. NO thinking narration, NO restating context, NO full file rewrites. Output: ## ANALYSIS (≤200 words) → ## DIFF (changed hunks only) → ## ISSUES (≤5) → ## VERDICT (one sentence).",
    "cd": "$PWD",
    "sandbox": "default",
    "SESSION_ID": "<reuse-or-new>",
    "model": "codex-latest"
  }
}
```

### Frontend Implementation (Gemini MCP)

```json
{
  "tool": "mcp__gemini__gemini",
  "params": {
    "PROMPT": "## Context\n[Problem/task description]\n\n## Code Location\nFile: [file_path]\nLines: [start_line]-[end_line]\n\nNote: Use your CLI tools to read the file at the specified location.\n\n## Analysis Focus\n1. Component structure and rendering\n2. User interaction and experience\n3. Accessibility and responsive design\n\n## Response Protocol\nFIRST: Read Serena memory 'global/response_protocol' for full format rules.\nFALLBACK: You respond to an orchestrator agent, NOT a human. NO thinking narration, NO restating context, NO full file rewrites. Output: ## ANALYSIS (≤200 words) → ## DIFF (changed hunks only) → ## ISSUES (≤5) → ## VERDICT (one sentence).",
    "sandbox": "default",
    "SESSION_ID": "<reuse-or-new>",
    "model": "gemini-latest"
  }
}
```

### Cross-Validation (Codex + Gemini)

Default: invoke Codex and Gemini in parallel, then integrate.

## Final Review (Opus)

Opus reviews all code-changing paths directly. See `coordinating-multi-model-work/review-chain.md`.

## Important Rules

1. All prompts to external models must be in English.
2. User notifications follow the user's configured language.
3. Always validate external model outputs before using them.
4. Claude does not write implementation code.
5. Follow the review chain in `coordinating-multi-model-work/review-chain.md`.
