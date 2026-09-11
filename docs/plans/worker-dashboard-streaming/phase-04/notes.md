<!-- ccg-shared-version: 10.5.0 -->

# Phase 4 — Decision Notes

## Task 1

### Decisions made
- Installed `@tanstack/react-virtual` in web workspace.
- Added test coverage in `useJobStream.test.jsx`.
- Covered initial replay and cursor pagination.
- Covered SSE invalidation notifications.
- Covered deduplication of replayed events.
- Covered EventSource reconnecting state.
- Covered fallback 5-second polling.
- Covered unmount cleanup and job switching.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Initial replay starts with cursor 0.

### Follow-ups for human
- none

### Test evidence
- RED: `npm --prefix web test -- --run src/hooks/useJobStream.test.jsx` failed with missing module.
- Root cause: `useJobStream.js` did not exist.

## Task 2

### Decisions made
- Added `getJobOutput` to `web/src/api.js`.
- Implemented `useJobStream` hook with cursor tracking.
- Invalidation events trigger drain to next cursor.
- EventSource closed on cleanup and job changes.
- Set active job token to drop stale responses.
- Implemented 5-second fallback poll interval.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- High-water mark triggers draining until empty batch.

### Follow-ups for human
- none

### Test evidence
- GREEN: `npm --prefix web test -- --run src/hooks/useJobStream.test.jsx` passed 8 tests.
- Root cause: not applicable.

## Task 3

### Decisions made
- Added reducer and component tests in `JobTranscript.test.jsx`.
- Covered attempt grouping and assistant text deltas.
- Covered tool lifecycle and terminal status display.
- Covered safe redaction of tool args and results.
- Covered truncation and error notice banners.
- Covered duplicate final result suppression in `JobDetails.test.jsx`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Tool arguments and results never render.

### Follow-ups for human
- none

### Test evidence
- RED: `npm --prefix web test -- --run src/components/JobTranscript.test.jsx src/components/JobDetails.test.jsx` failed with missing module.
- Root cause: `JobTranscript.jsx` did not exist.

## Task 4

### Decisions made
- Implemented `JobTranscript.jsx` with `@tanstack/react-virtual`.
- Added aria-live region for screen readers.
- Added scroll position tracking and auto-follow behavior.
- Displayed "New activity" button when scrolled away.
- Integrated `JobTranscript` into `JobDetails.jsx`.
- Suppressed duplicate result when transcript text matches.
- Retained authoritative result display when transcript is absent.
- Styled components in `web/src/styles/app.css`.
- Updated mock in `dashboard-flow.test.jsx`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Scroll threshold of 32 pixels indicates bottom attachment.

### Follow-ups for human
- none

### Test evidence
- GREEN: All 33 tests passed across 4 files.
- `npm --prefix web run build` succeeded cleanly.
- `git diff --check` passed cleanly.
- Root cause: not applicable.

## Review Findings Fix

### Decisions made
- Updated `reduceTranscriptEvents` for the durable public contract: `attempt.started`, `attempt.finished`, `assistant.message.started`, `assistant.text.delta`, `assistant.message.completed`, `tool.started`, and `tool.completed`.
- Extracted `data.tool` and `data.call_id` while strictly omitting tool arguments, results, or secrets.
- Decoupled `useJobStream` concurrency lock per active job ID and incremented fetch epoch counters.
- Aborted and discarded prior in-flight fetch responses upon job change or refresh.
- Wrapped back button locator in `dashboard-flow.test.jsx` with `findByRole` to await project job detail load.
- Added regressions in `useJobStream.test.jsx` and `JobTranscript.test.jsx`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Dotted durable contract is the canonical public representation.

### Follow-ups for human
- none

### Test evidence
- RED: `npm --prefix web test -- --run src/hooks/useJobStream.test.jsx src/components/JobTranscript.test.jsx` failed with 3 errors (unhandled attempt.finished, unhandled assistant message events, pending old fetch blocking new job).
- GREEN: `npm --prefix web test -- --run src/hooks/useJobStream.test.jsx src/components/JobTranscript.test.jsx src/components/JobDetails.test.jsx src/integration/dashboard-flow.test.jsx` passed all 36 tests.
- `npm --prefix web run build` passed cleanly.
- `git diff --check` passed cleanly.

## Hook Order Fix

### Decisions made
- Moved `useJobStream` and `useMemo` above all early returns in `JobDetails.jsx`.
- Ensured `useJobStream` performs no network or EventSource calls when `job` is absent.
- Added regression tests in `JobDetails.test.jsx` for loading-to-job transition and absent-job network suppression.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Hooks must be called unconditionally on every render in identical order.

### Follow-ups for human
- none

### Test evidence
- GREEN: `npm --prefix web test -- --run src/hooks/useJobStream.test.jsx src/components/JobTranscript.test.jsx src/components/JobDetails.test.jsx src/integration/dashboard-flow.test.jsx` passed all 38 tests with zero React static-flag errors.
- `npm --prefix web run build` passed cleanly.
- `git diff --check` passed cleanly.
- Root cause: `JobDetails` had early returns before calling `useJobStream` and `useMemo`, altering hook execution order on loading-to-job transitions.

## Result Equality and Bounded Measurement Fix

### Decisions made
- Removed trimming from `isDuplicateFinalText` in `JobDetails.jsx:73-76` to enforce exact original-string equality.
- Added a regression test in `JobDetails.test.jsx` proving whitespace differences retain authoritative result output.
- Replaced the unbounded flat-items fallback in `JobTranscript.jsx:91-100,155-160` with a bounded initial window of at most 20 items.
- Preserved virtual container height as `${virtualizer.getTotalSize()}px` across measured and unmeasured states.
- Added a large-transcript regression test in `JobTranscript.test.jsx` asserting DOM cards/headers remain bounded to at most 20 nodes.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Exact original-string equality prevents accidental suppression when trailing whitespaces or newlines differ.
- An initial bounded window of 20 items provides sufficient content for layout without DOM bloat.

### Follow-ups for human
- none

### Test evidence
- RED: `npm --prefix web test -- --run src/components/JobDetails.test.jsx src/components/JobTranscript.test.jsx` failed with 2 errors (unexpected suppression on whitespace difference; 300 nodes rendered instead of <= 20).
- GREEN: `npm --prefix web test -- --run src/hooks/useJobStream.test.jsx src/components/JobTranscript.test.jsx src/components/JobDetails.test.jsx src/integration/dashboard-flow.test.jsx` passed all 40 tests.
- `npm --prefix web run build` passed cleanly.
- `git diff --check` passed cleanly.
