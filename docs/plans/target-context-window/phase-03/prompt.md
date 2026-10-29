## User Request
Complete the approved target-context-window plan, working in place on main.

## Phase
3: Expose capacity editing and explain telemetry estimates.

## Tasks
- task-1: Test-first optional context capacity editing, strict integer validation, clearing and hydration safety.
- task-2: Test-first estimated context explanation and server measurement rendering.
- task-3: Document configuration precedence, clearing and estimation limitations.

## Context
Read /home/ngosi/projects/refract/docs/plans/target-context-window/DESIGN.md and PLAN.md Phase 3 completely. Phases 1 and 2 are accepted at their refs. API public key contextWindow is optional positive integer or null. Omitted updates preserve; explicit null clears. Server resolves capacity override, provider snapshots, then qualified estimated cumulative input plus output. Configured capacity source target_config quality reported; fallback source derived quality estimated. Do not compute percentages in frontend.

TargetEditor.jsx must add string state to initialForm, edit hydration, conflict reload, payload and labeled optional input. Blank submits null. Do not use coercive parseInt/rounding or silently convert invalid values to zero. Validate Number.isSafeInteger and positive value before submission; reject decimals, negatives, zero and unsafe integers. Native min=1 step=1 plus custom guard should coexist. Preserve drafts under polling and conflicts. Existing exact create-payload assertion in Targets.test.jsx must gain contextWindow:null.
JobDetails TelemetryRow already renders quality/source badges. Add visible caption only for server-qualified estimated cumulative context, not all provider snapshots or estimated consumption. Caption identifies cumulative job input plus output and possible overcounting across turns, retries and compaction. Preserve historical/absent measurements and unknown remaining. No aliases or formula.

Modern Web Guidance forms guide was retrieved by coordinator. Apply visible associated label and help description: "always associate `<label>` with its input using `for` and `id`"; "use `aria-describedby` to link inputs with help text or error messages". Keep scope surgical; no unrelated form rewrite. README prose follows STOW: factual precedence and qualification, no invented backend guarantees.

## Files
- server/web/src/components/TargetEditor.jsx
- server/web/src/components/JobDetails.jsx
- server/web/src/screens/Targets.test.jsx
- server/web/src/components/ConfigEditorSafety.test.jsx
- server/web/src/components/JobDetails.test.jsx
- server/README.md
- docs/plans/target-context-window/phase-03/notes.md
- docs/plans/target-context-window/phase-03/journal.md

## Done When
- All Phase 3 acceptance criteria and reviewer checks in PLAN.md pass.
- Tests cover integer create/edit, explicit null clearing, invalid numeric rejection, initial/edit/conflict reload hydration and dirty draft preservation.
- Tests cover estimated usage/remaining badges, precise explanatory text, provider snapshot exclusion, capacity without usage/remaining, legacy absent metadata.
- Valid [[targets]] TOML example includes contextWindow; docs cover optional clear, configured override, provider usage precedence, fallback requiring both totals, cache not added separately, estimation limitations, historical snapshot persistence.
- cd /home/ngosi/projects/refract/server && uv run pytest -q
- cd /home/ngosi/projects/refract/server/web && npm test
- cd /home/ngosi/projects/refract/server/web && npm run build -- --outDir /tmp/refract-target-context-window-baseline
- Build remains isolated and tracked packaged assets unchanged. Record actual RED/GREEN evidence per task and fresh full checks.

## Rules
Read and follow bundled files:
- Contract: /home/ngosi/projects/refract/plugin/shared/worker-contract.md
- Response: /home/ngosi/projects/refract/plugin/shared/erp.md
- Notes: /home/ngosi/projects/refract/plugin/shared/notes-template.md
- Journal: /home/ngosi/projects/refract/plugin/shared/journal-template.md
Do not mutate Git or edit plan/design/handover/other phase files. Only declared files may change. Leave docs/plans/worker-job-telemetry/ untouched. No secrets/runtime config, live probes, dependencies, adjacent refactors or production backend edits. Ask before expanding scope. Preserve notes/journal headings and prior evidence. Return full ERP # EXTERNAL RESPONSE and matching Phase 3 status line.
