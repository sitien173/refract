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

Define recursive JSON value/object types. Do not use `any` for event data.
Keep event `kind` open as `string`. Do not add database-only job fields.

Use TanStack Query v5. Create one stable `QueryClient`. General resources poll
near three seconds. Open job detail and events poll near two seconds. Use unique
keys containing resource identifiers. Export one query-key factory. Encode all
path identifiers. Every API wrapper accepts an optional `AbortSignal`. Forward
TanStack Query's signal from every query function.

Use named `3000` and `2000` interval constants. Set
`refetchIntervalInBackground: false`, `refetchOnWindowFocus: 'always'`, and
`retry: false`. Let TanStack's focus manager suppress hidden-tab requests and
refetch on visibility restoration. Do not create application timers or depend
only on a non-reactive `document.hidden` interval callback.

Export a finished `useAllJobs` hook. Use `useProjects` plus one `useQueries`
entry per project. Populate the same per-project caches. Merge available data
when another project fails. Sort newest `created_at` first with `id` as a stable
tie-breaker. Expose partial errors without discarding successful or cached
results. Do not use one aggregate `Promise.all`.

Treat "open job" as mounted and enabled detail/event hooks. Poll both near two
seconds. Disabled or unmounted hooks stop polling. Do not stop events
immediately on terminal detail state because the final event may race.

TanStack Query's background refetch error state retains cached data. Use that
behavior. Do not derive displayed data as `isError ? undefined : data`.
`dataUpdatedAt` must change only after successful data.

The top bar shows:

- `Running` for a successful running status response.
- `Degraded` for a successful non-running status response.
- `Disconnected` after any status query error.
- `Connecting` before the first success or error.
- Worker, active-job, and queued-job counts from last-known data.
- Last successful update time from `dataUpdatedAt`.

Only the status query controls connection state. Unrelated errors must not
change the pill. Status-error precedence is Disconnected, even when cached data
exists. Before the first success, show em dashes for counts and last update.
After success, retain numeric counts and last update through errors. Recover
after the next successful fetch.

Follow Flowforge status rules: icon plus label plus token color. Never rely on
color alone. Keep the existing theme toggle.

## Files

- `web/src/lib/types.ts`
- `web/src/lib/api.ts`
- `web/src/lib/queries.ts`
- `web/src/lib/queryClient.ts`
- `web/src/lib/*.test.ts`
- `web/src/lib/*.test.tsx`
- `web/src/App.tsx`
- `web/src/App.test.tsx`
- `web/src/components/TopBar.tsx`
- `web/src/components/*.test.tsx`
- `web/src/assets/icons/circle-check.svg`
- `web/src/assets/icons/triangle-alert.svg`
- `web/src/assets/icons/wifi-off.svg`
- `web/src/setupTests.ts`
- `web/src/styles/app.module.css`
- `src/openmcp/dashboard_static/`
- `docs/plans/react-monitor-console/phase-02/notes.md`
- `docs/plans/react-monitor-console/phase-02/journal.md`

## Done When

- Types match every existing read response.
- Fetch failures reject with endpoint and HTTP status context.
- Query keys are unique and job aggregation is centralized.
- Project-job aggregation retains partial successful data.
- General polling is near three seconds.
- Open-job polling is near two seconds.
- Hidden tabs make no polling requests.
- Visibility restoration triggers an immediate refetch.
- Disabled or unmounted job hooks stop polling.
- Background status failure shows `Disconnected`.
- Last-known counts remain rendered after that failure.
- Last-success timestamp remains unchanged after failure.
- Unrelated query failures do not alter connection status.
- A later successful status fetch restores connection status.
- Initial status is `Connecting` with unknown counts.
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
