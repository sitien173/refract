# Implementer Prompt Template

This file owns the Gate 2 worker payload. The coordinating skill owns submission,
waiting, recovery, and review. The worker edits files directly in the working repository and returns the ERP response. The coordinating skill reads the ERP response and updates the journal. The worker contract defines the stable execution process; the phase prompt defines the tasks, context, and acceptance criteria.

## First submission (new worker session)

The first `implement` job on the plan `context_key` teaches the worker its role
and output format. Include the full pointer set exactly once:

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
  context_key: <slug>
  profile: <phase implementation profile>
```

## Resumed submission (same context_key, same plan)

Every later `implement` job — next phase, fix, or continuation — resumes that
same worker session. It already knows the contract, ERP format, and its role.
Send a thin prompt with only the new delta and the phase prompt to read:

```text
job_submit:
  project_id: <stored project UUID>
  workflow: implement
  prompt: |
    <one line: what this job adds>
    Read: docs/plans/<slug>/phase-<NN>/prompt.md
    Return the ERP response as before.
  context_key: <slug>
  profile: <phase implementation profile>
```

Omit `profile` when guidance omits it. Every job is prompt-only:
the worker edits files but never commits. After the job is terminal, the
coordinating skill validates the filesystem changes and commits them with the
phase Conventional Commit message.

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

A review fix is a resumed `implement` job (see above), so it is thin. Prefix its
prompt with `FIX:` and include only:

- actionable review findings,
- changed requirements and allowed files,
- checks that must be rerun.

Do not resend the contract, ERP format, or role. Submit with the plan
`context_key` (`<slug>`), like every job in the plan. The coordinating skill runs
the bounded review–fix loop, then commits the validated fix with a `fix:` commit
message.
