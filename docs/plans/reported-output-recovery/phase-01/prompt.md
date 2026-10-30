# Phase 1: Report acknowledgement recovery metadata

## User Request

Provide explicit recovery for a job whose state is `succeeded` but whose output is unusable. User approved acknowledgement-only routing metadata and implementation on `main`. The original execution remains unchanged. No automatic replay or text classification.

## Phase

Implement Phase 1 of `docs/plans/reported-output-recovery/PLAN.md`. Read that phase and DESIGN.md. Phase 2 documentation and plugin changes remain out of scope.

## Tasks

- task-1: Reproduce the missing acknowledgement token with a deterministic failing regression. Characterize existing immutable state and retry behavior.
- task-2: Record or deduplicate first, then read the job and attach live recovery metadata. Render the top-level `retry` object in the MCP acknowledgement.
- task-3: Test state/category boundaries, exhausted/unhealthy candidates, duplicate freshness after health/configuration changes, token binding, stale-token rejection, and refreshed duplicate tokens.
- task-4: Test explicit new-job fallback with `fresh_session: true`, plus unchanged execution fields, result metadata, sessions, health, and absence of automatic execution.

## Context

Root: `/home/ngosi/projects/refract`. Attached branch: `main`. Plan base: `refs/plans/reported-output-recovery/base`. The coordinator will set a clean phase base before dispatch. Only coordinator-created phase metadata differs from the approved planning checkpoint.

`Runtime.report_error` currently returns `database.record_error_report` directly. `server.job_report_error` currently renders only `report` and `duplicate`. `live_result_metadata` deliberately suppresses succeeded retries; leave it unchanged. `_prepare_retry` deliberately rejects succeeded jobs; leave it unchanged.

`Runtime._next_target_token` already selects live fallback tokens. Existing planning/submission logic validates their configuration revision, project, profile, workflow, and target. Reuse those paths. Do not change planning, execution, database schema, or token formats.

Report `1625` concerned succeeded job `f4c6aace-a609-4ac1-a9d4-5ed284f53df3`, whose complete result was refusal text. Do not contact live backends or mutate that historical job; reproduce through test fixtures.

## Files

Production and test edits are restricted to:
- `server/src/refract/runtime.py`
- `server/src/refract/server.py`
- `server/tests/test_runtime.py`
- `server/tests/test_server.py`

Worker-owned phase records:
- `docs/plans/reported-output-recovery/phase-01/notes.md`
- `docs/plans/reported-output-recovery/phase-01/journal.md`

Do not edit PLAN.md, DESIGN.md, .handover.md, prompt.md, unrelated plans, plugin files, dashboard files, dependencies, secrets, or live configuration. If another source path is required, stop and ask.

## Done When

- Every successful report acknowledgement retains the original `report` and `duplicate` fields and adds exactly `retry: {retryable, next_target}` at the top level.
- Record/deduplicate the report before computing routing. Read current job state after recording.
- Only state `succeeded` with category `output` may yield a token. A token means `retryable: true`. Ineligible cases and no available fallback yield `retryable: false` and `next_target: null`.
- Other report categories/states never unlock recovery in the acknowledgement. Existing failed-job metadata from `job_wait` remains unchanged.
- An identical retained duplicate keeps its report ID and recomputes live routing. Tokens and eligibility are not persisted.
- Existing key conflict, redaction, request bounds, compact payload, unknown-job, and correlation logging behavior remains valid.
- Snapshot original state, result, attempts, timestamps, session rows, health, and result metadata around reporting. Only diagnostic storage changes. Reports alone never enqueue or execute a new job.
- Cover nonterminal reporting, target exhaustion/health, current configuration changes, old-token rejection, and duplicate refresh.
- Explicit `job_submit` with the acknowledged token and matching routing scope creates a new job ID at the intended fallback with `fresh_session: true` requested.
- Actual MCP tests cover serialization; update old exact-key expectations for the additive response field.
- Succeeded `job_wait` retry fields remain null; `job_retry` still rejects succeeded jobs.
- Regression evidence quotes the real missing-behavior RED failure before production changes, then GREEN results. Characterization assertions that already pass are identified as such.
- Every task has notes and all touched paths appear in ERP.

Run all checks from the root:

```sh
(cd server && uv run pytest -q tests/test_runtime.py tests/test_server.py tests/test_database.py)
(cd server && uv run pytest -q)
bash plugin/tests/test-contracts.sh
git diff --check
```

Baseline: focused tests 188 passed, four skipped; full suite 1250 passed, 23 skipped, 15 live tests deselected; plugin contracts passed. Existing environment warnings concern ambient VIRTUAL_ENV and SSL_CERT_DIR. Do not modify environment configuration to silence them.

## Rules

Follow these bundled files completely:
- Contract: `/home/ngosi/projects/refract/plugin/shared/worker-contract.md`
- Response: `/home/ngosi/projects/refract/plugin/shared/erp.md`
- Notes: `/home/ngosi/projects/refract/plugin/shared/notes-template.md`
- Journal: `/home/ngosi/projects/refract/plugin/shared/journal-template.md`

Use RED then minimal GREEN for production behavior. Do not implement before proving the missing behavior. No commits, resets, stashes, restores, branch changes, dependency changes, daemon restarts, or live probes. The coordinator owns Git and orchestration. Preserve existing working code and unrelated files. Ask through `refract ask` for unresolved requirements, or return BLOCKED if that facility fails.

This worker is the implementer, not Coordinator. Perform these tasks directly in the supplied root; do not launch nested Refract jobs or run the coordinator skill workflow.

## Response Format

Append the complete ERP block to the phase journal, then return the `# EXTERNAL RESPONSE` block and matching Phase 1 status line. Include exact test evidence and all touched paths. Report partial work honestly if blocked.
