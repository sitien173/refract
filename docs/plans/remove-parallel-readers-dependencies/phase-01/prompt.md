## User Request
Remove parallel readers and job dependencies from Refract. This phase first repairs two baseline test failures so later evidence gates are meaningful.

## Phase
All three verification suites pass repeatedly at the plan base behavior.

## Tasks
- task-1: Update `plugin/tests/test-contracts.sh:45` so the expected `job_wait` return is `{job:summary, result:{text, error, next_offset, metadata}}`, matching `plugin/skills/coordinating-multi-model-work/references/tool-contract.md`. Change no other assertion.
- task-2: Find the root cause of intermittent failures in `server/web/src/integration/dashboard-flow.test.jsx` and fix it.

## Context
- Baseline at HEAD: `bash plugin/tests/run.sh` fails deterministically with `AssertionError: {job:summary, result:{text, error, next_offset}}` because the job-failover-metadata plan added `metadata` to the documented envelope.
- Baseline at HEAD: `npx vitest run` in `server/web` fails intermittently. Run 1: 33 failed and 2 errors over 205 tests, duration about 300 s. Runs 2 and 3: exactly 1 failure each, a different test in `src/integration/dashboard-flow.test.jsx` each run: "manages targets through creation, inspection, and deletion workflows" and "manages project profile overrides through creation and removal workflo...". Failure form: `AssertionError: expected "spy" to be called with arguments: [ ObjectContaining{...}, ...]`.
- A prior plan recorded vitest flakes under host load. The host has 8 CPUs.
- Server pytest passes: 578 passed, 3 deselected.

## Files
- `plugin/tests/test-contracts.sh`
- `server/web/src/integration/dashboard-flow.test.jsx`
- If the root cause is in shared test setup or a component under test, you may edit that file. Record every extra path and why in notes.md.
- `docs/plans/remove-parallel-readers-dependencies/phase-01/notes.md` and `journal.md` (append only)

## Done When
- `cd /home/ngosi/projects/refract && bash plugin/tests/run.sh` exits 0.
- `cd /home/ngosi/projects/refract/server/web && npx vitest run && npx vitest run && npx vitest run` passes all three runs.
- `cd /home/ngosi/projects/refract/server && uv run --extra dev pytest -q` passes.
- `cd /home/ngosi/projects/refract && git diff --check` passes.
- notes.md names the flakiness root cause with evidence and states whether product code changed.

## Rules
Follow these bundled files:
- Contract: /home/ngosi/projects/refract/plugin/shared/worker-contract.md
- Response: /home/ngosi/projects/refract/plugin/shared/erp.md
- Notes: /home/ngosi/projects/refract/plugin/shared/notes-template.md
- Journal: /home/ngosi/projects/refract/plugin/shared/journal-template.md
- Apply systematic root-cause debugging. Do not raise timeouts, add retries, or skip or delete tests to make the suite pass.
- Do not weaken or remove any plugin assertion other than the one envelope string.
- No Git writes. Do not read or edit secrets, `~/.refract`, the live daemon, or its database. Do not edit other files under `docs/plans/`.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
