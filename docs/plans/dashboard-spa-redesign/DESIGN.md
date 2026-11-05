# Dashboard SPA Redesign Design

**Status:** Confirmed 2026-11-05
**Consultation:** Two read-only consults agreed: polling over SSE, a bounded `/dashboard/api` surface, a summary SQL list query, `has_more` on output, `question_id` on answer, five phases with security first. Jobs `dcc9a820-c3cb-476c-ab2e-d73758fb18b9` (base) and `41c675e9-b8b7-4045-8d68-d09798fca866` (balanced) succeeded after agy targets failed with `transient`.

## Purpose

Replace the server-rendered dashboard in `server/src/refract/dashboard.py` with a React single-page console. The console is built with Vite, TypeScript, Tailwind v4, and shadcn/ui, and styled with TDS. It adds live filtering, readable transcripts, a split-pane layout, and job actions.

This design supersedes the dashboard sections of `docs/plans/refract-v3-simplification/DESIGN.md:124-132` and `docs/plans/readonly-dashboard-redesign/DESIGN.md`. Those files remain as history.

## Users and Success Criteria

Users: developers running the Refract daemon locally who monitor and steer worker jobs.

Success criteria:

- Every current page has an SPA equivalent: job list, job detail with live output, and targets with config health.
- Persisted job state and events of live jobs appear within about 2 s, with no page reload.
- Cancel, retry, and answer call the existing runtime methods and show the result or error.
- The TDS Rule 10 self-check from `tds rules` passes.
- Keyboard and screen-reader access work through Radix primitives.
- Vitest, `tsc --noEmit`, pytest, and the bundle staleness check pass.

## Constraints, Invariants, and Non-Goals

Constraints:

- Behavior layer: shadcn/ui with Radix primitives. Look layer: TDS classes and semantic tokens.
- Tailwind utilities are allowed for layout only, with TDS token values such as `gap-(--gap-md)`. Colors, typography, and component looks come only from TDS.
- The built bundle is committed under `server/src/refract/dashboard_static/app/`. CI fails when it is stale.
- TypeScript source. npm with a lockfile. Node pinned through `.nvmrc`.

Invariants:

- The dashboard and `/ask` stay loopback-only through `_loopback_route` (`server/src/refract/dashboard.py:90`).
- The six MCP tools and `/ask` are unchanged in schema and behavior.
- No config editing.
- No database schema change.

Non-goals: dark theme, config mutation, authentication or remote access, mobile-first layout below tablet width, telemetry or Langfuse views, and a retry target override in the UI.

## Chosen Approach

Polling plus a bounded JSON API under `/dashboard/api`, with the SPA served at `/dashboard/*` through an index fallback.

Rejected alternatives:

- Server-sent events: there is no push source, so the server would still poll stream files, and long-lived connections slow cancel and shutdown.
- Keep server-rendered pages: cannot use shadcn/ui, which requires React.
- Call MCP tools from the browser: MCP is not a browser API, and it would risk the six-tool invariant.

## Architecture and Data Flow

### Server routes

| Route | Behavior |
|---|---|
| `GET /dashboard`, `/dashboard/jobs/{id}`, `/dashboard/targets`, other `/dashboard/*` | Serve the SPA `index.html` shell |
| `GET /dashboard/assets/*` | Hashed Vite assets. A missing asset returns 404, not the shell. |
| `GET /dashboard/api/jobs?state&project&workflow&target&q&cursor&limit` | Job summaries from a summary-only SQL query that does not read result files. Filters run before pagination. Returns filter options. |
| `GET /dashboard/api/jobs/{id}` | Detail object: job fields, prompt, result, project root, `pending_question {question_id, text}` or null |
| `GET /dashboard/api/jobs/{id}/output?after=N` | Envelope `{events, next, has_more, available, state, terminal}`. Bounded read of the stream file. |
| `GET /dashboard/api/targets` | Targets and config health |
| `POST /dashboard/api/jobs/{id}/cancel` | Calls `Runtime.cancel` |
| `POST /dashboard/api/jobs/{id}/retry` | Body `{}`. Calls `Runtime.retry`. Returns the new job ID and state. |
| `POST /dashboard/api/jobs/{id}/answer` | Body `{answer, question_id}`. Calls `Runtime.job_answer` with an expected question ID. |

Rules for every route:

- All routes use `_loopback_route`. `/ask` keeps its own token check and is untouched.
- API routes register before the SPA fallback. An unknown `/dashboard/api/*` path returns a JSON 404.
- Responses use allowlisted fields and `Cache-Control: no-store`. Raw database records, ask tokens, futures, and execution plans are never serialized.

### CSRF guard for POST routes

A POST is rejected unless all of these hold:

- `Origin` is present, not `null`, and is a loopback origin whose scheme, host, and port match the request.
- `Sec-Fetch-Site` is `same-origin` when the header is present.
- The `X-Refract-Dashboard` header is present with its fixed value.
- The content type parses as `application/json`.

No CORS headers are emitted.

### Answer race protection

`AskRegistry.deliver_answer` (`server/src/refract/ask.py:199`) is keyed only by job ID. It gains an optional `expected_question_id` argument. When it is set and does not match the pending question, delivery fails with `invalid_state`. The MCP `answer` tool omits the argument, so its behavior is unchanged.

### Frontend

- Location: `server/web/`. Vite base `/dashboard/`. Build output `server/src/refract/dashboard_static/app/`, and only that directory is emptied.
- TDS CSS moves to `server/web/src/styles/tds/` and is imported with `layer(components)`. `globals.css` holds the shadcn-to-TDS token bridge. Tailwind default color and radius theme variables are cleared to avoid collisions such as `--color-neutral-100` and `--radius-md`.
- Layout: a resizable split pane. Left: job list with filters and job-ID search. Right: job detail with tabs for transcript, prompt, result, and metadata, plus action buttons. Targets is a separate route.
- URL state: filters and search in the query string. The selected job is in the path.
- shadcn components with Radix behavior and TDS classes: Button, Select, Input, Tabs, Dialog, AlertDialog, Resizable. Action results show as TDS announcements.
- Polling: about every 1 s for the list and the selected job. No overlapping requests. Stale responses are dropped when the selection changes. Polling pauses while the tab is hidden and refreshes on return. Output keeps fetching while `has_more` is true, including after the job ends.
- Transcript reducer: groups events by attempt and entity, merges contiguous text deltas, and pairs tool start and completion events. Unknown event kinds show a fallback row. Missing timestamps or missing tool output are not filled in. All text renders as React text with no raw HTML.

## Errors and Edge Cases

Errors:

- API errors keep the `_error` JSON shape `{error, code, unchanged, recovery}` with HTTP status codes: 400 bad input, 403 loopback or CSRF failure, 404 unknown job, 409 `invalid_state`, 503 runtime not ready.
- On a polling error, the UI keeps the last good data, shows a TDS warning announcement, and backs off to about 5 s until a request succeeds.
- Action buttons are disabled while a request is in flight. A POST that times out is never resent automatically.

Edge cases:

- Cancel can return `state="running"` (`server/src/refract/runtime.py:459`). The UI shows "Cancellation requested" and lets polling show the final state.
- Retry creates a new job that can run on a different target (`server/src/refract/runtime.py:503`). The UI selects the new job ID.
- A stale or expired `question_id` returns 409, and the UI reloads detail. Answering a terminal job returns 409.
- A missing stream file returns empty events with `available: false`. A partial last line is held back. Pages are capped at 500 events, and the client follows `has_more`.
- Large transcripts render a bounded window with a control to show earlier events.
- A job removed by retention returns 404 from detail, and the UI clears the selection.

## Migration

- Phases 1 to 4 add routes and the SPA alongside the existing HTML pages.
- Phase 5 removes the HTML page renderers, `_POLL_SCRIPT`, `_stylesheet`, `GET /dashboard/jobs/{id}/output`, and `server/src/refract/dashboard_static/tds/`.
- `CHANGELOG.md` gets an Unreleased entry listing added and removed routes. The README dashboard section is updated.

## Testing

pytest:

- JSON contract tests for each `/dashboard/api` route with exact allowlisted keys.
- CSRF rejection matrix: missing Origin, `null` Origin, foreign Origin, port mismatch, missing custom header, wrong content type, `Sec-Fetch-Site: cross-site`.
- Loopback guard on every new route, including assets and the shell fallback.
- Answer race: stale `question_id`, expired question, MCP path without a question ID.
- Cancel and retry from each job state.
- Output: more than 500 events, partial final line, missing file, draining after the job ends.
- The list query does not read result files.
- The SPA fallback serves the shell. An unknown API path or missing asset returns 404.
- Existing six-tool schema, `/ask`, and off-loop tests stay unchanged.

Vitest with Testing Library:

- Transcript reducer on fixtures from the Codex, Claude, Pi, and agy backends.
- Polling with fake timers: no overlap, pause while hidden, backoff, `has_more` drain.
- URL state and filters.
- Action flows, including the "cancellation requested" and retry selection cases.
- Escaping of hostile event text.

Other checks:

- `tsc --noEmit`.
- A bundle staleness script rebuilds into a staging directory and compares every file name and byte with `dashboard_static/app/`. It runs in a new `web` job in `.github/workflows/server.yml` on Ubuntu, with `npm ci`.
- Manual acceptance: a Playwright smoke run through the attached browser covering deep links, keyboard navigation, and live updates within 2 s. The TDS Rule 10 checklist is recorded in the final phase notes.

## Risks and Open Questions

Risks:

- Tailwind v4 and TDS token name collisions. Mitigation: clear the default theme and check computed styles in Phase 3.
- Radix portal content rendering outside the TDS layer. Mitigation: check dialogs and select menus in Phase 3.
- Bundle hash churn across machines. Mitigation: pinned Node, `npm ci`, and a byte comparison on Ubuntu only.
- Transcript accuracy is limited by what each backend emits. Claude tool completion has no output (`server/src/refract/backends/claude.py:89-117`). Documented, not fixed here.
- Existing debt: `claude.py` `complete_tool` hardcodes status `completed`, so failed Claude tools appear completed. This is recorded in `docs/plans/readonly-dashboard-redesign/.handover.md` and is out of scope.

Open questions:

- The exact pytest baseline count for this checkout is confirmed when `PLAN.md` is written.
