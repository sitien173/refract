# Phase 2: Build the conversation timeline

## Objective

Redesign the Live transcript into a chronological conversation timeline. Stream assistant text in place. Keep tool calls inline and collapsed by default. Expanded calls show raw input and output.

Improve readability, accessibility, narrow-layout behavior, follow-live scrolling, and long-transcript performance. Preserve all existing stream connection and terminal behavior.

## Scope

Modify only:

- `web/src/hooks/useJobStream.js`
- `web/src/hooks/useJobStream.test.jsx`
- `web/src/components/JobTranscript.jsx`
- `web/src/components/JobTranscript.test.jsx`
- `web/src/components/JobDetails.test.jsx`
- `web/src/styles/app.css`

Do not modify backend code or generated dashboard assets.

## Reducer contract

Consume optional normalized fields:

```text
tool.started.data.input
tool.completed.data.output
```

Build one tool entity for each lifecycle. Preserve property presence:

```js
{
  type: 'tool_call',
  entity_id,
  tool_name,
  status,
  input,
  output,
}
```

Only include `input` or `output` when the source property exists. Valid values include null, false, zero, empty string, empty arrays, and empty objects.

Merge completion by explicit normalized `entity_id`. Never attach an explicitly identified completion to another tool. Preserve legacy event aliases and historical status-only rows.

## Tasks

### 1. Reducer tests

Add failing coverage for:

- assistant, tool, assistant chronological ordering;
- interleaved tools with distinct identifiers;
- raw object input and raw string output;
- authoritative completion matching;
- absent values versus present null;
- failed status with available output;
- historical rows without payloads;
- legacy event aliases.

Keep existing terminal transition and final-fetch tests unchanged.

### 2. Disclosure and formatting tests

Add failing coverage for:

- native `details` and `summary`;
- collapsed-by-default state;
- tool name and status in summary;
- keyboard activation through native semantics;
- separate Input and Output sections;
- exact `Input not available` and `Output not available` text;
- indented JSON objects and arrays;
- multiline text preserving line breaks;
- valid falsy values remaining visible;
- normal interface typography for assistant prose;
- monospace typography for IDs and raw payloads;
- narrow-layout containment;
- existing polite connection live region remaining status-only.

Render payloads as inert React text. Never use HTML interpretation.

### 3. Measured virtualization

Add failing tests covering assistant growth, disclosure opening and closing, non-overlapping later rows, responsive reflow, and bounded DOM behavior.

Keep `estimateSize` only as an initial estimate. Connect every rendered row to `@tanstack/react-virtual` measurement. Remeasure after:

- streamed assistant text changes;
- disclosure toggles;
- width changes affecting wrapping.

Ensure measured spacing matches CSS. Do not solve overlap by rendering every row.

### 4. Follow-live behavior

Add failing tests for:

- initial following;
- assistant growth while following;
- new entities while following;
- manual upward scrolling disabling following;
- no viewport movement while disabled;
- persistent `Jump to live` while disabled;
- Jump to live restoring following;
- subsequent content following again;
- programmatic measurement not disabling following.

Track following intent separately from bottom proximity. Detect relevant wheel, touch, keyboard, and manual scroll paths. Preserve keyboard scrolling. Prefer virtualizer live-edge scrolling over stale `scrollHeight` assumptions.

## Constraints

Preserve `useJobStream` network behavior:

- initial durable fetch;
- SSE cursor notifications;
- reconnect fallback polling;
- one final drain on false-to-true terminal transition;
- stale-request supersession;
- EventSource closure;
- no extra initially-terminal fetch;
- no terminal polling.

Also preserve:

- event-ID chronological ordering;
- final-result deduplication;
- truncation and unavailable states;
- historical transcript compatibility;
- bounded DOM virtualization.

Use property existence, not truthiness. Do not re-redact approved payloads. Do not derive completion or result state from tool content. Use native disclosure elements. Do not flood live regions with assistant deltas.

On narrow layouts, summaries may wrap. IDs and payloads must remain contained. Jump to live must not obscure disclosure content.

## Acceptance criteria

- Assistant and tools render chronologically.
- Each tool remains one lifecycle row.
- Completion cannot attach to another tool.
- Tools are collapsed by default.
- Native disclosure works by pointer and keyboard.
- Expanded rows show raw input and output.
- Structured payloads display indented JSON.
- Text payloads preserve line breaks.
- Missing details show explicit unavailable text.
- Falsy JSON values remain visible.
- Assistant prose uses readable interface typography.
- Long and expanded rows never overlap later rows.
- Responsive reflow preserves measured layout.
- Large transcripts retain bounded mounted rows.
- Assistant growth and new rows follow while enabled.
- Manual upward scrolling disables following.
- Disabled following never steals viewport position.
- Jump to live stays available while disabled.
- Jump to live restores following.
- Existing stream and terminal semantics remain unchanged.
- Narrow layouts remain readable and contained.

## Verification

```bash
npm --prefix web test -- --run web/src/hooks/useJobStream.test.jsx
npm --prefix web test -- --run web/src/components/JobTranscript.test.jsx
npm --prefix web test -- --run web/src/hooks/useJobStream.test.jsx web/src/components/JobTranscript.test.jsx web/src/components/JobDetails.test.jsx
npm --prefix web test
npm --prefix web test -- --run web/src/components/JobTranscript.test.jsx -t "tool|follow|scroll|virtual|height|disclosure"
git diff --check
```

Confirm only the six scoped frontend files changed.

## Commit

```text
feat(dashboard): improve live transcript timeline
```
