# Target Context Window Design

**Status:** Confirmed 2026-10-29
**Consultation:** Refract consult job `33ece1a4-2635-46ac-961b-1181f7acb84b` advised on precedence, persistence, and lifecycle risks. User selected configured-capacity override rather than the consultation's provider-capacity preference.

## Purpose

Configure target capacity and calculate qualified context telemetry automatically.

## Users and Success Criteria

Operators configure optional `contextWindow` under global `[[targets]]`.
The dashboard supports editing and clearing this setting.
Telemetry displays capacity and remaining percentage without provider capacity.
Provider snapshots determine usage before cumulative job estimates.
Historical jobs retain their execution-time telemetry after configuration changes.

## Constraints and Non-Goals

- Preserve existing telemetry field names and measurement metadata.
- Keep `docs/plans/worker-job-telemetry/` untouched.
- No model-capacity lookup, dependencies, or backend CLI flags.
- No project-local capacity overrides or live backend probes.
- No changes to token accounting or scheduler concurrency.
- Capacity configuration alone must not reset reusable worker sessions.

## Chosen Approach

Configured capacity overrides provider capacity.
Provider context usage takes precedence over cumulative estimates.
Rejected: always using totals, because repeated inputs overcount occupancy.
Rejected: provider capacity overriding configuration, by user decision.

## Architecture and Data Flow

### Configuration

Public TOML and target-editor payload key: `contextWindow`.
Internal target field: `context_window: int | None`.
Accept only positive integers; reject booleans and coercible strings.
Omission means no configured override.
Editor updates preserve the setting when omitted.
Explicit null clears it; TOML serialization removes the key.

Capture capacity in immutable execution-plan target data.
Old execution plans without capacity continue to load.
Keep capacity outside session/process identity calculation.

### Resolution

Resolve capacity from configured target capacity, then provider capacity.
With neither, capacity and calculated remaining percentage are unavailable.
Configured measurements use source `target_config` and quality `reported`.
Add `target_config` to the existing source allowlist.
Reuse `Measurement` rather than introducing parallel telemetry fields.

Resolve usage from a valid provider context snapshot first.
Otherwise, use `total_input_tokens + total_output_tokens`.
Require both totals to be known; zero remains valid.
Missing totals never silently become zero.
Fallback usage uses source `derived` and quality `estimated`.
Do not add cache counters separately to usage.

Calculate:

```text
remaining_percent = round(clamp(100 * (1 - used / capacity), 0, 100), 2)
```

Estimated usage produces estimated remaining percentage.
Otherwise, calculated remaining percentage has quality `derived`.
When configured capacity overrides provider capacity, recompute remaining.
Never retain a provider percentage calculated against another capacity.
Without an override, preserve valid existing provider-percentage behavior.

### Lifecycle and Persistence

Bind configured capacity when execution selects a target.
Preserve cumulative consumption accounting across retries and invocations.
Invalidate stale provider snapshots at existing lifecycle boundaries.
Rebind capacity when execution switches targets.
Compaction invalidates provider context, not configured capacity.
After invalidation, the same qualified fallback rule applies.
Cumulative estimates may include earlier attempts and pre-compaction tokens.

Persist resolved measurements through existing telemetry serialization and merges.
Preserve configured capacity even before consumption arrives.
Live events, final results, cancellation, and failures share resolution rules.
Historical reads never consult current target capacity.

### Dashboard

Add an optional labeled numeric capacity field.
Blank input explicitly clears the configured override.
Reuse existing measurement quality and source badges.
Explain that estimates use cumulative job input plus output.
The dashboard renders server measurements without duplicating calculations.

## Errors and Edge Cases

- Reject zero, negative, floating-point, boolean, and string capacities.
- Capacity alone does not imply zero usage or 100% remaining.
- Known zero input and output yield 100% remaining.
- Usage beyond capacity yields 0% remaining, not negative values.
- Keep raw usage unchanged when it exceeds capacity.
- Reject late context events from finalized invocations as today.
- Target switches must not retain another target's capacity.
- Missing historical configuration fields remain compatible.

## Migration

No database schema migration is planned.
Existing telemetry JSON fields carry resolved measurements.
Absent configuration preserves provider-capacity behavior.
Fallback estimates also work with provider capacity when configuration is absent.
Do not backfill or reinterpret historical jobs.

## Testing

Cover configuration validation, mutation, inspection, and execution-plan round trips.
Cover override precedence, missing totals, zero, and percentage bounds.
Cover provider snapshots replacing estimates and later invalidation.
Cover retries, target switches, restart persistence, and terminal paths.
Cover editor clearing, validation, and qualified telemetry rendering.
Run existing server tests, dashboard tests, and an isolated build.

## Risks and Open Questions

Cumulative consumption is not actual context occupancy.
Estimates remain explicitly labeled, including after retries and compaction.
Provider-only percentages cannot be translated without known usage.
An override with unknown usage therefore leaves remaining unavailable.
No unresolved product decisions remain under the approved design.
