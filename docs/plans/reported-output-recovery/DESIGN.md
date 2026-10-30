# Reported Output Recovery Design

**Status:** Confirmed 2026-10-30
**Consultation:** One unusable consultation; one usable consultation supported explicit recovery. Its durable eligibility and migration proposals were rejected for the approved acknowledgement-only scope.

## Purpose

Expose explicit recovery when completed output is unusable. Preserve the original job's execution record.

Observed job `f4c6aace-a609-4ac1-a9d4-5ed284f53df3` returned:

> I'm having a hard time fulfilling your request. Can I help you with something else instead?

Its state was `succeeded`. Its failure and retry fields were null. The user supplied output report `1625` for this job.

## Users and Success Criteria

The Coordinator reports unusable output after reading every terminal page. A report acknowledgement supplies a live fallback token. The Coordinator inspects partial effects before explicitly submitting recovery.

Success means:

- Only `succeeded` plus report category `output` exposes fallback.
- Available fallback returns `retryable: true` and `next_target`.
- Unavailable fallback returns `retryable: false` and `next_target: null`.
- Other report categories and job states expose no fallback.
- Duplicate reports recompute availability without duplicating retained events.
- Recovery creates a new job, using a fresh session.
- Original state, result, attempts, sessions, and health remain unchanged.

## Constraints and Non-Goals

Keep report arguments and existing acknowledgement fields unchanged. Add a top-level `retry` object to successful report acknowledgements. Its fields are `retryable` and `next_target`.

Keep `job_wait`, stored result metadata, and `job_retry` unchanged. Existing failure recovery through `job_wait` remains available independently.

Exclude automatic execution, output classification, database migrations, durable eligibility markers, dashboard changes, and new token formats. Reporting remains a client observation, not verified execution failure.

## Chosen Approach

Compute recovery metadata in the report response only. Reuse existing live target selection and opaque tokens.

Rejected alternatives:

- Marking the original job failed would rewrite execution history.
- Automatic detection and fallback would risk unintended replay.
- Persistent eligibility would require unnecessary storage and retention decisions.
- Exposing recovery through `job_wait` would expand the approved contract.

## Architecture and Data Flow

1. `Runtime.report_error` records or deduplicates the report first.
2. It reads the current job after recording succeeds.
3. For `succeeded` plus `output`, reuse `_next_target_token`.
4. Compute `retryable` from whether that token exists.
5. For other combinations, return `false` and `null`.
6. `server.job_report_error` includes the `retry` object.
7. The Coordinator inspects workspace changes and external effects.
8. It explicitly calls `job_submit` with the returned token.

The new submission preserves the original project, workflow, profile, and intended task. It uses `fresh_session: true`. The Coordinator retains the original job ID for diagnostic correlation.

Example eligible acknowledgement shape:

```json
{
  "report": {
    "id": "<report-id>",
    "job_id": "<original-job-id>",
    "category": "output",
    "created_at": "<timestamp>"
  },
  "duplicate": false,
  "retry": {
    "retryable": true,
    "next_target": "<opaque-token>"
  }
}
```

## Errors and Edge Cases

Preserve existing validation, redaction, key conflicts, and unknown-job errors. Report creation must not enqueue execution or change target health.

A duplicate report returns its retained report ID. Compute its token from current configuration and health. Persist neither the token nor recovery eligibility.

No eligible target means `false` and `null`. This is not proof that the task succeeded. The Coordinator stops and requests routing guidance.

Configuration may change after acknowledgement. Preserve existing token validation during submission. Refresh through an identical report request when its deduplication event remains retained. Never silently drop `next_target` and restart the primary target.

`job_wait` continues to suppress retry metadata for succeeded jobs. Older reports can obtain recovery metadata by repeating their original report request. After retention removes events, existing deduplication limits still apply. A later report may receive a new report ID.

A new job can repeat partial side effects. Fresh sessions prevent session reuse, not duplicate writes. Recovery requires explicit reconciliation before submission.

## Migration

No schema or data migration. Existing clients may ignore the additive `retry` field. Clients enforcing exact response keys must update their acknowledgement expectations.

## Testing

Use deterministic fake targets and temporary databases. First reproduce the missing acknowledgement token with a failing test.

Cover eligible and ineligible state/category combinations; healthy, unavailable, and exhausted targets; duplicate freshness after health and configuration changes; stale token rejection; and explicit new-job submission with a fresh session.

Snapshot execution fields, stored result metadata, sessions, and target health around reporting. Verify only the diagnostic event changes. Confirm reports alone never start another execution. Preserve `job_wait` and `job_retry` behavior.

Test actual MCP acknowledgement serialization, compactness, redaction, duplicate IDs, and unchanged request arguments. Add plugin contract coverage for acknowledgement-based recovery instructions.

## Risks and Open Questions

- Tokens are routing hints, not replay authorization.
- Availability can change between reporting and submission.
- Strict clients need the additive response contract update.
- Original tasks can have partial local or external effects.
- No unresolved architecture questions remain within this scope.

Consultation references: `d62bba8e-4a88-40c6-928c-96d64404fb41` returned generic error text under `succeeded` and was reported as `1637`; `67ab273c-4fe1-492c-bf52-bfbf4944a10f` supplied usable design advice. Repository code, rather than consultation claims, determines implementation details.
