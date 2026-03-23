# Multi-Model Integration Guide

This file provides standard integration patterns for other skills to use multi-model capabilities.

## Quick Reference

```
Task Type → Model Selection:
├─ Frontend (UI, components, styles) → GEMINI
├─ Backend (API, database, logic) → CODEX
├─ Full-stack or uncertain → CROSS_VALIDATION
├─ Design docs, implementation docs, requirements specs, architecture docs, and other critical documentation → CROSS_VALIDATION
├─ Simple (docs, configs) → CLAUDE (no external model needed)
└─ Code quality review (automatic) → CURSOR (not a routing target — see below)
```

## Standard Integration Section

Copy this section to your skill and customize the prompts:

```markdown
## Multi-Model Integration

**Related skill:** superpowers:coordinating-multi-model-work

For tasks requiring specialized expertise, apply semantic routing:

1. **Analyze task domain** using `coordinating-multi-model-work/routing-decision.md`
2. **Notify user**: "I will use [model] to [task purpose]"
3. **Invoke model** with English prompts via the MCP tools (`mcp__codex__codex` for backend, `mcp__gemini__gemini` for frontend)
4. **Integrate results** before proceeding

**Fallback (Fail-Closed):** If the MCP tool call fails or times out, STOP and follow `coordinating-multi-model-work/GATE.md`.
```

## Invocation Templates

### Backend Analysis (Codex MCP)

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

### Frontend Analysis (Gemini MCP)

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

### Cross-Validation (Both)

Invoke both MCP tools in parallel, then integrate:

```markdown
## Cross-Validation Results

### Codex Analysis (Backend via mcp**codex**codex)

[Results]

### Gemini Analysis (Frontend via mcp**gemini**gemini)

[Results]

### Integrated Conclusion

- **Agreement**: [Consistent findings]
- **Divergence**: [Differences]
- **Recommendation**: [Final determination]
```

### Code Quality Review (Cursor MCP)

Cursor is invoked automatically for code quality review — it is NOT a routing target. Use this template when code changes need quality validation (subagent stage 2, CP3 with code changes).

```json
{
  "tool": "mcp__cursor__cursor",
  "params": {
    "PROMPT": "## Code Quality Review\n\n### Task Context\n[Original task spec — what was being built and why]\n\n### Changes to Review\n[Diff or file paths with line ranges]\nCommit: [SHA]\n\n### Review Focus\n1. Correctness: bugs, edge cases, off-by-one errors, null handling\n2. Readability: naming, structure, comments where non-obvious\n3. Maintainability: DRY, coupling, separation of concerns\n4. Performance: anti-patterns, unnecessary allocations, N+1 queries\n\n### Important\n- Spec compliance has already been verified — focus only on code quality\n- Do NOT suggest feature additions or scope changes\n\n### Output Format\n- APPROVE if no issues found\n- Or list issues as:\n  - File: [path]\n  - Line: [number]\n  - Severity: Critical | Important | Minor\n  - Issue: [description]\n  - Suggestion: [fix]",
    "cd": "$PWD",
    "sandbox": "default",
    "SESSION_ID": "<reuse-or-new>"
  }
}
```

**Cursor-specific rules:**
- Pin review to a specific commit SHA (artifact pinning)
- Max 3 fix-review loops before escalating to user
- If Cursor unavailable at subagent stage 2: fall back to Opus quality reviewer
- If Cursor unavailable at CP3: proceed without (supplementary)
- See `GATE.md` for tiered failure policy details

## Important Rules

1. **All prompts to external models MUST be in English**
2. User notifications follow user's configured language
3. Always validate external model outputs before using
4. Claude handles simple tasks directly (no external model needed)
