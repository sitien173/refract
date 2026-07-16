# Implementer Prompt Template

OpenMCP runs workers inside isolated Git worktrees. It commits successful write
jobs automatically. Workers never stage, commit, reset, squash, or integrate.

## Submit sequence

Select the public nickname and stable `execution_role` through `task_route`.
OpenMCP never infers either value from task words.

Initialize once before registration:

```text
project_init:
  path: <absolute repository root>
```

Review and commit created `.openmcp` files. Then register cleanly:

```text
project_register:
  path: <absolute repository root>
  alias: <repository name>
```

Submit the phase:

```text
job_submit:
  project_id: <stored project UUID>
  workflow: <owner_execution_role>-write
  inputs:
    prompt: |
      You are <owner_nickname>. Implement the plan phase correctly. Follow the instructions below. Do not stage, commit, reset, squash, or integrate. Do not use Git mutation commands. Do not edit the root repository while an isolated chain remains active.
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

Then call `job_wait`:

```text
job_wait:
  job_id: <returned job UUID>
  include_stage_outputs: false
```

Wait again while queued or running. Read only `job.result.text`. Never combine
it with stage output. Record only project and job identifiers.

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
this phase directory. Do not use Git mutation commands.

## Response Format

Return the `# EXTERNAL RESPONSE` block and matching status line from ERP.
```

## Same-phase fix

Submit the same `<owner_execution_role>-write` workflow. Set `parent_job_id` to the
latest write job. Reuse its implementer `context_key`. Start the prompt with
`FIX:` and include only changed requirements, findings, files, and checks. Use
a `fix:` commit message.
