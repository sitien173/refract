# Live Transcript UX Design

## Purpose

Make job execution readable while it runs. The transcript should resemble a
conversation timeline. Assistant messages and tool activity must appear in their
actual event order.

## Approved behavior

- Stream assistant text into the active message.
- Follow the newest content while at the live edge.
- Stop following after manual upward scrolling.
- Show a persistent `Jump to live` control.
- Resume following after activating that control.
- Render tool calls inline between assistant messages.
- Keep tool calls collapsed by default.
- Expand tool calls with native disclosure controls.
- Show raw tool input and raw tool output.
- Format structured payloads as readable JSON.
- Format command output as preformatted text.
- Show unavailable details explicitly.
- Preserve keyboard access and polite status announcements.

## Timeline structure

Each target attempt forms one transcript group. Its header shows the attempt
number, target, backend, and status. The group contains chronological entities:

1. Assistant message blocks.
2. Tool call disclosure rows.
3. Stream notices.
4. Truncation notices.

Assistant prose uses the normal interface font. Commands, identifiers, JSON,
and tool output use monospace styling.

## Tool details

`tool.started` events carry the provider's available tool name and raw input.
`tool.completed` events carry status and raw output. The reducer merges both
records into one tool entity by `entity_id`.

Provider event shapes differ. Adapters should retain the payload available from
the provider without inventing missing values. The UI displays `Input not
available` or `Output not available` when a provider omits either value.

Raw payload display is an explicit local-operator decision. Tool inputs and
outputs may contain prompts, credentials, file contents, or other sensitive
material. Existing transcript event and byte quotas remain authoritative. Large
raw payloads can therefore truncate a transcript earlier.

Historical jobs cannot recover details discarded during their execution.

## Live scrolling

The scroll container tracks whether the operator remains near its live edge.
New assistant deltas and new timeline entities scroll to the newest measured
content only while live following remains enabled. Manual upward scrolling
disables following. `Jump to live` restores it.

Virtualized rows must use measured heights. Fixed row estimates are only initial
estimates. Dynamic assistant messages and expanded tool rows must not overlap.

## Error states

- Connection failures retain already loaded transcript content.
- Reconnecting status remains visible without replacing content.
- Failed tools show their provider status and available output.
- Stream truncation keeps the final truncation notice visible.
- Malformed structured tool details fall back to readable text.

## Accessibility

- Tool details use native `details` and `summary` semantics.
- The transcript remains keyboard-scrollable.
- Connection changes use the existing polite live region.
- Streaming deltas do not flood assistive announcements.
- `Jump to live` has an explicit accessible name.

## Verification

- Backend fixtures cover raw inputs and outputs per backend.
- Persistence and dashboard API tests retain raw payloads.
- Reducer tests merge tool lifecycle details.
- Component tests cover disclosure behavior.
- Scroll tests cover live following and manual pause.
- Virtualization tests cover variable-height rows.
- The production dashboard bundle matches frontend source.
- Playwright verifies the referenced job details page.
