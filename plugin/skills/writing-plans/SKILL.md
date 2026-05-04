---
name: writing-plans
description: "Creates implementation plans made of coarse implementation phases, each with 2-4 related tasks, explicit routing, review checklist, and integration checks."
---

# Writing Plans

## Overview

Write plans for execution by external workers, not for a human narrator.

Plans are organized into implementation phases. Each phase should be large enough to make meaningful progress, but small enough that one worker can implement it and Claude can review it without restating the whole project.

## Rules

1. Read the codebase and design docs only as much as needed.
2. Break work into phases, not tiny task lists.
3. Each phase must contain 2-4 related implementation tasks.
4. Prefer one owner per phase:
   - `codex` first for most implementation
   - `gemini` only for UI-heavy phases
   - `claude` only for orchestration, review, docs, or clarification
5. Avoid two-pass tasks where one worker drafts code and Claude re-implements it.
6. Use `cross-validation` only for architecture or genuine multi-domain conflicts.
7. Each phase must include acceptance criteria, reviewer checklist, and integration checks.

## Phase Shape

```markdown
### Phase N: [Short outcome]

**Owner:** `codex` | `gemini` | `claude`

**Goal:** [One clear outcome for this phase]

**Files:**
- Modify: `path/to/file`
- Create: `path/to/file`

**Tasks:**
1. [related implementation task]
2. [related implementation task]
3. [optional related implementation task]
4. [optional related implementation task]

**Acceptance Criteria:**
- [criterion]
- [criterion]

**Reviewer Checklist:**
- [spec requirement]
- [edge case / regression risk]
- [verification expectation]

**Integration Checks:**
- `exact command`
- [manual or repo-state check if needed]
```

## Planner Output

The final plan should contain:

1. A short phase table with phase number, owner, and outcome.
2. The full phase details using the phase shape above.
3. Routing notes only when a phase is `gemini` or `claude`.
4. A final integration section that runs only after all phases pass.

## Execution Handoff

Plans should be executable one phase at a time.

After saving the plan, offer:
1. Same-session execution with `executing-phases`
2. Dedicated execution session with `executing-plans`
