# Phase 3 Prompt: Package and Verify Transcript Filters

Implement Phase 3 from `docs/plans/live-transcript-filters/DESIGN.md` and
`PLAN.md`. Follow `/home/ngosi/projects/superpowers-ccg/shared/worker-contract.md`.
Do not commit.

## Objective

Rebuild the packaged dashboard from the current frontend working tree. Verify
backend, frontend, generated assets, and the real Job Detail route. Preserve all
approved transcript behavior and security boundaries.

## Existing dirty work

Preserve every unrelated uncommitted change. Existing work includes:

- Job Prompt Details API, component, tests, and CSS.
- Revised historical payload text in `JobTranscript` and its tests.
- Previously generated dashboard assets and index references.
- Untracked `.mcp.json` and `.playwright-mcp/` paths.

The current generated assets contain Prompt Details and revised missing-payload
copy, but omit Phase 2 transcript filters. They are stale. Rebuild them from the
current source. Do not overwrite, revert, reformat, or edit source files to make
packaging pass.

Protect these dirty frontend files with pre-build and post-build SHA-256 checks:

- `web/src/components/JobDetails.jsx`
- `web/src/components/JobDetails.test.jsx`
- `web/src/components/JobTranscript.jsx`
- `web/src/components/JobTranscript.test.jsx`
- `web/src/styles/app.css`

## Allowed files

- `src/openmcp/dashboard_static/index.html`
- `src/openmcp/dashboard_static/assets/`
- `docs/plans/live-transcript-filters/phase-03/notes.md`
- `docs/plans/live-transcript-filters/phase-03/journal.md`

Do not modify application source, tests, package metadata, lockfiles,
configuration, other plan files, `.mcp.json`, or `.playwright-mcp/`.

## Tasks

1. Record the current generated asset names and SHA-256 hashes for the protected
   dirty frontend source files.
2. Run the production dashboard build exactly once from the current working tree.
   Do not delete generated files manually. Vite owns the output directory.
3. Recompute the protected source hashes. Confirm every source file is unchanged.
4. Confirm `dashboard_static/index.html` references only generated current hashes.
5. Confirm old hashed JavaScript and CSS assets are absent.
6. Confirm the generated JavaScript contains filter, Prompt Details, and
   missing-payload strings. Confirm generated CSS contains their selectors.
7. Run the full backend suite and complete frontend suite.
8. Record packaging and verification evidence in `notes.md` and `journal.md`.
9. Leave daemon restart, Playwright interaction, Git staging, commits, and
   independent review to the coordinator.

## Browser verification contract

The coordinator will restart the local daemon and verify this route:

```text
http://127.0.0.1:8765/dashboard/projects/ad9a3a2d-4583-4ac7-a954-ba21c7162055/jobs/a41dab52-ca27-4139-b982-f990eaab4de8
```

Desktop and narrow checks must cover:

- Role checkboxes: User and Assistant.
- Content checkboxes: Text, Thinking, Tool Call, and Command.
- Exact approved default selections.
- OR behavior within each group.
- AND behavior across groups.
- Filtered-empty message and Reset filters.
- Command and Tool Call collapsed disclosures.
- Expanded raw local Input and Output when captured.
- Explicit missing-payload text for unavailable historical values.
- Follow-live pause preservation after upward navigation.
- Keyboard and pointer accessibility.
- No unexpected browser console errors.

## Security invariants

- Only stored `jobs.prompt` may render as User/Text.
- Target system prompts remain hidden.
- Expanded history and `execution_plan.raw_prompt` remain hidden.
- Environment contents remain hidden.
- Diagnostics and provider internals remain hidden.
- Generic thinking, reasoning, and chain-of-thought remain hidden.
- Thinking may render explicit provider summaries only.
- Command classification remains exact and provider-backed.
- Tool payloads remain inert text with property-based presence semantics.
- Historically discarded payloads remain unrecoverable.

## Done When

```bash
npm --prefix web run build
uv run pytest -q
npm --prefix web test -- --poolOptions.threads.maxThreads=2
git diff --check
```

Confirm the build exits successfully. Confirm tests report zero failures. Confirm
only allowed files changed during worker execution. Report generated hashes,
stale files removed, unchanged protected-source hashes, bundle string and selector
checks, warnings, skipped checks, and debt.

## Rules

Follow the supplied worker contract. Stay within scope. Maintain this phase's
`notes.md` and `journal.md`. Return the ERP `# EXTERNAL RESPONSE` block and
matching status line.
