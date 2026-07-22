# Implementer Prompt Template

This file owns the Gate 2 worker payload. The coordinating skill owns submission,
waiting, recovery, and review. The worker edits files directly in the working repository and returns the ERP response. The coordinating skill reads the ERP response and updates the journal. The worker contract defines the stable execution process; the phase prompt defines the tasks, context, and acceptance criteria.

## Submission

```text
job_submit:
  project_id: <stored project UUID>
  workflow: implement
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
  profile: <phase implementation profile>
```

Omit `profile` when guidance omits it.

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
<minimum necessary existing-code context>

## Files
- `path/to/file`

## Done When
- <acceptance criterion>
- `<fresh verification command>`

## Rules
Follow the supplied worker contract. Stay within scope. Maintain this phase's
`notes.md` and `journal.md`.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
```

## Fix Prompt

A review fix uses a new `implement` job. Prefix its prompt with `FIX:` and
include only:

- actionable review findings,
- changed requirements and allowed files,
- checks that must be rerun.

Reuse the implementation context key only when continuity helps. Use a `fix:`
commit message.
