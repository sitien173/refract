---
name: writing-plans
description: "Creates implementation plans made of bounded worker-owned tasks with explicit file sets, verification commands, and minimal execution context."
---

# Writing Plans

## Overview

Write plans for execution by external workers, not for a human narrator. Each task should be small enough that one worker can own it end-to-end without restating the whole project.

## Rules

1. Read the codebase and design docs only as much as needed.
2. Break work into bounded tasks with explicit ownership.
3. Each task must have:
   - clear goal
   - explicit file set
   - acceptance criteria
   - exact verify command
4. Prefer one worker owner per task.
5. Avoid two-pass tasks where one worker drafts code and Claude re-implements it.
6. Use `cross-validation` only for architecture or genuine multi-domain conflicts.

## Task Shape

```markdown
### Task N: [Short outcome]

**Owner:** `codex` | `gemini` | `auto`

**Files:**
- Modify: `path/to/file`
- Create: `path/to/file`

**Acceptance Criteria:**
- [criterion]
- [criterion]

**Verify:**
`exact command`

**Steps:**
1. [small action]
2. [small action]
3. [small action]
```

## Execution Handoff

Plans should be executable one bounded task at a time.

After saving the plan, offer:
1. Same-session execution with `developing-with-subagents`
2. Dedicated execution session with `executing-plans`
