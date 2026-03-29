# Native Task Management Migration Design

> **Source:** https://github.com/pcvelz/superpowers
> **Feature:** Native Task Management
> **Date:** 2026-03-26

---

## Goal

Integrate Claude Code's native TaskCreate/TaskUpdate/TaskList tools into the superpowers-cccg workflow so tasks are created during design, enriched during planning, persisted as `.tasks.json`, and executed with dependency enforcement and cross-session resume.

## Architecture

Tasks flow through the three-phase lifecycle:

```
Brainstorming → Writing Plans → Executing Plans
  (create)         (enrich)       (load + run)
```

Each phase hands off to the next via native tasks and a `.tasks.json` persistence file co-located with the plan document.

## Path Convention

Plans and their task files live at:
```
docs/plans/YYYY-MM-DD-<feature>.md
docs/plans/YYYY-MM-DD-<feature>.md.tasks.json
```

## Changes

### 1. New File: `skills/shared/task-format-reference.md`

Canonical reference for the TaskCreate description format and metadata schema. Referenced by both `brainstorming` and `writing-plans` skills.

**Template structure:**
```
**Goal:** One sentence — what this task produces.

**Files:**
- Create/Modify/Delete: `exact/path/to/file`

**Acceptance Criteria:**
- [ ] Concrete, testable criterion

**Verify:** `exact command` → expected output

**Steps:** (optional, for multi-step tasks)

```json:metadata
{"files": [...], "verifyCommand": "...", "acceptanceCriteria": [...]}
```
```

**Metadata schema:**

| Key | Type | Required | Purpose |
|-----|------|----------|---------|
| `files` | string[] | yes | Paths to create/modify/delete |
| `verifyCommand` | string | yes | Command to verify task completion |
| `acceptanceCriteria` | string[] | yes | List of testable criteria |
| `estimatedScope` | "small"\|"medium"\|"large" | no | Relative effort |

> **Why embedded metadata:** The `metadata` param on TaskCreate is accepted but not returned by TaskGet. Embedding as a `json:metadata` code fence in the description is the only reliable cross-session approach.

---

### 2. `skills/brainstorming/SKILL.md` — Append section

Add **"Native Task Integration"** section at the end of "After the Design":

**During Design Validation** — after each section is confirmed by user, create a native task:
```yaml
TaskCreate:
  subject: "Implement [Component Name]"
  description: |
    **Goal:** [What this component produces]
    **Files:**
    - Create/Modify: [paths from design]
    **Acceptance Criteria:**
    - [ ] [Criterion from design]
    **Verify:** [How to test]
    ```json:metadata
    {"files": [...], "verifyCommand": "...", "acceptanceCriteria": [...]}
    ```
  activeForm: "Implementing [Component Name]"
```
Track all returned task IDs.

**After All Components Validated** — wire dependencies:
```yaml
TaskUpdate:
  taskId: [dependent-task-id]
  addBlockedBy: [prerequisite-task-ids]
```

**Before Handoff** — run `TaskList` to display full task tree with dependency status.

Reference: `skills/shared/task-format-reference.md`

---

### 3. `skills/writing-plans/SKILL.md` — Two additions

**Addition A — REQUIRED FIRST STEP block** (inserted before exploration):

> Before exploring code or writing the plan, call `TaskList`.
> - If tasks exist from brainstorming: enhance them with implementation details as you write.
> - If no tasks: create them with `TaskCreate` as you write each task.

**Addition B — "Native Task Integration Reference" section** (append after current content):

- **Creating tasks:** One TaskCreate per plan task using the format from `skills/shared/task-format-reference.md`
- **Dependency wiring:** `TaskUpdate` with `addBlockedBy` after all tasks created
- **Status during execution:** `in_progress` when starting, `completed` when done
- **Persistence file:** Write `.tasks.json` to `docs/plans/<plan-name>.md.tasks.json`

`.tasks.json` schema:
```json
{
  "planPath": "docs/plans/YYYY-MM-DD-feature.md",
  "tasks": [
    {
      "id": 0,
      "subject": "Task 0: ...",
      "status": "pending",
      "description": "**Goal:** ...\n\n```json:metadata\n{...}\n```"
    },
    {
      "id": 1,
      "subject": "Task 1: ...",
      "status": "pending",
      "blockedBy": [0],
      "description": "..."
    }
  ],
  "lastUpdated": "<ISO timestamp>"
}
```

---

### 4. `skills/executing-plans/SKILL.md` — Two new steps + enhanced Step 2

**Step 0: Load Persisted Tasks** (before current Step 1):
1. Call `TaskList` — check for existing native tasks
2. Locate `.tasks.json` at `<plan-path>.tasks.json`
3. If file exists AND native tasks are empty: recreate from JSON via TaskCreate (restore `blockedBy` with TaskUpdate)
4. If native tasks exist: verify they match plan, resume from first `pending`/`in_progress`
5. If neither: proceed to Step 1b

**Step 1b: Bootstrap Tasks from Plan** (if neither .tasks.json nor native tasks found):
1. Parse plan for `## Task N:` or `### Task N:` headers
2. For each task: TaskCreate with full structured description + `json:metadata` fence
3. For each task with dependencies: TaskUpdate with `addBlockedBy`
4. Call `TaskList` to verify `blockedBy` relationships

**Enhanced Step 2 (Execute Tasks):**
- Parse `json:metadata` from task description for `verifyCommand` and `acceptanceCriteria`
- Run `verifyCommand` and check each criterion before marking complete
- After every status change, sync `.tasks.json`: update `"status"` field + `"lastUpdated"` timestamp

---

## Data Flow

```
Brainstorming           Writing Plans           Executing Plans
──────────────          ─────────────           ───────────────
Design section N        TaskList (check)        Step 0: Load .tasks.json
  └─ TaskCreate ──────► Enhance OR create       Step 1b: Bootstrap if needed
     (task ID)          TaskUpdate (deps)       Step 2: Execute
                        Write .tasks.json         ├─ parse json:metadata
                          └─ docs/plans/           ├─ run verifyCommand
                             *.md.tasks.json        ├─ check acceptanceCriteria
                                                    └─ sync .tasks.json
```

## Error Handling

- **No native task tools available:** Log warning, continue without task tracking (graceful degradation)
- **`.tasks.json` missing on resume:** Bootstrap from plan document (Step 1b)
- **Task ID mismatch:** Re-bootstrap all tasks, warn user
- **`verifyCommand` fails:** Stop and report — do not mark complete

## Testing

Manual verification after each skill change:
1. Run a brainstorming session → confirm TaskCreate calls appear, TaskList shows dependency tree
2. Run writing-plans → confirm TaskList called first, tasks enriched/created, `.tasks.json` written to `docs/plans/`
3. Run executing-plans on plan with `.tasks.json` → confirm tasks loaded, metadata used for verification, file synced on completion
4. Kill session mid-execution, restart → confirm resume works from `.tasks.json`

---

## Implementation Order

1. Create `skills/shared/task-format-reference.md` (no dependencies)
2. Update `skills/brainstorming/SKILL.md` (references shared file)
3. Update `skills/writing-plans/SKILL.md` (references shared file)
4. Update `skills/executing-plans/SKILL.md` (depends on format defined in steps 1-3)
