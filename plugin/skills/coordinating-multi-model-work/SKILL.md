---
name: coordinating-multi-model-work
description: "Routes work to Codex (backend), Gemini (frontend), and Cursor (general implementation) via MCP tools. Claude is orchestrator-only — all code goes through external models. Use when: any implementation task, UI/components/styles, APIs/databases/auth/security/performance, debugging, refactoring, code review, or tasks mentioning Codex/Gemini/Cursor/CCCG/multi-model. Keywords: codex mcp, gemini mcp, cursor mcp, cross-validation, implementation, api, database, auth, security, performance, ui, component, debugging, refactoring"
---

## Contents

- [Coordinating Multi-Model Work](#coordinating-multi-model-work)
  - [Overview](#overview)
  - [Core Instructions](#core-instructions)
  - [The Two Rules](#the-two-rules)
  - [Checkpoint Workflow](#checkpoint-workflow)
  - [Reference Files](#reference-files)

---

# Coordinating Multi-Model Work

## Overview

Claude is the **orchestrator** — it routes tasks, coordinates models, and integrates results but **never writes implementation code**.

Use this module to route implementation to the right external model:
- **Codex** (`mcp__codex__codex`) — backend: APIs, databases, algorithms, server-side logic
- **Gemini** (`mcp__gemini__gemini`) — frontend: UI, components, styles, interactions
- **Cursor** (`mcp__cursor__cursor`) — general: debugging, refactoring, DevOps, scripts, tasks not fitting Codex/Gemini

This module is intentionally minimal: it provides a small workflow and pushes details into reference files.

## Core Instructions

You **must** execute the steps below:

**1** After forming an initial analysis of the user request, share the request and your initial thinking with the appropriate external model (Codex/Gemini/Cursor based on routing) and ask them to improve the requirement analysis and implementation plan.

**2** Before implementing any concrete coding task, **route to the appropriate external model for implementation**. Claude does NOT write code — all coding goes through CODEX, GEMINI, or CURSOR.

**3** After the external model completes implementation, **obtain quality review**:
- If Codex/Gemini implemented → Cursor reviews code quality
- If Cursor implemented → Opus reviews code quality (no self-review)
- Deterministic rule: `Reviewer = (Implementer == Cursor ? Opus : Cursor)`

**4** All external models provide references and implementations. You **must** think independently and question their answers. Blind trust is worse than no trust; your joint mission is to converge on a unified, comprehensive, precise result.

## The Two Rules

1. **Main rule (Fail-Closed Gate):** If you decide `Routing != CLAUDE`, you MUST obtain external output, or STOP in `BLOCKED`. Since Claude never implements code, all coding tasks MUST go external.

2. **Early exposure:** If you decide `Routing != CLAUDE`, run the external call **before** doing real work (writing code, generating tests, or producing final conclusions).

## Checkpoint Workflow

At skill checkpoints (CP1/CP2/CP3):

1. Decide routing using `coordinating-multi-model-work/routing-decision.md`
2. If `Routing != CLAUDE`, apply `coordinating-multi-model-work/GATE.md` immediately (evidence or BLOCKED)
3. Continue only after evidence is recorded

## Reference Files

- **Checkpoint logic:** `coordinating-multi-model-work/checkpoints.md`
- **Routing framework (semantic):** `coordinating-multi-model-work/routing-decision.md`
- **Fail-closed gate + evidence format:** `coordinating-multi-model-work/GATE.md`
- **Invocation templates:** `coordinating-multi-model-work/INTEGRATION.md`
- **Quick heuristics (non-normative):** `coordinating-multi-model-work/routing-rules.md`
- **Cross-validation mechanism:** `coordinating-multi-model-work/cross-validation.md`
