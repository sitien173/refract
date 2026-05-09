# Superpowers CCG - Agent Rules

> This document defines the skills, workflows, and principles for AI agents working in this project.
> Any agent MUST read and follow these rules.
>
> **Skill Namespace:** All skills use the `superpowers-ccg:` prefix (for example `superpowers-ccg:brainstorming`).

---

## Table of Contents

- Core Philosophy
- Iron Laws
- Skill Discovery
- Primary Workflows
- Skills Reference
- Commands Reference
- Multi-Model Coordination
- Red Flags

---

## Core Philosophy

1. **Skills Before Action** - Check for applicable skills before any response or action.
2. **Evidence Before Claims** - Never claim completion without verification evidence.
3. **Root Cause Before Fixes** - No fixes without investigation.
4. **Test Before Code** - Write failing tests first.
5. **YAGNI Ruthlessly** - Remove unnecessary features from designs.

---

## Iron Laws

| Iron Law | Enforced By | Consequence |
|----------|-------------|-------------|
| `NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST` | Testing discipline | Delete code, start over |
| `NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST` | Debugging | Return to Phase 1 |
| `NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE` | Verification | Run command, read output |

---

## Skill Discovery

### How to Find Skills

Get skills from the `superpowers-ccg` plugin.

**Namespace:** `superpowers-ccg:`

**Invocation format:** `superpowers-ccg:<skill-name>`

### When to Use Skills

```text
BEFORE any response or action:
  1. Could any superpowers-ccg: skill apply?
  2. If yes, invoke it immediately.
  3. Announce: "I'm using superpowers-ccg:[skill] to [purpose]"
  4. Follow the skill exactly.
```

---

## Primary Workflows

### Workflow 1: Creating Features

```text
superpowers-ccg:brainstorming → superpowers-ccg:writing-plans → superpowers-ccg:executing-plans → superpowers-ccg:verifying-before-completion
```

### Workflow 2: Debugging

```text
superpowers-ccg:debugging-systematically → [TDD for fix] → superpowers-ccg:verifying-before-completion
```

## Skills Reference

### Process Skills

| Skill | Trigger | Purpose |
|-------|---------|---------|
| `superpowers-ccg:brainstorming` | Creating features, building components, starting creative work | Explore requirements and design before implementation |
| `superpowers-ccg:debugging-systematically` | Bugs, test failures, unexpected behavior, errors | Find root cause through four-phase investigation |
| `superpowers-ccg:verifying-before-completion` | About to claim work is done | Ensure evidence before assertions |

### Planning Skills

| Skill | Trigger | Purpose |
|-------|---------|---------|
| `superpowers-ccg:writing-plans` | Have spec/requirements before coding | Create phase-based implementation plan |
| `superpowers-ccg:executing-plans` | Have a plan document, active phase, or same-session execution request | Route one phase at a time with review and integration |

### Meta Skills

| Skill | Trigger | Purpose |
|-------|---------|---------|
| `superpowers-ccg:coordinating-multi-model-work` | Any implementation work, cross-validation needed | Route to Codex/Gemini via MCP |

---

## Commands Reference

| Command | Invokes Skill | Purpose |
|---------|---------------|---------|
| `/brainstorm` | `superpowers-ccg:brainstorming` | Start creative exploration |
| `/write-plan` | `superpowers-ccg:writing-plans` | Create implementation plan |
| `/execute-plan` | `superpowers-ccg:executing-plans` | Execute one phase at a time |

---

## Multi-Model Coordination

Routing matrix, tiebreakers, and failure handling: `rules/ccg-workflow.mdc` (always loaded).
Checkpoint protocol details: `skills/coordinating-multi-model-work/checkpoints.md`.
Phase review: `skills/coordinating-multi-model-work/review-chain.md`.

| Label | MCP Tool |
|-------|----------|
| `CODEX` | `mcp__codex__codex` — default executor |
| `GEMINI` | `mcp__gemini__gemini` — UI/multimodal/large-context |
| `CROSS_VALIDATION` | Both — rare arbitration only |
| `CLAUDE` | None — planning, review, integration, docs |

---

## Red Flags

| Thought | Reality |
|---------|---------|
| "This is just a simple question" | Questions are tasks. Check for skills. |
| "Let me explore first" | Skill check comes first. |
| "Quick fix now, investigate later" | No fixes without root cause. |
| "Should work now" | Run verification. |
| "I'm confident" | Confidence is not evidence. |

### Forbidden Responses

- "You're absolutely right!"
- "Great point!"
- "Let me implement that now" before verification
- "should", "probably", or "seems to" for completion claims

---

*This document is the authoritative reference for agent behavior in superpowers-ccg. Routing, checkpoints, and failure handling are canonical in `rules/ccg-workflow.mdc` and `skills/coordinating-multi-model-work/`.*
