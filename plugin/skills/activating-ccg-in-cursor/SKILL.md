---
name: activating-ccg-in-cursor
description: "Activates the CCG multi-model workflow in Cursor. Use when: starting a new session, setting up CCG orchestration, or when the user mentions CCG, multi-model, Codex, or Gemini routing."
---

# Activating CCG in Cursor

## Overview

This skill bootstraps the CCG (Claude + Codex + Gemini) workflow in Cursor. Claude plans phases, routes execution, reviews outputs, and runs integration checks. Codex is the default executor; Gemini is reserved for UI-heavy phases.

## When to Activate

- Starting a new implementation session
- User mentions "CCG", "multi-model", "Codex", or "Gemini"
- Complex tasks requiring external model coordination

## Activation Steps

1. **Verify MCP Tools**
   - Check for `mcp__codex__codex` availability
   - Check for `mcp__gemini__gemini` availability
   - If Gemini is unstable, note fallback to Codex or Claude-code after one failure

2. **Load Core Skills**
   - `coordinating-multi-model-work` for routing
   - `brainstorming` for design exploration
   - `writing-plans` for implementation planning
   - `executing-plans` for phase execution

3. **Confirm Protocol**
   - CP0 → CP1 → CP2 → CP3 → CP4 checkpoint flow
   - External Response Protocol v1.1 for all MCP calls
   - Phase discipline (2-4 related tasks, one primary executor, one review, one integration gate)

## Post-Activation

Tell the user:
- CCG workflow is active
- Which MCP tools are available
- Ready to route tasks to Codex/Gemini

## Reference

See `skills/coordinating-multi-model-work/SKILL.md` for full routing rules and checkpoint protocol.
