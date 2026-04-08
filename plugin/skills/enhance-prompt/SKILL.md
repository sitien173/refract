---
name: enhance-prompt
description: "Enhances a user prompt with codebase context, structure, and conventions using the prompt-enhancer MCP. Use when: prompt is vague, task needs context injection, or before routing to external models. Keywords: enhance, improve prompt, clarify, context, refine request"
---

# Enhance Prompt

## Overview

Improve a raw or vague prompt by injecting relevant codebase context, structure, and conventions via the `mcp__prompt-enahncer__enhance_prompt` MCP tool. Use this to sharpen task descriptions before routing them through the CP workflow.

## When to Use

- The user's prompt is ambiguous or lacks architectural context
- You are about to route a task to Codex or Gemini and want to improve signal quality
- The user explicitly invokes `/enhance-prompt`
- A task description would benefit from referencing existing patterns, conventions, or file structure

## The Process

**Step 1 — Capture the prompt**

Take the user's raw prompt as-is. If invoked standalone (via `/enhance-prompt`), ask for the prompt if not already provided.

**Step 2 — Call the MCP tool**

```
mcp__prompt-enahncer__enhance_prompt
  prompt: <raw user prompt>
  workspacePath: <current working directory, if known>
```

- Always pass `workspacePath` when you know the project root (use the active working directory).
- Pass the prompt verbatim — do not pre-process or summarize it before sending.

**Step 3 — Present the enhanced prompt**

Show the enhanced prompt to the user in a fenced block. Ask:

> "Does this look right? Should I proceed with this enhanced prompt, adjust it, or use the original?"

**Step 4 — Proceed or hand off**

- If the user confirms → use the enhanced prompt as the active task description going forward.
- If the user adjusts → incorporate their edit and re-present.
- If the user declines → fall back to the original prompt.
- If continuing into implementation → apply CP1 routing using the (now enhanced) prompt.

## Integration with CP Workflow

This skill can be called:

1. **Standalone** via `/enhance-prompt` before the user starts a task
2. **Inline at CP0** — Claude may invoke it silently when a task prompt is thin, then use the result as the CP1 task summary

When used inline, do not ask for confirmation — apply the enhancement and continue. Surface the enhanced prompt in the CP1 task summary block so the user can see what was used.

## Error Handling

- If the MCP call fails, log a warning and proceed with the original prompt unchanged.
- Do not block the workflow on enhancement failure — it is a quality improvement, not a gate.

## Key Principles

- **Verbatim input** — Never alter the prompt before sending to the MCP; let the tool do the enrichment.
- **Transparent output** — Always show the enhanced prompt; never apply it silently in standalone mode.
- **Non-blocking** — Enhancement failure must not stop the workflow.
- **Workspace-aware** — Pass `workspacePath` whenever available for better context injection.
