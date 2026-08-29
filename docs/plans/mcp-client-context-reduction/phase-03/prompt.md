## Original User Request
Ship backlog item B-003.

## Phase
Version the coordinator contract change at 10.2.0.

## Tasks
- task-1: Set both plugin manifest versions to 10.2.0.
- task-2: Set all six shared contract markers to 10.2.0.

## Context
Execute Phase 3 from `../PLAN.md` in `/home/ngosi/projects/superpowers-ccg`. This phase is a mechanical version bump and runs directly under the coordination skip rule.

## Files
- `.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `shared/worker-contract.md`
- `shared/erp.md`
- `shared/notes-template.md`
- `shared/journal-template.md`
- `shared/backlog-contract.md`
- `shared/closeout-template.md`

## Done When
- Both manifests report 10.2.0.
- All six shared markers report 10.2.0.
- No instructional content changes.
- `bash tests/run.sh`

## Rules
Change only the eight version fields.

## Response Format
Record evidence in this phase's notes and journal.
