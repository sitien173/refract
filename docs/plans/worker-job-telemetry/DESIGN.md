# Worker Job Telemetry Design

**Status:** Confirmed 2026-10-26
**Consultation:** Consult job `45d1371c-f427-4e55-a703-685c0cf14cbb` returned tool-call text, not usable advice. The coordinator continued from inspected code and documented interfaces.

## Purpose

Expose live context tracking and final per-job consumption. Cover Agy, Codex, Claude Code, and Pi.

The user confirmed these requirements:

- Collect live measurements and final job totals.
- Define `used-tokens` as occupied current context tokens.
- Keep consumption separate from current context.
- Retain existing worker transports and add telemetry collectors.
- Expose measurements through the API and dashboard.
- Preserve unknown measurements as `null`.

## Users and Success Criteria

Coordinators consume metadata through `job_wait`. Dashboard users inspect running and completed jobs.

- Running job details expose the latest supported measurements.
- The dashboard refreshes using its existing active-job polling.
- Completed jobs retain measurements after daemon restart.
- Transcript truncation or pruning does not erase telemetry.
- Job consumption excludes earlier work in resumed sessions.
- Retries and session recovery cannot silently double-count consumption.
- Missing telemetry does not change execution outcomes.
- Historical jobs remain readable without invented measurements.

## Constraints and Non-Goals

Keep `codex exec`, Claude print mode, Agy print mode, and Pi JSON mode. Do not replace execution transports with RPC.

Do not modify global status-line settings or authentication. Do not inspect credential stores. Do not run additional model requests for telemetry.

Do not hard-code model capacity tables. Do not infer context occupancy from cumulative consumption. Do not present unsupported capabilities as implemented.

No new telemetry daemon, chart history, account quota tracking, or billing estimate is required. No database schema migration is required: reuse `jobs.result_metadata_json`.

## Chosen Approach

Keep transports and add normalized telemetry collectors.

- Reject transport replacement: it expands execution and cancellation risk.
- Reject rendered status-line scraping: headless hooks are unverified.

Reuse provider events first. Add bounded, read-only session collectors only when the session identity and format are verified. Leave unsupported measurements unavailable.

## Architecture and Data Flow

### Measurement contract

Store a versioned `telemetry` object inside result metadata. Retain existing metadata keys and their backend-native meaning. New clients use normalized telemetry rather than interpreting legacy counters uniformly.

The telemetry object contains job consumption totals, the current context snapshot, compact attempt/invocation attribution, and a completeness indicator. Retain completed-attempt aggregates and active invocation state, not an unbounded per-attempt history. Each measurement carries its value, source, quality, and observation timestamp. Values are non-negative integers or `null`. Percentages are finite numbers between zero and 100 or `null`.

| Requested identifier | Normalized meaning | Dashboard label |
|---|---|---|
| `context-remaining` | Remaining percentage of the observed context capacity | Context remaining |
| `context-window-size` | Observed effective model capacity in tokens | Context capacity |
| `used-tokens` | Latest occupied context snapshot in tokens | Context used |
| `total-input-tokens` | Input consumed by this job, including cache reads and writes exactly once | Job input tokens |
| `total-output-tokens` | Output consumed by this job | Job output tokens |

Use snake_case fields internally: `context_remaining_percent`, `context_window_size`, `context_used_tokens`, `total_input_tokens`, and `total_output_tokens`. Preserve separate `cache_read_tokens` and `cache_write_tokens` measurements.

`quality` distinguishes reported, derived, estimated, and unavailable measurements. `source` is an allowlisted interface identifier, not a raw path or payload. `observed_at` records the observation, not the dashboard fetch time.

Prefer an explicit provider context snapshot. A latest-response usage calculation may supply a derived snapshot only when its retained components are established. Never sum context snapshots. Never count cached tokens twice. Hidden reasoning or removed messages must not be guessed into context occupancy.

Derive remaining percentage from compatible occupied tokens and capacity. This normalized percentage need not reproduce a vendor status line's reserved-token adjustments.

### Collection

1. Backend parsers emit normalized `telemetry.updated` observations.
2. A shared accumulator validates and reconciles observations.
3. Execution consumes telemetry before transcript recording or quota checks.
4. Database writes merge telemetry into existing result metadata.
5. Runtime and dashboard reads expose the latest stored snapshot.
6. Existing job-detail polling refreshes the dashboard while running.
7. Terminal persistence retains telemetry alongside final result fields.

Telemetry does not depend on transcript cursors or retention. Do not add telemetry-only transcript events indefinitely after transcript truncation. The existing polling interval bounds presentation delay after persistence, excluding network and scheduling delay.

### Backend responsibilities

| Backend | Primary collection | Optional context enrichment |
|---|---|---|
| Claude Code | Assistant response usage and final result totals | Response-local usage and observed model capacity |
| Codex | `turn.completed.usage` | Exact-session rollout `token_count` records |
| Pi | Authoritative assistant `message_end` usage | Verified session artifacts and effective model metadata |
| Agy | Completed step usage and terminal result counters | Explicit context metadata when present |

Final result counters reconcile prior observations; they are not added again. A cumulative session counter requires a baseline from the same session and counter generation. Without that baseline, use verified invocation-local events or mark totals incomplete.

No separate Pi RPC process is permitted. The RPC statistics interface remains a rejected transport alternative, not a hidden dependency.

### Attribution

Keep observations separate by job, persisted attempt, backend session, and execution invocation. Session reconstruction and fresh-session recovery create distinct invocation identities, even within one attempt.

Aggregate consumption across observed attempts belonging to the same job ID. Exclude historical consumption merely loaded from a resumed session. Preserve per-attempt accounting across retry of that job ID. A newly submitted job begins separate accounting.

If any contributing invocation has unknown consumption, expose completeness as partial or unavailable. Do not silently label a known subtotal as a complete total.

### API compatibility

Add `telemetry` to metadata without removing failure, retry, routing, duration, or legacy usage fields. Keep old response shapes readable. Historical metadata without telemetry remains valid.

`Runtime.live_result_metadata` must preserve the new object. `job_wait` must return it for running and terminal responses without changing pagination semantics. Dashboard job details already serialize result metadata.

Keep telemetry payloads bounded. Never include raw provider events, prompts, tool arguments, session paths, or credentials. Do not persist message-level telemetry history in the metadata object.

## Errors and Edge Cases

- Duplicate response events update the same observation, not consumption twice.
- Cumulative streaming updates replace earlier snapshots.
- Counter decreases or session changes invalidate prior baselines.
- Compaction and model changes invalidate incompatible context snapshots.
- Missing capacity leaves remaining percentage unavailable.
- Unsupported or malformed telemetry preserves execution behavior.
- Cancellation, timeout, and failure retain observed partial consumption.
- Terminal writes do not overwrite newer telemetry with empty metadata.
- Late observations cannot mutate an already finalized invocation.
- Concurrent jobs cannot share collectors or baselines accidentally.
- Session collectors stop with the owning process and deadline.
- Collector failures remain bounded and non-sensitive.

## Migration

Retain SQLite schema version 15 and existing records. Extend the metadata JSON contract additively. Do not backfill unknown historical measurements.

Document that legacy counters remain backend-native. New normalized input totals include cache reads and writes once. Document unavailable backend capabilities and measured CLI versions.

## Testing

Use test-first implementation and independent phase review. Verify offline fixtures before optional live probes.

Cover multi-response jobs, duplicate events, streaming snapshots, cache accounting, resumed sessions, counter resets, attempts, recovery invocations, compaction, model switches, cancellation, timeout, and malformed payloads.

Test telemetry persistence after restart, transcript truncation, and pruning. Test running and terminal MCP metadata, response bounds, historical jobs, and dashboard navigation races.

Backend capability claims require captured evidence. Keep fixtures sanitized. Live probes require explicit execution-time authorization and configured credentials; missing prerequisites are not passing evidence.

## Risks and Open Questions

- Codex rollout schemas are internal and version-sensitive.
- Pi JSON mode may not expose effective model capacity.
- Agy headless capacity remains unverified.
- Provider counters differ in scope and cache semantics.
- Some failed requests report no measurable consumption.

These uncertainties do not authorize guessed values or transport replacement. Phase 3 records verified capabilities and leaves unsupported fields unavailable. A requirement for complete live metrics on every backend would require renewed design approval.
