<!-- ccg-shared-version: 10.2.0 -->

# Phase 2 — Decision Notes

## Task 1

### Decisions made
- Dashboard responses use explicit Pydantic models for errors, bootstrap data, overview, jobs, and context mutations.

### Spec deviations
- none

### Tradeoffs accepted
- Error envelopes retain a stable top-level `error` message while also carrying machine-readable recovery metadata.

### Assumptions
- The existing runtime and project view models remain the source of truth for operational fields.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Dashboard tests initially failed because the dashboard state and routes did not exist; model and route scaffolding brought the focused dashboard tests to green.

## Task 2

### Decisions made
- Dashboard project reads resolve against the cached global catalog and preserve global/project declaration boundaries for source attribution.
- Project profile payloads separately expose declared, inherited, effective, and source values.

### Spec deviations
- none

### Tradeoffs accepted
- Task-guide responses expose source path metadata alongside the existing guide payload.

### Assumptions
- Project configuration files may be read for project resolution, but dashboard reads must never trigger a global reload attempt.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Overview, project resolution, profile source, target, settings, and task-guide route coverage passed in the focused dashboard/runtime suite.

## Task 3

### Decisions made
- Stored execution plans are parsed and projected through an explicit safe allow-list; prompts, instructions, arguments, backend profiles, reasoning, and unknown future fields are omitted.

### Spec deviations
- none

### Tradeoffs accepted
- Invalid historical execution-plan JSON produces an empty safe plan rather than exposing the raw payload.

### Assumptions
- Target model and operational policy fields are safe dashboard metadata; provider credentials are not present in the existing target model.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Job detail regression confirmed revision visibility and omission of prompts, system prompts, backend profiles, arguments, and instruction content.

## Task 4

### Decisions made
- Dashboard state is owned by OpenMCP application state and is reset on startup failure, shutdown, and failed runtime initialization.
- Mutations require loopback client and Host addresses, matching same-origin Origin, and a cryptographically random CSRF token checked with `compare_digest`.
- Context compare-and-set is synchronous and transactional in SQLite, treating absent and empty values equivalently.

### Spec deviations
- none

### Tradeoffs accepted
- The same mutation endpoint supports replacement and clearing by accepting an empty instruction; DELETE is also supported for clients that prefer it.

### Assumptions
- Loopback IP addresses are the supported administrative boundary; forwarded headers are untrusted and ignored.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Authorization, bootstrap no-store, successful mutation, and HTTP 409 stale-value tests passed; focused Phase 2 suite passed with 65 tests.
