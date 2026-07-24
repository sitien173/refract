<!-- ccg-shared-version: 7.4.0 -->

# Phase 3 — Decision Notes

<!--
Append one `## Task <M>` block per task. Keep earlier task blocks.
Empty sub-sections use `- none`.
-->

## Task 1

### Decisions made
- Rebuild projects and jobs with explicit v6 tables.
- Validate foreign keys and database integrity before committing migration.

### Spec deviations
- none

### Tradeoffs accepted
- Migration uses named temporary v6 tables during the transaction.

### Assumptions
- Existing support tables can retain their foreign-key table names across rebuilds.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Fresh and v5 migration tests initially found schema version 5 and missing migration. After the rebuild implementation, migration tests passed.

## Task 2

### Decisions made
- Convert older legacy schemas directly into v6.
- Preserve prompt, result text, target, attempts, errors, events, contexts, turns, and health data.

### Spec deviations
- none

### Tradeoffs accepted
- Historical Git values are intentionally discarded during normalization.

### Assumptions
- Legacy job prompts are available in the historical inputs payload.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Legacy normalization failed with the old column count and Git result expectations. The rewritten direct-v6 conversion passed legacy migration tests.

## Task 3

### Decisions made
- Remove Git fields from database methods, SQL readers, and retry state updates.

### Spec deviations
- none

### Tradeoffs accepted
- Existing legacy fixtures retain old physical schemas for migration coverage.

### Assumptions
- Phase 3 callers are the only current database API consumers.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Execution startup initially failed against the old project API. Updated methods and readers passed the backend test suite.

## Task 4

### Decisions made
- Remove Git fields from public Pydantic models.
- Remove compatibility placeholders from runtime and execution callers.

### Spec deviations
- none

### Tradeoffs accepted
- No model aliases preserve the removed fields.

### Assumptions
- Dashboard and MCP payloads derive their shape from these models.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Server model-contract coverage initially found `base_commit`. Updated models and callers passed all Python tests.

## Task 5

### Decisions made
- Add v5 preservation, rollback, exact-schema, no-op reopen, and dashboard payload tests.

### Spec deviations
- none

### Tradeoffs accepted
- Legacy test fixtures continue to mention removed columns only as source database setup.

### Assumptions
- Integrity-check failures are sufficient to verify transactional rollback.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Migration and dashboard contract tests passed. Python suite passed 137 tests, with 2 live tests deselected.

## Task 6

### Decisions made
- Remove Git fields from dashboard types, views, fixtures, and inspector content.
- Remove obsolete project cleanliness and commit presentation helpers.

### Spec deviations
- none

### Tradeoffs accepted
- Existing status badge health states remain; project cleanliness states were removed.

### Assumptions
- Dashboard API responses remain structurally compatible after model trimming.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Inspector and Projects tests initially expected removed commit fields. Dashboard tests passed after updating views and fixtures: 145 tests.

## Task 7

### Decisions made
- Rebuild committed dashboard assets through the web build.
- Update README schema and directory-execution documentation.

### Spec deviations
- none

### Tradeoffs accepted
- The generated asset filename changes with the rebuilt bundle hash.

### Assumptions
- The committed static bundle must match the current web source.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `npm --prefix web test -- --run` passed 145 tests and `npm --prefix web run build` completed successfully. All required searches returned no Git contract fields.
