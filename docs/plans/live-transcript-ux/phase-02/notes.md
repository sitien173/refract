<!-- ccg-shared-version: 10.6.0 -->

# Phase 2 — Decision Notes

## Task 1

### Decisions made
- Used `data.input` on `tool.started` and `data.output` on `tool.completed` while preserving property existence (`hasOwnProperty`) to distinguish absent from explicit null or falsy values.
- Authoritatively matched tool completions via explicit normalized `entity_id` without matching against other tools' `call_id` to prevent ID collisions.
- Preserved legacy fallback matching by `call_id` or last running tool only when no explicit `entity_id` exists.
- Preserved separate streaming assistant message blocks when interleaved with tool executions to maintain chronological timeline order.

### Spec deviations
- none

### Tradeoffs accepted
- Preserved historical legacy aliases (`tool.start`, `tool.end`, `delta`, `done`, `message`, `attempt`) alongside canonical contract event types.

### Assumptions
- `entity_id` is unique per tool lifecycle across an attempt.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `src/hooks/useJobStream.test.jsx` (23 tests pass)
- Root cause (bugfix only): Explicit completions previously matched both entity_id and call_id, which caused collisions when another tool possessed a matching call_id.

## Task 2

### Decisions made
- Rendered tool calls using native `details` and `summary` elements with collapsed-by-default behavior.
- Supported native keyboard activation for disclosure toggle via Enter and Space keys on summary.
- Implemented lazy rendering for the tool body container, mounting payload sections only upon expansion.
- Rendered payloads as inert text via `formatPayload` with 2-space indented JSON or multiline text preserving line breaks without HTML interpretation.
- Displayed exact "Input not available" and "Output not available" captions when properties are omitted.
- Used monospace fonts for IDs and payloads while keeping standard UI typography for assistant prose.

### Spec deviations
- none

### Tradeoffs accepted
- Handled `summary` click, Enter/Space keydown, and `details` native toggle events to support both native browser and jsdom testing environments.

### Assumptions
- Collapsed details items do not require child payload DOM nodes.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `src/components/JobTranscript.test.jsx` disclosure tests pass (28 tests pass)
- Root cause (bugfix only): Native disclosure keyboard navigation was previously untested.

## Task 3

### Decisions made
- Directly remeasured affected disclosure rows via `virtualizer.measureElement` in a `useLayoutEffect` after open/close, replacing global `measure()` cache clearing to preserve cached sizes of stable unmounted rows.
- Directly remeasured all mounted row elements upon responsive reflow (window resize).
- Added `initialRect` and `observeElementRect` with fallback dimensions to ensure virtualizer calculates virtual items and positions in both browser and jsdom environments.
- Maintained bounded virtualization for large transcripts while preserving row height measurements and position updates.

### Spec deviations
- none

### Tradeoffs accepted
- Maintained initial size estimation (`estimateSize: () => 72`) before dynamic measurement executes.

### Assumptions
- Parent container provides scroll container with `overflow-y: auto`.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `src/components/JobTranscript.test.jsx` virtualization tests pass, asserting changed row heights, later-row non-overlap, disclosure open/close translateY positions, responsive reflow, and bounded DOM.
- Root cause (bugfix only): Previous global `measure()` calls cleared the size cache without synchronously remeasuring rows.

## Task 4

### Decisions made
- Consulted `isProgrammaticScrollRef` in `handleScroll` so that programmatic scroll events do not disable follow-live auto-scrolling.
- Bound `isProgrammaticScrollRef` to programmatic scroll execution via `try ... finally` block.
- Scrolled to live edge on mount and content updates while following is active.
- Tracked user scroll intent explicitly using wheel, touch, keyboard upward navigation, and manual scroll offset detection.
- Displayed persistent "Jump to live" button whenever following is disabled, restoring following on click.

### Spec deviations
- none

### Tradeoffs accepted
- Follow-live scrolling targets the virtualizer live edge using `virtualizer.scrollToEnd` and `parentRef.current.scrollTo`.

### Assumptions
- User scrolling upwards indicates intent to inspect historical lines and pause auto-scroll.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `src/components/JobTranscript.test.jsx` follow-live tests pass, asserting mount follow calls, real dispatched programmatic scroll event follow preservation, manual upward scroll follow disabling, and jump-to-live restoration.
- Root cause (bugfix only): `isProgrammaticScrollRef` was defined but never read in `handleScroll`, and mount `scrollTo` calls were not asserted.
