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

The current generated assets may already include these changes. Rebuild them from
the current source. Do not overwrite, revert, reformat, or edit source files to
make packaging pass.

## Allowed files

- `src/openmcp/dashboard_static/index.html`
- `src/openmcp/dashboard_static/assets/`
- `docs/plans/live-transcript-filters/phase-03/notes.md`
- `docs/plans/live-transcript-filters/phase-03/journal.md`

Do not modify application source, tests, package metadata, lockfiles,
configuration, other plan files, `.mcp.json`, or `.playwright-mcp/`.

## Tasks

1. Record the current generated asset names and dirty source paths.
2. Run the production dashboard build once from the current working tree.
3. Confirm `dashboard_static/index.html` references only generated current hashes.
4. Confirm old hashed JavaScript and CSS assets are absent.
5. Run the full backend suite and complete frontend suite.
6. Record packaging and verification evidence in `notes.md` and `journal.md`.
7. Leave daemon restart, Playwright interaction, Git staging, commits, and
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
stale files removed, source paths preserved, warnings, skipped checks, and debt.

## Rules

Follow the supplied worker contract. Stay within scope. Maintain this phase's
`notes.md` and `journal.md`. Return the ERP `# EXTERNAL RESPONSE` block and
matching status line.
