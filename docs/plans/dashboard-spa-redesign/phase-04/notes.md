

## Resumed batch — completion work (2026-11-05)

## Task 1

### Decisions made
- Kept the earlier hook implementation and added the requested fake-timer behavioral coverage. Polling remains sequential; changing keys invalidates old responses and cleanup cancels scheduled work.

### Spec deviations
- none

### Tradeoffs accepted
- Output requests continue checking `document.hidden` on scheduled polls instead of subscribing to a visibility event; hidden state is respected on the next scheduled tick.

### Assumptions
- Backend `terminal` and `has_more` values remain authoritative while draining stream pages.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: `cd server/web && npm test -- --run src/hooks/useJobOutput.test.tsx -t 'pauses a terminal has_more drain'` -> expected one request while hidden, observed two; drain loop did not honor hidden state.
  - GREEN: `cd server/web && npm test -- --run src/hooks/useJobOutput.test.tsx -t 'pauses a terminal has_more drain'` -> 1 passed, 3 skipped; plus `cd server/web && npm test -- --run src/hooks/usePolling.test.tsx src/hooks/useJobOutput.test.tsx` -> 2 files, 7 tests passed (1 s interval, no overlap, stale selection, hidden pause, 5 s backoff, terminal page drain, and unmount cleanup).
- Root cause (bugfix only): none.

## Task 2

### Decisions made
- Rows are keyed/grouped by provider entity id and event attempt metadata where present; assistant deltas append to their entity row, and tool completion updates the matching tool-start row.
- Fixtures use normalized event fields emitted by Codex, Claude, Pi, and agy backend adapters.

### Spec deviations
- none

### Tradeoffs accepted
- Adapter output does not universally expose an attempt number; events without one remain in attempt 1 rather than inventing retry metadata.

### Assumptions
- A retry is a distinct job; event `attempt`/`data.attempt`, when present, is the only source of in-stream attempt grouping.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: `cd server/web && npm test -- --run src/transcript/reduce.test.ts` -> `groups deltas by entity and pairs tool start/completion with unknown fallback` failed: expected 3 rows, got 4 (tool start and completion were not paired).
  - GREEN: `cd server/web && npm test -- --run` -> final full frontend suite passed, 15 files / 29 tests; includes reducer grouping/unknown fallback, four fixtures, bounded window, and hostile-string-as-text DOM assertions.
- Root cause (bugfix only): tool start and completion were treated as separate rows instead of being joined by entity id.

## Task 3

### Decisions made
- Split responsibilities into independently testable list, filter, detail, action, transcript, console, and targets components; `App` composes them and routes URL changes through `/dashboard/app/*` paths.
- Dialogs and selects use existing Radix/shadcn wrappers; all visible actions use the Button wrapper and status messages use the TDS announcement class.

### Spec deviations
- none

### Tradeoffs accepted
- Project filters use project IDs as the user-facing option text; the API's project root remains available in the options data.

### Assumptions
- Retry responses use the API contract's `job_id`, and actions remain API-only.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: component tests were authored before their implementations, but their first executions were after implementation; initial import-resolution failures were scaffolding failures and do not count as behavioral RED. The App retry test initially failed because its mock returned the old job ID for every detail request; correcting the mock made it pass, without a production change.
  - GREEN: `cd server/web && npm test -- --run` -> final frontend suite passed, 15 files / 29 tests. Coverage includes deep-link route/filter restoration, retry selection of the returned job, cancel confirmation, answer `question_id`, disabled action controls, portal/TDS class checks, targets, split pane, and hostile event text.
- Root cause (bugfix only): none.

## Task 4

### Decisions made
- Rebuilt bundle after all final source and test changes.

### Spec deviations
- Build still reports unresolved TDS spinner asset URL warnings from imported spinner CSS. No loading indicator uses those unavailable SVGs, so no fallback indicator is rendered or needed.

### Tradeoffs accepted
- none

### Assumptions
- CSS spinner assets can be addressed separately if a later screen adds an actual loading state.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: none; rebuild task has no behavioral RED.
  - GREEN: `cd server/web && npm run build && npm ci && npm run typecheck && npm test -- --run && npm run check:bundle` -> build succeeded; typecheck passed; 15 files / 29 tests passed; bundle current (3 files).
  - GREEN: `cd server && PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dashboard_api.py tests/test_dashboard.py` -> 41 passed.
  - GREEN: both prompt grep checks (`dangerouslySetInnerHTML`; hardcoded hex/dark selectors outside vendored TDS CSS) passed.
- Root cause (bugfix only): none.

## FIX cycle 1 — review findings 1–15 (2026-11-05)

### Task 1 — API, polling, split-pane behavior and job actions

#### Decisions made
- API failures are represented with `DashboardApiError` (HTTP status, backend code and message), preserving a useful fallback for non-JSON bodies; answer requests continue sending `question_id` and `answer`.
- Output polling now stops after terminal output is drained, checks liveness before scheduling work after failures, and preserves a bounded event window. Shared polling retains the previous successful value while a new key loads; the empty serialized filter key is valid.
- The resizable handle uses `--spacing-8` rather than a border color as its width. Added an arrow-key resize fallback with focusable separator semantics while retaining the `react-resizable-panels` implementation.
- Answer failures remain visible in the dialog and preserve the draft; `invalid_state` refreshes job detail. Terminal/inapplicable cancel and retry actions are disabled, and announcements/drafts clear when the selected job changes.

#### Spec deviations
- none

#### Tradeoffs accepted
- Loading and refresh states use text/status surfaces rather than spinner SVGs. The Vite build still warns that the imported TDS spinner CSS references unavailable SVG files; no such spinner is used by the new loading surfaces.

#### Assumptions
- `invalid_state` is the API error code for a stale pending question, as emitted by the dashboard action handler.

#### Follow-ups for human
- none

#### Test evidence
- RED → GREEN:
  - RED: the API error tests showed non-OK responses discarded status/code and an HTML error body surfaced a JSON parse error; action tests covered answer payload and failure behavior.
  - GREEN: `cd server/web && npm test -- --run src/api.test.ts src/components/JobActions.test.tsx` -> both files passed; answer body, HTTP/code metadata, non-JSON fallback, encoded paths, cache policy, draft retention and stale-question refresh covered.
  - RED: output cleanup tests exposed a rejection-after-unmount/selection timer reschedule and terminal drained polling continued; resizable keyboard test observed `defaultPrevented === false` and the invalid color-as-width was not a valid handle size.
  - GREEN: `cd server/web && npm test -- --run src/hooks/useJobOutput.test.tsx src/hooks/usePolling.test.tsx src/components/ui/resizable.test.tsx` -> all passed; tests cover cleanup, drain stopping, hidden pause, backoff, keyboard resizing, focus and TDS width.
- Root cause (bugfix only): output rejection scheduled after cleanup; terminal drain had no stop condition; polling treated `""` as a missing key; the separator width used a color token; answer action errors were swallowed before the dialog could preserve user input.

### Task 2 — transcript fidelity and fixture assertions

#### Decisions made
- Removed unsupported invented attempt-start event handling. Assistant/tool interleaving is grouped using observed entity/attempt metadata without merging unrelated assistant messages that reuse an entity ID. Unknown event rows retain their real kind.
- Strengthened provider fixture assertions to inspect rendered row kind/content rather than only checking non-empty output.

#### Spec deviations
- none

#### Tradeoffs accepted
- Provider adapters without attempt metadata continue to use the default attempt group; no attempt field is invented.

#### Assumptions
- Only backend-emitted event fields are valid grouping evidence; provider fixtures stay based on adapter shapes.

#### Follow-ups for human
- none

#### Test evidence
- RED → GREEN:
  - RED: `cd server/web && npm test -- --run src/transcript/reduce.test.ts` -> interleaved assistant/tool events produced an extra assistant row; the real unknown-kind assertion also showed the fallback did not expose the event kind.
  - GREEN: `cd server/web && npm test -- --run src/transcript/reduce.test.ts src/components/TranscriptView.test.tsx` -> both files passed, including fixture row assertions, interleaving, tool pairing, bounded output and hostile-string-as-text rendering.
- Root cause (bugfix only): assistant messages with reused provider entity IDs were appended across an intervening tool event; fallback rows concealed the source kind.

### Task 3 — targets, routing, filters, list/detail surfaces and pagination

#### Decisions made
- Targets rendering now follows `TargetView` fields and includes health/breaker/concurrency and config status; errors are not rendered as an empty-target state, and navigation back to the console stays in-app.
- Route matching distinguishes `/targets` from `/jobs/targets`; project filter options display roots while submitting IDs, and sentinel values cannot collide with a literal `all` option.
- Job list/detail/output expose loading and error states, including a not-found deep link. Cursor pagination appends pages; the load-more control is hidden during a filter refresh so it cannot submit a stale cursor.

#### Spec deviations
- none

#### Tradeoffs accepted
- Existing list rows remain visible during filter refresh while the loading status is announced; old pagination controls are hidden until the new filter response arrives.

#### Assumptions
- The API's `next_cursor` is opaque and must be passed back unchanged.

#### Follow-ups for human
- none

#### Test evidence
- RED → GREEN:
  - RED: targets tests failed against a real target shape (no `name` field) and required config/health fields; route test matched the `targets` job ID as the targets view; project filter test surfaced an ID rather than the configured root.
  - GREEN: `cd server/web && npm test -- --run src/views/TargetsView.test.tsx src/router.test.ts src/components/JobFilters.test.tsx src/components/JobList.test.tsx src/components/JobDetail.test.tsx src/views/ConsoleView.test.tsx` -> all passed with real-shaped target, root-label/ID-submit, route-collision, loading/error and console assertions.
  - RED: the App cursor test initially found `getJobs` was never called for the empty serialized filter key (the hook considered it absent); after that fix a flaky `toHaveBeenLastCalledWith` assertion caught a later normal poll, not a pagination defect.
  - GREEN: changed the pagination assertion to assert the cursor request occurred, then `cd server/web && npm test -- --run` -> 16 files / 53 tests passed.
- Root cause (bugfix only): targets UI relied on an invented `name`; route matching was too broad; project root labels and pagination were missing; empty filters short-circuited polling.

### Task 4 — rebuilt bundle and final verification

#### Decisions made
- Rebuilt the checked-in SPA assets after the review fixes.

#### Spec deviations
- none; the build retains existing warnings for unavailable TDS spinner SVG URLs, documented under Task 1.

#### Tradeoffs accepted
- none

#### Assumptions
- none

#### Follow-ups for human
- none

#### Test evidence
- RED → GREEN:
  - RED: none (bundle regeneration has no behavioral RED).
  - GREEN: `cd server/web && npm ci && npm run typecheck && npm test -- --run && npm run build && npm run check:bundle` -> typecheck passed; 16 files / 53 tests passed; build succeeded; bundle current (3 files). The first post-`npm ci` run exposed a timing-sensitive last-call assertion in the pagination test; it was narrowed to assert the cursor request itself and the full suite then passed.
  - GREEN: `cd server && PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dashboard_api.py tests/test_dashboard.py` -> 41 passed.
  - GREEN: both Phase 4 grep checks passed (`dangerouslySetInnerHTML`; hardcoded hex/dark selectors outside vendored TDS CSS).
- Root cause (bugfix only): none.

### FIX 1 compliance note
- Review findings 1–15 are addressed in source and regression coverage. Some test-first red observations were captured at the finding/group level rather than independently for every small UI branch; this evidence limitation remains the only documented compliance debt. No Python files were changed.

## Batch — FIX 2 (final cycle): re-review items A, B, HIGH, MEDIUM, PARTIAL 5/6/9, LOW, maintainability

#### Decisions made
- **Polling stop (PARTIAL 9):** `usePolling(key, load, interval, shouldContinue)` stops rescheduling when `shouldContinue(next)` is false. `App` passes `isJobActive` for the detail poll only; list polling is unchanged. A `detailRevision` in the key lets a retry/answer restart polling for the same job.
- **Empty-string keys (PARTIAL 5):** `loading` is `key !== null`, so `""` is a valid key.
- **Pagination (HIGH stale, MEDIUM coherence):** extracted to `hooks/useJobPages.ts`. Results, errors and finalizers carry a generation token; older generations are discarded. The first page keeps polling live. When its `next_cursor` moves, loaded cursor pages are refetched from the new cursor, and the combined list is deduplicated by id (earlier pages win).
- **Output history (HIGH):** `useJobOutput` keeps every fetched event. Only the rendered window is bounded, via `TranscriptView` `limit` and its existing "Show earlier events" control.
- **Polling errors (MEDIUM):** after a successful load, a refresh error keeps the last good detail mounted and shows a `role=status` warning. The replacement error panel appears only if there is no detail. The answer draft survives.
- **LOW:** `useJobActions` calls `onRetried` (navigation) and then `announce`; `followRetry` keeps the announcement across navigation.
- **Maintainability:** compressed code reformatted. Action handling extracted to `hooks/useJobActions.ts`; `JobActions` has `submitAnswer`/`openAnswer`; `App` has `navigate`, `selectJob`, `followRetry`, `refreshDetail`.
- **Resizable (B):** `components/ui/resizable.tsx` is now a thin wrapper over react-resizable-panels 3.0.6. It keeps TDS token sizing, a default aria-label "Resize panels" and prop forwarding. All keyboard and `aria-value*` behavior comes from the library; there are no DOM fallbacks.
- **Determinism (A):** `App`, `JobActions`, `ConsoleView`, `JobFilters` and `tds-render` tests use fake timers with `settle()` (`act(async () => vi.advanceTimersByTimeAsync(ms))`). No per-test timeouts are raised and `findBy`/`waitFor` are not used with fake timers. The pagination test uses a NONEMPTY first page.
- **New test helpers:** `src/test/async.ts` (`settle`, `deferred`) and `src/test/warmup.tsx` (`warmUpComponents`).
- **Global warm-up:** `src/test/setup.ts` has a `beforeAll` that renders once and runs one `getByRole`. The first render and first role query in a fresh worker cost about 1 s of one-time work, and under machine load (load average 25–30 on 8 cores) that pushed the first test of a file past the default 5 s timeout. Instead of raising timeouts, the cost is moved into a hook.
- Prettier was run from /tmp (the repo has no Prettier dependency) on the compressed source and test files.

#### Spec deviations
- `vite.config.ts` adds a Vitest-only `test.alias` for `react-resizable-panels` pointing at its browser build. Under Vitest/Node the package resolves to the edge-light server build, whose `useIsomorphicLayoutEffect` is a no-op, so `aria-valuenow` and keyboard handling never run. The alias affects tests only; the production bundle is unchanged.
- `vite.config.ts` and `src/test/setup.ts` are outside the original declared file set; they are test-infrastructure files required by items A and B.

#### Tradeoffs accepted
- Revalidating loaded pages costs up to N requests each time the first page's `next_cursor` shifts. This keeps the combined list gapless.
- The 5000-row render performance is covered at hook and reducer level; `TranscriptView` is tested with a small window around the boundary, because `getAllByRole` over thousands of nodes is itself slow in jsdom.

#### Assumptions
- Entity ids are unique only within an attempt (as the existing reducer already assumed), so attempt grouping keys are `${attempt}:${entity}`.

#### Follow-ups for human
- Revalidation cost: a first-page shift triggers N requests; consider a server-side "page-after-job-id" cursor if lists grow large.
- A revalidation failure is not retried until the cursor moves again; the user sees the load-more error.
- Fixtures are still synthetic; replace them with captured real streams when available.
- When the new filter key errors, the hook can briefly show a stale first-page value from the previous key.

#### Test evidence
- RED → GREEN (test-first, observed failing before the fix):
  - `usePolling`: empty-key loading test and stop-on-terminal test failed against the old hook, then passed.
  - `useJobOutput`: 6000-event retention test failed with "got 5000" (old slice), then passed once the slice was removed.
  - `resizable`: the new library-keyboard test failed against the old hand-written wrapper (no `aria-valuenow` change). Root cause for the follow-on failure was the edge-light build; fixed with the Vitest alias. 5 tests now pass: naming, library keyboard (maxSize 60: 50→60→60→50), disabled handle, prop forwarding.
  - `useJobPages` (7 tests): stale load-more after a filter change (deferred response), stale error/finally, live first-page refresh with revalidation, dedupe by id, and nonempty-first-page pagination. A mutation check (removing the generation guard) made the stale tests fail, then restored.
  - `JobDetail`: warning-with-last-good-detail test failed against the replacement-error behavior, then passed.
  - `App` (10 tests, fake timers): stale load-more discard, "Retry started" announcement after navigation, detail polling stopping at terminal state while list polling continues, and last-good detail on a polling error with the draft preserved all failed before the fixes and pass after.
  - Characterization tests (already green, added to lock behavior): attempt grouping in `reduce.test.ts`; a tool pair spanning the render-window boundary over 5200 events in the reducer/`TranscriptView` tests.
- GREEN, full suite: `cd server/web && npm ci && npm run typecheck && npm test -- --run && npm run check:bundle` -> typecheck clean; 17 files / 80 tests passed; "Dashboard bundle is current (3 files)".
- GREEN, Python: `cd server && PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dashboard_api.py tests/test_dashboard.py` -> 41 passed.
- GREEN, greps: `dangerouslySetInnerHTML` check and hex/`.dark` check both passed (exit 0).
- Stability (`for i in 1 2 3 4 5; do npm test -- --run || exit 1; done`, saved at /tmp/stability3.txt): 5 of 5 runs passed, each 17 files / 80 tests, durations 35.5 s, 47.1 s, 40.3 s, 47.2 s, 43.9 s. Earlier attempts before the global warm-up were not stable (e.g. 1 failure in 3 runs: a first test in a file at about 5.1 s under load); the global warm-up resolved it. The machine was heavily loaded throughout, so this is a conservative result.
- Python files: `git status` shows no modified `.py` files. `docs/plans/dashboard-spa-redesign/.handover.md` appears modified in `git status`, but I did not edit it.
- Root cause (bugfix only): stale async results were applied without a generation check; output history was truncated by a hard slice; refresh errors replaced a good detail; tests depended on real timers and on first-render cold-start cost.

## Batch — FIX 3 (narrow): revalidate all loaded pages on the polling cadence

#### Decisions made
- `useJobPages` now refetches every loaded cursor page on each first-page poll, starting from the first page's current `next_cursor`, sequentially and guarded by the existing `inflight` flag so requests never overlap. This replaces the cursor-moved-only trigger and the `anchor` ref (removed).
- A failed revalidation keeps the previous pages, sets `loadMoreError`, and pauses revalidation for 5 s (`retryAt`). It does not record any new anchor, so the next poll after the backoff retries. A success clears the error only if it came from revalidation.
- Generation discard and dedupe by id are unchanged.

#### Spec deviations
- none

#### Tradeoffs accepted
- Each poll costs one request per loaded extra page (previously N only when the cursor shifted). The cost grows with how many pages the user has loaded.

#### Assumptions
- The first-page poll interval (1 s) is the intended list cadence for revalidation.

#### Follow-ups for human
- Consider a slower revalidation cadence for deep lists, or a server-side change feed, if many pages are loaded in practice. This replaces the earlier follow-up about revalidation failures not retrying, which is now fixed.

#### Test evidence
- RED → GREEN (`src/hooks/useJobPages.test.tsx`, fake timers):
  - RED (3 new tests failed against the cursor-only revalidation): "refreshes a later-page job when the first-page cursor has not moved" (`expected 'running' to be 'succeeded'`); "drops a later-page job that no longer matches the state filter" (`['a','c','d']` vs `['a','d']`); "keeps loaded pages on a revalidation failure, backs off, and recovers" (`expected null to be 'page 2 offline'`).
  - GREEN: after the change, `npx vitest run --maxWorkers=2 src/hooks/useJobPages.test.tsx` -> 10 passed.
- GREEN, full: `npm run typecheck` clean; `npx vitest run --maxWorkers=2` -> 17 files / 83 tests passed; `npm run build` then `npm run check:bundle` -> "Dashboard bundle is current (3 files)"; dashboard pytest -> 41 passed; both grep checks passed; no Python files changed.
- Bundle: the JS asset is now `index-Bzb6iCOd.js` (CSS unchanged, `index-BUWCTkN_.css`).
- Root cause (bugfix only): revalidation was gated on the first-page cursor changing, so later-page changes that left the cursor unchanged were never refetched.
