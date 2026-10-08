# Phase 5: Specification fix batch 1

This is automatic fix cycle 1 of at most 2. Preserve the existing Phase 5 implementation, RED/GREEN and failed baseline records, completed Phases 1-4, and the original phase base. Read authoritative prompt.md and current journal.md. No independent quality review has occurred yet.

## Confirmed specification gaps

1. `web/src/screens/Jobs.jsx:61` still resolves `[]` when no project is selected, contrary to the finalized grouped empty-shape requirement. Use `{active:[], recent:[], more_recent:0}` and retain project-selected behavior and polling rules. No legacy array fallback or global endpoint.
2. Jobs and ProjectDetail tables render access_mode and waiting_reason but not complete depends_on and waiting_on metadata. The runtime reason names only the first blocker; a job with several dependencies loses the remaining IDs from the lists, and a job whose dependencies already succeeded exposes none of its dependency IDs there. Render compact complete dependency/waiting IDs in each existing table, without new components or navigation/pagination features. Reuse the existing row-rendering patterns. Shared JobDetails already renders all four fields and must remain unchanged.

Add focused regressions with multiple depends_on/waiting_on IDs in both tables and completed-dependency metadata. RED must establish the missing list evidence before source edits.

## Reader-draft conflict hypothesis

H1: RuntimeSettings preserves readerDraft when a background/explicit refresh changes settings, but saveReaderCapacity takes `settings?.revision` from the newest response rather than the draft's originating revision. Predict: initial capacity1/revisionA, user draft5, refresh capacity2/revisionB, then Save submits `(5, B)` instead of `(5, A)` and can overwrite the concurrent edit without a conflict. Existing App.test.jsx:85-121 forces a409 response but never asserts the submitted revision after refresh, so it does not confirm correct optimistic concurrency.

Reproduce dynamically in the existing App test before changing this source. Wait for the refreshed settings to be actually committed, not merely getSettings called, then assert the update's revision. If H1 is confirmed, retain the revision associated with the draft through dirty refreshes; only a deliberate reload or successful save may rebase it. Follow existing editor revision/draft patterns where possible. Do not erase dirty input or automatically clear a conflict after refresh. Explicit reload must display the fetched value AND bind the same fetched revision; avoid two GET results being combined into mismatched value/revision. Add RED/GREEN for refresh-preserved revision,409 retention, and successful explicit reload. If H1 is refuted, record exact reproduction/evidence and do not implement speculative handling.

## Allowed writes

Only these paths, plus build-generated assets and worker-owned notes/journal:

- web/src/screens/Jobs.jsx
- web/src/screens/ProjectDetail.jsx
- web/src/screens/RuntimeSettings.jsx, only after confirmed regression
- web/src/screens/Jobs.test.jsx
- web/src/screens/ProjectDetail.test.jsx
- web/src/App.test.jsx
- src/openmcp/dashboard_static/**, only through declared build
- docs/plans/mcp-v2-claude-code/phase-05/notes.md
- docs/plans/mcp-v2-claude-code/phase-05/journal.md

Dashboard/models/runtime/scheduler/database/MCP server/API helpers and all other files remain read-only. Do not modify unrelated Profiles/Targets/editor/modal behavior or act warnings. Do not rewrite earlier worker ERP blocks or Coordinator records. The Coordinator corrected the job metadata; this was an OpenMCP implementation job, not direct implementation.

## Fresh verification

Record focused RED before fixes, then GREEN, then rerun all original checks with hard deadlines:

- timeout --kill-after=5s 180s uv run --extra dev pytest tests/test_dashboard.py -q
- timeout --kill-after=5s 180s npm --prefix web test
- timeout --kill-after=5s 180s npm --prefix web run build
- timeout --kill-after=5s 180s uv run --extra dev pytest -q
- git diff --check
- Snapshot the full generated asset directory outside the repository, build again, and require identical directories with diff -r, including new/untracked files and obsolete removals.

All source changes require confirmed RED. No Git writes, OpenMCP calls, daemon restart, installs/upgrades, live/global config/database/auth/session reads, Coordinator-file changes, or private execution identities. Return full ERP as before, including the hypothesis outcome and every modified path. Report any baseline flake recurrence separately; do not hide it by reporting only the final run.
