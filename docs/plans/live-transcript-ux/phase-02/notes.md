<!-- ccg-shared-version: 10.6.0 -->

# Phase 2 — Decision Notes

## Task 1

### Decisions made
- Used `data.input` on `tool.started` and `data.output` on `tool.completed` while preserving property existence (`hasOwnProperty`) to distinguish absent from explicit null or falsy values.
- Authoritatively matched tool completions via `entity_id` lookup in an entity map rather than attaching to the latest active item.
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
- RED -> GREEN: `src/hooks/useJobStream.test.jsx` (21 tests pass)
- Root cause (bugfix only): n/a

## Task 2

### Decisions made
- Rendered tool calls using native `details` and `summary` elements with collapsed-by-default behavior.
- Implemented lazy rendering for the tool body container, mounting payload sections only upon expansion.
- Rendered payloads as inert text via `formatPayload` with 2-space indented JSON or multiline text preserving line breaks without HTML interpretation.
- Displayed exact "Input not available" and "Output not available" captions when properties are omitted.
- Used monospace fonts for IDs and payloads while keeping standard UI typography for assistant prose.

### Spec deviations
- none

### Tradeoffs accepted
- Handled both `details` toggle events and `summary` click events to support native browser and jsdom testing environments.

### Assumptions
- Collapsed details items do not require child payload DOM nodes.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `src/components/JobTranscript.test.jsx` disclosure tests pass (25 tests pass)
- Root cause (bugfix only): n/a

## Task 3

### Decisions made
- Connected each rendered row via TanStack Virtual `virtualizer.measureElement` ref callback.
- Configured `gap: 8` and `useFlushSync: false` on `useVirtualizer` to match CSS card gap and prevent React 19 warnings.
- Triggered remeasurement via a resize listener and disclosure toggle handler.
- Preserved bounded DOM row counts for large transcripts using measured virtualization.

### Spec deviations
- none

### Tradeoffs accepted
- Maintained initial size estimation (`estimateSize: () => 80`) before dynamic measurement executes.

### Assumptions
- Parent container provides scroll container with `overflow-y: auto`.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `src/components/JobTranscript.test.jsx` virtualization tests pass
- Root cause (bugfix only): n/a

## Task 4

### Decisions made
- Initialized in follow-live mode and scrolled to live edge on mount and content updates while following is active.
- Tracked user scroll intent explicitly using wheel, touch, and keyboard upward navigation to distinguish manual user scrolling from programmatic measurement scrolling.
- Displayed persistent "Jump to live" button whenever following is disabled.
- Restored following immediately upon clicking "Jump to live".

### Spec deviations
- none

### Tradeoffs accepted
- Follow-live scrolling targets the virtualizer live edge using `virtualizer.scrollToIndex(count - 1)` rather than raw `scrollHeight`.

### Assumptions
- User scrolling upwards indicates intent to inspect historical lines and pause auto-scroll.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `src/components/JobTranscript.test.jsx` follow-live tests pass
- Root cause (bugfix only): n/a
