## User Request
Continue the approved improve-diagnostics plan with bounded dashboard diagnostic read APIs. Implement Phase 2 only.

## Phase
2: Bounded dashboard diagnostic read APIs

## Tasks and Files
 Bounded dashboard diagnostic read APIs

**Task Guide Input:** Expose stored diagnostic reports to the dashboard using guarded bounded queries and separate suspect metadata. This is non-UI API and database implementation, building on Phase 1's event contract.

**Goal:** Operators can query sanitized reports without altering MCP contracts or execution state.

**Files:**
- Modify: `server/src/refract/database.py`
- Modify: `server/src/refract/models.py`
- Modify: `server/src/refract/dashboard.py`
- Modify: `server/tests/test_database.py`
- Modify: `server/tests/test_dashboard.py`
- Modify: `server/tests/test_dashboard_consolidation.py`
- Modify: `server/tests/test_retention.py`

**Tasks:**
1. Write failing tests for dashboard query filters, cursor boundaries, invalid values, access controls, absent jobs, and retained-event suspect derivation.
2. Implement parameterized filtered report reads and the guarded diagnostics endpoint with bounded pages and allowlisted response fields.
3. Add dashboard-only suspect/count fields to list/detail job representations; avoid scanning every event once per listed job.

**Acceptance Criteria:**
- Default and maximum page sizes, exclusive cursors, and stable ordering match the contract.
- Category, project, and job filters compose correctly across more than one page.
- New reports arriving between requests do not duplicate older-page entries.
- Diagnostics can find reports for jobs outside the ten most recent terminal jobs.
- Unknown filters, forbidden requests, and unavailable runtime follow explicit dashboard errors.
- Job detail and project job lists derive matching suspect/count values.
- No retained report means `suspect: false` and `diagnostic_count: 0`.
- Retention clears diagnostic indicators without changing execution status.
- Existing MCP summary and result shapes remain unchanged.

**Reviewer Checklist:**
- Check filter validation, SQL parameterization, and count/query bounds.
- Verify endpoint registration uses the same guards as existing dashboard GET routes.
- Check no raw payload, report key, prompt, transcript, or configuration secret leaks.
- Confirm category filtering cannot include unrelated historical event kinds.
- Verify no unbounded per-job report list is added to dashboard job payloads.

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
Repository /home/ngosi/.worktrees/refract/improve-diagnostic, branch improve-diagnostic. Read approved DESIGN.md and PLAN.md. Phase 1 is closed at refs/plans/improve-diagnostics/phase-01/impl. The tool stores job.error_reported events with version/category/redacted expected/observed/report_key and returns event ID as decimal string. Do not alter that MCP contract. Baseline: 834 server tests passed with 15 live deselected; plugin checks passed. Existing Phase 1 nonblocking test-coverage debt remains owned by Phase 1 maintainer; do not broaden this phase to repair it. Read-only dashboard API work only; UI belongs to Phase 3. Reuse existing guards, worker helpers, and job serializers. No schema/table/index changes authorized. Avoid per-job full history scans when rendering job lists.

## Rules
Follow these bundled files:
- Contract: /home/ngosi/projects/refract/plugin/shared/worker-contract.md
- Response: /home/ngosi/projects/refract/plugin/shared/erp.md
- Notes: /home/ngosi/projects/refract/plugin/shared/notes-template.md
- Journal: /home/ngosi/projects/refract/plugin/shared/journal-template.md

Stay within the exact Phase 2 product file list above. You may append phase-02/notes.md and phase-02/journal.md. Do not edit plan/design/handover, other phases or unrelated plans. No commits, resets, stashes, dependency changes, generated assets, deployment/restart, live backend probes, network or secret-bearing files. Record genuine RED then GREEN evidence per changed behavior, not missing-import errors. Keep earlier evidence. Ask via refract ask if blocked; never guess an unresolved contract.

Run both full Verification Checks and report actual summaries, plus git diff --check. Return all changed paths including notes/journal. Coordinator owns Git, final verification, and independent review. No product changes beyond this phase.

## Response Format
Return the ERP # EXTERNAL RESPONSE block and matching Phase 2 status line. Append the full ERP under Implementation Response in phase-02/journal.md.
