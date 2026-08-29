## Original User Request
Ship backlog item B-003.

## Phase
Defer coordinator review details and document reduced resources.

## Tasks
- task-1: Correct tool and resource contract documentation.
- task-2: Move Gate 3 details into `references/review.md`.
- task-3: Document `context_init` and bounded job reconciliation.
- task-4: Repoint and extend contract assertions.

## Context
Execute Phase 2 from `../PLAN.md` in `/home/ngosi/projects/superpowers-ccg`. This phase is documentation and Bash contract testing, so it runs directly under the coordination skip rule.

## Files
- `skills/coordinating-multi-model-work/SKILL.md`
- `skills/coordinating-multi-model-work/references/tool-contract.md`
- `skills/coordinating-multi-model-work/references/review.md`
- `skills/executing-plans/SKILL.md`
- `tests/test-contracts.sh`

## Done When
- Coordinator skill is at most 7.9 KB and 265 lines.
- Tool contract lists eight tools and six resources.
- Review reference contains the complete finalize checklist.
- Provider identity guards remain clean.
- `bash tests/run.sh`

## Rules
Stay within Phase 2 scope. Preserve required safety wording.

## Response Format
Record decisions and evidence in this phase's notes and journal.
