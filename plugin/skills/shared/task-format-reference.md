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
| `contextRefs` | string[] | no | CONTEXT_REFS artifact IDs from CP0/Auggie |
| `hydratedContext` | string[] | no | Hydrated snippets for TASK_CONTEXT_BUNDLE |
| `contextBundle` | object | no | Full task-scoped bundle summary for deltas |

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
