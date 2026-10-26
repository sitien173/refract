# Worker Job Telemetry Implementation Plan

**Status:** Approved 2026-10-26; executing
**Design:** `docs/plans/worker-job-telemetry/DESIGN.md`
**Base:** `refs/plans/worker-job-telemetry/base`
**Base commit:** `94e6631df0181e23d59fd6daabd06523929eb06a`
**Commit:** `feat(telemetry): expose live worker context and per-job token totals`
**Tracking:** tracked

## Approved Outcome

Collect live context snapshots and final per-job consumption. Support Agy, Codex, Claude Code, and Pi without replacing their transports.

`used-tokens` means occupied context tokens. It never means Codex's non-cached consumption counter. Unsupported values remain `null`.

Expose normalized telemetry through metadata and job details. Preserve legacy fields, historical jobs, execution policy, and cancellation behavior.

## Execution Contract

- Execute one phase, validate, review independently, then stop.
- Write regression tests before changing production behavior.
- Use current task guidance when each phase starts.
- Do not pin profiles, providers, models, or targets here.
- Keep Coordinator ownership of Git and coordination files.
- Follow the bundled worker contract and ERP.
- Do not modify credentials or global CLI configuration.
- Do not launch live model requests without explicit authorization.
- Do not replace execution transports with RPC.

Each implementation prompt must include the approved design, this plan, the phase file set, and these contracts:

- `plugin/shared/worker-contract.md`
- `plugin/shared/erp.md`
- `plugin/shared/notes-template.md`
- `plugin/shared/journal-template.md`

## Baseline Evidence

Baseline verified 2026-10-26 at `94e6631`:

- `cd server && uv run pytest` -> 627 passed, 11 deselected.
- `cd server/web && npm test` -> 232 passed in 21 files.
- `cd server/web && npm run build -- --outDir /tmp/refract-worker-job-telemetry-build` -> built.
- `bash plugin/tests/run.sh` -> FAIL, pre-existing. `test-contracts.sh` asserts the admission sentence "At most one job per project runs at a time. ..." which `tool-contract.md` no longer contains. Phase 4 edits that file and must restore the sentence.

Verified command definitions:

- `server/pyproject.toml` configures default pytest to exclude live tests.
- `server/web/package.json` defines `npm test` and `npm run build`.
- Installed Vite CLI declares the `--outDir` build option.
- `plugin/tests/run.sh` requires Bash.

The build check uses `/tmp/refract-worker-job-telemetry-build`. It must not replace tracked dashboard assets during planning.

## Shared Contract and Boundaries

### Metadata

Add one versioned `telemetry` object under `result.metadata`. Its five primary measurements are:

- `context_remaining_percent`
- `context_window_size`
- `context_used_tokens`
- `total_input_tokens`
- `total_output_tokens`

Also retain normalized `cache_read_tokens` and `cache_write_tokens`. Each measurement contains `value`, `source`, `quality`, and `observed_at`. Use a shared typed representation, not backend-specific public shapes.

`quality` is `reported`, `derived`, `estimated`, or `unavailable`. Unsupported fields have null values. Zero is a valid reported value. Reject booleans, negative counts, malformed types, and non-finite numbers.

Include compact attribution for persisted attempts and execution invocations. Retain completed-attempt aggregates and active invocation state, not an unbounded attempt list. Keep the current context separate from aggregate job consumption. Keep only the latest relevant context snapshot, not context history.

A completeness field distinguishes complete totals from partial observations. If an invocation has unknown consumption, an aggregate of known observations is a partial subtotal. An entirely unobserved measurement is null, not zero.

Legacy top-level metadata keys remain readable and retain backend-native meaning. Do not silently redefine them as normalized totals. New consumers use `telemetry`.

### Persistence and live updates

Reuse `jobs.result_metadata_json`; retain schema version 15. Add transactional metadata merge methods rather than a new table or migration framework.

Process telemetry before transcript recorder quota checks. Persist the latest snapshot independently from transcript events. Terminal writes must merge rather than replace telemetry accidentally.

Reuse existing job-detail polling for live presentation. The normal active-job polling interval is the presentation bound after persistence, excluding request and scheduling delay. Do not introduce a second streaming protocol for this feature.

### Accounting

Completed response identities prevent duplicate additions. Streaming snapshots replace earlier snapshots for the same response. Final cumulative totals reconcile observations rather than add again.

Normalize input to include cache reads and writes exactly once. Codex input already includes cached input; do not add cached input again. Claude and Pi expose separate cache components; normalize according to verified payload semantics. Agy semantics must follow sanitized evidence, not assumptions.

Baseline cumulative counters against the same session and generation. Missing baselines require invocation-local evidence or incomplete totals. Counter decreases, new sessions, reconstruction, and fresh recovery cannot reuse old baselines.

Preserve measurements across retry of a job ID. Distinguish retry attempts and internal recovery invocations. Newly submitted jobs start separate accounting.

### Context and safety

Prefer explicit context snapshots. Latest-response usage can derive occupancy only when retained components are established. Never derive occupancy from job totals.

Invalidate incompatible context on compaction or model change. Missing capacity leaves percentage unknown. Do not apply Codex's vendor-specific status-line baseline to normalized percentages.

Collectors read only the verified owning session. Never select an unrelated latest session. Never execute another agent or API call to obtain telemetry. Restrict reads, polling, and payload sizes with tested bounds.

Telemetry parsing and collector errors cannot change backend outcome, timeout, permissions, tools, or cancellation. Persist no raw payloads, session paths, prompts, or credentials in telemetry.

## Phase 1: Durable telemetry contract and read APIs

**Task Guide Input:** Implement the normalized measurement model, attempt/invocation accumulator, metadata merge persistence, and running/terminal metadata exposure. Use cases include live job reads, historical jobs, failed jobs, retried jobs, and transcript truncation. Keep schema version 15 and all worker transports unchanged.

**Goal:** Synthetic observations survive persistence and API reads independently from transcripts.

**Files:**
- Create: `server/src/refract/telemetry.py`
- Create: `server/tests/test_telemetry.py`
- Modify: `server/src/refract/models.py`
- Modify: `server/src/refract/database.py`
- Modify: `server/src/refract/drivers.py`
- Modify: `server/src/refract/execution.py`
- Modify: `server/src/refract/runtime.py`
- Modify: `server/src/refract/server.py`
- Modify: `server/src/refract/dashboard.py`
- Modify: `server/tests/test_database.py`
- Modify: `server/tests/test_database_atomicity.py`
- Modify: `server/tests/test_execution.py`
- Modify: `server/tests/test_runtime.py`
- Modify: `server/tests/test_server.py`
- Modify: `server/tests/test_dashboard.py`
- Modify: `server/tests/test_mcp_schema_contract.py`

**Tasks:**
1. Add failing tests and the shared typed telemetry contract. Implement validation, identity-based reconciliation, nullable measurements, provenance, and completeness. Cover response snapshots, consumption, and context invalidation separately.
2. Add transactional telemetry merges into metadata. Preserve unrelated fields, existing v15 records, attempt history, and observed totals across job retry. Protect terminal metadata against stale observations and partial overwrite.
3. Route `telemetry.updated` through execution before transcript recording. Assign actual persisted attempt and invocation identities, including session-recovery invocations. Retain observed partial telemetry on cancellation, failure, timeout, and daemon interruption.
4. Expose additive telemetry through runtime, MCP waits, and dashboard job reads. Keep result paging, routing tokens, failure metadata, response bounds, and historical metadata behavior intact.

**Acceptance Criteria:**
- All five primary measurements accept reported zero and unavailable null.
- Invalid numeric inputs cannot create invalid metadata.
- Duplicate and stale observations cannot inflate consumption.
- Missing contributions produce explicit incomplete totals.
- A running job read returns persisted synthetic telemetry.
- Terminal and paginated waits retain identical telemetry.
- Database reopen retains snapshots without a schema upgrade.
- Transcript quota exhaustion and pruning do not erase telemetry.
- Retry preserves prior consumption without treating it as current context.
- Internal session recovery receives a separate invocation identity.
- Cancellation and failure preserve last observed partial measurements.
- Historical jobs with empty metadata remain valid.

**Reviewer Checklist:**
- Check transaction boundaries and terminal-write races.
- Check actual attempt numbering rather than hard-coded `1`.
- Check metadata retains completed-attempt aggregates, not unbounded attempt history.
- Check metadata contains no raw payload or sensitive path.
- Check telemetry cannot block the subprocess deadline indefinitely.
- Check existing MCP pagination and byte-budget handling.

**Verification Checks:**
- `cd server && uv run pytest`

## Phase 2: Correct usage collection across existing backend streams

**Task Guide Input:** Integrate the shared telemetry contract into Agy, Codex, Claude Code, and Pi using their existing structured output. Use cases include multi-response jobs, duplicate lifecycle records, resumed sessions, cached input, malformed usage, and final counter reconciliation. Preserve existing response text, session resolution, tool events, subprocess policy, and legacy metadata fields.

**Goal:** Each adapter emits trustworthy live observations and final normalized job consumption.

**Files:**
- Modify: `server/src/refract/backends/__init__.py`
- Modify: `server/src/refract/backends/_shell.py`
- Modify: `server/src/refract/backends/agy.py`
- Modify: `server/src/refract/backends/claude.py`
- Modify: `server/src/refract/backends/codex.py`
- Modify: `server/src/refract/backends/pi.py`
- Modify: `server/src/refract/telemetry.py`
- Modify: `server/tests/test_telemetry.py`
- Modify: `server/tests/test_streaming_backends.py`
- Modify: `server/tests/test_execution.py`
- Modify: `server/tests/test_processes.py`
- Modify: `server/tests/fixtures/usage/agy.jsonl`
- Modify: `server/tests/fixtures/usage/claude.jsonl`
- Modify: `server/tests/fixtures/usage/codex.jsonl`
- Modify: `server/tests/fixtures/usage/pi.jsonl`

**Tasks:**
1. Add sanitized multi-response regression fixtures and failing cache-accounting tests. Extend backend result propagation only as required for normalized telemetry. Use one authoritative usage observation per response or step.
2. Integrate Claude and Pi collectors. Claude reconciles assistant observations with final aggregate usage and observed model capacity. Pi aggregates authoritative completed assistant messages, not repeated `turn_end.message` or streaming snapshots. Include separately reported summary usage where available without counting it twice.
3. Integrate Codex and Agy collectors. Codex reconciles `turn.completed.usage`; Agy reconciles completed step usage with terminal counters. Establish counter scope from fixtures or documented evidence before subtracting baselines.
4. Add live context derivation only where response-local retained components are established. Handle compaction, model changes, unavailable capacities, malformed data, and missing final events. Ensure no-emitter execution still returns normalized final telemetry.

**Acceptance Criteria:**
- Multi-response Pi consumption exceeds the final message alone.
- Pi lifecycle duplicates do not double-count response usage.
- Claude cache reads and writes enter normalized input once.
- Claude capacity is not selected arbitrarily from unrelated model usage.
- Codex cached input is not added twice.
- Agy final totals do not duplicate prior step consumption.
- Repeated cumulative snapshots are replacements, not additions.
- Resumed history is not counted as prior job consumption.
- Missing baselines produce explicit incomplete totals.
- At least one observation is persisted before completion for a synthetic multi-response stream.
- Context snapshots can shrink after compaction without reducing consumption totals.
- Parsing failures leave text, tool events, and backend outcomes unchanged.
- Legacy extraction remains backward-compatible where already supported.

**Reviewer Checklist:**
- Inspect cache semantics for each backend independently.
- Inspect reasoning token handling for double-counting.
- Inspect final result reconciliation and response identity.
- Inspect error paths that currently return before attaching usage.
- Verify no transport, permission, or process-group behavior changed.
- Distinguish inferred context from explicitly reported context.

**Verification Checks:**
- `cd server && uv run pytest`

## Phase 3: Bounded session telemetry and capability evidence

**Task Guide Input:** Enrich context snapshots without changing transports. Implement exact-session Codex rollout collection and verify whether Pi session artifacts expose usable effective model capacity. Use cases include concurrent jobs, resumed sessions, missing session files, partial JSONL writes, compaction, model changes, and cancellation. Unsupported Pi or Agy fields remain unavailable with documented evidence. No credential reads, global configuration changes, RPC transport replacement, or extra model requests.

**Goal:** Add safe context enrichment and state precisely which live measurements each backend supports.

**Files:**
- Modify: `server/src/refract/backends/codex.py`
- Modify: `server/src/refract/backends/pi.py`
- Modify: `server/src/refract/backends/agy.py`
- Modify: `server/src/refract/backends/_shell.py`
- Modify: `server/src/refract/telemetry.py`
- Modify: `server/tests/test_telemetry.py`
- Modify: `server/tests/test_streaming_backends.py`
- Modify: `server/tests/test_processes.py`
- Modify: `server/tests/test_live_backends.py`
- Modify: `server/CLI_ARGUMENTS.md`

**Tasks:**
1. Verify installed CLI interfaces and sanitized session formats through documentation and read-only local inspection. Record versions, supported measurements, counter scope, and missing capabilities in `server/CLI_ARGUMENTS.md`. Do not inspect existing user conversations. Reuse sanitized fixtures or explicitly authorized temporary probe sessions.
2. Add a bounded Codex collector for the exact known session ID. Read current `token_count` context and capacity, baseline cumulative counters safely, and integrate with the owning invocation. Prefer event-triggered incremental reads and final reconciliation over a new watcher service. Test identity mismatch, concurrent sessions, partial lines, file growth, rotation, truncation, and missing files.
3. Add Pi enrichment only where verified existing artifacts expose effective model metadata. If capacity cannot be established without another agent process or unverified flags, leave it null and document the limitation. Handle explicit Agy context metadata if present; otherwise document headless capacity as unavailable. Add opt-in live telemetry probes and offline capability tests.

**Acceptance Criteria:**
- Codex collector refuses files with mismatched session identity.
- No collector chooses an unrelated latest conversation.
- Session reads and retries have explicit tested bounds.
- Partial or malformed lines cannot fail the worker.
- Concurrent jobs cannot exchange measurements or baselines.
- Compaction and model changes invalidate stale context.
- Missing files or unsupported formats degrade to unavailable telemetry.
- Collector lifecycle ends with completion, cancellation, or timeout.
- No extra model call or RPC execution process is launched.
- Capability documentation distinguishes observed, fixture-only, and unverified behavior.
- Unsupported Pi and Agy capacity is shown as unavailable.
- Live probes are opt-in and never report missing prerequisites as passes.

**Reviewer Checklist:**
- Check path resolution against exact session identity and configured roots.
- Check no raw session content enters logs or metadata.
- Check file reads cannot scan unbounded user history.
- Check collectors do not outlive the subprocess or extend deadlines.
- Check model capacity is effective runtime metadata, not a guessed catalog value.
- Check unsupported capabilities are explicit rather than silently approximated.

**Verification Checks:**
- `cd server && uv run pytest`

Live probe commands are added only after their test selectors exist. Validate collection first, then obtain execution authorization. Lack of authorization leaves live evidence unverified, not passing.

## Phase 4: Dashboard telemetry, documentation, and release checks

**Task Guide Input:** Display normalized telemetry in existing job details using current active-job polling. Show context and consumption separately, including quality, source, observation time, and partial totals. Cover both canonical project job details and the legacy route. Preserve transcript rendering, keyboard access, routing races, terminal refresh, and historical jobs. Document the public metadata contract and backend capability limits.

**Goal:** Users can inspect live context and final consumption without misreading unknown or partial data.

**Files:**
- Modify: `server/web/src/components/JobDetails.jsx`
- Modify: `server/web/src/components/JobDetails.test.jsx`
- Modify: `server/web/src/hooks/useProjectDetail.js`
- Modify: `server/web/src/screens/ProjectDetail.test.jsx`
- Modify: `server/web/src/screens/JobDetail.jsx`
- Modify: `server/web/src/integration/dashboard-flow.test.jsx`
- Modify: `server/web/src/styles/app.css`
- Modify: `server/tests/test_dashboard.py`
- Modify: `server/tests/test_server.py`
- Modify: `server/tests/test_retention.py`
- Modify: `server/tests/test_live_backends.py`
- Modify: `server/README.md`
- Modify: `server/CLI_ARGUMENTS.md`
- Modify: `plugin/skills/coordinating-multi-model-work/references/tool-contract.md`
- Generated: `server/src/refract/dashboard_static/index.html`
- Generated: `server/src/refract/dashboard_static/assets/`

**Tasks:**
1. Add failing rendering tests and display the five primary measurements in job details. Label context used, context capacity, context remaining, job input tokens, and job output tokens. Show unknown values explicitly, preserve reported zero, and disclose estimated or partial measurements.
2. Reuse selected-job polling on canonical and legacy routes. Test refreshed values, initial loading, terminal transition, reconnect or request failure, stale responses after navigation, and transcript truncation. Keep telemetry independent of `useJobStream` retention or status.
3. Add integration coverage for running-to-terminal telemetry, reload after persistence, transcript pruning, and historical jobs. Document normalized and legacy semantics, cache components, observation timing, unavailable capabilities, and opt-in probe limitations.
4. Run release checks and build dashboard assets using the existing Vite configuration. Inspect generated changes and preserve unrelated packaged assets. Update the worker-facing metadata contract without changing its workflow rules.

**Acceptance Criteria:**
- Context used never displays the consumption-based Codex counter.
- Remaining percentage is null when capacity is unknown.
- All five primary measurements are visible when supplied.
- Unknown, zero, estimated, and partial values are distinguishable.
- Active-job polling refreshes telemetry on both routes.
- A terminal transition retains the final persisted telemetry.
- Late responses for another job cannot replace current measurements.
- Transcript truncation and pruning do not stop telemetry refresh.
- Historical jobs render without errors or fabricated values.
- Documentation identifies verified backend capability limits.
- Packaged assets contain the new telemetry panel.
- Offline Python, frontend, plugin, and isolated build checks pass.

**Reviewer Checklist:**
- Check accessible text labels and percentage interpretation.
- Check existing polling rather than duplicate timers or SSE listeners.
- Check terminal refresh and navigation race coverage.
- Check source and timestamps remain non-sensitive.
- Check public contract preserves existing routing/failure metadata.
- Check generated output belongs only to the dashboard build.

**Verification Checks:**
- `cd server && uv run pytest`
- `cd server/web && npm test`
- `cd server/web && npm run build -- --outDir /tmp/refract-worker-job-telemetry-build`
- `bash plugin/tests/run.sh`

Packaging additionally uses the existing build script with its configured output directory. The isolated build above remains the baseline-verifiable build check. Inspect generated assets before checkpointing.

## Final Acceptance Matrix

| Requirement | Required evidence |
|---|---|
| Four backend integrations | Sanitized multi-response fixture tests for every adapter |
| Live supported measurements | Synthetic observations visible in running API reads and dashboard refresh |
| Correct job totals | Cache, duplicate, resumed-session, retry, and recovery tests |
| Context distinct from consumption | Compaction and independent snapshot tests |
| Unknown values remain null | Backend capability and historical-job tests |
| Durable metadata | Database reopen, terminal merge, truncation, and pruning tests |
| Compatible APIs | MCP metadata, pagination, response-budget, and dashboard tests |
| Safe collection | Exact-session matching, bounded reads, cancellation, and privacy tests |
| Live capability claims | Explicitly authorized probe evidence or an unverified designation |
| Release readiness | Fresh full checks and independent phase reviews |

## Stop Conditions

Stop for renewed approval if implementation requires a transport replacement, database migration, global CLI setting change, credential inspection, additional model requests for telemetry, or complete metrics on unsupported backends.

Unavailable telemetry is acceptable only when identified and tested. Do not substitute guessed capacities or cumulative consumption for current context.

## Finalization

After all phases pass, finish journals and handover. Consolidate local checkpoints using the plan anchors. Set the plan implementation ref only after consolidation. Run fresh verification at that final revision and report remaining capability limitations.
