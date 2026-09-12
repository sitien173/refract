# Worker Dashboard Streaming Implementation Plan

Design: [DESIGN.md](DESIGN.md)

Implement durable backend worker transcript streaming for dashboard job details.
The implementation preserves final job results and existing MCP contracts while
adding provider normalization, durable cursor replay, SSE invalidation, and a
virtualized transcript UI.

All phases run in `/home/ngosi/projects/openmcp`. Execute every behavior change
through RED, GREEN, and REFACTOR. Provider fixtures are the required acceptance
evidence. Live provider tests remain optional because they invoke external
services.

---

### Phase 1: Durable stream storage and recorder

**Task Guide Input:** Add the durable transcript foundation for OpenMCP jobs.
Four use cases must work together: schema version 11 creates a separate
`job_stream_events` table without rewriting existing job data; database methods
append bounded event batches and retrieve cursor pages; an event-loop recorder
coalesces assistant deltas and enforces per-event and per-job limits; retention
removes only expired terminal transcripts. Keep lifecycle events and final job
results unchanged. Write tests before implementation.

**Goal:** Normalized stream events are durably committed, replayable by cursor,
bounded, and written only from the database-owning thread.

**Files:**
- Modify: `src/openmcp/database.py`
- Modify: `src/openmcp/models.py`
- Create: `src/openmcp/streaming.py`
- Modify: `src/openmcp/runtime.py`
- Modify: `tests/test_database.py`
- Create: `tests/test_streaming.py`
- Modify: `tests/test_runtime.py`

**Tasks:**
1. Add RED migration and cursor tests covering version 10 to 11, event batch
   insertion, ascending cursor pages, high-water lookup, retained-from lookup,
   cascade deletion, and database reopen.
2. Add the normalized internal and dashboard event models. Add the
   `job_stream_events` table, its `(job_id, id)` index, transactional append,
   bounded page retrieval, per-job byte and event totals, and terminal retention
   deletion.
3. Add RED recorder tests for text coalescing, 50-event and 64-KiB flushes,
   timer flushes, 8-KiB text splitting, 8-MiB and 20,000-event job limits, one
   truncation marker, explicit final flush, and failed persistence status.
4. Implement the event-loop `StreamRecorder`. Wire runtime startup retention
   cleanup without pruning active jobs. Keep unexpected stream failures isolated
   from worker job results.

**Acceptance Criteria:**
- Opening a version 10 database produces schema version 11.
- Historical jobs and lifecycle events remain unchanged.
- Cursor retrieval returns no duplicates or skipped retained events.
- The recorder publishes nothing before transaction commit.
- Active transcript rows are never removed by retention.
- Exactly one `stream.truncated` event marks each limited job.
- Stream persistence failure cannot overwrite `job.result.text`.

**Reviewer Checklist:**
- SQLite writes remain on the connection-owning thread.
- The stream table contains no raw provider payload field.
- Cursor ordering uses database identifiers, not timestamps.
- Quota calculations include serialized payload bytes.
- Retention queries require terminal job state.
- Lifecycle event behavior remains backward compatible.

**Verification Checks:**
- `uv run pytest tests/test_database.py tests/test_streaming.py tests/test_runtime.py`
- `git diff --check`

**Commit:** `feat(streaming): add durable job transcript storage`

---

### Phase 2: Provider normalization and execution bridge

**Task Guide Input:** Stream safe normalized assistant and tool events from every
OpenMCP backend. Four use cases must work together: Claude and Agy use structured
stream JSON modes; Codex and Pi map their existing JSON modes; provider worker
threads send events through a bounded asyncio bridge with blocking backpressure;
target attempts flush all accepted events before lifecycle completion. Preserve
existing final result and session extraction byte-for-byte where fixtures expect
it. Exclude prompts, reasoning, tool payloads, diagnostics, and subagent text.
Write characterization and security tests before implementation.

**Goal:** Claude, Codex, Pi, and Agy emit safe transcript events without changing
authoritative final results.

**Files:**
- Modify: `src/openmcp/backends/__init__.py`
- Modify: `src/openmcp/backends/_shell.py`
- Modify: `src/openmcp/backends/claude.py`
- Modify: `src/openmcp/backends/codex.py`
- Modify: `src/openmcp/backends/pi.py`
- Modify: `src/openmcp/backends/agy.py`
- Modify: `src/openmcp/drivers.py`
- Modify: `src/openmcp/execution.py`
- Modify: `tests/test_execution.py`
- Create: `tests/test_streaming_backends.py`
- Modify: `tests/test_live_backends.py`

**Tasks:**
1. Add sanitized RED fixtures for Claude, Codex, Pi, and Agy. Assert supported
   message and tool mappings, synthetic entity identifiers, ignored unknown
   events, excluded planted secrets, and unchanged final result extraction.
2. Add one synchronous adapter emitter contract. Update provider parameter
   objects and parsers. Use Claude partial stream JSON, Agy stream JSON, Codex
   JSONL, and Pi JSON. Omit forwarded subagent text and all unsafe payloads.
3. Add RED bridge tests using a real worker thread. Assert 256-slot blocking
   backpressure, producer sentinel closure, cancellation cleanup, persistence
   failure isolation, and no database access from provider threads.
4. Implement the driver bridge and attempt decoration. Ensure target attempt
   events, provider output, final stream flush, target lifecycle events, final
   result storage, and terminal job state occur in the confirmed order. Add
   pre-execution structured-mode capability checks with final-only fallback.

**Acceptance Criteria:**
- Every supported backend emits provider-neutral assistant events.
- Every supported backend emits safe tool lifecycle events when available.
- Agy continuations remain one OpenMCP target attempt.
- Failed attempt transcripts remain labeled and replayable.
- Only a successful `DriverResult.text` becomes `job.result.text`.
- Queue saturation blocks producers instead of dropping events.
- No fixture secret reaches normalized event serialization.

**Reviewer Checklist:**
- Provider adapters know no job, database, HTTP, or retention concepts.
- Claude does not enable forwarded subagent text.
- Agy never streams merged diagnostics as assistant content.
- Capability detection happens before prompt execution.
- Changed command retries cannot duplicate provider side effects.
- Cancellation drains accepted events without hanging.

**Verification Checks:**
- `uv run pytest tests/test_streaming_backends.py tests/test_execution.py tests/test_live_backends.py -m 'not live'`
- `git diff --check`

**Commit:** `feat(streaming): normalize backend transcript events`

---

### Phase 3: Cursor replay and SSE invalidation

**Task Guide Input:** Expose durable job transcripts through the dashboard HTTP
surface. Four use cases must work together: a bounded REST endpoint returns
events after a cursor; a runtime-owned hub publishes committed high-water
cursors; a Starlette SSE endpoint sends initial and coalesced cursor notifications
with keepalives; stream status reports unavailable, active, complete, truncated,
or failed without exposing lifecycle payloads. Preserve dashboard security,
existing routes, and URI-only MCP resource notifications. Write endpoint and
race tests before implementation.

**Goal:** Browsers can replay all retained transcript content and receive reliable
new-data notifications without SSE carrying transcript payloads.

**Files:**
- Modify: `src/openmcp/streaming.py`
- Modify: `src/openmcp/runtime.py`
- Modify: `src/openmcp/dashboard.py`
- Modify: `src/openmcp/models.py`
- Modify: `tests/test_streaming.py`
- Modify: `tests/test_dashboard.py`
- Modify: `tests/test_server.py`

**Tasks:**
1. Add RED dashboard tests for `GET /dashboard/api/jobs/{job_id}/output`, cursor
   pagination, bounded limits, retained-from, every stream status, unknown jobs,
   and payload redaction.
2. Implement dashboard response models and database-backed replay. Derive stream
   health from job state, retained events, truncation markers, and safe lifecycle
   failure kinds.
3. Add RED SSE tests covering initial high-water delivery, post-commit delivery,
   capacity-one coalescing, disconnect cleanup, keepalive output, and the race
   between initial REST retrieval and subscription establishment.
4. Implement the runtime notification hub and
   `GET /dashboard/api/jobs/{job_id}/output/updates`. Keep SSE payloads limited
   to cursors. Leave MCP subscription behavior unchanged.

**Acceptance Criteria:**
- REST replay is the only transcript payload transport.
- SSE sends the current high-water immediately.
- Missed SSE notifications cannot lose committed events.
- Slow subscribers retain only the latest pending cursor.
- Unknown jobs return the existing safe not-found shape.
- Existing dashboard and MCP contracts remain unchanged.

**Reviewer Checklist:**
- SSE notifications occur only after database commit.
- New routes appear before dashboard fallback routes.
- Endpoint limits are parsed and bounded safely.
- Stream failure details expose codes, not internal exceptions.
- Disconnect cleanup cannot leak subscriber queues.
- No prompt or provider-native object reaches HTTP output.

**Verification Checks:**
- `uv run pytest tests/test_streaming.py tests/test_dashboard.py tests/test_server.py`
- `git diff --check`

**Commit:** `feat(dashboard): expose durable transcript updates`

---

### Phase 4: Virtualized live transcript interface

**Task Guide Input:** Add a full provider-neutral transcript viewer to dashboard
job details. Four use cases must work together: a hook loads durable cursor pages
and follows SSE high-water notifications; a reducer groups attempts, assistant
messages, and tool activity; a virtualized UI grows live without unbounded DOM
size; scroll-aware behavior follows at the live edge but preserves the viewport
while users inspect history. Keep five-second metadata polling, historical job
fallback, accessible status announcements, and authoritative final results.
Write hook, reducer, component, and integration tests before implementation.

**Goal:** Running and retained jobs display reliable live assistant and safe tool
activity with reconnect and reload recovery.

**Files:**
- Modify: `web/package.json`
- Modify: `web/package-lock.json`
- Modify: `web/src/api.js`
- Create: `web/src/hooks/useJobStream.js`
- Create: `web/src/hooks/useJobStream.test.jsx`
- Create: `web/src/components/JobTranscript.jsx`
- Create: `web/src/components/JobTranscript.test.jsx`
- Modify: `web/src/components/JobDetails.jsx`
- Modify: `web/src/components/JobDetails.test.jsx`
- Modify: `web/src/screens/JobDetail.jsx`
- Modify: `web/src/styles/app.css`
- Modify: `web/src/integration/dashboard-flow.test.jsx`

**Tasks:**
1. Add `@tanstack/react-virtual`. Add RED API and hook tests for initial replay,
   cursor paging, duplicate notifications, burst debouncing, automatic SSE
   reconnect, five-second REST fallback, stale request cancellation, and job
   identity changes.
2. Implement `getJobOutput`, the EventSource client, and `useJobStream`. Maintain
   applied and notified cursors, drain all missing pages, preserve loaded content
   after errors, and expose connecting, live, reconnecting, failed, and terminal
   states.
3. Add RED reducer and component tests. Group by target attempt, merge adjacent
   assistant deltas by entity, update tool cards by entity, distinguish failed
   attempts, and avoid duplicate authoritative final text.
4. Implement the virtualized transcript, provider badges, safe tool cards,
   connection indicators, scroll anchoring, keyboard-accessible `New activity`
   control, polite live regions, historical fallback, and truncated-stream final
   result behavior.

**Acceptance Criteria:**
- Running jobs update without five-second visual latency.
- Page reload reconstructs identical committed transcript entities.
- SSE disconnect recovery loses no committed content.
- Users reading older content experience no forced scroll.
- Transcript DOM size remains bounded.
- Historical jobs retain the current final result experience.
- Tool arguments, results, and reasoning never render.

**Reviewer Checklist:**
- EventSource closes on unmount and job changes.
- Stale fetches cannot mutate a newly selected job.
- Cursor deduplication precedes transcript reduction.
- Virtualization preserves accessible transcript semantics.
- Delta updates do not trigger one live-region announcement each.
- Final result suppression requires exact text equality.

**Verification Checks:**
- `npm --prefix web test -- --run src/hooks/useJobStream.test.jsx src/components/JobTranscript.test.jsx src/components/JobDetails.test.jsx src/integration/dashboard-flow.test.jsx`
- `npm --prefix web run build`
- `git diff --check`

**Commit:** `feat(dashboard): render live worker transcripts`

---

### Phase 5: Cross-layer hardening and release verification

**Task Guide Input:** Complete and harden worker dashboard streaming across the
repository. Four use cases must work together: integration tests prove durable
reload, reconnect, retries, truncation, and final-result compatibility; security
tests prove forbidden provider content cannot reach the dashboard; production
frontend assets are rebuilt and packaged; documentation states support and
limits without changing existing MCP contracts. Resolve all test failures and
review findings before closeout. Do not invoke paid live providers.

**Goal:** The complete feature passes repository verification and ships with
reproducible dashboard assets.

**Files:**
- Modify: `tests/test_smoke.py`
- Modify: `tests/test_runtime.py`
- Modify: `tests/test_execution.py`
- Modify: `tests/test_dashboard.py`
- Modify: `web/src/integration/dashboard-flow.test.jsx`
- Modify: `README.md`
- Modify: `docs/plans/worker-dashboard-streaming/DESIGN.md`
- Modify: generated files under `src/openmcp/dashboard_static/`

**Tasks:**
1. Add cross-layer tests for queued to running to terminal flow, committed replay
   after database reopen, SSE disconnect catch-up, failed then successful target
   attempts, stream truncation, persistence failure degradation, and historical
   job fallback.
2. Add security regression fixtures containing prompt secrets, reasoning,
   commands, tool arguments, tool results, stderr tokens, and unknown events.
   Assert none reach database stream rows or dashboard responses.
3. Document dashboard transcript behavior, all-backend structured support,
   retention limits, safe exclusions, final-only legacy fallback, and deferred
   subagent support. Reconcile design text with implemented behavior.
4. Run complete Python and frontend suites, rebuild dashboard assets, build the
   Python package, run the doctor command, inspect the final diff, and fix every
   blocking failure.

**Acceptance Criteria:**
- All non-live Python tests pass.
- All frontend tests pass.
- The production dashboard build succeeds.
- The Python package includes rebuilt dashboard assets.
- `openmcp doctor` succeeds.
- Security fixtures expose no forbidden transcript content.
- Final results and MCP job resources retain prior behavior.
- Documentation matches verified implementation behavior.

**Reviewer Checklist:**
- Generated assets match current web sources.
- Tests cover all four backend adapters.
- No live provider invocation was required for acceptance.
- Stream failures cannot fail otherwise successful jobs.
- Retention cannot delete active transcripts.
- Existing dashboard redaction remains intact.
- The diff contains no unrelated refactoring.

**Verification Checks:**
- `uv run pytest`
- `npm --prefix web test`
- `npm --prefix web run build`
- `uv build`
- `uv run openmcp doctor`
- `git diff --check`

**Commit:** `test(streaming): verify worker transcript delivery`
