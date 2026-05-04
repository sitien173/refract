# Sonnet Worker Fallback Strategy

**Date:** 2026-04-06
**Status:** Design confirmed, ready for implementation

## Problem

When Codex or Gemini MCP tools are unavailable (server not running, not configured, or timing out), the current workflow hard-stops with `BLOCKED` status. No work gets done until the MCP infrastructure is restored. This creates unnecessary friction for users who could still get work done through alternative execution paths.

## Solution

Add a tiered failure handling strategy to CP2: retry the MCP call up to 2 times, then fall back to a Sonnet worker that implements the task via direct file editing using native Claude Code tools.

## Failure Handling Flow

```
CP2 External Execution (Codex/Gemini MCP call)
    |
    +-- SUCCESS --> continue to CP3/CP4 as normal
    |
    +-- FAILURE (timeout | tool-unavailable)
    |    |
    |    +-- Retry 1 --> same MCP tool, same params
    |    |    +-- SUCCESS --> continue normally
    |    |    +-- FAILURE
    |    |         |
    |    |         +-- Retry 2 --> same MCP tool, same params
    |    |              +-- SUCCESS --> continue normally
    |    |              +-- FAILURE --> FALLBACK: dispatch Sonnet worker
    |
    +-- FAILURE (permission-blocked)
         |
         +-- HARD BLOCKED (no retry, no fallback)
```

### Rules

- Retries are immediate (no delay) -- failure is infrastructure, not rate-limiting
- Each retry uses identical MCP params (same SESSION_ID if follow-up)
- After 2 failed retries, log a `[Fallback Triggered]` block for transparency
- `permission-blocked` is never retried or fallen back -- stays BLOCKED
- CP4 runs identically regardless of whether MCP or worker did the work

### Evidence Format (Fallback)

```text
[Multi-Model Gate]
Routing: CODEX | GEMINI
Status: FALLBACK
Reason: tool-unavailable | timeout (after 2 retries)
Fallback: Sonnet worker (direct file editing)
```

### Evidence Format (Hard Blocked)

```text
[Multi-Model Gate]
Routing: CODEX | GEMINI | CROSS_VALIDATION
Status: BLOCKED
Reason: permission-blocked
```

## Sonnet Worker Specification

### Invocation

```yaml
Agent:
  model: "sonnet"
  subagent_type: "general-purpose"
  description: "Fallback: implement [task summary]"
  prompt: |
    # Sonnet Fallback Implementation
    (uses sonnet-fallback-base.md template)
```

### Characteristics

- **Model:** Sonnet (cost-effective, fast, capable for bounded tasks)
- **Tools available:** Read, Edit, Write, Bash, Glob, Grep (full file access)
- **No MCP dependency** -- works entirely with native Claude Code tools
- **Direct editing** -- modifies files in-place, no protocol parsing needed
- **Isolation:** None by default (edits working tree directly). Use `isolation: "worktree"` for cross-validation fallback scenarios only.

### What the Worker Does NOT Do

- No External Response Protocol output
- No SESSION_ID tracking (one-shot dispatch)
- No CP3 reconciliation needed (single worker, direct edits)
- No follow-up session reuse -- if CP4 returns PARTIAL/FAIL, dispatch a new worker with delta context

### CP4 Integration

After worker completes, Claude reads modified files and runs CP4 spec review exactly as after a successful Codex/Gemini execution. The worker's result message serves as the summary.

### Cross-Validation Fallback

If both Codex AND Gemini fail during cross-validation, dispatch ONE Sonnet worker (not two). The fallback does not need parallel execution.

## File Changes

### New File

| File | Purpose |
|------|---------|
| `skills/coordinating-multi-model-work/prompts/sonnet-fallback-base.md` | Bounded implementation prompt template for Sonnet worker |

### Modified Files

| File | Change |
|------|--------|
| `skills/coordinating-multi-model-work/checkpoints.md` | Add "CP2 Failure & Fallback" subsection after CP2 -- retry logic (2x), fallback dispatch rules, evidence format |
| `skills/coordinating-multi-model-work/GATE.md` | Add FALLBACK status alongside BLOCKED, update failure handling to tiered policy |
| `skills/coordinating-multi-model-work/SKILL.md` | Add Sonnet fallback to Model Strategy mention, update Core Rules |
| `skills/shared/multi-model-integration-section.md` | Update Fallback section from hard BLOCKED to tiered retry + Sonnet fallback |
| `skills/executing-phases/SKILL.md` | Add Sonnet fallback row to Model Strategy table |

### Not Changed

- CP0/CP1/CP3/CP4 checkpoint sections -- untouched
- Codex/Gemini prompt templates -- untouched
- Hook scripts -- untouched (fallback is orchestrator logic)
- `lib/`, `bin/`, `templates/` -- untouched (no installer changes)
