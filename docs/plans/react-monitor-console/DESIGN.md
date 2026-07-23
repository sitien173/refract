# OpenMCP Monitor & Debug Console — Design

Status: CONFIRMED (design dialogue complete; implementation plan not yet written)
Date: 2026-07-23
Branch context: feat/web-dashboard

## Summary

Replace the Alpine.js static dashboard (`src/openmcp/dashboard_static/`) with a
React + Vite application, fully redesigned in the Flowforge product-shell style,
scoped to **monitoring and debugging only**. No configuration or task-guide
editing. No backend changes.

## Confirmed decisions

- **Framework:** React 19 + Vite + TypeScript.
- **Delivery:** Vite build committed into `src/openmcp/dashboard_static/`, served
  unchanged by the existing FastMCP `/dashboard` route and `/dashboard/assets`
  mount. `vite dev` proxies API calls to the daemon during development.
- **Offline:** vendor Libre Franklin `.woff2` and Lucide SVG icons locally; no CDN
  (matches the current vendored-asset pattern).
- **Scope:** all five read-only views — Overview (status), Jobs (+ job-detail /
  events debug), Projects, Targets, Profiles. Drop the config editor and
  task-guide editor entirely (frontend). Backend PUT endpoints are left untouched
  but unreferenced.
- **Real-time:** polling only, frontend-only. No new backend streaming.
- **Layout/IA:** Flowforge product shell — 200px sidebar + 64px top bar,
  aggregating Overview landing, job debug in a right-docked inspector with a live
  event timeline.
- **Data layer:** TanStack Query for polling, caching, dedup, pause-on-hidden.

## 1. Goals / non-goals / success criteria

- **Goal:** React+Vite monitor/debug console redesigned in Flowforge style.
- **Non-goals:** config editor, task-guide editor, backend/auth changes.
- **Success:** all five read-only views render with live polling; job debug
  inspector shows a live event timeline; committed build served unchanged by the
  existing route; works offline; light/dark parity.

## 2. Stack

React 19 + Vite + TypeScript · React Router · TanStack Query · Flowforge
`colors_and_type.css` tokens + CSS Modules · Lucide (vendored SVG) · Libre
Franklin (vendored woff2). No component library.

## 3. Architecture & layout

```
web/                      # new source (Vite root)
  index.html
  vite.config.ts          # base:'/dashboard/assets/', outDir -> ../src/openmcp/dashboard_static, dev proxy
  src/
    main.tsx, App.tsx
    styles/               # flowforge colors_and_type.css + tokens
    fonts/                # Libre Franklin woff2
    lib/api.ts            # typed fetch wrappers for /dashboard/api/*
    lib/queries.ts        # TanStack Query hooks + intervals
    lib/types.ts          # Job, Project, Target, Profile, Event, Status
    components/           # AppShell, Sidebar, TopBar, DataTable, StatusBadge, Inspector, EmptyState, ...
    views/                # Overview, Jobs, Projects, Targets, Profiles
```

Build output overwrites `src/openmcp/dashboard_static/`. `dashboard.py` route and
`/dashboard/assets` mount unchanged. Old `app.js`, `styles.css`,
`vendor/alpine.min.js` removed by the build replacement.

## 4. Routing & IA

- Routes: `/` Overview, `/jobs`, `/projects`, `/targets`, `/profiles`.
- Job debug: `/jobs?selected=<id>` opens a right-docked Inspector (slide-in,
  depth4) — header (id, workflow, state badge, base→result commit) + live event
  timeline polling `jobs/{id}/events` ~2s. Close restores list width.
- TopBar (64px): logo lockup, daemon status pill, worker/active/queued counts,
  last-updated, theme toggle.
- Sidebar (200px): five nav items; active item uses pale-green fill `#E5F0E8`.

## 5. Component mapping (Flowforge)

- Tables (Jobs, Projects, Targets): 44px header, 56px rows, subdued `#D2D2D2`
  grid, hover row `#F2F2F2`, Title Case headers.
- Status/state = color + Lucide icon + label (never color alone): DONE=success
  green, RUNNING=info blue, QUEUED=neutral, FAILED/CANCELLED=error red,
  circuit-open target=warn yellow.
- Overview tiles: neutral white panels, no decorative shadow; green reserved for
  healthy/active accents.
- Inspector / dialogs: white, 8px radius, depth4 docked / depth64 modal, 24px
  padding.
- Motion: 150ms hover/state, 250ms inspector slide. Blue `#0F748B` focus ring,
  never removed.

## 6. Data flow

TanStack Query hooks wrap each GET endpoint. `refetchInterval` ~3s for
status/targets/profiles/projects/jobs; ~2s for open job detail+events;
`refetchOnWindowFocus` + pause when `document.hidden`. Jobs aggregate across
projects (fetch projects, then each project's jobs, merge, sort by `created_at`
desc). Per-resource query keys for dedup/caching.

Endpoints consumed (all existing GET):
`/dashboard/api/status`, `/dashboard/api/projects`,
`/dashboard/api/projects/{id}/jobs`, `/dashboard/api/jobs/{id}`,
`/dashboard/api/jobs/{id}/events`, `/dashboard/api/targets`,
`/dashboard/api/profiles`.

## 7. Error / empty / loading

- Connection loss → TopBar pill flips to "disconnected"; last-known data stays
  visible (stale), not blanked.
- Empty states: Flowforge declarative sentence case ("No jobs found.").
- Per-panel error inline; a failed sub-fetch never blanks the whole page.

## 8. Theme

Light default. Toggle sets `data-theme="dark"` on root using the design system's
paired dark tokens. Preference persisted in `localStorage`.

## 9. Build & serve

- Dev: `vite dev` proxies `/dashboard/api/*` to `127.0.0.1:8765`.
- Prod: `vite build` emits hashed assets into `dashboard_static/assets/` + an
  `index.html` served by the existing `/dashboard` route. `base:
  '/dashboard/assets/'` so asset URLs resolve under the current mount.

## 10. Migration / cutover

Single cutover: new build replaces `dashboard_static/` contents. Backend routes
and asset mount unchanged; no Python edits. Config/task-guide PUT endpoints remain
but become unreferenced dead UI paths — left alone per surgical-change rules,
flagged not deleted.

## 11. Testing

- Unit/component: Vitest + React Testing Library — DataTable, StatusBadge,
  Inspector, polling hook (mock fetch).
- Build verification: `vite build` succeeds; `index.html` + assets land in
  `dashboard_static/`; daemon serves `/dashboard` and renders.
- Manual smoke: run daemon, submit a job, confirm live job list + event timeline.

## 12. Risks

- Asset base-path mismatch under `/dashboard/assets` (mitigate: `base` config +
  build-output check).
- Cross-project job aggregation is N+1 fetches; acceptable at current scale, note
  for later.
- Dark-mode per-surface parity is upstream "in progress"; flag surfaces that read
  poorly.

## Open follow-ups (deferred, not blocking)

- Formal Gate 1 OpenMCP `consult` was deferred: repo root was dirty with unknown
  changes (`.claude/.headroom_wrap_marker.json`, `.mcp.json`) that coordination
  rules forbid touching. Low architectural risk (frontend-only, read-only,
  design fully specified). Run a consult at plan time if root is clean.
