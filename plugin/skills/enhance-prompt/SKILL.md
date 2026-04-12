---
name: enhance-prompt
description: "Enhances user prompts with codebase context and conventions before routing. Use when: the user provides a brief request that needs context enrichment, or when preparing a prompt for external model routing."
---

# Enhance Prompt

## Overview

Take a raw user prompt and enrich it with codebase context, conventions, and relevant file references before routing through the CCG workflow.

## Process

### Step 1: Understand Intent

- Parse the user's request
- Identify the core goal
- Note any mentioned files or features

### Step 2: Gather Context

Use CP0-style context acquisition:
- **Auggie** for local codebase context
- **Grok Search** for external/current knowledge (if needed)
- Identify relevant files, patterns, and conventions

### Step 3: Enrich the Prompt

Add to the original request:
- Relevant file paths
- Existing patterns to follow
- Project conventions
- Constraints or dependencies

### Step 4: Format for Routing

Produce an enhanced prompt ready for CP1 routing:

```markdown
## Original Request
[User's original prompt]

## Context
- Files in scope: [list]
- Patterns to follow: [patterns]
- Conventions: [conventions]

## Enhanced Request
[Enriched version of the request with full context]
```

## When to Use

- Brief user requests lacking context
- Before routing to Codex/Gemini
- When the user says "enhance" or asks for context enrichment

## Output

Return the enhanced prompt ready for CP1 task assessment and routing.
