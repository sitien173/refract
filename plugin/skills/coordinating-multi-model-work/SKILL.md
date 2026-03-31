---
name: coordinating-multi-model-work
description: "Routes work to Codex (backend and systems) and Gemini (frontend) via MCP tools. Claude is orchestrator-only — all code goes through external models. Use when: any implementation task, UI/components/styles, APIs/databases/auth/security/performance, DevOps/CI/scripts, or tasks mentioning Codex/Gemini/CCG/multi-model. Keywords: codex mcp, gemini mcp, cross-validation, implementation, api, database, auth, security, performance, ui, component, devops, ci/cd"
---

## Contents

- Overview
- Core Instructions
- The Two Rules
- Checkpoint Workflow
- Reference Files

---

# Coordinating Multi-Model Work

## Overview

Claude is the **orchestrator**. It routes tasks, coordinates models, and integrates results, but **never writes implementation code**.

Use this module to route implementation to the right external model:
- **Codex** (`mcp__codex__codex`) — backend and systems: APIs, databases, algorithms, server-side logic, CI/CD, scripts, Dockerfiles, infrastructure
- **Gemini** (`mcp__gemini__gemini`) — frontend: UI, components, styles, interactions

For review chain details, see `coordinating-multi-model-work/review-chain.md`.

## Core Instructions

1. After forming an initial analysis of the user request, share the request and your initial thinking with the appropriate external model and ask it to improve the requirement analysis and implementation plan.
2. Before implementing any concrete coding task, route to the appropriate external model for implementation. Claude does not write code.
3. After the external model completes implementation, obtain Opus review per `coordinating-multi-model-work/review-chain.md`.
4. Think independently and question external model output.

## The Two Rules

1. **Main rule (Fail-Closed Gate):** If you decide `Routing != CLAUDE`, you must obtain external output or stop in `BLOCKED`.
2. **Early exposure:** If you decide `Routing != CLAUDE`, run the external call before doing real work.

## Checkpoint Workflow

At skill checkpoints (CP1/CP2/CP3):

1. Decide routing using `coordinating-multi-model-work/routing-decision.md`
2. If `Routing != CLAUDE`, apply `coordinating-multi-model-work/GATE.md` immediately
3. Continue only after evidence is recorded

## Token Optimization (Response Protocol)

All external model prompts include the response protocol stored in Serena shared memory (`global/response_protocol`).

## Reference Files

- `coordinating-multi-model-work/checkpoints.md`
- `coordinating-multi-model-work/routing-decision.md`
- `coordinating-multi-model-work/GATE.md`
- `coordinating-multi-model-work/INTEGRATION.md`
- `coordinating-multi-model-work/review-chain.md`
- `coordinating-multi-model-work/cross-validation.md`
