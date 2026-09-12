# Live Transcript Filters Design

## Purpose

Let operators focus the Live transcript by participant and activity type without
changing durable stream ordering, pagination, retention, or follow-live behavior.

## Approved filter model

The transcript has two checkbox groups:

- Role: `User`, `Assistant`.
- Content: `Text`, `Thinking`, `Tool Call`, `Command`.

Selections use OR within each group and AND across groups. An entry appears only
when its role and content type are both enabled.

Default filters enable `User`, `Assistant`, `Text`, `Tool Call`, and `Command`.
`Thinking` starts disabled and requires deliberate opt-in.

## Transcript categories

| Role | Content | Source |
| --- | --- | --- |
| User | Text | Stored `jobs.prompt` only |
| Assistant | Text | Existing assistant message events |
| Assistant | Thinking | Explicit provider reasoning-summary events only |
| Assistant | Tool Call | Non-shell tool lifecycle events |
| Assistant | Command | Shell and terminal tool lifecycle events |

Attempt headers, stream notices, and truncation notices are structural. They
remain visible when relevant and never receive a fabricated role or content type.

## User prompt boundary

The User entry uses the stored submitted `jobs.prompt` value already returned by
the Job Detail API. It must never use:

- The expanded prompt produced by `TargetExecutor._with_history`.
- Target or system prompts.
- Environment contents.
- Provider prompt echoes.
- Diagnostics or provider internals.

The User entry appears once for the job, not once per retry. Historically
unavailable transcripts remain unavailable and do not become synthetic User-only
transcripts.

## Thinking boundary

Thinking means an explicit provider-supplied reasoning summary. It never means:

- Hidden chain-of-thought.
- Generic `thinking` or `reasoning` objects.
- Raw reasoning tokens or deltas.
- Diagnostics, traces, or arbitrary provider fields.

No current provider fixture proves a safe reasoning-summary event. The Thinking
filter may therefore contain no entries initially. Future mappings require a
sanitized provider fixture proving explicit summary semantics.

## Tool and command classification

Existing `tool.started` and `tool.completed` events remain the lifecycle
contract. New starts may add:

```json
{
  "activity": "tool_call"
}
```

or:

```json
{
  "activity": "command"
}
```

Classification uses explicit provider event types first. Otherwise it uses
exact, provider-specific, test-backed shell tool names. It never inspects input,
output, command text, or tool-name substrings.

Historical events without `activity` remain Tool Call. The dashboard must not
retroactively guess their category.

Raw local input and output remain unchanged. Missing values stay absent. Present
`null`, `false`, `0`, empty strings, arrays, and objects remain valid captured
values.

## Stream contract

A future explicit reasoning summary uses:

```text
assistant.reasoning_summary.delta
```

with:

```json
{
  "text": "provider supplied summary"
}
```

The recorder applies the existing UTF-8 text splitting and same-kind entity
coalescing rules. Existing event, byte, batch, retention, and truncation limits
remain unchanged.

No database migration is required. Cursor pagination and SSE continue carrying
the complete normalized stream. Filtering remains client-side.

## Filtering and virtualization

The reducer assigns semantic metadata to content entries:

- `role`: `user` or `assistant`.
- `contentType`: `text`, `thinking`, `tool_call`, or `command`.

Filtering occurs before transcript rows reach the virtualizer. Attempt headers
render only when their attempt retains visible content or operational notices.
Mounted rows remain bounded. Expanded Tool Call and Command disclosures continue
using measured dynamic heights.

Filter changes do not reset follow-live state. Visible streaming Text or Thinking
may follow only while following is already active. Filtering never moves the
viewport after explicit upward navigation.

## Empty and unavailable states

When the stream exists but no content matches, show:

`No transcript entries match the current filters.`

A keyboard-accessible `Reset filters` action restores defaults.

This state differs from `Transcript unavailable`. Historical payloads, Thinking,
and Command metadata that were not captured cannot be reconstructed.

## Accessibility

- Use native checkboxes grouped by `fieldset` and `legend`.
- Keep every label visible and keyboard accessible.
- Do not announce each streaming token.
- Retain the existing polite connection-status live region.
- Use native disclosures for Tool Call and Command details.
- Label disclosures as `Tool` or `Command` consistently.

## Verification

- Backend fixtures prove conservative Command classification.
- Negative tests keep raw thinking and generic reasoning excluded.
- Recorder tests cover reasoning-summary splitting and coalescing.
- Reducer tests cover every role and content type.
- Component tests cover defaults, combinations, reset, and empty states.
- Follow-live tests prove filter changes preserve manual pause.
- Virtualization tests prove filtered and expanded rows remain bounded.
- Browser verification covers desktop and narrow layouts.
- Packaged assets must match frontend source.
