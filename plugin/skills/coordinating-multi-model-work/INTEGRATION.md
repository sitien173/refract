# Multi-Model Integration Guide

This file provides standard integration patterns for other skills to use multi-model capabilities.

**Claude is orchestrator-only** — all implementation code goes through external models.

## Quick Reference

See `coordinating-multi-model-work/routing-decision.md` for routing rules.
See `coordinating-multi-model-work/review-chain.md` for the review chain.

## Standard Integration Section

Copy this section to your skill and customize the prompts:

```markdown
## Multi-Model Integration

**Related skill:** superpowers-cccg:coordinating-multi-model-work

For tasks requiring implementation, apply semantic routing:

1. **Analyze task domain** using `coordinating-multi-model-work/routing-decision.md`
2. **Notify user**: "I will use [model] to [task purpose]"
3. **Invoke model** via MCP tools (`mcp__codex__codex` for backend, `mcp__gemini__gemini` for frontend, `mcp__cursor__cursor` for DevOps)
4. **Run the review chain** before completion claims
5. **Integrate results** before proceeding

**Fallback (Fail-Closed):** If the MCP tool call fails or times out, STOP and follow `coordinating-multi-model-work/GATE.md`.
```

## Invocation Templates

### Backend Implementation (Codex MCP)

```json
{
  "tool": "mcp__codex__codex",
  "params": {
    "PROMPT": "## Context\n[Problem/task description]\n\n## Code Location (if applicable)\nFile: [file_path]\nLines: [start_line]-[end_line]\n\nNote: Use your CLI tools to read the file at the specified location.\n\n## Analysis Focus\n1. API design and implementation\n2. Data flow and state management\n3. Performance and security considerations\n\n## Expected Output\n- Assessment with strengths/risks\n- Specific recommendations",
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
    "PROMPT": "## Context\n[Problem/task description]\n\n## Code Location (if applicable)\nFile: [file_path]\nLines: [start_line]-[end_line]\n\nNote: Use your CLI tools to read the file at the specified location.\n\n## Analysis Focus\n1. Component structure and rendering\n2. User interaction and experience\n3. Accessibility and responsive design\n\n## Expected Output\n- Assessment with strengths/risks\n- Specific recommendations",
    "sandbox": "default",
    "SESSION_ID": "<reuse-or-new>",
    "model": "gemini-latest"
  }
}
```

### DevOps Implementation (Cursor MCP)

Use this template when Cursor is the **implementation agent** (CURSOR routing — DevOps tasks only: CI/CD, scripts, Dockerfiles, infrastructure).

```json
{
  "tool": "mcp__cursor__cursor",
  "params": {
    "PROMPT": "## Implementation Task\n\n### Context\n[Problem/task description — what needs to be built/fixed and why]\n\n### Code Location\nFile: [file_path]\nLines: [start_line]-[end_line]\n\nNote: Use your CLI tools to read the file at the specified location.\n\n### Requirements\n1. [Requirement 1]\n2. [Requirement 2]\n3. [Requirement 3]\n\n### Implementation Focus\n1. Correctness and edge case handling\n2. Clean, maintainable code\n3. Appropriate test coverage\n\n### Expected Output\n- Implementation with unified diff patch\n- Test cases covering the changes\n- Brief explanation of approach taken",
    "cd": "$PWD",
    "sandbox": "default",
    "SESSION_ID": "<reuse-or-new>",
    "model": "claude-4.6-sonnet-medium-thinking"
  }
}
```

**CURSOR routing rules:**
- Cursor handles DevOps tasks only (CI/CD, scripts, Dockerfiles, infrastructure)
- Fail-closed: BLOCKED if Cursor unavailable (same as CODEX/GEMINI)
- Final review by Opus
- Max 3 fix-review loops before escalating to user
- See `GATE.md` for tiered failure policy details

### Cross-Validation (Multiple Models)

Default: invoke Codex + Gemini in parallel, then integrate.
For critical/high-uncertainty tasks: optionally escalate to 3-way (Codex + Gemini + Cursor). When Cursor participates in cross-validation, use `model: claude-4.5-opus-high-thinking`.

```markdown
## Cross-Validation Results

### Codex Analysis (Backend via mcp__codex__codex)

[Results]

### Gemini Analysis (Frontend via mcp__gemini__gemini)

[Results]

### Cursor Analysis (DevOps via mcp__cursor__cursor, `model: claude-4.5-opus-high-thinking`) — optional 3-way

[Results]

### Integrated Conclusion

- **Agreement**: [Consistent findings]
- **Divergence**: [Differences]
- **Recommendation**: [Final determination]
```

### Optional Cursor Cross-Validation Invocation

```json
{
  "tool": "mcp__cursor__cursor",
  "params": {
    "PROMPT": "## Cross-Validation Analysis\n\n### Context\n[Problem/task description]\n\n### Focus\n1. Cross-cutting implementation risks\n2. Integration edge cases\n3. Tradeoffs between proposed solutions\n\n### Output\n- Main conclusion\n- Issues found\n- Suggested resolution",
    "cd": "$PWD",
    "sandbox": "default",
    "SESSION_ID": "<reuse-or-new>",
    "model": "claude-4.5-opus-high-thinking"
  }
}
```

### Final Review (Opus)

Opus reviews all code-changing paths directly. See `coordinating-multi-model-work/review-chain.md` for the full review protocol.

## Supplementary Tool Integration

Claude may use these MCP tools to enhance orchestration. They are **optional** — if unavailable, proceed without them.

### Pre-Routing Enhancement

Before routing to an external model, optionally use:
- **Grok Search** (`mcp__grok-search__web_search`) — gather current info about unfamiliar libraries, APIs, or patterns
- **Sequential-Thinking** — decompose complex multi-component tasks
- **Serena** — understand existing codebase structure and symbol relationships

### During Implementation

Alongside external model work, optionally use:
- **Magic** — generate UI component patterns to include in Gemini prompts
- **Morphllm** — apply bulk pattern edits after external model provides the diff template

### Post-Implementation

After external model completes, optionally use:
- **Serena** — verify symbol references and dependencies are intact
- **Sequential-Thinking** — systematically evaluate review findings when divergences exist

**No fail-closed gate** for supplementary tools. See `skills/shared/supplementary-tools.md` for full reference.

## Important Rules

1. **All prompts to external models MUST be in English**
2. User notifications follow user's configured language
3. Always validate external model outputs before using
4. **Claude does NOT write implementation code** — route to CODEX, GEMINI, or CURSOR
5. **Review chain:** See `coordinating-multi-model-work/review-chain.md`
