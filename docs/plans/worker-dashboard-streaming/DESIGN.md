# Worker Dashboard Streaming Design

## Status

Confirmed and verified on 2026-09-11.

## Purpose

Stream backend worker messages into the dashboard job detail while each job is
running. The dashboard must retain committed transcript content across reconnects,
page reloads, target retries, and daemon restarts.

The first version supports Claude, Codex, Pi, and Agy. It displays assistant text
and safe tool lifecycle activity. It excludes prompts, hidden reasoning, tool
arguments, tool results, provider diagnostics, and subagent messages.

## Current state

OpenMCP already contains the first streaming primitive. The generator in
`src/openmcp/backends/_shell.py` yields subprocess output line by line. Each
provider adapter currently collects those lines before returning one final
`BackendResult`.

`src/openmcp/execution.py` records job and target lifecycle events. The durable
`events` table stores those events, but the dashboard endpoint exposes only event
identifiers, timestamps, and kinds. The dashboard has no server-push route.

`web/src/screens/JobDetail.jsx` polls job details every five seconds.
`web/src/components/JobDetails.jsx` displays only the final result text.

The current provider transports already expose structured modes:

- Claude supports `--output-format stream-json` and
  `--include-partial-messages`.
- Codex supports `codex exec --json`.
- Pi supports `--mode json`.
- Agy supports `--output-format stream-json`.

The SQLite connection uses default same-thread checking. Provider adapters run
through `asyncio.to_thread()`. Provider worker threads therefore must never write
to SQLite directly.

## Reference flow

`/home/ngosi/projects/claude-code-history-viewer` uses filesystem notifications
to create a live session experience.

Its WebUI flow is:

```text
session file change
  -> bounded broadcast notification
  -> SSE invalidation event
  -> EventSource callback
  -> debounced durable session reload
  -> scroll-aware transcript update
```

Relevant reference files include:

- `src-tauri/src/server/mod.rs`
- `src-tauri/src/server/state.rs`
- `src/hooks/useFileWatcher.ts`
- `src/store/slices/watcherSlice.ts`
- `src/components/MessageViewer/MessageViewer.tsx`

The reference project does not stream model tokens through SSE. SSE only signals
that durable content changed. OpenMCP will preserve that separation while using
cursor-based delta retrieval instead of full session reloads.

## Decisions

- Persist normalized stream events before notifying browsers.
- Use REST cursor retrieval as the authoritative replay mechanism.
- Use SSE only for lossy, coalesced cursor invalidation.
- Keep existing lifecycle events separate from transcript events.
- Keep `job.result.text` as the authoritative final result.
- Preserve failed attempt transcripts with attempt metadata.
- Normalize provider output before persistence.
- Apply bounded backpressure between worker threads and asyncio.
- Render a provider-neutral, virtualized transcript.
- Continue existing job metadata polling.
- Defer subagent streaming.

## Rejected alternatives

### Full event payloads through replayable SSE

This duplicates replay, pagination, redaction, and backpressure behavior between
REST and SSE. Slow SSE consumers also become part of durable delivery. The
cursor REST endpoint already provides one reliable replay path.

### Ephemeral SSE payloads with periodic snapshots

This creates ordering and deduplication races between live payloads and recovered
snapshots. Reliable recovery still requires durable sequence identifiers, which
converges on the selected design.

### Reusing the lifecycle `events` table

Lifecycle event payloads were not designed as a dashboard transcript contract.
Combining both concerns would couple retention and redaction rules. A separate
stream table keeps the exposure boundary explicit.

## Architecture

```text
provider subprocess
  -> provider adapter
  -> normalized BackendStreamEvent
  -> bounded worker-thread bridge
  -> event-loop StreamRecorder
  -> SQLite job_stream_events
       -> REST cursor replay
       -> committed-cursor notification hub
            -> SSE invalidation
                 -> React transcript viewer
```

The architecture enforces one invariant:

> Content becomes dashboard-visible only after durable commit.

### Provider adapter

Each adapter performs three tasks:

1. Run its provider CLI.
2. Normalize allowlisted native events.
3. Produce the existing final `BackendResult` independently.

Adapters do not know job identifiers, database methods, HTTP routes, retention
rules, or frontend components.

### Worker-thread bridge

`DriverRegistry.execute()` owns one bounded bridge per target attempt. The
provider adapter receives a synchronous emitter callback. The callback runs on
the provider worker thread and submits events through
`asyncio.run_coroutine_threadsafe(queue.put(event), loop)`.

The queue has 256 slots. A full queue blocks the producer callback. That slows
the stdout reader and allows operating-system pipe backpressure to reach the
provider subprocess.

The bridge uses a producer-finished sentinel. Its `finally` path always closes
the producer side and drains accepted events. Cancellation and provider failure
must not leave the consumer waiting.

### Stream recorder

The `StreamRecorder` runs on the daemon event-loop thread. It adds job, target,
backend, and attempt metadata. It coalesces adjacent text deltas for the same
message entity.

The recorder flushes when one condition occurs:

- 50 events accumulate.
- 64 KiB accumulates.
- 100 milliseconds elapse.
- The target attempt ends.

Text coalescing targets 1 to 4 KiB chunks and 50 to 100 millisecond windows. A
single persisted text event cannot exceed 8 KiB.

The recorder publishes the committed high-water cursor only after the database
transaction succeeds.

### Runtime notification hub

The runtime owns an in-memory job stream hub. Dashboard SSE handlers subscribe
by job identifier.

Each subscriber queue holds one cursor. When another committed cursor arrives,
the hub replaces any pending cursor with the latest value. Missing intermediate
notifications is safe because REST retrieves every durable event after the
client cursor.

The hub stores no transcript content.

## Durable stream model

Increment the database schema version from 10 to 11.

```sql
CREATE TABLE job_stream_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    target_id TEXT NOT NULL,
    backend TEXT NOT NULL,
    kind TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    parent_entity_id TEXT NOT NULL,
    data_json TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
);

CREATE INDEX job_stream_events_job_idx
ON job_stream_events(job_id, id);
```

`id` is the replay cursor. It is globally monotonic and always queried within one
job.

No backfill occurs. Historical jobs continue showing their final result and have
no retained transcript.

### Public event contract

```json
{
  "id": 1842,
  "version": 1,
  "created_at": "2026-09-11T04:40:00Z",
  "attempt": 2,
  "target_id": "claude-primary",
  "backend": "claude",
  "kind": "assistant.text.delta",
  "entity_id": "message-7",
  "parent_entity_id": "",
  "data": {
    "text": "Checking the configuration..."
  }
}
```

Provider adapters generate synthetic entity identifiers. Raw provider
identifiers are not part of the public contract.

### Event kinds

The first version supports:

- `attempt.started`
- `attempt.finished`
- `assistant.message.started`
- `assistant.text.delta`
- `assistant.message.completed`
- `tool.started`
- `tool.completed`
- `stream.notice`
- `stream.truncated`

Tool events expose only a synthetic activity identifier, tool name, completion
status, and safe duration metadata. They never expose arguments or results.

### Storage limits

Initial limits are:

- 8 MiB per job.
- 20,000 events per job.
- 8 KiB per text event.
- Seven-day retention for terminal stream history.

Active job streams are never pruned. When either job limit is reached, the
recorder persists one `stream.truncated` event and stops accepting transcript
content. The authoritative final result remains unaffected.

These values are initial defaults. Load testing must validate them before they
become configurable policy.

## Provider normalization

### Claude

Change print mode from single-result JSON to:

```text
-p
--output-format stream-json
--include-partial-messages
```

The adapter maps assistant display text and safe tool lifecycle events. It keeps
the terminal `result` event as the source for final text and session identity.
It ignores thinking blocks, system content, input echoes, raw envelopes, and
unknown event types.

The first version does not pass `--forward-subagent-text`.

### Codex

Keep `codex exec --json`. Normalize known agent message and tool activity events.
Continue using `--output-last-message` as the authoritative final result source.
When the CLI supplies only completed agent messages, emit completed message
content without manufacturing token deltas.

### Pi

Keep `--mode json`. Normalize known assistant message and tool lifecycle events.
Preserve the current `message_end` and `agent_end` final extraction behavior.
Drop unknown or arbitrary message structures.

### Agy

Change Agy print mode to `--output-format stream-json`. Normalize structured
assistant and tool events. Preserve conversation identification and the current
continuation loop.

Agy continuations remain one OpenMCP target attempt. Each continuation can create
new assistant message entities. Raw standard error and log diagnostics remain
excluded.

### Provider capability

The driver checks structured-output capability before starting a prompt. It
caches the result for each resolved executable. A provider version without the
required structured mode uses the existing final-only execution path.

The driver must not discover unsupported flags by retrying a changed invocation
after prompt execution starts. Such retries could duplicate tool side effects.

### Characterization fixtures

Implementation begins with sanitized provider fixtures. These fixtures define
supported native mappings and preserve final result extraction. Production code
never stores raw provider envelopes.

## Attempt and completion ordering

Each transcript event carries the OpenMCP target attempt number. Failed attempt
content remains visible and is separated from later target attempts.

Partial content from failed attempts never becomes `job.result.text`.

The terminal sequence is:

1. Accept the provider's final normalized event.
2. Close the producer side.
3. Drain the bounded queue.
4. Commit the final stream batch.
5. Record `attempt.finished`.
6. Process the final `BackendResult`.
7. Store the authoritative job result.
8. Mark the job terminal.
9. Publish the existing MCP resource update.

Cancellation and failure follow the same drain-before-terminal rule.

## Dashboard API

### Cursor replay endpoint

```http
GET /dashboard/api/jobs/{job_id}/output?after=1842&limit=200
```

```json
{
  "events": [],
  "cursor": 1868,
  "has_more": false,
  "retained_from": 1201,
  "stream_status": "active"
}
```

The endpoint validates job ownership through the existing dashboard runtime.
It orders events by ascending identifier. `limit` is bounded server-side.

Valid stream statuses are:

- `unavailable`
- `active`
- `complete`
- `truncated`
- `failed`

Historical jobs with no stream events return `unavailable`. Non-terminal jobs
return `active`. Terminal jobs with retained events return `complete` unless a
truncation or persistence failure occurred.

### SSE invalidation endpoint

```http
GET /dashboard/api/jobs/{job_id}/output/updates
```

```text
event: output-updated
id: 1868
data: {"cursor":1868}
```

The endpoint sends the current high-water cursor immediately. It then sends
coalesced cursor notifications after committed batches. It emits keepalive
comments every 20 seconds.

SSE carries no assistant or tool payload. Browser correctness does not depend on
`Last-Event-ID`.

### Reconnect sequence

1. Fetch retained events from cursor zero.
2. Open the SSE endpoint.
3. Receive the current high-water cursor.
4. Fetch all missing REST pages.
5. Repeat after each higher cursor notification.

The initial SSE cursor closes the race between the initial REST response and
subscription establishment.

## Dashboard transcript

Add a `useJobStream(jobId)` hook. It owns:

- Durable event pages.
- The highest applied cursor.
- The highest notified cursor.
- EventSource connection state.
- In-flight delta request deduplication.
- Job-switch cancellation.
- Transcript entity reduction.
- Auto-follow state.

The existing five-second job polling remains. It continues owning job metadata
and terminal-state refresh.

### Transcript rendering

Add a provider-neutral transcript above the final result section. Group content
by target attempt. Render assistant messages as growing message cards. Render
safe tool activity as nested status cards.

Use `@tanstack/react-virtual`, following the reference viewer, to bound DOM size.
This is a new dashboard dependency.

The transcript retains provider and target badges. It does not reproduce
provider-native payload layouts.

### Result compatibility

Historical jobs keep the current final result panel. Streamed jobs show the
transcript first. Errors remain below the transcript.

When reconstructed final text exactly matches `job.result.text`, the dashboard
does not repeat it. When the transcript is unavailable, truncated, or different,
the authoritative final result remains visible.

### Scroll behavior

When the viewport is near the bottom, new transcript content keeps the view
following live output.

When the user scrolls upward, new events continue loading without moving the
viewport. The UI shows a keyboard-accessible `New activity` control. Activating
it returns to the live edge and resumes auto-follow.

The dashboard announces connection and completion changes through polite live
regions. It does not announce every text delta.

## Failure handling

- EventSource transport errors enter a reconnecting state.
- EventSource uses browser automatic reconnection.
- Five-second REST delta polling continues while SSE is unavailable.
- Failed delta requests retain previously loaded transcript content.
- Unknown provider events are dropped and logged internally.
- Queue closure drains accepted events before attempt completion.
- Runtime restart preserves committed transcript content.
- Unexpected stream persistence failure does not fail the worker job.
- A safe lifecycle event records stream persistence failure when possible.
- Final job results remain authoritative after stream failure.

No transcript content is published live after the recorder declines to persist
it.

## Security boundary

Provider adapters normalize before persistence. The stream table must never
contain:

- Original prompts.
- Effective prompts containing history.
- System prompts.
- Hidden reasoning or chain-of-thought.
- Provider request or response envelopes.
- Target arguments.
- Environment variables.
- Authentication material.
- Tool arguments.
- Tool results.
- Shell commands.
- File contents.
- Raw standard output diagnostics.
- Standard error diagnostics.
- Subagent text.

The existing dashboard execution-plan allowlist remains unchanged. Existing MCP
resource notifications remain URI-only.

## Implementation surfaces

Expected backend changes:

- `src/openmcp/backends/_shell.py`
- `src/openmcp/backends/claude.py`
- `src/openmcp/backends/codex.py`
- `src/openmcp/backends/pi.py`
- `src/openmcp/backends/agy.py`
- `src/openmcp/drivers.py`
- `src/openmcp/execution.py`
- `src/openmcp/database.py`
- `src/openmcp/runtime.py`
- `src/openmcp/dashboard.py`
- `src/openmcp/models.py`

Expected frontend changes:

- `web/src/api.js`
- `web/src/screens/JobDetail.jsx`
- `web/src/components/JobDetails.jsx`
- New transcript components.
- New stream query and reducer hooks.
- Dashboard styles and tests.

## Delivery order

1. Add the stream schema and database cursor methods.
2. Add the normalized stream event model.
3. Add the bounded bridge and stream recorder.
4. Add provider characterization fixtures.
5. Add provider normalization incrementally.
6. Add REST cursor replay.
7. Add SSE cursor invalidation.
8. Add the transcript reducer and hook.
9. Add virtualized transcript components.
10. Add scroll, reconnect, and fallback behavior.
11. Verify complete job flows across every backend.

## Testing

### Database and recorder

- Migrate schema version 10 without data loss.
- Return exact events after a supplied cursor.
- Preserve ordering across transaction batches.
- Enforce event and byte limits.
- Emit exactly one truncation marker.
- Prune only terminal stream history.
- Reconstruct retained content after database reopen.

### Threading and execution

- Emit adapter events from a real worker thread.
- Assert all SQLite writes use the owning thread.
- Block producers when the queue reaches capacity.
- Drain accepted events before terminal state.
- Close producer and consumer paths after cancellation.
- Preserve attempt boundaries across target retries.
- Keep final result extraction unchanged.

### Provider security

Sanitized Claude, Codex, Pi, and Agy fixtures must prove that adapters exclude:

- Prompts.
- Reasoning.
- Tool arguments.
- Tool results.
- Standard error.
- Unknown native events.
- Planted secret values.

### Dashboard API

- Page by cursor without duplication.
- Return bounded limits.
- Send the current cursor upon SSE connection.
- Close the initial subscription race.
- Coalesce slow subscriber notifications.
- Recover after disconnect using REST replay.
- Preserve historical job compatibility.

### Frontend

- Merge adjacent assistant deltas.
- Update tool cards by entity identifier.
- Separate target attempts.
- Ignore duplicate event identifiers.
- Fetch all missing cursor pages.
- Recover after EventSource reconnect.
- Continue REST fallback polling.
- Cancel stale job requests.
- Preserve viewport while reading history.
- Resume auto-follow explicitly.
- Render retained terminal transcripts.
- Fall back to final results for old jobs.

### End-to-end acceptance

- Running jobs show live assistant text.
- Running jobs show safe tool status updates.
- Claude, Codex, Pi, and Agy produce transcripts.
- Reloading reconstructs the same committed transcript.
- Disconnecting loses no committed content.
- Failed attempts remain separated from successful attempts.
- Stream limits never affect final job results.
- Existing MCP job contracts remain unchanged.
- Existing final result behavior remains unchanged.

## Deferred scope

- Subagent message streaming.
- Tool arguments and tool results.
- Hidden reasoning display.
- Full payload replay through SSE.
- Global SSE multiplexing across jobs.
- Cross-process notification infrastructure.
- Transcript search.
- Persistent browser cursors.
- Provider-native transcript layouts.
- User-configurable retention controls.
