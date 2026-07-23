## Original User Request

Execute the `react-monitor-console` folder plan. Complete only Phase 2.

## Phase

Deliver the typed dashboard data layer and resilient polling.

## Tasks

- task-1: Define exact TypeScript response types.
- task-2: Add typed fetch wrappers for every read endpoint.
- task-3: Add TanStack Query hooks and polling policies.
- task-4: Wire the top-bar connection state and live counts.

## Context

Existing read endpoints:

- `/dashboard/api/status`
- `/dashboard/api/projects`
- `/dashboard/api/projects/{id}/jobs`
- `/dashboard/api/jobs/{id}`
- `/dashboard/api/jobs/{id}/events`
- `/dashboard/api/targets`
- `/dashboard/api/profiles`

Mirror the current Python payloads exactly. Important fields include:

- Status: `status`, `workers`, `active_jobs`, `queued_jobs`
- Project: `id`, `alias`, `root`, `head_commit`, `clean`, `created_at`
- Job: identifiers, workflow/profile/state, context/base/target, attempts,
  timestamps, and nested `result.text`, `result.commit`, `result.error`
- Job event: `id`, `created_at`, `kind`, object-valued `data`
- Target: `id`, `model`, `capabilities`, `max_concurrency`, `active`,
  `healthy`, `circuit_open_until`
- Profiles: `default`, `available`

Use TanStack Query v5. Create one stable `QueryClient`. General resources poll
near three seconds. Open job detail and events poll near two seconds. Use unique
keys containing resource identifiers. Pause intervals while
`document.hidden`. Refetch when visibility returns. Avoid custom timers.

TanStack Query v5 passes the query object to `refetchInterval`. Its background
refetch error state retains cached data. Use that behavior. Do not clear
last-known status after a failed poll.

The top bar shows:

- `Running` for a successful running status response.
- `Degraded` for a successful non-running status response.
- `Disconnected` after any status query error.
- Worker, active-job, and queued-job counts from last-known data.
- Last successful update time from `dataUpdatedAt`.

Follow Flowforge status rules: icon plus label plus token color. Never rely on
color alone. Keep the existing theme toggle.

## Files

- `web/src/lib/types.ts`
- `web/src/lib/api.ts`
- `web/src/lib/queries.ts`
- `web/src/lib/*.test.ts`
- `web/src/lib/*.test.tsx`
- `web/src/App.tsx`
- `web/src/App.test.tsx`
- `web/src/components/TopBar.tsx`
- `web/src/components/*.test.tsx`
- `web/src/styles/app.module.css`
- `src/openmcp/dashboard_static/`
- `docs/plans/react-monitor-console/phase-02/notes.md`
- `docs/plans/react-monitor-console/phase-02/journal.md`

## Done When

- Types match every existing read response.
- Fetch failures reject with endpoint and HTTP status context.
- Query keys are unique and job aggregation is centralized.
- General polling is near three seconds.
- Open-job polling is near two seconds.
- Hidden tabs stop interval polling.
- Visible or focused tabs refetch.
- Background status failure shows `Disconnected`.
- Last-known counts remain rendered after that failure.
- Top-bar status uses icon, label, and Flowforge tokens.
- No custom interval or timeout drives polling.
- `npm --prefix web run build`
- `npm --prefix web test -- --run`

## Rules

Follow the supplied worker contract. Use test-first development. Stay within
the declared file set. Do not change backend Python files. Maintain this
phase's `notes.md` and `journal.md`.

## Response Format

Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
