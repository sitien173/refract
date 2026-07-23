## Original User Request

Finalize the React monitor console plan.

## Phase

Cut over the generated dashboard and prove the shipped console works end to end.

## Tasks

- task-1: Rebuild production assets and audit the static output.
- task-2: Prove legacy Alpine and editor UI references are absent.
- task-3: Prove backend Python and existing PUT routes remain unchanged.
- task-4: Exercise the live daemon with a real durable job.
- task-5: Correct the documented light default using test-first changes.
- task-6: Verify packaging, offline assets, themes, tests, and HTTP serving.

## Context

Phases 1 through 4 implemented the React 19, Vite, TypeScript, and Flowforge
console. The current production build already lives under
`src/openmcp/dashboard_static/`. This final phase primarily verifies the shipped
result. Do not change backend Python. Leave existing config and task-guide PUT
routes intact but unreferenced by the React source and generated application.

The coordinator's consultation job is a valid real durable job for the live
dashboard smoke. The implementation job itself is also valid. Record the job
identifier used and prove it appears through the dashboard jobs and events
endpoints.

Consultation identified `a79b9308cad381323dff328fcc465eed8113cd73` as the
pre-Phase-1 baseline. Use it for the complete backend Python immutability check.
It also found that `web/index.html` and `ThemeToggle.tsx` currently select dark
from OS preference. The confirmed design says light is the default. Add failing
coverage, then make unstored initialization light regardless of OS preference.
Stored light and dark values must still restore. Both toggle directions and
persistence must remain covered.

## Files

- `src/openmcp/dashboard_static/`
- `docs/plans/react-monitor-console/phase-05/notes.md`
- `docs/plans/react-monitor-console/phase-05/journal.md`
- `web/` only when verification exposes a frontend defect
- `tests/test_dashboard.py` only for a required regression test

## Done When

- Production output contains only `index.html`, hashed assets, and fonts.
- `app.js`, `styles.css`, and `vendor/alpine.min.js` are absent.
- React source and generated UI contain no config editor.
- React source and generated UI contain no task-guide editor.
- Existing backend PUT routes remain present and unchanged.
- No backend Python differs from
  `a79b9308cad381323dff328fcc465eed8113cd73`.
- `/dashboard` and every referenced local asset return HTTP 200.
- Consultation job `10ae52fd-69db-47e3-ab0e-c94e7de3f488` appears in dashboard
  project jobs.
- That job has dashboard-visible detail and lifecycle events.
- Unstored theme initialization is light regardless of OS preference.
- Stored light and dark values restore correctly.
- Both theme toggle directions and persistence have fresh coverage.
- Runtime application assets contain no external CDN dependencies.
- A fresh wheel contains the complete generated dashboard.
- The wheel contains no `web/` development source.
- `npm --prefix web test -- --run`
- `npm --prefix web run build`
- `uv run pytest tests/test_dashboard.py`
- `uv build`
- `git diff --check`
- `git status --porcelain src/openmcp`
- `git diff --stat -- 'src/openmcp/*.py'`

## Rules

Follow the supplied worker contract. Stay within scope. Maintain this phase's
`notes.md` and `journal.md`. Do not delete backend routes. Do not add streaming,
configuration, or task-guide UI. Treat minified React documentation URLs as
library diagnostics, not runtime CDN dependencies.

## Response Format

Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
