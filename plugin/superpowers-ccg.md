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

| Iron Law | Skill | Consequence |
|----------|-------|-------------|
| `NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST` | TDD | Delete code, start over |
| `NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST` | Debugging | Return to Phase 1 |
| `NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE` | Verification | Run command, read output |
| `NO SKILL WITHOUT A FAILING TEST FIRST` | Writing Skills | Delete skill, start over |

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
superpowers-ccg:brainstorming → superpowers-ccg:writing-plans → [superpowers-ccg:using-git-worktrees] → superpowers-ccg:executing-plans OR superpowers-ccg:developing-with-subagents → superpowers-ccg:finishing-development-branches
```

### Workflow 2: Debugging

```text
superpowers-ccg:debugging-systematically → [TDD for fix] → superpowers-ccg:verifying-before-completion
```

### Workflow 3: Code Review

```text
superpowers-ccg:requesting-code-review → [reviewer subagent] → superpowers-ccg:receiving-code-review → [implement fixes]
```

---

## Skills Reference

### Process Skills

| Skill | Trigger | Purpose |
|-------|---------|---------|
| `superpowers-ccg:brainstorming` | Creating features, building components, starting creative work | Explore requirements and design before implementation |
| `superpowers-ccg:debugging-systematically` | Bugs, test failures, unexpected behavior, errors | Find root cause through four-phase investigation |
| `superpowers-ccg:practicing-test-driven-development` | Implementing features, fixing bugs, refactoring | Red-green-refactor cycle |
| `superpowers-ccg:verifying-before-completion` | About to claim work is done | Ensure evidence before assertions |

### Planning Skills

| Skill | Trigger | Purpose |
|-------|---------|---------|
| `superpowers-ccg:writing-plans` | Have spec/requirements before coding | Create detailed implementation plan |
| `superpowers-ccg:executing-plans` | Have a plan document | Execute plan in batches |
| `superpowers-ccg:developing-with-subagents` | Have a plan and independent tasks | Fresh subagent per task with review |

### Git/Workspace Skills

| Skill | Trigger | Purpose |
|-------|---------|---------|
| `superpowers-ccg:using-git-worktrees` | Starting feature work needing isolation | Create isolated git worktree |
| `superpowers-ccg:finishing-development-branches` | Implementation complete, tests pass | Guide merge/PR/cleanup |

### Review Skills

| Skill | Trigger | Purpose |
|-------|---------|---------|
| `superpowers-ccg:requesting-code-review` | Completing tasks before merge | Dispatch code reviewer subagent |
| `superpowers-ccg:receiving-code-review` | Got review feedback | Evaluate feedback with rigor |

### Parallel Execution

| Skill | Trigger | Purpose |
|-------|---------|---------|
| `superpowers-ccg:dispatching-parallel-agents` | 2+ independent tasks | One agent per problem domain |

### Meta Skills

| Skill | Trigger | Purpose |
|-------|---------|---------|
| `superpowers-ccg:using-superpowers` | Starting conversation, need skill guidance | How to find and use skills |
| `superpowers-ccg:writing-skills` | Creating/editing skills | TDD for process documentation |
| `superpowers-ccg:coordinating-multi-model-work` | Any implementation work, cross-validation needed | Route to Codex/Gemini via MCP |

---

## Commands Reference

| Command | Invokes Skill | Purpose |
|---------|---------------|---------|
| `/brainstorm` | `superpowers-ccg:brainstorming` | Start creative exploration |
| `/write-plan` | `superpowers-ccg:writing-plans` | Create implementation plan |
| `/execute-plan` | `superpowers-ccg:executing-plans` | Execute plan in batches |

---

## Multi-Model Coordination

### Routing Labels

| Label | When to Use | MCP Tool |
|-------|-------------|----------|
| `CODEX` | Backend and systems: API, database, auth, shell scripts, Dockerfiles, CI/CD, infrastructure, repo tooling | `mcp__codex__codex` |
| `GEMINI` | Frontend: UI, components, styles, interactions | `mcp__gemini__gemini` |
| `CROSS_VALIDATION` | Full-stack, uncertain, or critical tasks | Multiple MCP tools |
| `CLAUDE` | Orchestration only: routing, coordination, docs editing (no implementation code) | No MCP call |

> **Important:** Claude is the orchestrator. It routes tasks, coordinates models, and integrates results, but never writes implementation code. All coding tasks must route to CODEX or GEMINI.

### Review Chain

Opus reviews all code-changing paths directly. See `coordinating-multi-model-work/review-chain.md`.

### Core Instructions

1. **Route to an external model** after initial analysis.
2. **Claude does not write code**.
3. **Opus reviews all code** after implementation.
4. **Think independently** and challenge external model output.
5. **Fail closed**: if required MCP evidence is missing, output `BLOCKED`.
6. **Use the response protocol** from `global/response_protocol`.

---

## Checkpoints Protocol

- **CP1** — Before first Task call: assess routing and invoke external model if needed
- **CP2** — Mid-execution: triggered by uncertainty, stalled debugging, or repeated failures
- **CP3** — Before claiming completion: run verification, record evidence, run review chain

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

## Model Selection (For Subagents)

| Task Type | Model |
|-----------|-------|
| Backend and systems implementation | Codex MCP (`mcp__codex__codex`) |
| Frontend implementation | Gemini MCP (`mcp__gemini__gemini`) |
| Review and architecture | Opus |
| Exploration and search | `model: haiku` |

### Shared Context Layer (Serena HTTP)

All agents (Claude, Codex, Gemini) connect to a single Serena instance via Streamable HTTP (port 9121).

### Supplementary Tools

Supplementary tools are optional enhancements. See `skills/shared/supplementary-tools.md`.

---

*This document is the authoritative reference for agent behavior in superpowers-ccg.*
