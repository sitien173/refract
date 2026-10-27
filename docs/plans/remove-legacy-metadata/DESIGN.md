# Job Result Metadata Design

**Status:** Confirmed 2026-10-27
**Consultation:** Job `fb2aa28f-2f67-45f1-85d1-194bf00fa78e` returned an error apology without advice. Design continued from inspected code.

## Purpose

Remove legacy semantics from `result.metadata` completely. Replace the untyped dictionary with one concise, typed contract. Migrate historical records before removing runtime compatibility.

The user approved historical migration, grouped metadata, and this design. The confirmed slug is `remove-legacy-metadata`.

## Users and Success Criteria

Coordinators consume MCP results. Operators inspect dashboard job details.

- Every public metadata response follows the same grouped contract.
- Legacy counters and aliases disappear from current responses.
- Context occupancy stays separate from job consumption.
- Valid historical normalized telemetry survives migration unchanged.
- Unverifiable historical measurements remain unavailable.
- Retry, routing, cancellation, pagination, and accounting behavior survive.
- Internal accumulator fields never appear in public metadata.

## Constraints and Non-Goals

Retain the `result.metadata` envelope and snake_case identifiers. Keep the existing seven normalized measurement names and provenance fields. Add no dependencies, new telemetry collectors, model capacity tables, or live probes.

Do not remove unrelated legacy routes, configuration aliases, or backend event parsers. Provider-native payload keys may remain inside collectors when necessary for normalized measurements. They must not survive as an alternative result-usage contract.

This design supersedes the additive compatibility requirement in `docs/plans/worker-job-telemetry/DESIGN.md` for this branch. Leave that historical plan unchanged. The unexecuted `shared-retry-policies` plan is separate work, not part of this cleanup.

## Chosen Approach

Use strict typed metadata grouped by responsibility.

- Reject counter-only deletion: it retains an inconsistent untyped contract.
- Reject removing the metadata envelope: it expands the API break unnecessarily.

### Public structure

```text
metadata
  execution
    model: string | null
    duration_ms: non-negative integer | null
  failure: null | object
    kind: existing failure-kind enum
  retry
    retryable: boolean | null
    next_target: string | null
  telemetry
    completeness: complete | partial | unavailable
    context_remaining_percent: Measurement
    context_window_size: Measurement
    context_used_tokens: Measurement
    total_input_tokens: Measurement
    total_output_tokens: Measurement
    cache_read_tokens: Measurement
    cache_write_tokens: Measurement
```

`Measurement` retains `value`, `source`, `quality`, and `observed_at`. Token values are non-negative integers or null. Percentages are finite numbers from zero through 100 or null. Booleans are not numbers. Unknown values have unavailable quality. Historical observation timestamps are never replaced with migration time.

Public metadata and nested objects reject unknown fields. Do not silently coerce invalid types. Absence of telemetry produces an explicit unavailable snapshot. Queued and running jobs have no terminal failure. Successful jobs have `failure: null` and no retry token. Preserve existing retryability behavior, including context-overflow handling, rather than redefining it as simple token presence.

Remove the flat fields `model_name`, `context_window_max`, `context_window_used`, `input_tokens`, `output_tokens`, `cached_input_tokens`, `duration_ms`, `failure_kind`, `retryable`, and `next_target`. Their supported operational replacements live only in the groups above. Public telemetry excludes its former `version`, `attribution`, and `completed_attempts` bookkeeping fields.

## Architecture and Data Flow

Use typed execution, failure, retry, telemetry, and metadata models. Define a single explicit public serializer. Public metadata must not be an unrestricted dictionary.

Keep the existing accumulator's attribution, reconciliation, retry rollover, and completed-attempt accounting internal. Persist its bounded snapshot separately from public metadata, in a dedicated `jobs.telemetry_state_json` column. The database schema version owns that storage boundary. Do not introduce a second public telemetry representation.

Backend collectors retain provider-native parsing solely to produce normalized observations. Replace the legacy `BackendResult.usage` and `DriverResult.usage` bridge with explicit model identity where needed. Retain all current normalized telemetry events and non-streaming fallback coverage.

Execution writes grouped operational facts and normalized telemetry. Persistence updates the public snapshot and internal accounting state transactionally. Terminal writes retain newer valid measurements. Retrying the same job preserves its accounting while clearing attempt-local failure, timing, and routing state as appropriate.

Runtime synthesizes `retry.next_target` using current configuration and target health. Never persist opaque retry tokens. MCP and dashboard detail responses use the same public projection. Preserve MCP pagination, pending questions, and response-size bounds.

Update coordinator instructions to read `metadata.failure.kind`, `metadata.retry.next_target`, and `metadata.retry.retryable`. The submit argument remains `next_target`; only the result path changes.

## Errors and Edge Cases

- Invalid producer metadata fails validation at its boundary.
- Collector failures still cannot change execution outcomes.
- Migration errors identify the job and field, not raw payloads.
- Malformed JSON, invalid recognized values, or unsupported telemetry versions abort migration.
- Do not invent missing historical timestamps or provenance.
- Late telemetry cannot modify a terminal job.
- Retry accounting cannot count earlier attempts twice.
- Unknown capacity keeps remaining percentage unavailable.
- Active historical jobs follow existing restart recovery behavior.
- Migration runs before startup recovery or scheduler activity.

## Migration

Introduce database schema 16, upgrading only schema 15. Fresh databases initialize directly to 16. Older and newer unsupported schemas remain rejected before writes. Nonempty unversioned or incomplete databases remain errors.

Stop the daemon and back up the complete state directory before upgrade. Do not migrate the operator's real database during implementation or verification. Old binaries cannot read schema 16; downgrade requires restoring the backup.

Validate all source rows before mutation. Within one transaction, add internal telemetry storage, rewrite historical metadata, and update `PRAGMA user_version` last. Avoid transaction-breaking schema helpers. Roll back all schema and row changes on failure. Reopening schema 16 must not reapply migration.

Migration rules:

1. Accept empty metadata as an unavailable canonical snapshot.
2. Map valid model, duration, and failure facts into their groups.
3. Preserve existing normalized measurements and provenance without recomputation.
4. Move telemetry attribution and completed-attempt state into internal storage.
5. Remove legacy counters without reinterpreting backend-native meanings.
6. Discard stored retry tokens; derive current routing at read time.
7. Preserve job IDs, text, errors, states, timestamps, plans, sessions, history, and streams.

Known obsolete fields are removed intentionally. Unknown extension fields are not copied into the strict contract. An invalid recognized field aborts rather than disappearing silently. Missing measurements stay unavailable; missing timestamps on valued historical measurements require repair before migration.

## Testing

Use test-first changes and independent phase review. Test exact serialized key sets, strict nested types, null semantics, enums, and measurement constraints.

Use synthetic schema-15 databases. Cover empty metadata, legacy-only records, mixed counters and normalized telemetry, retries, every job state, malformed records, unsupported versions, rollback, fresh schema creation, repeated reopen, and unchanged non-metadata data.

Cover live updates, terminal merges, restart, retry rollover, cancellation, failure, transcript truncation, pending questions, and bounded Unicode pagination. Verify all four collectors still produce normalized telemetry without the legacy usage bridge.

Dashboard fixtures must use canonical metadata. Verify available, partial, unavailable, running, and terminal telemetry. Rebuild packaged dashboard assets from source. Update server documentation and plugin contract tests together.

## Risks and Open Questions

This is an intentional breaking result contract. Server, plugin, and packaged dashboard must be deployed together. External clients must update their result paths.

Historical backend-native counters cannot be normalized reliably. Their deletion is intentional; backup preserves the original database.

Schema migration reintroduces an upgrade path into code that currently rejects every non-15 schema. Preserve its unsupported-database and connection-cleanup safeguards.

No unresolved product decision remains. Implementation details must satisfy the strict public boundary and preserve accounting. Any required expansion beyond these constraints needs approval.
