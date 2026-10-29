## User Request
Complete target-context-window plan, working in place.

## Phase
2: Resolve and persist qualified context telemetry.

## Tasks
- task-1: Test-first precedence, missing-data, rounding and bounds.
- task-2: Resolve configured capacity, provider usage and qualified fallback centrally.
- task-3: Bind execution lifecycle capacity and persist live and terminal measurements.
- task-4: Verify hydration, retry, target changes, invalidation and terminal paths.

## Context
Read /home/ngosi/projects/refract/docs/plans/target-context-window/DESIGN.md and PLAN.md Phase 2. Phase 1 accepted at refs/plans/target-context-window/phase-01/impl. TargetConfig.context_window is strict optional positive integer, persisted in immutable plan target records, omitted from session identity. Public configuration spelling is contextWindow.

Resolve capacity: configured target override, then provider capacity, then unavailable.
Resolve usage: valid backend/provider context observation, then ESTIMATED job total_input_tokens + total_output_tokens only when BOTH known. Zero valid; do not add cache counters.
Use existing Measurement fields. Add source target_config, quality reported for configured capacity. Cumulative fallback source derived and quality estimated. Derived remaining must retain estimated quality if usage estimated. Preserve backend provenance; backend snapshots can themselves have quality derived, not just reported.
round(clamp(100 * (1 - used/capacity), 0, 100), 2). Keep raw used above cap. Override must recompute remaining even if provider supplies conflicting percent; override with unknown used leaves remaining unavailable. Without override retain valid existing provider-percent behavior.

Implementation anchors:
- execution.py execute restores accumulator then selects snapshotted plan target; bind selected target capacity, never refreshed TOML.
- _safe_telemetry_dump currently drops capacity-only state; fix.
- _handle_telemetry processes events and immediately merges telemetry. Seed capacity before token events with equivalent live persistence for streaming and non-streaming jobs.
- Existing same-target retries/recovery invalidate context via complete_attempt/invalidate_context. Preserve configured capacity but clear native usage and provider capacity when appropriate. Consumption totals still span attempts.
- Executor selects one target per execute call, no in-loop target-switch feature needed. On later execution/retry selecting another target, replace/remove old configured capacity and clear stale provider context.
- Existing backend observations can be quality derived. Do not promote your fallback estimates into authoritative snapshots on hydration/finalization or when processing DriverResult.telemetry.
- Persist resolved telemetry through existing JSON merge/metadata paths. Historical reads never consult current config.

Useful existing tests:
- test_execution.py test_telemetry_updated_routes_through_execution_before_stream_recording: emitter and persisted state.
- test_retry_telemetry_rollover_cumulative_consumption and test_telemetry_fallback_preserves_cumulative_totals_across_retries: retry streams and final-result fallback.
- test_new_submissions_use_refreshed_catalog_while_existing_plan_stable.
- test_database.py retry/reopen telemetry tests.
- test_streaming_backends.py parser provenance, compaction and actual snapshot fixtures.
Update old expectations only where approved new estimated fallback changes behavior. Keep invalidation guards and explicit provenance checks, never weaken tests merely to pass.

## Files
- server/src/refract/telemetry.py
- server/src/refract/execution.py
- server/tests/test_telemetry.py
- server/tests/test_execution.py
- server/tests/test_streaming_backends.py
- server/tests/test_result_metadata.py
- server/tests/test_database.py
- docs/plans/target-context-window/phase-02/notes.md
- docs/plans/target-context-window/phase-02/journal.md

## Done When
- Every Phase 2 acceptance criterion/reviewer check in PLAN.md passes.
- Capacity-only live and terminal state persists before token events, remaining unavailable.
- Both unknown totals or one missing total never become zero; known 0+0 yields 100%.
- Cache counters not separately added. Existing deduplication/completeness unchanged.
- Snapshots supersede fallback; invalidation re-enables explicitly estimated fallback.
- Target changes/retries/recovery do not resurrect stale provider observations.
- Failure/cancellation/finalization/reopen paths preserve resolved measurement provenance.
- No public alias fields, frontend arithmetic, backend CLI changes or database migration.
- cd /home/ngosi/projects/refract/server && uv run pytest -q
- Record fresh RED then GREEN per task; full verification after each task.

## Rules
Follow these bundled files:
- Contract: /home/ngosi/projects/refract/plugin/shared/worker-contract.md
- Response: /home/ngosi/projects/refract/plugin/shared/erp.md
- Notes: /home/ngosi/projects/refract/plugin/shared/notes-template.md
- Journal: /home/ngosi/projects/refract/plugin/shared/journal-template.md
Do not commit, reset, stash, or mutate Git. Coordinator owns Git.
Only edit declared files. Ask coordinator before expanding scope.
Do not edit plan/design/handover, other phase files, or docs/plans/worker-job-telemetry.
No secrets, .env/runtime secret config, live probes, dependencies, adjacent refactors.
Keep notes honest and preserve journal headings.

## Response Format
Return full ERP # EXTERNAL RESPONSE block with matching phase status line.
