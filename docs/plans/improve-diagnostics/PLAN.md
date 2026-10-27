# Improve Job Diagnostics

**Design:** [DESIGN.md](DESIGN.md)
**Status:** All phases validated and reviewed; final consolidated verification required before completion.
**Base:** `refs/plans/improve-diagnostics/base`
**Commit:** `feat(diagnostics): add client error reports and dashboard visibility`

## Scope

Add client-reported job diagnostics, durable job events, correlated logs, a separate suspect indicator, and dashboard inspection. Preserve execution status and every existing MCP response contract. No implementation is authorized until the user approves this plan.

Existing plans concern retry policies and telemetry, not diagnostic reporting. Leave their files and unresolved work untouched. The consultation returned an unusable generic error despite a successful job state; record that limitation rather than treating it as design evidence.

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

## Execution and Review

Sequence for every phase: implement -> specification validation -> independent review.

Resolve implementation and review profiles from fresh task guidance during execution. No profile, model, provider, or target is pinned by this plan. Require test-first evidence for new behavior. Read skill-authoring guidance before modifying plugin skill documents. Do not restart or deploy the running server during this plan.

The existing MCP client will not discover the added tool until the changed server is deployed and the client reconnects. Deployment and live backend probes are outside this plan.

## Baseline Verification

Baseline application revision: `67bf3d71cca4c26b04b0338a62e426ce6dad8dc2`.

Task `b8d48f272` completed with exit code 0. Product sources remained identical to the base revision throughout these checks.

- Server: `cd server && uv run --extra dev pytest -q` passed with 821 tests and 15 live tests deselected.
- Frontend setup: `cd server/web && npm ci` exited 0.
- Frontend: `cd server/web && npm test` passed with 246 tests across 21 files.
- Isolated production build exited 0 using the Phase 3 build command.
- Plugin: `bash plugin/tests/run.sh` exited 0; session-start tests, contract tests, and both installed validators passed.
- `git diff --check` exited 0; no tracked product files changed.

Existing warnings remain outside this diagnostic feature: npm reported six dependency vulnerabilities, comprising two moderate, two high, and two critical; deprecated dependencies and an esbuild install-script approval warning also appeared. Frontend tests emitted React `act` warnings. Plugin validation emitted three existing compatibility warnings about `.mcp.json`, commands, and `hooks/hooks.json`. These warnings do not establish exploitability or authorize dependency upgrades. Owner for security triage: Refract maintainer. No security audit or live backend probe was run.

Frontend dependency setup: `cd server/web && npm ci`. Server checks use the declared development extra. Builds use an external temporary output directory to preserve checked-in dashboard assets.

## Phases

### Phase 1: Durable client reporting without execution changes

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

### Phase 2: Bounded dashboard diagnostic read APIs

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

### Phase 3: Dashboard investigation and client adoption guidance

**Task Guide Input:** Implement the dedicated diagnostics screen, report inspection, filtering, job links, and suspect badges. Update client guidance and public server documentation for the new tool. This phase combines UI/client implementation with narrowly scoped contract documentation and tests. Preserve existing layout, polling, navigation, and access patterns.

**Goal:** Operators can investigate client observations, and clients receive precise reporting instructions.

**Files:**
- Create: `server/web/src/screens/Diagnostics.jsx`
- Create: `server/web/src/screens/Diagnostics.test.jsx`
- Modify: `server/web/src/App.jsx`
- Modify: `server/web/src/App.test.jsx`
- Modify: `server/web/src/api.js`
- Modify: `server/web/src/api.test.js`
- Modify: `server/web/src/components/Sidebar.jsx`
- Modify: `server/web/src/components/JobDetails.jsx`
- Modify: `server/web/src/components/JobDetails.test.jsx`
- Modify: `server/web/src/screens/Jobs.jsx`
- Modify: `server/web/src/screens/Jobs.test.jsx`
- Modify: `server/web/src/screens/ProjectDetail.jsx`
- Modify: `server/web/src/screens/ProjectDetail.test.jsx`
- Modify: `server/web/src/styles/app.css`
- Modify: `server/web/src/integration/dashboard-flow.test.jsx`
- Modify: `server/README.md`
- Modify: `plugin/skills/coordinating-multi-model-work/references/tool-contract.md`
- Modify: `plugin/skills/coordinating-multi-model-work/references/review.md`
- Modify: `plugin/tests/test-contracts.sh`

**Tasks:**
1. Add failing UI/API-client tests, then implement the diagnostics route, navigation, bounded filtering, pagination, refresh, and job links using existing UI primitives.
2. Display separate suspect badges in standalone/project job lists and job details. Fetch bounded job reports with loading, empty, error, and stale-response handling. Ensure manual refresh discovers reports on terminal jobs.
3. Document tool inputs, key reuse, privacy, retention, and observation semantics. In coordinator guidance, report protocol anomalies or confirmed output-contract anomalies before recovery; reporting failures never trigger recursive reports or block safe reconciliation.
4. Run integration, server, plugin, and isolated production-build checks. Do not modify generated dashboard assets in this phase; deployment rebuilds the package through its existing procedure after approval.

**Acceptance Criteria:**
- The diagnostics screen supports project/job/category filters and next-page navigation.
- Changing a filter resets pagination and ignores stale responses.
- Every report displays its ID, timestamp, category, expected/observed summaries, job link, and explicitly current execution state.
- Reports appear as client observations; suspect is visually separate from execution state.
- User-controlled report text renders as text, never injected HTML.
- Job details show bounded reports in both standalone and project navigation.
- Refresh works after terminal completion; no automatic retry/reroute control is added.
- Loading, empty, unavailable-runtime, and refresh-failure states remain usable.
- Keyboard navigation, labels, and non-color suspect indicators are covered by tests.
- Guidance waits for terminal pagination completion before reporting missing output, and requires ERP only where the workflow does.
- Generic worker error text returned under `succeeded` is a documented output-report example, not a reason to rewrite job status automatically.
- Tool documentation remains consistent across the server and plugin, including existing contract line-count guards.

**Reviewer Checklist:**
- Check accessible filters, links, badges, focus behavior, and error states.
- Check bounded reads, refresh behavior, and stale-request protection after route changes.
- Verify no changes to execution-status badge meanings or transcript handling.
- Ensure reporting guidance preserves original IDs and safe recovery semantics.
- Confirm no automatic reporting loop or unsupported promise of universal client detection.
- Ensure generated assets, dependencies, unrelated plans, and deployment files remain untouched.

**Verification Checks:**
- `cd server && uv run --extra dev pytest -q`
- `cd server/web && npm test`
- `build_dir=$(mktemp -d /tmp/refract-diagnostics-build.XXXXXX) && (cd server/web && npm run build -- --outDir "$build_dir")`
- `bash plugin/tests/run.sh`

## Final Acceptance

All three phases require specification validation and independent review. Run all Phase 3 verification commands again against the final consolidated revision. Report any debt and unrun checks explicitly. Deployment, daemon restart, live provider probes, report resolution, and historical report backfill remain excluded.
