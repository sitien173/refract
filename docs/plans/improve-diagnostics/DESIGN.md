# Job Diagnostics Design

**Status:** Confirmed 2026-10-27
**Consultation:** Attempted through Refract consult job `261c8514-ed8f-4b86-b0ea-ba44165b9564`. The job reported `succeeded` but returned only `Sorry, something went wrong. Please try your request again.` No usable design advice was returned. Continue with the user-confirmed design.

## Purpose

Let MCP clients report unexpected job results for investigation. Preserve execution status while exposing diagnostic suspicion separately.

## Users and Success Criteria

- MCP clients report protocol and output problems separately.
- Operators inspect durable reports through dashboard diagnostics and job details.
- Reports persist as job events and produce correlated logs.
- Reported jobs display suspect badges without changing execution status.
- Reporting never triggers retries, rerouting, cancellation, or target-health changes.
- Duplicate submissions return the existing report ID.

## Constraints and Non-Goals

Reuse job events, existing logging, and dashboard access controls. Keep existing MCP response contracts unchanged. Clients detect unexpected results; the tool only receives their reports. Client guidance cannot guarantee every client reports problems.

Exclude raw transcripts, attachments, report resolution workflows, and automatic recovery. Reports are client observations, not verified failures.

## Chosen Approach

Reuse job events as report storage. Derive suspect flags from retained diagnostic report events. Add a dedicated dashboard diagnostics view with job links, filtering, and suspect badges.

Rejected alternative: logs alone lack the requested durable job-linked dashboard workflow.

Rejected alternative: dedicated report storage adds schema complexity without a confirmed need.

## Architecture and Data Flow

1. A client detects an unexpected result and calls `job_report_error`.
2. The tool accepts a job ID, category, expected summary, observed summary, and client-generated report key.
3. Categories are `protocol` and `output`.
4. Validate required nonempty bounded summaries and the referenced job.
5. Redact sensitive content before storing or logging summaries.
6. Persist a diagnostic job event with a stable report ID.
7. Emit correlated logs referencing the report ID and job.
8. Return the report ID after successful persistence.
9. Dashboard reads expose reports and derive suspect flags separately from execution status.

Protocol reports cover malformed responses, missing fields, and broken pagination. Output reports cover empty output, missing required ERP, and unmet requirements. Missing ERP is reportable only when the requested workflow requires ERP.

Update client guidance with detection criteria and the reporting contract. Clients must distinguish incomplete pagination from missing output.

## Errors and Edge Cases

- Reject unknown or purged jobs and invalid categories.
- Reject empty or oversized summaries.
- Use the client-generated report key for retry deduplication.
- Duplicate submissions return the existing report ID without duplicate events.
- Keep suspect badges while diagnostic report events remain retained.
- Apply existing job retention to report events.
- Reuse dashboard access controls and render summaries as untrusted text.
- Reports must not alter execution state or automatically recover jobs.

## Migration

Add the MCP tool without changing existing response contracts. Preserve historical job events and execution states. Jobs without diagnostic reports remain unflagged. Reuse the events table rather than introduce a dedicated reports table.

## Testing

Cover input validation, redaction before persistence, durable event creation, deduplication, and retention. Verify unchanged execution state and no automatic retries or rerouting. Cover MCP schema registration and existing response compatibility. Test dashboard filters, suspect badges, report links, and access controls. Update client reporting guidance and its contract tests.

## Risks and Open Questions

- Client observations can be incorrect; label them accordingly.
- Redaction cannot identify every possible secret; discourage sensitive submissions.
- Invalid pagination handling can create false output reports.
- Reports disappear with existing job retention; no independent archive is requested.
- Exact field limits, duplicate-key conflict behavior, query pagination, and index requirements must be specified during planning against existing code.
- The user approved the complete design before implementation planning.
