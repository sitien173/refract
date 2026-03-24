# Multi-Model Integration Guide

This file provides standard integration patterns for other skills to use multi-model capabilities.

**Claude is orchestrator-only** — all implementation code goes through external models.

## Quick Reference

```
Task Type → Model Selection:
├─ Backend (API, database, logic) → CODEX
├─ Frontend (UI, components, styles) → GEMINI
├─ General (debugging, refactoring, DevOps, scripts) → CURSOR
├─ Full-stack or uncertain → CROSS_VALIDATION
├─ Design docs, architecture docs, critical documentation → CROSS_VALIDATION
└─ Documentation-only / coordination (no code) → CLAUDE (orchestrator)

Quality Reviewer Selection:
├─ Codex/Gemini implements → Cursor reviews
├─ Cursor implements → Opus reviews (no self-review)
└─ Docs-only → Skip quality review
```

## Standard Integration Section

Copy this section to your skill and customize the prompts:

```markdown
## Multi-Model Integration

**Related skill:** superpowers-ccg:coordinating-multi-model-work

For tasks requiring implementation, apply semantic routing:

1. **Analyze task domain** using `coordinating-multi-model-work/routing-decision.md`
2. **Notify user**: "I will use [model] to [task purpose]"
3. **Invoke model** via MCP tools (`mcp__codex__codex` for backend, `mcp__gemini__gemini` for frontend, `mcp__cursor__cursor` for general)
4. **Integrate results** before proceeding

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

### General Implementation (Cursor MCP)

Use this template when Cursor is the **implementation agent** (CURSOR routing). This is distinct from the quality review template below.

```json
{
  "tool": "mcp__cursor__cursor",
  "params": {
    "PROMPT": "## Implementation Task\n\n### Context\n[Problem/task description — what needs to be built/fixed and why]\n\n### Code Location\nFile: [file_path]\nLines: [start_line]-[end_line]\n\nNote: Use your CLI tools to read the file at the specified location.\n\n### Requirements\n1. [Requirement 1]\n2. [Requirement 2]\n3. [Requirement 3]\n\n### Implementation Focus\n1. Correctness and edge case handling\n2. Clean, maintainable code\n3. Appropriate test coverage\n\n### Expected Output\n- Implementation with unified diff patch\n- Test cases covering the changes\n- Brief explanation of approach taken",
    "cd": "$PWD",
    "sandbox": "default",
    "SESSION_ID": "<reuse-or-new>"
  }
}
```

**CURSOR routing rules:**
- Fail-closed: BLOCKED if Cursor unavailable (same as CODEX/GEMINI)
- Quality review by Opus (never self-review) — see quality review template below
- Max 3 fix-review loops before escalating to user
- See `GATE.md` for tiered failure policy details

### Cross-Validation (Multiple Models)

Default: invoke Codex + Gemini in parallel, then integrate.
For critical/high-uncertainty tasks: optionally escalate to 3-way (Codex + Gemini + Cursor).

```markdown
## Cross-Validation Results

### Codex Analysis (Backend via mcp__codex__codex)

[Results]

### Gemini Analysis (Frontend via mcp__gemini__gemini)

[Results]

### Cursor Analysis (General via mcp__cursor__cursor) — optional 3-way

[Results]

### Integrated Conclusion

- **Agreement**: [Consistent findings]
- **Divergence**: [Differences]
- **Recommendation**: [Final determination]
```

### Code Quality Review (Cursor — when Codex/Gemini implements)

Use this template when Cursor is the **quality reviewer** (not the implementer). Only use when Codex or Gemini implemented the code.

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

**Quality review rules:**
- Pin review to a specific commit SHA (artifact pinning)
- Max 3 fix-review loops before escalating to user
- If Cursor unavailable at subagent stage 2: fall back to Opus quality reviewer
- If Cursor unavailable at CP3: proceed without (supplementary)

### Code Quality Review (Opus — when Cursor implements)

When Cursor is the implementer, use Opus for quality review (no self-review). Dispatch an Opus subagent using `superpowers-ccg:code-reviewer` with the same review focus as above.

## Important Rules

1. **All prompts to external models MUST be in English**
2. User notifications follow user's configured language
3. Always validate external model outputs before using
4. **Claude does NOT write implementation code** — route to CODEX, GEMINI, or CURSOR
5. **Deterministic reviewer:** `Reviewer = (Implementer == Cursor ? Opus : Cursor)`
