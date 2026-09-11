## Original User Request

Turn the confirmed worker dashboard streaming design into an implementation plan,
then execute every phase through completion.

## Phase

Render a virtualized live transcript in dashboard job details.

## Tasks

- task-1: Add `@tanstack/react-virtual` and RED tests for durable replay,
  cursor paging, notifications, reconnect, polling fallback, cancellation, and
  job changes.
- task-2: Implement `getJobOutput` and `useJobStream` with cursor-based REST
  replay and EventSource invalidation.
- task-3: Add RED reducer and component tests for attempt groups, assistant
  deltas, safe tool status cards, duplicates, and final-result suppression.
- task-4: Implement the virtualized transcript and job-details integration,
  including connection status, accessible updates, and scroll-aware live follow.

## Context

Phase 3 provides `GET /dashboard/api/jobs/{job_id}/output` for bounded cursor
pages and `.../output/updates` for cursor-only SSE notifications. Transcript
replay is durable. SSE is lossy invalidation and must trigger REST page drains.
The current five-second job metadata poll remains. Provider-neutral events
include attempts, assistant message lifecycle and text deltas, safe tool
lifecycle, notices, and truncation. Historical jobs have no stream events and
must retain the existing result display. Never render tool arguments, results,
reasoning, prompts, or provider-native data.

## Files

- `web/package.json`
- `web/package-lock.json`
- `web/src/api.js`
- `web/src/hooks/useJobStream.js`
- `web/src/hooks/useJobStream.test.jsx`
- `web/src/components/JobTranscript.jsx`
- `web/src/components/JobTranscript.test.jsx`
- `web/src/components/JobDetails.jsx`
- `web/src/components/JobDetails.test.jsx`
- `web/src/screens/JobDetail.jsx`
- `web/src/styles/app.css`
- `web/src/integration/dashboard-flow.test.jsx`

## Done When

- Running jobs update without five-second visual latency.
- Reload reconstructs identical committed transcript entities.
- SSE reconnect recovery loses no committed content.
- Users reading history are not forced to scroll.
- Transcript DOM size remains bounded.
- Historical jobs retain the existing final-result experience.
- Tool arguments, results, and reasoning never render.
- `npm --prefix web test -- --run src/hooks/useJobStream.test.jsx src/components/JobTranscript.test.jsx src/components/JobDetails.test.jsx src/integration/dashboard-flow.test.jsx`
- `npm --prefix web run build`
- `git diff --check`

## Rules

Follow the supplied worker contract. Stay within scope. Maintain this phase's
`notes.md` and `journal.md`. Use RED, GREEN, and REFACTOR for every behavior.
Close EventSource connections on unmount and job changes. Prevent stale fetches
from modifying a new job. Dedupe cursor events before reduction. Do not add
backend routes or change the five-second metadata polling cadence.

## Response Format

Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
