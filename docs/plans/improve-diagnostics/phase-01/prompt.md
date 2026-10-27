## User Request
Enhance Refract diagnostics with an MCP client error-reporting tool. The approved plan also includes later dashboard work, but implement only Phase 1 now.

## Phase
1: Durable client reporting without execution changes

## Tasks and Files
 Durable client reporting without execution changes

**Task Guide Input:** Implement the approved diagnostic report MCP contract, event persistence, privacy, idempotency, and unchanged execution semantics. This is non-UI server implementation. Update the canonical tool reference and its exact-surface test alongside registration so the new tool does not leave an inconsistent tool count.

**Goal:** Clients can persist one sanitized report per observation and safely retry delivery.

**Files:**
- Modify: `server/src/refract/server.py`
- Modify: `server/src/refract/runtime.py`
- Modify: `server/src/refract/database.py`
- Modify: `server/src/refract/models.py`
- Modify: `server/src/refract/logging_setup.py`
- Modify: `server/tests/test_server.py`
- Modify: `server/tests/test_mcp_schema_contract.py`
- Modify: `server/tests/test_database.py`
- Modify: `server/tests/test_logging.py`
- Modify: `server/tests/test_retention.py`
- Modify: `plugin/skills/coordinating-multi-model-work/references/tool-contract.md`
- Modify: `plugin/tests/test-contracts.sh`

**Tasks:**
1. Write failing tests for validation, redaction, duplicate delivery, conflict, concurrent insertions, unknown jobs, failed writes, and restart persistence.
2. Implement narrow report models, redaction reuse, and transactional event-backed reporting through runtime worker helpers and the new MCP tool.
3. Test unchanged state, attempts, execution timestamps, result text, routing, target health, and queue behavior; test report pruning and deduplication scope.
4. Register the ninth tool and update the canonical contract and exact tool-surface checks without weakening existing validation or line-count guards.

**Acceptance Criteria:**
- The new tool matches all contract decisions and reports mutation failure truthfully.
- Concurrent same-key calls persist exactly one event with one stable report ID.
- Different jobs may use the same key independently.
- Known secret-pattern fixtures never appear unredacted in stored reports, dashboard reads, or logs. Compact MCP acknowledgements contain no summaries.
- Reporting does not enqueue, retry, reroute, cancel, or change execution fields.
- Duplicate reports remain retrievable after reopening the database.
- Retention removes report events and derived diagnostic evidence under the existing policy.
- Eight existing tools retain their exact inputs, summary shapes, and response behavior.

**Reviewer Checklist:**
- Inspect transaction boundaries across thread-local connections and purge races.
- Verify redaction precedes every persistence and response path.
- Confirm no duplicate log is emitted for duplicate delivery.
- Confirm mutation annotations describe a local write, not a read-only operation.
- Confirm the database schema version remains 15 and existing events still decode.
- Check canonical documentation and test expectations both list nine tools.

**Verification Checks:**
- `cd server && uv run --extra dev pytest -q`
- `bash plugin/tests/run.sh`



## Contract Decisions

These details refine the approved design for implementation review.

- Tool: `job_report_error(job_id, category, expected, observed, report_key)`.
- All five arguments are required. Reject additional arguments and wrong types.
- `category` is exactly `protocol` or `output`.
- `expected` and `observed` each contain 1 through 2048 Unicode characters after trimming. Reject whitespace-only values and inputs exceeding the limit before trimming. Do not silently truncate.
- `report_key` contains 1 through 128 ASCII letters, digits, underscores, or hyphens. Clients generate a unique opaque key per observation and reuse it only for delivery retries. Never include credentials in keys.
- Persist event kind `job.error_reported`. Its payload contains a version, category, sanitized expected and observed summaries, and report key. Use the existing event ID as the report ID, serialized as a decimal string in public report objects.
- Return compact `{report: {id, job_id, category, created_at}, duplicate: boolean}` only after persistence. Keep summaries in dashboard reads rather than risk exceeding the MCP response byte budget.
- Deduplicate by job ID and report key inside the existing immediate transaction. Same key and identical sanitized category/summaries return the original report and `duplicate: true`. Changed sanitized content with the same key returns `invalid_request` without mutation. Test simultaneous submissions through separate database connections.
- Use existing `unknown_job`, `invalid_request`, and sanitized `internal_error` handling. Do not add error codes or echo rejected summaries in errors.
- Log a successful new report using event `job.error_reported`, report ID, job ID, project ID, request ID, and category. Do not log summaries or keys. Duplicate delivery does not create a second report log.
- Expose the existing text-redaction behavior through a narrowly scoped reusable function. Apply it before database persistence. Do not introduce a second secret-pattern registry or claim complete secret detection.
- Accept reports for existing jobs regardless of execution state. The server cannot determine whether a client's protocol observation is valid. Client guidance must distinguish pending questions, normal wait timeouts, partial pagination, and actual anomalies.
- Derive `suspect` and `diagnostic_count` from retained report events. Add these fields only to dashboard job representations, never to MCP job summaries or execution states.
- Add `GET /dashboard/api/diagnostics` with optional `project_id`, `job_id`, and `category` filters. Use `before` as an exclusive positive event-ID cursor and `limit` from 1 through 100, default 50. Order by event ID descending. Return `{reports, next_before}`; read one extra row to determine whether another page exists. Missing `before` starts at the newest event.
- Each dashboard report includes the public report fields, sanitized expected and observed summaries, project ID, and current job execution state. Label that state as current, not the state at the time of observation. Never expose raw event payloads.
- Reject malformed query parameters with HTTP 400. Explicit unknown project/job filters return HTTP 404. Apply filters together; valid filters with no matching reports return an empty page. Reuse existing dashboard loopback/origin protection.
- Dashboard route: `/dashboard/diagnostics`. Filter by project, job, and category; provide bounded next-page navigation, refresh, job links, and separate suspect badges in job lists and details.
- Job details fetch their reports through the bounded diagnostics endpoint. Do not embed an unlimited report history in job responses. Refresh must work for terminal jobs because reports may arrive after completion. Use existing manual refresh rather than add a new streaming system.
- Retention follows `Database.prune_history`: report events can disappear while job records remain. Old terminal jobs can lose newly submitted reports at the next existing history prune because retention uses job `updated_at`. Document this behavior; never modify execution timestamps to prolong report retention. Deduplication lasts only while the event remains retained.
- No new table, schema-version change, persistent suspect column, or new index is planned. Reuse existing transactions and parameterized queries. If realistic query checks demonstrate an index is necessary, stop for a separately approved compatible schema approach rather than silently raising schema version 15.



## Context
Repository: /home/ngosi/.worktrees/refract/improve-diagnostic, attached branch improve-diagnostic. Approved DESIGN.md and PLAN.md are in docs/plans/improve-diagnostics. Read both. Dashboard read APIs and UI belong to later phases. Do not implement them in Phase 1. Shared contract decisions referring to dashboard reads define future compatibility, not Phase 1 scope. Baseline: 821 server tests passed with 15 live deselected; plugin checks passed with 3 existing validator compatibility warnings. No schema change or new table/index is authorized.

## Rules
Follow these bundled files:
- Contract: /home/ngosi/projects/refract/plugin/shared/worker-contract.md
- Response: /home/ngosi/projects/refract/plugin/shared/erp.md
- Notes: /home/ngosi/projects/refract/plugin/shared/notes-template.md
- Journal: /home/ngosi/projects/refract/plugin/shared/journal-template.md

Read /home/ngosi/.agents/skills/writing-for-agents/SKILL.md before editing plugin skill documentation. Follow its applicable guidance. Use test-first behavior changes; record actual failure output, command and GREEN evidence per task in phase-01/notes.md. An import error does not count as RED. Do not fake historical failures. Reuse existing worker-thread helpers for blocking database work and existing error normalization. Reuse the existing redaction patterns through a narrow public helper; no new library or separate secret registry.

Allowed product paths are exactly the Phase 1 Files above. You may also append phase-01/notes.md and phase-01/journal.md. Do not edit PLAN.md, DESIGN.md, .handover.md, other phase directories, unrelated plans, dependency files, generated assets, or secret-bearing environment/auth/config files. Do not commit, reset, stash, deploy, restart services, or run live backend probes. Do not print credentials or environment tokens. If scope or a decision blocks you, ask the coordinator with refract ask, or return BLOCKED if unavailable.

Run both verification commands listed in the phase, recording full summaries. Ordinary full server checks can take about five minutes. Keep all existing contract validation guards; fit updated tool documentation within its existing line limit. Return every changed path in ERP. The coordinator owns Git and final verification.

## Response Format
Return the full ERP # EXTERNAL RESPONSE block, append it to phase-01/journal.md under Implementation Response, and emit the matching Phase 1 status line.
