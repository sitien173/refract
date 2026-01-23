---
name: coordinating-multi-model-work
description: "Routes work to Codex (backend) and Gemini (frontend) via codeagent-wrapper, with cross-validation for full-stack/uncertain tasks. Use when: UI/components/styles, APIs/databases/auth/security/performance, debugging, code review, or tasks mentioning Codex/Gemini/CCG/multi-model. Keywords: codeagent-wrapper, codex, gemini, cross-validation, api, database, auth, security, performance, ui, component"
---

## Contents
- [Overview](#overview)
- [The Two Rules](#the-two-rules)
- [Checkpoint Workflow](#checkpoint-workflow)
- [Reference Files](#reference-files)

---

# Coordinating Multi-Model Work

## Overview

Use this module to decide whether to call **Codex** (backend) and/or **Gemini** (frontend) via `codeagent-wrapper`, and to enforce a consistent evidence protocol.

This module is intentionally minimal: it provides a small workflow and pushes details into reference files.

## The Two Rules

1) **Main rule (Fail-Closed Gate):** If you decide `Routing != CLAUDE`, you MUST obtain external output, or STOP in `BLOCKED`.

2) **Early exposure:** If you decide `Routing != CLAUDE`, run the external call **before** doing real work (writing code, generating tests, or producing final conclusions).

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