# Native Task Management Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate the Native Task Management feature from pcvelz/superpowers into superpowers-ccg by adding TaskCreate/TaskUpdate/TaskList integration to the brainstorming, writing-plans, and executing-plans skills.

**Architecture:** Four Markdown edits in dependency order — shared reference file first, then brainstorming, writing-plans, and executing-plans. No code compilation. Verification is grep-based (check that required sections exist in each file after editing).

**Tech Stack:** Markdown, bash grep for verification.

---

### Task 1: Create `skills/shared/task-format-reference.md`

**Files:**
- Create: `skills/shared/task-format-reference.md`

**Step 1: Verify the file does not exist yet**

```bash
test -f skills/shared/task-format-reference.md && echo "EXISTS" || echo "MISSING"
```
Expected: `MISSING`

**Step 2: Create the file with this exact content**

Create `skills/shared/task-format-reference.md`:

```markdown
# Native Task Format Reference

Skills that create native tasks (TaskCreate) MUST follow this format.

## Task Description Template

Every TaskCreate description MUST follow this structure:

### Required Sections

**Goal:** One sentence — what this task produces (not how).

**Files:**
- Create/Modify/Delete: `exact/path/to/file` (with line ranges for modifications)

**Acceptance Criteria:**
- [ ] Concrete, testable criterion
- [ ] Another criterion

**Verify:** `exact command to run` → expected output summary

### Optional Sections (include when relevant)

**Context:** Why this task exists, what depends on it, architectural notes.
Only needed when the task can't be understood from Goal + Files alone.

**Steps:** Ordered implementation steps (only for multi-step tasks where order matters).
TDD cycles happen WITHIN steps, not as separate steps.

## Metadata Schema

Embed metadata as a `json:metadata` code fence at the end of the TaskCreate description. The `metadata` parameter on TaskCreate is accepted but **not returned by TaskGet** — embedding in the description is the only reliable way.

| Key | Type | Required | Purpose |
|-----|------|----------|---------|
| `files` | string[] | yes | Paths to create/modify/delete |
| `verifyCommand` | string | yes | Command to verify task completion |
| `acceptanceCriteria` | string[] | yes | List of testable criteria |
| `estimatedScope` | "small" \| "medium" \| "large" | no | Relative effort indicator |

### Example

~~~yaml
TaskCreate:
  subject: "Task 1: Add authentication middleware"
  description: |
    **Goal:** Add JWT verification middleware to all protected API routes.

    **Files:**
    - Create: `src/middleware/auth.py`
    - Modify: `src/api/routes.py:45-60`

    **Acceptance Criteria:**
    - [ ] Requests without valid JWT return 401
    - [ ] Requests with valid JWT pass through to handler
    - [ ] Expired tokens return 401 with "token expired" message

    **Verify:** `pytest tests/middleware/test_auth.py -v` → 3 tests pass

    ```json:metadata
    {"files": ["src/middleware/auth.py", "src/api/routes.py"], "verifyCommand": "pytest tests/middleware/test_auth.py -v", "acceptanceCriteria": ["Requests without valid JWT return 401", "Requests with valid JWT pass through", "Expired tokens return 401"]}
    ```
  activeForm: "Implementing authentication middleware"
~~~

## Task Granularity

### The Right Scope

A task is **a coherent unit of work that produces a testable, committable outcome**.

**Scope test — ask these questions:**
1. Does this task produce something I can verify independently? (if no → too small)
2. Does it touch more than one concern? (if yes → too big)
3. Would it get its own commit? (if no → too small; if commit message needs bullet points → too big)

### TDD Within Tasks (Not Across Tasks)

TDD cycles (write test → verify fail → implement → verify pass) happen WITHIN a single task, not as separate tasks. The task is "Implement X with tests" — the TDD steps are execution detail, not task boundaries.

### Commit Boundary = Task Boundary

Each task should produce exactly one commit. If a task needs multiple commits, split it. If separate tasks share a commit, merge them.
```

**Step 3: Verify the file was created and contains required sections**

```bash
grep -c "Metadata Schema" skills/shared/task-format-reference.md
grep -c "json:metadata" skills/shared/task-format-reference.md
grep -c "verifyCommand" skills/shared/task-format-reference.md
```
Expected: each returns `1` (or more)

**Step 4: Commit**

```bash
git add skills/shared/task-format-reference.md
git commit -m "feat: add shared native task format reference"
```

---

### Task 2: Add Native Task Integration to `skills/brainstorming/SKILL.md`

**Files:**
- Modify: `skills/brainstorming/SKILL.md`

**Step 1: Verify the section does not exist yet**

```bash
grep -c "Native Task Integration" skills/brainstorming/SKILL.md
```
Expected: `0`

**Step 2: Append the Native Task Integration section**

Open `skills/brainstorming/SKILL.md`. Find the line:

```
**Implementation (if continuing):**
```

Insert the following block **between** the Documentation block and the Implementation block (after the "Only commit if the user explicitly asks you to commit." line, before "**Implementation (if continuing):**"):

```markdown
**Native Task Integration (must not be skipped):**

After each design section is confirmed by the user, create a native task using Claude Code's TaskCreate tool. Follow the format in `skills/shared/task-format-reference.md`.

```yaml
TaskCreate:
  subject: "Implement [Component Name]"
  description: |
    **Goal:** [What this component produces — one sentence]

    **Files:**
    - Create/Modify: [paths identified during design]

    **Acceptance Criteria:**
    - [ ] [Criterion from design validation]
    - [ ] [Criterion from design validation]

    **Verify:** [How to test this component works]

    ```json:metadata
    {"files": ["path/from/design"], "verifyCommand": "command to verify", "acceptanceCriteria": ["criterion 1", "criterion 2"]}
    ```
  activeForm: "Implementing [Component Name]"
```

Track all returned task IDs.

After **all** components are validated, wire dependency relationships:

```yaml
TaskUpdate:
  taskId: [dependent-task-id]
  addBlockedBy: [prerequisite-task-ids]
```

Before handing off to writing-plans, run `TaskList` to display the complete task tree with dependency status so the user can confirm it looks right.
```

**Step 3: Verify the section was added**

```bash
grep -c "Native Task Integration" skills/brainstorming/SKILL.md
grep -c "addBlockedBy" skills/brainstorming/SKILL.md
grep -c "task-format-reference" skills/brainstorming/SKILL.md
```
Expected: each returns `1` (or more)

**Step 4: Commit**

```bash
git add skills/brainstorming/SKILL.md
git commit -m "feat: add native task integration to brainstorming skill"
```

---

### Task 3: Update `skills/writing-plans/SKILL.md` — Task tracking init + integration reference

**Files:**
- Modify: `skills/writing-plans/SKILL.md`

This task has two additions: a "REQUIRED FIRST STEP" block and a "Native Task Integration Reference" section.

**Step 1: Verify neither section exists yet**

```bash
grep -c "REQUIRED FIRST STEP" skills/writing-plans/SKILL.md
grep -c "Native Task Integration Reference" skills/writing-plans/SKILL.md
```
Expected: both return `0`

**Step 2: Add the REQUIRED FIRST STEP block**

Open `skills/writing-plans/SKILL.md`. Find this line (it appears after the Protocol Threshold section):

```
**Announce at start:** "I'm using the writing-plans skill to create the implementation plan."
```

Insert the following block **immediately after** that line (before the `Hard reminder:` line):

```markdown

**REQUIRED FIRST STEP — Initialize Task Tracking:**

Before exploring code or writing the plan, you MUST:

1. Call `TaskList` to check for existing tasks from brainstorming
2. If tasks exist: you will enhance them with implementation details as you write each plan task (use `TaskUpdate` to add Steps, Verify, and metadata)
3. If no tasks exist: you will create them with `TaskCreate` as you write each task

Do not proceed to codebase exploration until `TaskList` has been called.

```

**Step 3: Add the Native Task Integration Reference section**

Find this line near the end of the file:

```
## Execution Handoff
```

Insert the following block **immediately before** that line:

```markdown
## Native Task Integration Reference

Use Claude Code's native task tools to create structured tasks alongside the plan document.

### Creating Tasks

For each task in the plan, create a corresponding native task. Follow the format in `skills/shared/task-format-reference.md`. Embed metadata as a `json:metadata` code fence at the end of the description — this is the only way to ensure metadata survives TaskGet (the `metadata` parameter on TaskCreate is accepted but not returned by TaskGet).

```yaml
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
```

### Setting Dependencies

After all tasks are created, wire blockedBy relationships:

```yaml
TaskUpdate:
  taskId: [dependent-task-id]
  addBlockedBy: [prerequisite-task-ids]
```

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

```

**Step 4: Verify both additions are present**

```bash
grep -c "REQUIRED FIRST STEP" skills/writing-plans/SKILL.md
grep -c "Native Task Integration Reference" skills/writing-plans/SKILL.md
grep -c "tasks.json" skills/writing-plans/SKILL.md
grep -c "task-format-reference" skills/writing-plans/SKILL.md
```
Expected: each returns `1` (or more)

**Step 5: Commit**

```bash
git add skills/writing-plans/SKILL.md
git commit -m "feat: add native task tracking init and integration reference to writing-plans skill"
```

---

### Task 4: Update `skills/executing-plans/SKILL.md` — Step 0, Step 1b, enhanced Step 2

**Files:**
- Modify: `skills/executing-plans/SKILL.md`

**Step 1: Verify new steps do not exist yet**

```bash
grep -c "Step 0: Load Persisted Tasks" skills/executing-plans/SKILL.md
grep -c "Step 1b: Bootstrap Tasks" skills/executing-plans/SKILL.md
```
Expected: both return `0`

**Step 2: Insert Step 0 before the current Step 1**

Open `skills/executing-plans/SKILL.md`. Find this exact line:

```
### Step 1: Load and Review Plan
```

Insert the following block **immediately before** that line:

```markdown
### Step 0: Load Persisted Tasks

1. Call `TaskList` to check for existing native tasks in this session
2. **Locate tasks file:** Look for `<plan-path>.tasks.json` (same directory as the plan `.md`)
3. **If tasks file exists AND native tasks are empty** (fresh session): recreate from JSON using TaskCreate:
   - Include full `description` from `.tasks.json` (not just subject — it contains the `json:metadata` fence)
   - Restore `blockedBy` relationships with `TaskUpdate` after all tasks are created
4. **If native tasks already exist:** verify they match the plan, then resume from the first `pending` or `in_progress` task
5. **If neither tasks file nor native tasks exist:** proceed to Step 1b after reviewing the plan

Update `.tasks.json` after every task status change (see Step 2).

```

**Step 3: Insert Step 1b after the current Step 1**

Find the line that begins the current "Step 2: Execute Batch" section:

```
### Step 2: Execute Batch
```

Insert the following block **immediately before** that line:

```markdown
### Step 1b: Bootstrap Tasks from Plan (if needed)

Only run this step if TaskList returned no tasks AND no `.tasks.json` file was found.

1. Parse the plan document for `## Task N:` or `### Task N:` headers
2. For each task found, use TaskCreate with:
   - `subject`: the task title from the plan (e.g. `"Task 1: [Component Name]"`)
   - `description`: full structured content (Goal, Files, Acceptance Criteria, Verify, Steps) with `json:metadata` code fence at the end
   - `activeForm`: present tense action (e.g. `"Implementing X"`)
3. **CRITICAL — Dependencies:** For each task that has `blockedBy` in the plan, call `TaskUpdate` with `addBlockedBy`. Do NOT skip this — dependencies enforce correct execution order.
4. Call `TaskList` to verify `blockedBy` relationships are correctly shown (e.g. "blocked by #1, #2")

```

**Step 4: Enhance Step 2 with metadata verification and .tasks.json sync**

Find this block in the current Step 2:

```
For each task:

1. Mark as in_progress
2. Hard reminder: before your first Task tool call, you must output a standalone `【CP1 Assessment】` block (fixed format with fields).
3. **► Checkpoint 1 (Task Analysis):** Apply checkpoint logic from `coordinating-multi-model-work/checkpoints.md`:
```

Replace only the "For each task:" list — change it to:

```markdown
For each task:

1. Mark as `in_progress` (`TaskUpdate status: in_progress`); sync `.tasks.json` (update `"status"` to `"in_progress"`, set `"lastUpdated"` to current ISO timestamp)
2. **Parse task metadata:** Extract the `json:metadata` code fence from the task description to get `verifyCommand` and `acceptanceCriteria`
3. Hard reminder: before your first Task tool call, you must output a standalone `【CP1 Assessment】` block (fixed format with fields).
4. **► Checkpoint 1 (Task Analysis):** Apply checkpoint logic from `coordinating-multi-model-work/checkpoints.md`:
```

Then find the lines at the end of the "For each task:" list:

```
6. Run verifications as specified
7. **► Checkpoint 3 (Quality Gate):** Before marking complete:
   - Code generation complete → invoke domain expert for review
8. Mark as completed
```

Replace with:

```markdown
6. **Run verification using metadata:** Execute `verifyCommand` from the parsed metadata. Check each item in `acceptanceCriteria` before proceeding. If verification fails, stop and report — do NOT mark as completed.
7. **► Checkpoint 3 (Quality Gate):** Before marking complete:
   - Code generation complete → invoke domain expert for review
8. Mark as `completed` (`TaskUpdate status: completed`); sync `.tasks.json` (update `"status"` to `"completed"`, set `"lastUpdated"` to current ISO timestamp)
```

**Step 5: Verify all additions are present**

```bash
grep -c "Step 0: Load Persisted Tasks" skills/executing-plans/SKILL.md
grep -c "Step 1b: Bootstrap Tasks" skills/executing-plans/SKILL.md
grep -c "json:metadata" skills/executing-plans/SKILL.md
grep -c "tasks.json" skills/executing-plans/SKILL.md
```
Expected: each returns `1` (or more)

**Step 6: Commit**

```bash
git add skills/executing-plans/SKILL.md
git commit -m "feat: add step 0/1b and metadata-driven verification to executing-plans skill"
```
