# Read-Only Dashboard Redesign Design

**Status:** Confirmed 2026-11-03
**Consultation:** One `consult` job `c55f7fa1-39e7-4e12-a27a-76eadb25e12c` succeeded; endpoint inventory, removal set, and lock replacement verified against code. Second job `2b2f508e-4e87-4b41-831a-ee4d6b50d48d` cancelled at user request. Consult token names such as `--text-primary` rejected; TDS rules define `--text-default`, `--surface-neutral-01..04`, `--surface-selected`.

## Purpose

Replace the Refract dashboard with a fresh, strictly read-only UI for developers who watch live jobs and debug failures. Remove every server path that only existed to support editing configuration from the UI.

## Users and Success Criteria

Users: a developer running Refract locally, following jobs submitted from an editor or coordinator session.

Success criteria:

- The Live view shows active and recent jobs for the selected project and streams the selected job transcript in real time.
- Secondary views exist for Projects, Targets and profiles, Diagnostics, and Runtime and config health.
- The UI offers no control that mutates configuration or jobs.
- The server exposes no POST, PUT, or DELETE under `/dashboard/api/*`; `POST /ask` remains.
- `config_mutation.py`, `tomlkit`, CSRF and If-Match handling, and editor models are gone.
- All server and UI tests pass, and committed `dashboard_static` has no build drift.

## Constraints, Invariants, and Non-Goals

Constraints:

- Stack: React 19 and Vite with a fresh `server/web/src`. Keep `@tanstack/react-virtual`. No new dependencies.
- Visual system: TDS semantic tokens and `tds-*` classes only, light theme only.
- The old UI is deleted. Git history is the only archive. New code does not reference it.

Invariants:

- Loopback client and Host guards stay on every `/dashboard/*` route and `/ask`.
- `POST /ask` behavior is unchanged.
- Unknown `/dashboard/api/*` paths and verbs return the JSON 404 `DashboardError`.
- SQLite schema is unchanged.
- Vite `base: '/dashboard/'` and `outDir: '../src/refract/dashboard_static'` are unchanged.
- Configuration reload through `Runtime.publish_configuration` and `_ensure_fresh_configuration` keeps working.

Non-goals:

- Editing targets, profiles, or project overrides from any interface.
- Job actions from the UI such as cancel or retry.
- A cross-project job listing endpoint.
- Dark theme.

## Chosen Approach

Split-pane live console: status strip, nav rail with project switcher, job feed, and a persistent job inspector with a live transcript.

- Rejected: full-width job table with slide-over drawer. The drawer hides the feed and slows switching between live jobs.
- Rejected: active-job chip strip above a full-width transcript. It does not scale past about five concurrent jobs and hides history.
- Rejected: cross-project jobs endpoint. It adds server code; a project switcher covers the need.

## Architecture and Data Flow

### Layout

```text
+----------------------------------------------------------------------+
| Status strip: daemon | active | queued | unhealthy targets | config  |
+-----------+----------------------+-----------------------------------+
| Nav rail  | Job feed (~360px)    | Job inspector (flex)              |
| [project] | ACTIVE               | id | workflow | profile | target   |
| Live      |   running / queued   | state | attempt | context usage   |
| Projects  | RECENT               | failure card when failed          |
| Targets   |   last 10 terminal   | Tabs: Transcript | Result | Plan  |
| Diagnost. |   more_recent note   | virtualized live transcript       |
| Runtime   |                      | follow tail, jump-to-live control |
+-----------+----------------------+-----------------------------------+
```

Hash routes: `#/jobs`, `#/jobs/:id`, `#/projects`, `#/projects/:id`, `#/targets`, `#/diagnostics`, `#/runtime`. Secondary views occupy the feed and inspector area.

Project switcher: remembers the last selected project in `localStorage`, otherwise the first project. The status strip shows global active and queued counts from `overview`. No per-project activity badges.

Live view option: a "follow newest running job" toggle selects new running jobs automatically.

### Views

- **Live:** feed from `projects/{id}/jobs`; inspector from `jobs/{id}`. Inspector header shows id, workflow, profile, target, context key, timestamps, attempts, and token telemetry from `result.metadata.telemetry`. Tabs: Transcript, Result with `result.text`, `result.error`, and `result.metadata`, and Plan with `execution_plan`, attempts, and job-scoped diagnostics.
- **Projects:** project table; selecting one shows default profiles and the per-workflow target chains with source attribution from `projects/{id}`.
- **Targets and profiles:** target table from `targets` with backend, model, isolation, read-only flag, active over max concurrency, breaker state, cooldown, and probing; profile routing matrix from the enriched `profiles`.
- **Diagnostics:** filter by project, category, and job id; cursor pagination through `before`; rows expand to compare `expected` and `observed`; each row links to `#/jobs/{job_id}`.
- **Runtime:** config health from `overview.configuration`; daemon and logging settings from `settings`.

### Polling and Streaming

- `overview` every 3 s for the status strip.
- `projects/{id}/jobs` every 2 s while the Live view is shown.
- `jobs/{id}` every 2 s until the job is terminal.
- All polling pauses when `document.visibilityState` is `hidden`.
- Transcript: one `EventSource` on `jobs/{id}/output/updates`, only for the selected non-terminal job. On each update, page `jobs/{id}/output?after=<cursor>` until `has_more` is false. Close the stream on job switch, view change, and once the job is terminal and drained. Merge contiguous `assistant.text_delta` events per `entity_id`; pair `tool.started` and `tool.completed` by `entity_id`; show lifecycle markers.

### Read-Only API Contract

Keep:

| Route | Note |
|---|---|
| `GET /dashboard/api/overview` | Status strip and config health |
| `GET /dashboard/api/settings` | Runtime view |
| `GET /dashboard/api/targets` | Targets view |
| `GET /dashboard/api/profiles` | Enriched with profile routing data from `_profile_config_data` over the in-memory catalog |
| `GET /dashboard/api/projects` | Project switcher and Projects view |
| `GET /dashboard/api/projects/{project_id}` | Project detail |
| `GET /dashboard/api/projects/{project_id}/jobs` | Job feed |
| `GET /dashboard/api/jobs/{job_id}` | Inspector |
| `GET /dashboard/api/jobs/{job_id}/output` | Transcript pages |
| `GET /dashboard/api/jobs/{job_id}/output/updates` | Transcript SSE |
| `GET /dashboard/api/diagnostics` | Diagnostics view and job-scoped reports |
| `POST /ask` | Worker callback, unchanged |
| Static shell and asset routes | Unchanged |

Delete GET routes: `bootstrap`, `status`, `configuration`, `configuration/targets`, `configuration/targets/{target_id}`, `configuration/profiles`, `configuration/profiles/{profile_id}`, `projects/{project_id}/profile-overrides`, `projects/{project_id}/profile-overrides/{profile_id}`, `task-guide`.

Delete write routes: POST, PUT, and DELETE on `configuration/targets`, `configuration/profiles`, and `projects/{project_id}/profile-overrides`.

### Server Removals

- Delete `server/src/refract/config_mutation.py`.
- In `runtime.py`, replace `self.mutations = ConfigurationMutationService(self)` with a `threading.RLock` and switch the four `with self.mutations.lock:` sites to it. Delete `_publish_project_configuration_locked` if no caller remains.
- In `dashboard.py`, delete the CSRF and If-Match headers and helpers, `_mutation_error_response`, mutation and editor-read authorization helpers, and the target, profile, and project-override route registrars. Remove `csrf_token` from `DashboardState` and its setup in `server.py`.
- In `models.py`, delete editor and bootstrap models and `DashboardError` fields used only by mutations, after confirming no remaining reference.
- In `config.py`, delete `load_config_bytes` and the `data` parameter of `load_project_config` if no caller remains.
- Remove `tomlkit` from `server/pyproject.toml` and regenerate `uv.lock`.
- Change recovery strings at `runtime.py:377` and `server.py:632` to name `.refract/config.toml` instead of the dashboard.

## Errors and Edge Cases

- API unreachable: status strip shows disconnected, last data stays visible and marked stale, polling backs off to 10 s.
- Config invalid: persistent banner with `latest_error` and `last_known_good_revision`; text directs the user to the TOML file.
- Unknown job: inline "Job not found" in the inspector; feed stays usable.
- Transcript: show `result.text` when `stream_status` is unavailable; show a notice when `retained_from` indicates pruned events; render `stream.truncated` and `stream.persistence_failed` markers.
- SSE drop on an active job: reconnect with exponential backoff and resume from the last cursor.
- Failure card when `result.metadata.failure` or `result.error` is set: shows `kind`, `retryable`, and whether `next_target` exists, with a link to job diagnostics.
- Removed routes and verbs return the JSON 404.

## Migration

Phases:

1. **Server trim.** Python changes and test updates listed above. Old UI config screens break during this phase only.
2. **New UI core.** Delete `server/web/src` contents. Build shell, Live view, inspector, and transcript.
3. **Secondary views.** Projects, Targets and profiles, Diagnostics, Runtime.
4. **Build and docs.** Rebuild and commit `dashboard_static`, removing old hashed assets and the FlowForge logo. Update README and CHANGELOG.

No data migration. SQLite schema is unchanged.

## Testing

Server, `cd server && uv run pytest`:

- Deleted routes return the JSON 404 for each method.
- Kept routes reject non-loopback clients and hosts.
- `profiles` returns routing detail.
- Job submission works without `runtime.mutations`.
- Recovery strings name `.refract/config.toml`.
- Existing SSE, job output, diagnostics, and `/ask` tests stay green.
- Delete `tests/test_config_mutation.py` and mutation-specific tests in `test_dashboard.py` and `test_runtime.py`; drop `csrf_token` from test fixtures.

UI, `cd server/web && npm test && npm run build`, written test-first:

- Polling pauses when hidden.
- At most one `EventSource`; it closes on job switch and on terminal drain.
- Transcript paging drains until `has_more` is false.
- Text delta merging and tool event pairing.
- Failure card, config-invalid banner, stale state, and job-not-found rendering.
- Hash routing.
- No mutating form controls.

Build drift: `test_committed_dashboard_static_has_no_build_drift` passes after rebuild.

Manual smoke: `refract serve`, submit a consult job, watch the transcript stream live in the inspector.

## Risks and Open Questions

Risks:

- Browser per-origin connection limit if more than one `EventSource` opens. Mitigated by the single-stream rule.
- Server-closed SSE triggers browser auto-reconnect. Mitigated by client close on terminal state.
- Missing lock replacement would raise `AttributeError` on every job submission. Covered by the submission test.
- TDS components may not cover every needed pattern such as a virtualized transcript row. Compose from TDS tokens; do not invent `tds-*` class names.

Open questions: none.
