# Superpowers CCCG - Agent Rules

> This document defines the skills, workflows, and principles for AI agents working in this project.
> Any agent MUST read and follow these rules.
>
> **Skill Namespace:** All skills use the `superpowers-cccg:` prefix (e.g., `superpowers-cccg:brainstorming`)

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

1. **Skills Before Action** - Check for applicable skills BEFORE any response or action. Even a 1% chance a skill applies means invoke it.
2. **Evidence Before Claims** - Never claim completion without running verification commands and confirming output.
3. **Root Cause Before Fixes** - No fixes without systematic investigation. Symptom fixes are failure.
4. **Test Before Code** - Write failing tests first. If you didn't watch it fail, you don't know if it tests the right thing.
5. **YAGNI Ruthlessly** - Remove unnecessary features from all designs. Don't build what's not needed.

---

## Iron Laws

These are non-negotiable. Violating them requires stopping and starting over.

| Iron Law | Skill | Consequence |
|----------|-------|-------------|
| `NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST` | TDD | Delete code, start over |
| `NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST` | Debugging | Return to Phase 1 |
| `NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE` | Verification | Run command, read output |
| `NO SKILL WITHOUT A FAILING TEST FIRST` | Writing Skills | Delete skill, start over |

---

## Skill Discovery

### How to Find Skills

GET Skills from superpowers-cccg plugin

**Namespace:** All skills use the `superpowers-cccg:` prefix.

**Invocation format:** `superpowers-cccg:<skill-name>` (e.g., `superpowers-cccg:brainstorming`)

### When to Use Skills

```
BEFORE any response or action:
  1. Could ANY superpowers-cccg: skill apply? (even 1% chance)
  2. If yes → Invoke skill immediately
  3. Announce: "I'm using superpowers-cccg:[skill] to [purpose]"
  4. Follow skill exactly
```

### Skill Priority

1. **Process skills first** (brainstorming, debugging) - determine HOW to approach
2. **Implementation skills second** (TDD, git-worktrees) - guide execution

---

## Primary Workflows

### Workflow 1: Creating Features (Creative Work)

```
superpowers-cccg:brainstorming → superpowers-cccg:writing-plans → [superpowers-cccg:using-git-worktrees] → superpowers-cccg:executing-plans OR superpowers-cccg:developing-with-subagents → superpowers-cccg:finishing-development-branches
```

| Step | Skill | Purpose |
|------|-------|---------|
| 1 | `superpowers-cccg:brainstorming` | Explore requirements, design before implementation |
| 2 | `superpowers-cccg:writing-plans` | Create bite-sized implementation plan |
| 3 | `superpowers-cccg:using-git-worktrees` | (Optional) Isolated workspace |
| 4 | `superpowers-cccg:executing-plans` OR `superpowers-cccg:developing-with-subagents` | Execute plan task-by-task |
| 5 | `superpowers-cccg:finishing-development-branches` | Verify tests, merge/PR/cleanup |

### Workflow 2: Debugging

```
superpowers-cccg:debugging-systematically → [TDD for fix] → superpowers-cccg:verifying-before-completion
```

| Phase | Action |
|-------|--------|
| 1. Root Cause Investigation | Read errors, reproduce, check changes, trace data flow |
| 2. Pattern Analysis | Find working examples, compare differences |
| 3. Hypothesis & Testing | Single hypothesis, minimal test, verify |
| 4. Implementation | Create failing test, single fix, verify |

### Workflow 3: Code Review

```
superpowers-cccg:requesting-code-review → [reviewer subagent] → superpowers-cccg:receiving-code-review → [implement fixes]
```

---

## Skills Reference

### Process Skills

| Skill | Trigger | Purpose |
|-------|---------|---------|
| `superpowers-cccg:brainstorming` | Creating features, building components, starting creative work | Explore requirements and design before implementation |
| `superpowers-cccg:debugging-systematically` | Bugs, test failures, unexpected behavior, errors | Find root cause through four-phase investigation |
| `superpowers-cccg:practicing-test-driven-development` | Implementing features, fixing bugs, refactoring | Red-green-refactor cycle |
| `superpowers-cccg:verifying-before-completion` | About to claim work is done, before commit/PR | Ensure evidence before assertions |

### Planning Skills

| Skill | Trigger | Purpose |
|-------|---------|---------|
| `superpowers-cccg:writing-plans` | Have spec/requirements, before coding | Create detailed implementation plan with bite-sized tasks |
| `superpowers-cccg:executing-plans` | Have plan document, separate session | Execute plan in batches with review checkpoints |
| `superpowers-cccg:developing-with-subagents` | Have plan, same session, independent tasks | Fresh subagent per task with two-stage review |

### Git/Workspace Skills

| Skill | Trigger | Purpose |
|-------|---------|---------|
| `superpowers-cccg:using-git-worktrees` | Starting feature work needing isolation | Create isolated git worktree |
| `superpowers-cccg:finishing-development-branches` | Implementation complete, tests pass | Guide merge/PR/cleanup options |

### Review Skills

| Skill | Trigger | Purpose |
|-------|---------|---------|
| `superpowers-cccg:requesting-code-review` | Completing tasks, before merge | Dispatch code reviewer subagent |
| `superpowers-cccg:receiving-code-review` | Got review feedback | Evaluate feedback with technical rigor |

### Parallel Execution

| Skill | Trigger | Purpose |
|-------|---------|---------|
| `superpowers-cccg:dispatching-parallel-agents` | 2+ independent tasks, parallel investigations | One agent per problem domain |

### Meta Skills

| Skill | Trigger | Purpose |
|-------|---------|---------|
| `superpowers-cccg:using-superpowers` | Starting conversation, need skill guidance | How to find and use skills |
| `superpowers-cccg:writing-skills` | Creating/editing skills | TDD for process documentation |
| `superpowers-cccg:coordinating-multi-model-work` | Any implementation work, cross-validation needed | Route to Codex/Gemini/Cursor via MCP |

---

## Commands Reference

These are quick-invoke workflows located in `commands/`.

| Command | Invokes Skill | Purpose |
|---------|---------------|---------|
| `/brainstorm` | `superpowers-cccg:brainstorming` | Start creative exploration |
| `/write-plan` | `superpowers-cccg:writing-plans` | Create implementation plan |
| `/execute-plan` | `superpowers-cccg:executing-plans` | Execute plan in batches |

---

## Multi-Model Coordination

### Routing Labels

| Label | When to Use | MCP Tool |
|-------|-------------|----------|
| `CODEX` | Backend: API, database, algorithms, auth, security | `mcp__codex__codex` |
| `GEMINI` | Frontend: UI, components, styles, interactions | `mcp__gemini__gemini` |
| `CURSOR` | General: debugging, refactoring, DevOps, scripts, tasks not fitting Codex/Gemini | `mcp__cursor__cursor` |
| `CROSS_VALIDATION` | Full-stack, uncertain, critical tasks | Multiple MCP tools |
| `CLAUDE` | Orchestration only: routing, coordination, docs editing (NO code) | No MCP call |

> **Important:** Claude is the **orchestrator** — it routes tasks, coordinates models, and integrates results but **never writes implementation code**. All coding tasks must route to CODEX, GEMINI, or CURSOR. If all external models are unavailable, the task is BLOCKED by design.

### Cursor (Dual Role)

Cursor serves two distinct roles:

**1. Implementation Agent (CURSOR routing):**
- Debugging, refactoring, DevOps, scripts, general implementation
- Catches all tasks that don't clearly fit CODEX or GEMINI
- Fail-closed: BLOCKED if unavailable

**2. Quality Reviewer (automatic, when Codex/Gemini implements):**
- Reviews code quality at subagent stage 2 and CP3
- Falls back to Opus if unavailable at stage 2
- Proceeds without if unavailable at CP3

**Deterministic Reviewer Rule:** `Reviewer = (Implementer == Cursor ? Opus : Cursor)`
- When Cursor implements → Opus reviews (no self-review)
- When Codex/Gemini implements → Cursor reviews

Max 3 fix-review loops before escalating to user. Docs-only changes are exempt.

### Core Instructions

1. **Route to external model** - After initial analysis, route implementation to the appropriate model (Codex/Gemini/Cursor)
2. **Claude does NOT write code** - All coding goes through external models; Claude orchestrates only
3. **Obtain quality review** - After implementation, get quality review from the deterministic reviewer
4. **Think independently** - Question external model answers; blind trust is worse than no trust

### Fail-Closed Gate

```
IF Routing != CLAUDE:
  MUST obtain external output
  OR STOP in BLOCKED state
  
DO NOT proceed without evidence
```

---

## Checkpoints Protocol

Skills use checkpoints (CP1, CP2, CP3) for quality gates.

### CP1 - Task Analysis (Before First Task Call)

```
[CP1 Assessment]
Task: <description>
Files: <involved files>
Tech Stack: <technologies>
Routing: CLAUDE | CODEX | GEMINI | CURSOR | CROSS_VALIDATION
Action: <proceed | invoke external>
```

### CP2 - Mid-Review (During Execution)

Triggers:
- Multiple implementation approaches
- 2+ failed fix attempts
- Debugging stalled
- Blocked or uncertain

### CP3 - Quality Gate (Before Completion Claims)

```
[CP3 Assessment]
Verification: <command run and output>
Result: <pass | fail>
Evidence: <proof>
Routing: <if external review needed>
```

---

## Red Flags

### Stop Immediately If You Think:

| Thought | Reality |
|---------|---------|
| "This is just a simple question" | Questions are tasks. Check for skills. |
| "I need more context first" | Skill check comes BEFORE clarifying questions. |
| "Let me explore the codebase first" | Skills tell you HOW to explore. Check first. |
| "Quick fix for now, investigate later" | No fixes without root cause. |
| "Just try changing X and see if it works" | Systematic debugging is faster. |
| "Skip TDD just this once" | That's rationalization. |
| "Should work now" | RUN the verification. |
| "I'm confident" | Confidence ≠ evidence. |
| "One more fix attempt" (after 2+) | 3+ failures = architectural problem. |

### Forbidden Responses

- "You're absolutely right!" (performative agreement)
- "Great point!" / "Excellent feedback!" (performative)
- "Let me implement that now" (before verification)
- Using "should", "probably", "seems to" for completion claims
- Expressing satisfaction before verification ("Great!", "Perfect!", "Done!")

---

## Task Structure (For Plans)

```markdown
### Task N: [Component Name]

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py:123-145`
- Test: `tests/exact/path/to/test.py`

**Step 1: Write the failing test**
```python
def test_specific_behavior():
    result = function(input)
    assert result == expected
```

**Step 2: Run test to verify it fails**
Run: `pytest tests/path/test.py::test_name -v`
Expected: FAIL

**Step 3: Write minimal implementation**
```python
def function(input):
    return expected
```

**Step 4: Run test to verify it passes**
Run: `pytest tests/path/test.py::test_name -v`
Expected: PASS

**Step 5: Commit**
```bash
git add tests/path/test.py src/path/file.py
git commit -m "feat: add specific feature"
```
```

---

## Model Selection (For Subagents)

See `superpowers-cccg:developing-with-subagents` and `superpowers-cccg:dispatching-parallel-agents` for details.

| Task Type | Model |
|-----------|-------|
| Backend implementation | Codex MCP (`mcp__codex__codex`) |
| Frontend implementation | Gemini MCP (`mcp__gemini__gemini`) |
| General implementation (debugging, refactoring, DevOps) | Cursor MCP (`mcp__cursor__cursor`) |
| Review, architecture, complex reasoning | Opus (default) |
| Exploration, search, quick lookups | `model: haiku` |
| Quality review (Codex/Gemini implements) | Cursor MCP (`mcp__cursor__cursor`); Opus fallback |
| Quality review (Cursor implements) | Opus (no self-review) |

---

## Quick Reference Card

```
┌─────────────────────────────────────────────────────────────┐
│ BEFORE ANY ACTION                                           │
│ ✓ Could any superpowers-cccg: skill apply? → Invoke skill    │
│ ✓ Check for applicable iron laws                            │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ CREATIVE WORK (superpowers-cccg:*)                           │
│ brainstorming → writing-plans → [using-git-worktrees]       │
│ → executing-plans OR developing-with-subagents              │
│ → finishing-development-branches                            │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ DEBUGGING (superpowers-cccg:debugging-systematically)        │
│ Root Cause → Pattern → Hypothesis → Implementation          │
│ (NO FIXES until Phase 1 complete)                           │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ TDD (superpowers-cccg:practicing-test-driven-development)    │
│ RED (write failing test) → GREEN (minimal code) → REFACTOR  │
│ (NO CODE without failing test first)                        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ COMPLETION (superpowers-cccg:verifying-before-completion)    │
│ Run verification → Read output → THEN claim result          │
│ (NO CLAIMS without evidence)                                │
└─────────────────────────────────────────────────────────────┘
```

---

*This document is the authoritative reference for agent behavior in superpowers-cccg.*
