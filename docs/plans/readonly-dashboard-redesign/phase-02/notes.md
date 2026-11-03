<!-- refract-shared-version: 2.4.0 -->

# Phase 2 — Decision Notes

## Task 1

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: `cd server/web && npm test` -> `FAIL src/api.test.js > API client > fetches overview with GET /dashboard/api/overview (AssertionError: expected "spy" to be called with arguments: [ '/dashboard/api/overview', …(1) ]; Number of calls: 0) and FAIL src/hooks/usePolling.test.jsx > usePolling and data hooks > polls fetcher periodically and updates data (AssertionError: expected "spy" to be called 1 times, but got 0 times; 11 failed | 1 passed (12))`
  - GREEN: `cd server/web && npm test` -> `Test Files 2 passed (2), Tests 12 passed (12)`
- Root cause (bugfix only): none

## Task 2

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: `cd server/web && npm test` -> `FAIL src/components/TranscriptViewer.test.jsx > TranscriptViewer component > falls back to result text when stream_status is unavailable (Unable to find an element with the text: Completed fallback output text) and FAIL src/hooks/useTranscriptStream.test.jsx > useTranscriptStream & EventSource lifecycle > maintains at most one EventSource for active non-terminal job and closes on unmount (expected +0 to be 1); 13 failed | 13 passed (26)`
  - GREEN: `cd server/web && npm test` -> `Test Files 4 passed (4), Tests 26 passed (26)`
- Root cause (bugfix only): none

## Task 3

### Decisions made
- none

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: `cd server/web && npm test` -> `FAIL src/components/JobInspector.test.jsx > JobInspector component > renders inspector header with id, workflow, profile, target, timestamps, attempts, and telemetry (Unable to find an element with the text: job-inspect-1) and FAIL src/components/JobFeed.test.jsx > JobFeed component > renders ACTIVE and RECENT sections with more_recent note (Unable to find an element with the text: /ACTIVE/); 14 failed | 32 passed (46)`
  - GREEN: `cd server/web && npm test` -> `Test Files 10 passed (10), Tests 46 passed (46)`
- Root cause (bugfix only): none

## FIX 1

### Decisions made
- Coalesced concurrent drain requests via pending drain flag.
- Invoked immediate REST drain upon EventSource connection or reconnection.
- Deferred terminal EventSource close until pending drain completes.
- Extracted tool name from tool field.
- Preserved tool failure completion status.
- Rendered failure card when error is present.
- Read retry attributes from result metadata retry object.
- Replaced non-existent stacked announcement class with standard announcement.
- Rebuilt tabs using documented TDS indicator structure.
- Implemented roving tabindex shifting focus on arrow keys.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: `cd server/web && npm test` -> `FAIL src/hooks/useTranscriptStream.test.jsx (3 tests failed), FAIL src/components/TranscriptViewer.test.jsx (1 test failed), FAIL src/components/ConfigInvalidBanner.test.jsx (1 test failed), FAIL src/components/JobInspector.test.jsx (3 tests failed), FAIL src/components/JobFeed.test.jsx (2 tests failed); 10 failed | 43 passed (53)`
  - GREEN: `cd server/web && npm test` -> `Test Files 10 passed (10), Tests 53 passed (53)`
- Root cause (bugfix only):
  - Finding 1: drain dropped concurrent updates when fetch was active.
  - Finding 2: connect lacked immediate drain from last cursor.
  - Finding 3: terminal transition closed stream before active drain finished.
  - Finding 4: tool stream parsing missed tool field and failure status.
  - Finding 5: failure card ignored error without failure metadata.
  - Finding 6: stacked announcement was an invented class.
  - Finding 7: feed arrow keys changed highlight without focus.

## FIX 2

### Decisions made
- Keyed active and pending drain promises by job id.
- Ignored in-flight stale drains when user switches jobs.
- Added non-advancing cursor check stopping loop and setting error.
- Made coalesced drain callers return follow-up drain promise.
- Clamped roving focused index in JobFeed to valid bounds.
- Defaulted roving index to first item when list shrinks.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: `cd server/web && npm test` -> `FAIL src/components/JobFeed.test.jsx > JobFeed component > clamps roving focused index when job list changes or selected job disappears (expected tabindex="0", received "-1"), FAIL src/hooks/useTranscriptStream.test.jsx > fetches and renders new job initial page when switching jobs while previous job request is in flight (AssertionError: expected "fetchJobOutput" to be called with arguments: [ 'job-2', ... ]), and non-advancing cursor test hung in infinite loop`
  - GREEN: `cd server/web && npm test` -> `Test Files 10 passed (10), Tests 57 passed (57)`
- Root cause (bugfix only):
  - Item A: shared fetch ref dropped initial drain on switch.
  - Item B: drain loop looped infinitely when cursor stalled.
  - Item C: coalesced drain returned void instead of chained promise.
  - Item D: focused index exceeded bounds when jobs list shortened.

## FIX 3

### Decisions made
- Captured switch id when creating pending drain object.
- Returned early from stale pending continuation on switch mismatch.
- Cleared pending drain reference only when matching current pending object.
- Guarded active drain assignment with switch id match in executeDrain.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: `cd server/web && npm test` -> `FAIL src/hooks/useTranscriptStream.test.jsx > useTranscriptStream & EventSource lifecycle > does not trigger concurrent fetches or overwrite activeDrain when stale pending drain resolves after switching A to B to A (AssertionError: expected 2 to be 1)`
  - GREEN: `cd server/web && npm test` -> `Test Files 10 passed (10), Tests 58 passed (58)`
- Root cause (bugfix only):
  - Stale pending continuation checked active job id without switch id.
  - Quick A-to-B-to-A switch allowed stale session continuation to run.
  - Stale continuation triggered executeDrain and overwrote newer active drain.
