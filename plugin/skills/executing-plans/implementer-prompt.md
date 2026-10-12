# Implementer Prompt Template

This file owns the phase prompt every Gate 2 job reads; the coordinating skill owns submission, waiting, recovery, and review. Workers edit and return ERP; the coordinator updates the journal. The worker contract defines process; the phase prompt defines tasks, context, and criteria.

Write `<plugin-root>` as the absolute installed plugin directory. Workers run without the plugin loaded and can mis-resolve relative paths.

## Phase Prompt

Write `docs/plans/<slug>/phase-<NN>/prompt.md`:

```markdown
## User Request
<clean, concise summary of the user request>

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
Follow these bundled files:
- Contract: <plugin-root>/shared/worker-contract.md
- Response: <plugin-root>/shared/erp.md
- Notes: <plugin-root>/shared/notes-template.md
- Journal: <plugin-root>/shared/journal-template.md
<minimum necessary rules for the phase>

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
```
