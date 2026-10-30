# Phase 2: Coordinator contract for explicit output recovery

## User Request

Finish the approved acknowledgement-only recovery plan. User requested the next phase and previously chose implementation on `main`. Phase 1 is reviewed and complete. Phase 2 documents safe use of the new acknowledgement and tests that guidance.

## Phase

Execute only Phase 2 in `docs/plans/reported-output-recovery/PLAN.md`. Read DESIGN.md and that phase. Coordinator handles final review, commits, anchors, and consolidation after your work.

## Tasks

- task-1: Add failing plugin contract assertions for acknowledgement-based output recovery, explicit new-job submission, and fresh-session/reconciliation safeguards. Run RED before editing documentation or server guidance. Record actual failing assertion.
- task-2: Update server README and MCP tool description/instructions to match Phase 1's acknowledgement contract. Cover eligibility, duplicates, availability, retention, and compatibility.
- task-3: Make the plugin tool contract the authoritative detailed recovery procedure. Link review guidance to it. Complete safeguards and run all checks.

## Context

Repository root: `/home/ngosi/projects/refract`; attached branch: `main`. Phase 1 implementation ref `refs/plans/reported-output-recovery/phase-01/impl` resolves to `ddaae977740f85043a2feab4895f00e5ad7fdc63` before phase preparation.

Phase 1 adds top-level `retry: {retryable, next_target}` to EVERY successful `job_report_error` acknowledgement. Existing top-level `report` and `duplicate` remain unchanged. Only a succeeded job with report category output can return true plus an opaque token; all ineligible combinations and unavailable fallback return false/null. Reports persist/deduplicate before computing live routing. Tokens and eligibility are response-only, never stored. Duplicate retained reports preserve IDs but recompute current target health/configuration.

`job_wait` deliberately still returns null retry fields for succeeded jobs. `job_retry` still rejects succeeded jobs. Original execution records, sessions, target health and attempts remain unchanged. No automatic execution, text classification, schema migration, or dashboard changes.

`server.py` has `_JOB_REPORT_ERROR_DESCRIPTION` and `_INSTRUCTIONS` strings that still describe the old acknowledgement. Limit changes there to those relevant descriptions/instructions; do not alter Phase 1 runtime behavior.

## Files

Edits are restricted to:
- `server/README.md`
- `server/src/refract/server.py`
- `plugin/skills/coordinating-multi-model-work/references/tool-contract.md`
- `plugin/skills/coordinating-multi-model-work/references/review.md`
- `plugin/tests/test-contracts.sh`
- `docs/plans/reported-output-recovery/phase-02/notes.md`
- `docs/plans/reported-output-recovery/phase-02/journal.md`

Preserve all other files, including coordinator-owned PLAN.md, DESIGN.md, .handover.md, prompt.md, Phase 1 records, unrelated plans, dependencies, secrets and live configuration. Ask if another path is needed.

## Done When

- Server tool description, MCP instructions, README and plugin contract correctly show acknowledgement-level `retry`, not `result.metadata.retry` for this succeeded-output recovery case.
- Preserve existing failed-job `result.metadata.retry.next_target` guidance separately.
- Keep existing five report arguments, input bounds, privacy/redaction, deduplication conflicts, correlation logging, and client-observation semantics.
- The authoritative procedure requires reading all terminal pages, reporting an actual anomaly with original job/project correlation, and inspecting partial local and external effects before replay.
- Only succeeded+output reports expose fallback; false/null means stop and request routing guidance, never automatic primary retry.
- Explicit recovery calls `job_submit` with the acknowledgement's `next_target`, matching original project/workflow/profile/task and `fresh_session: true`. A token is a routing hint, not authorization to replay side effects. Preserve original context/task intent without reusing a contaminated session.
- Configuration changes can stale tokens. Refresh via identical original report request while its event remains retained. Never silently omit `next_target` to restart the primary target. Existing report retention can remove deduplication and produce a new report ID later.
- Report failure never triggers recursive reporting or prevents safe reconciliation.
- Clearly state original succeeded state/result remains unchanged, succeeded `job_wait` does not gain retry metadata, and `job_retry` remains restricted.
- State additive compatibility: tolerant clients can ignore `retry`; exact-key clients need an update. No schema/data migration or durable eligibility is introduced.
- Review guidance references one authoritative detailed procedure rather than duplicating it.
- New plugin contract assertions fail against old guidance and pass against updated guidance. Test the recovery branches/safeguards, not only generic mentions of job_report_error.
- Each task has notes and RED/GREEN evidence. Append the full ERP response to the journal and list all touched paths.

Run from the repository root:

```sh
bash plugin/tests/test-contracts.sh
(cd server && uv run pytest -q tests/test_runtime.py tests/test_server.py tests/test_database.py)
(cd server && uv run pytest -q)
git diff --check
```

Phase 1 baseline: contracts passed, 193 focused tests passed/four skipped; full suite 1255 passed/23 skipped/15 live deselected. Existing environment warnings are unrelated; do not modify environment configuration.

## Rules

Read and follow bundled contracts:
- `/home/ngosi/projects/refract/plugin/shared/worker-contract.md`
- `/home/ngosi/projects/refract/plugin/shared/erp.md`
- `/home/ngosi/projects/refract/plugin/shared/notes-template.md`
- `/home/ngosi/projects/refract/plugin/shared/journal-template.md`

For agent-facing instructions, follow `/home/ngosi/.agents/skills/writing-for-agents/SKILL.md`. Preserve literal field names, command syntax, identifiers, and quotations. Keep prose concise and place branch-specific steps next to their conditions.

You are implementer, not Coordinator. Work directly; do not launch nested workers or coordination workflows. No commits, resets, stashes, branch changes, dependency changes, daemon restarts, live probes, or mutations of historical jobs. Use `refract ask` for unresolved scope or return BLOCKED if unavailable. No blanket test waivers or deferred required tests.

## Response Format

Return the complete ERP `# EXTERNAL RESPONSE` block and matching Phase 2 status line after appending the response to the journal. Report exact commands/results, actual RED assertion, all touched paths, and any unresolved obstacles.
