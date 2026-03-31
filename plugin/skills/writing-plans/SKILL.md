---
name: writing-plans
description: "Creates comprehensive implementation plans with bite-sized tasks, exact file paths, and TDD steps. Use when: having a spec or requirements for multi-step tasks, before writing code. Keywords: implementation plan, task breakdown, planning, roadmap"
---

# Writing Plans

## Contents

- [Writing Plans](#writing-plans)
  - [Contents](#contents)
  - [Overview](#overview)
  - [Protocol Threshold (Required)](#protocol-threshold-required)
  - [Bite-Sized Task Granularity](#bite-sized-task-granularity)
  - [Plan Document Header](#plan-document-header)
  - [Task Structure](#task-structure)
  - [Execution Handoff](#execution-handoff)

## Overview

Write comprehensive implementation plans assuming the engineer has zero context for our codebase and questionable taste. Document everything they need to know: which files to touch for each task, code, testing, docs they might need to check, how to test it. Give them the whole plan as bite-sized tasks. DRY. YAGNI. TDD. Frequent commits.

## Protocol Threshold (Required)

Follow `skills/shared/protocol-threshold.md`. The hook injects CP reminders automatically.

Assume they are a skilled developer, but know almost nothing about our toolset or problem domain. Assume they don't know good test design very well.

**Announce at start:** "I'm using the writing-plans skill to create the implementation plan."

**REQUIRED FIRST STEP — Initialize Task Tracking:**

Before exploring code or writing the plan, you MUST:

1. Call `TaskList` to check for existing tasks from brainstorming
2. If tasks exist: enhance them with implementation details as you write each plan task (use `TaskUpdate` to add Steps, Verify, and metadata)
3. If no tasks exist: create them with `TaskCreate` as you write each task

Do not proceed to codebase exploration until `TaskList` has been called.

**► CP1 (Task Analysis):** Before writing the plan, apply `coordinating-multi-model-work/checkpoints.md`.

**Supplementary tools (optional, enhance planning):**
- **Sequential-Thinking:** For architecturally complex plans (3+ interacting components, multiple viable approaches), use Sequential-Thinking MCP to decompose task dependencies and validate the ordering.
- **Grok Search (Tavily):** When the plan involves unfamiliar libraries or APIs, use `mcp__grok-search__web_search` to gather current documentation and best practices before writing implementation steps.
- **Serena:** For plans that modify existing code, use Serena to understand current symbol relationships and identify all files that need modification.
- See `skills/shared/supplementary-tools.md` for full reference.

**Context:** This should be run in a dedicated worktree (created by brainstorming skill).

**Save plans to:** `docs/plans/YYYY-MM-DD-<feature-name>.md`

## Bite-Sized Task Granularity

**Each step is one action (2-5 minutes):**

- "Write the failing test" - step
- "Run it to make sure it fails" - step
- "Implement the minimal code to make the test pass" - step
- "Run the tests and make sure they pass" - step
- "Commit" - step

## Plan Document Header

**Every plan MUST start with this header:**

```markdown
# [Feature Name] Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** [One sentence describing what this builds]

**Architecture:** [2-3 sentences about approach]

**Tech Stack:** [Key technologies/libraries]

---
```

## Task Structure

````markdown
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
````

**Step 2: Run test to verify it fails**

Run: `pytest tests/path/test.py::test_name -v`
Expected: FAIL with "function not defined"

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

````

## Remember
- Exact file paths always
- Complete code in plan (not "add validation")
- Exact commands with expected output
- Reference relevant skills with @ syntax
- DRY, YAGNI, TDD, frequent commits

## Multi-Model Task Routing

**Related skill:** superpowers:coordinating-multi-model-work

When writing plans, you can optionally annotate tasks with model hints to guide execution. However, these hints are **suggestions only** - actual execution uses semantic analysis.

**Task annotation format (optional):**

```markdown
### Task N: [Component Name]
**Model hint:** `auto` | `codex` | `gemini` | `cross-validation`

**Files:**
- Create: `exact/path/to/file.py`
...
````

**Routing hint meanings:**

- `auto` - Executor determines routing through semantic analysis (default)
- `codex` - Suggests backend focus (API, database, algorithms)
- `gemini` - Suggests frontend focus (components, styles, interactions)
- `cross-validation` - Suggests critical task needing dual-model verification

**How execution handles hints:**

During plan execution (via `executing-plans` or `developing-with-subagents`):

1. Executor reads the `Model hint` if present
2. **Applies semantic routing** using `coordinating-multi-model-work/routing-decision.md`:
   - Collects task information (files, description, tech stack)
   - Analyzes task domain, complexity, and uncertainty
   - Makes routing decision based on semantic understanding
   - Uses hint as **guidance**, not strict rule

3. Routes task to optimal model (MCP tools):
   - Frontend → GEMINI (Gemini MCP `mcp__gemini__gemini`)
   - Backend → CODEX (Codex MCP `mcp__codex__codex`)
   - Full-stack/uncertain → CROSS_VALIDATION (call both MCP tools)
   - Simple → CLAUDE (no MCP call)

**Example with hints:**

```markdown
### Task 1: Create API endpoint

**Model hint:** `codex`

**Files:**

- Create: `server/api/users.go`
- Test: `server/api/users_test.go`
  ...

### Task 2: Create user profile component

**Model hint:** `gemini`

**Files:**

- Create: `src/components/UserProfile.tsx`
- Create: `src/components/UserProfile.css`
  ...

### Task 3: Integrate API with component

**Model hint:** `cross-validation`

**Files:**

- Modify: `src/components/UserProfile.tsx`
- Modify: `server/api/users.go`
  ...
```

**Important notes:**

- Model hints are **optional** - executor can always succeed without them
- Hints are **suggestions** - executor may route differently based on semantic analysis
- Missing or `auto` hint → Executor performs full semantic analysis
- Plan author doesn't need to understand routing logic deeply
- Focus on clear task descriptions and file paths; routing is handled automatically

## Native Task Integration Reference

Use Claude Code's native task tools to create structured tasks alongside the plan document. Follow the format in `skills/shared/task-format-reference.md`.

### Creating Tasks

For each task in the plan, create a corresponding native task. Embed metadata as a `json:metadata` code fence at the end of the description — this is the only way to ensure metadata survives TaskGet (the `metadata` parameter on TaskCreate is accepted but not returned by TaskGet).

~~~yaml
TaskCreate:
  subject: "Task N: [Component Name]"
  description: |
    **Goal:** [From task's Goal line]

    **Files:**
    [From task's Files section]

    **Acceptance Criteria:**
    [From task's Acceptance Criteria]

    **Verify:** [From task's Verify line]

    **Steps:**
    [Key actions from task's Steps — abbreviated]

    ```json:metadata
    {"files": ["path/to/file"], "verifyCommand": "command -v", "acceptanceCriteria": ["criterion 1", "criterion 2"]}
    ```
  activeForm: "Implementing [Component Name]"
~~~

### Setting Dependencies

After all tasks are created, wire blockedBy relationships:

~~~yaml
TaskUpdate:
  taskId: [dependent-task-id]
  addBlockedBy: [prerequisite-task-ids]
~~~

### Task Persistence File

At plan completion, write a `.tasks.json` file **in the same directory as the plan document**.

If the plan is `docs/plans/2026-01-15-feature.md`, the tasks file MUST be `docs/plans/2026-01-15-feature.md.tasks.json`.

```json
{
  "planPath": "docs/plans/YYYY-MM-DD-feature.md",
  "tasks": [
    {
      "id": 0,
      "subject": "Task 0: ...",
      "status": "pending",
      "description": "**Goal:** ...\n\n**Files:**\n...\n\n```json:metadata\n{\"files\": [\"path/to/file\"], \"verifyCommand\": \"command -v\", \"acceptanceCriteria\": [\"criterion 1\"]}\n```"
    },
    {
      "id": 1,
      "subject": "Task 1: ...",
      "status": "pending",
      "blockedBy": [0],
      "description": "**Goal:** ...\n\n```json:metadata\n{\"files\": [], \"verifyCommand\": \"\", \"acceptanceCriteria\": []}\n```"
    }
  ],
  "lastUpdated": "<ISO timestamp>"
}
```

Both the plan `.md` and `.tasks.json` must be co-located in `docs/plans/`.

### Resuming Work

Any new session can resume execution by running:
```
/superpowers-ccg:executing-plans <plan-path>
```
The skill reads the `.tasks.json` file and continues from the first `pending` or `in_progress` task.

## Execution Handoff

**► CP3 (Quality Gate):** Before handoff, apply `coordinating-multi-model-work/checkpoints.md`.

After saving the plan, offer execution choice:

**"Plan complete and saved to `docs/plans/<filename>.md`. Two execution options:**

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?"**

**If Subagent-Driven chosen:**

- **REQUIRED SUB-SKILL:** Use superpowers:developing-with-subagents
- Stay in this session
- Fresh subagent per task + code review

**If Parallel Session chosen:**

- Guide them to open new session in worktree
- **REQUIRED SUB-SKILL:** New session uses superpowers:executing-plans
