# Implementer Prompt Template

Concrete dispatch artifacts for Gate 2. Project setup, `job_wait`, and job-state
handling are canonical in `coordinating-multi-model-work` — follow it for those.
OpenMCP runs workers in isolated worktrees and commits successful implement
jobs; workers never stage, commit, reset, squash, merge, or integrate.

## Implement-job submission

Select the nickname and stable `execution_role` via `task_route` (OpenMCP never
infers them). After setup, submit the phase:

```text
job_submit:
  project_id: <stored project UUID>
  workflow: implement
  inputs:
    prompt: |
      <one or two compressed sentences of the original user request>
      Read: docs/plans/<slug>/phase-<NN>/prompt.md
      Contract: <plugin-root>/shared/worker-contract.md
      Response: <plugin-root>/shared/erp.md
      Notes: <plugin-root>/shared/notes-template.md
      Journal: <plugin-root>/shared/journal-template.md
      Follow those files. Create `notes.md` and `journal.md` inside the phase directory.
      Return the ERP response.
    commit_message: <phase Conventional Commit message>
  context_key: <slug>/phase-<NN>/<owner_execution_role>
  parent_job_id: ""
  routing_profile: <stored phase profile>
```

Then `job_wait` with `include_stage_outputs: false`. Read only
`job.result.text`; never combine it with stage output.

## Phase prompt

Write `<plan-dir>/phase-<NN>/prompt.md`:

```markdown
## Original User Request
[one or two compressed sentences]

## Phase
[one sentence]

## Tasks
- task-1: <one line>
- task-2: <one line>

## Context
[minimum existing-code context]

## Files
- `path/to/file`

## Done When
- [acceptance criterion]
- `[fresh verification command]`

## Rules

Follow the supplied worker contract. Write `notes.md` and `journal.md` inside
this phase directory, create new files if they do not exist.
  
## Response Format

Return the `# EXTERNAL RESPONSE` block and matching status line from ERP.
```

## Same-phase fix

Resubmit the built-in `implement` workflow with `parent_job_id`
set to the latest implement job and the implementer `context_key` reused. Start the
prompt with `FIX:` and include only changed requirements, findings, files, and
checks. Use a `fix:` commit message.
