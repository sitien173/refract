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
- Checkpoints Protocol
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
superpowers-ccg:brainstorming → superpowers-ccg:writing-plans → superpowers-ccg:executing-plans OR superpowers-ccg:executing-phases → superpowers-ccg:verifying-before-completion
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
| `superpowers-ccg:executing-plans` | Have a plan document | Execute one phase at a time |
| `superpowers-ccg:executing-phases` | Have a plan and implementation phases | Route one phase at a time with review and integration |

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

### Routing Labels

| Label | When to Use | MCP Tool |
|-------|-------------|----------|
| `CODEX` | Default implementation: backend, full-stack, tests, debugging, shell scripts, Dockerfiles, CI/CD, infrastructure, repo tooling | `mcp__codex__codex` |
| `GEMINI` | UI-heavy visual phases: layout, components, styles, interactions, motion, canvas/SVG | `mcp__gemini__gemini` |
| `CROSS_VALIDATION` | Unresolved architecture or true multi-domain conflict | Multiple MCP tools |
| `CLAUDE` | Planning, review, integration, routing, coordination, docs editing, or clarification | No MCP call |

> **Important:** Claude is the planner, orchestrator, reviewer, and integrator. Codex is the default executor. Gemini is only for UI-heavy phases. If Codex or Gemini MCP execution fails, the phase stops with `BLOCKED`.

### Phase Review

CP4 runs after each implementation phase. Claude reviews against the original request, CP1 success criteria, reviewer checklist, and integration results. Status is `PASS`, `PASS_WITH_DEBT`, or `FAIL`. See `coordinating-multi-model-work/review-chain.md`.

### Core Instructions

1. **Route to an executor** after initial analysis.
2. **Codex first for most implementation**.
3. **Gemini only for UI-heavy phases**.
4. **Claude performs CP4 phase review** after implementation.
5. **Think independently** and challenge external model output.
6. **Fail closed**: if required MCP evidence is missing or executor MCP execution fails, output `BLOCKED`.
7. **Use the inline External Response Protocol v1.1** in the active CP2 docs and prompts.

---

## Checkpoints Protocol

- **CP0** — Before CP1: decide whether selective `docs/wiki/` durable knowledge lookup is useful, then acquire only the minimum current code context needed to route the next phase, and normalize useful findings into reusable context artifacts
- **CP1** — Immediately after CP0: perform Phase Assessment & Routing using the CP1 routing matrix, then invoke the selected executor if needed
- **CP2** — External Execution: after CP1 routes to Codex, Gemini, or Cross-Validation, the executor performs the phase using a phase-scoped context bundle, edits files directly via MCP write tools, and reports the changed-file list via External Response Protocol v1.1
- **CP3** — Reconciliation: after cross-validation or non-trivial external feedback, resolve conflicts and hand off to CP4
- **CP4** — Phase Review: run after each phase and determine PASS / PASS_WITH_DEBT / FAIL against the original requirement, reviewer checklist, and integration results

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

## Default Model Routing

| Task Type | Model |
|-----------|-------|
| Most implementation | Codex MCP (`mcp__codex__codex`) |
| UI-heavy visual implementation | Gemini MCP (`mcp__gemini__gemini`) |
| Unresolved architecture conflict | Cross-Validation (`CODEX` + `GEMINI`) |
| Planning, orchestration, clarification, CP3 reconciliation, CP4 phase review, integration | Claude main thread |

Claude `haiku` / `sonnet` / `opus` Task selection is no longer the default implementation route. Only use those legacy Task models when a separate skill explicitly requires them.

### Context Retrieval

Use Auggie for full local codebase context retrieval during CP0. Use Grok Search only when the task needs external/current knowledge or web research.

### Supplementary Tools

Supplementary tools are optional enhancements. See `skills/shared/supplementary-tools.md`.

---

*This document is the authoritative reference for agent behavior in superpowers-ccg.*
