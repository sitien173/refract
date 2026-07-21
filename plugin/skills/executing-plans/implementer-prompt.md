# Implementer Prompt Template

Gate 2 dispatch artifact. Project setup, waiting, recovery, and integration remain
canonical in `coordinating-multi-model-work`. OpenMCP runs `implement` in an
isolated worktree and commits successful writes; workers never stage, commit,
reset, merge, or integrate.

## Initial Submission

```text
job_submit:
  project_id: <stored project UUID>
  workflow: implement
  inputs:
    prompt: |
      <one or two compressed sentences from the user request>
      Read: docs/plans/<slug>/phase-<NN>/prompt.md
      Contract: <plugin-root>/shared/worker-contract.md
      Response: <plugin-root>/shared/erp.md
      Notes: <plugin-root>/shared/notes-template.md
      Journal: <plugin-root>/shared/journal-template.md
      Follow those files and return the ERP response.
    commit_message: <phase Conventional Commit message>
  context_key: <slug>/phase-<NN>/implement
  parent_job_id: ""
  profile: <phase implementation profile>
```

Omit `profile` when task guidance omits it. Then call `job_wait` with
`timeout_s: 30` and `include_stage_outputs: false`. Read only
`job.result.text`; do not combine it with stage output.

## Phase Prompt

Write `docs/plans/<slug>/phase-<NN>/prompt.md`:

```markdown
## Original User Request
<one or two compressed sentences>

## Phase
<one outcome>

## Tasks
- task-1: <one line>
- task-2: <one line>

## Context
<minimum existing-code context>

## Files
- `path/to/file`

## Done When
- <acceptance criterion>
- `<fresh verification command>`

## Rules
Follow the supplied worker contract. Stay within scope. Maintain `notes.md` and
`journal.md` in this phase directory, creating them from the supplied templates
when absent.

## Response Format
Return the `# EXTERNAL RESPONSE` block and matching status line from ERP.
```

## Same-Phase Fix

Submit another `implement` job with the latest successful implementation job as
`parent_job_id`; never use the read-only review job as parent. Include the review
findings and only the changed requirements, files, and checks. Prefix the prompt
with `FIX:`, reuse the implementation context only when continuity helps, and
use a `fix:` commit message.
