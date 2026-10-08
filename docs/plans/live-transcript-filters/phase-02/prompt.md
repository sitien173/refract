# Phase 2 Prompt: Add Transcript Filter Controls

Implement Phase 2 from `docs/plans/live-transcript-filters/DESIGN.md` and
`PLAN.md`. Follow `/home/ngosi/projects/superpowers-ccg/shared/worker-contract.md`.
Do not commit.

## Objective

Add accessible client-side Role and Content filters to Live transcript. Add the
stored submitted prompt as one User/Text entry, render safe normalized reasoning
summaries as Thinking, and distinguish Command disclosures from Tool Call
without changing stream persistence, ordering, connection behavior, or final
results.

## Existing dirty work

Preserve every unrelated uncommitted change. Existing work includes:

- Job Prompt Details API, component, tests, and CSS.
- Revised historical payload text in `JobTranscript` and its tests.
- Previously generated dashboard assets and index references.
- Untracked `.mcp.json` and `.playwright-mcp/` paths.

Do not overwrite, revert, reformat, or package those changes. Phase 2 may extend
shared frontend files only where required.

The focused Phase 2 baseline reported by consultation is 77 passing tests.
Existing React `act(...)` warnings are baseline noise. Do not broaden scope to
remove them.

## Allowed files

- `web/src/hooks/useJobStream.js`
- `web/src/hooks/useJobStream.test.jsx`
- `web/src/components/JobTranscript.jsx`
- `web/src/components/JobTranscript.test.jsx`
- `web/src/components/JobDetails.jsx`
- `web/src/components/JobDetails.test.jsx`
- `web/src/integration/dashboard-flow.test.jsx`
- `web/src/styles/app.css`
- `docs/plans/live-transcript-filters/phase-02/notes.md`
- `docs/plans/live-transcript-filters/phase-02/journal.md`

Do not modify Python, database, API models, generated static assets, package
metadata, configuration, or other plan files.

## Semantic item contract

Add these fields to content items produced by `reduceTranscriptEvents`:

```text
role: user | assistant
contentType: text | thinking | tool_call | command
```

Reducer-owned stream items use:

- Assistant messages: `role: "assistant"`, `contentType: "text"`.
- Explicit `assistant.reasoning_summary.delta`: `role: "assistant"`,
  `contentType: "thinking"`.
- New tool starts with exact `data.activity === "command"`:
  `role: "assistant"`, `contentType: "command"`.
- Every other tool start, including missing or unknown activity:
  `role: "assistant"`, `contentType: "tool_call"`.

Keep existing item types and lifecycle matching where practical. Do not infer
Command from provider, tool name, input, output, or substrings in the frontend.
Only exact normalized activity controls the category.

Reasoning summary deltas must merge only with the matching summary entity and
must never merge into assistant Text. Copy only `data.text`. Never copy generic
thinking, reasoning, chain-of-thought, diagnostics, prompts, or extra provider
fields.

## User prompt boundary

Pass exactly `job.prompt` from `JobDetails` to `JobTranscript` as a dedicated
`submittedPrompt` prop. Do not read any prompt from stream events, execution
plans, targets, expanded history, final results, provider objects, or
environment data.

Create one User/Text card for a captured transcript, before attempt rows. Preserve
the prompt exactly, including whitespace and line breaks. It appears once for
the job, never once per attempt.

Do not turn unavailable historical streams into synthetic User-only transcripts.
When `streamStatus === "unavailable"`, preserve the existing unavailable state
and do not render the User card. An empty prompt adds no User entry.

## Filters

Render two native checkbox groups using `fieldset`, `legend`, labeled checkboxes,
and visible labels:

- Role: User, Assistant.
- Content: Text, Thinking, Tool Call, Command.

Default enabled values:

- User: enabled.
- Assistant: enabled.
- Text: enabled.
- Thinking: disabled.
- Tool Call: enabled.
- Command: enabled.

Use OR within each group and AND across groups. A content entry is visible only
when its role and content type are both enabled. Keep filter state local to the
mounted transcript. Do not persist it or change API requests.

Filter content before building rows and before passing the row count to the
virtualizer. Keep chronological ordering unchanged. Include an attempt header
only when that attempt retains visible content or contains operational `notice`
or `truncated` rows. Operational notices remain structural and are not assigned
fabricated role or content metadata.

## Rendering

- User/Text: card labeled `User`, preserving prompt whitespace.
- Assistant/Text: preserve current streaming card behavior.
- Assistant/Thinking: card labeled `Thinking`, rendering only summary text.
- Assistant/Tool Call: native collapsed disclosure labeled `Tool`.
- Assistant/Command: native collapsed disclosure labeled `Command`.

Both disclosure categories preserve existing raw local Input and Output
formatting, inert text rendering, absent versus present null/falsy distinctions,
collapsed defaults, dynamic remeasurement, and historical missing-payload copy.

When a transcript exists but no content or structural rows match, display:

```text
No transcript entries match the current filters.
```

Provide a keyboard-accessible `Reset filters` button restoring the exact default
selection. This state must remain distinct from transcript unavailable.

## Follow-live and virtualization

Filter changes must not alter `isFollowing`. In particular:

- Explicit upward navigation keeps following paused.
- Filter changes while paused never scroll the viewport.
- `Jump to live` alone resumes following.
- Visible Text and Thinking growth may scroll only while following is active.
- Dynamic disclosure heights remain measured.
- Later rows do not overlap expanded rows.
- Mounted rows remain bounded.
- The bounded fallback uses the filtered rows.

Include Thinking text length in the content signature. Filter toggles may change
row count, but must not implicitly resume following.

## TDD tasks

1. Run the focused baseline and record it.
2. Add failing reducer tests for Assistant/Text, Assistant/Thinking, exact
   Command activity, Tool Call defaults, unknown activity fallback, and forbidden
   reasoning-field exclusion.
3. Implement minimal reducer metadata and reasoning-summary merging.
4. Add failing JobDetails tests proving only exact stored `job.prompt` reaches
   the transcript and unavailable history remains unavailable.
5. Add failing component tests for native groups, exact defaults, role OR,
   content OR, cross-group AND, and a single User/Text card.
6. Add failing tests for Thinking, Command versus Tool labels, historical Tool
   Call fallback, filtered-empty text, and Reset filters.
7. Add failing tests proving filtering occurs before virtualization, mounted rows
   remain bounded, disclosures remeasure, and filtering preserves manual
   follow-live pause.
8. Add or extend the integrated Job Detail flow for the stored prompt, normalized
   categories, filtering, and security exclusions.
9. Implement the minimum component, prop, and CSS changes.
10. Run all Phase 2 verification checks and record RED to GREEN evidence.

Record one `## Task <N>` block per task in `notes.md`. Append the required ERP
response under `## Implementation Response` in `journal.md`.

## Security invariants

- Only stored `job.prompt` becomes User/Text.
- Expanded prompt history and target system prompts remain hidden.
- Generic thinking, reasoning, chain-of-thought, diagnostics, and arbitrary
  provider fields remain hidden.
- Frontend Command classification trusts only exact normalized `activity`.
- Unknown or missing activity remains Tool Call.
- Tool payloads remain inert text and retain exact presence semantics.
- Filtering never changes durable data, API pagination, SSE, reconnect, quotas,
  retention, truncation, or authoritative final results.

## Done When

```bash
npm --prefix web test -- \
  src/hooks/useJobStream.test.jsx \
  src/components/JobTranscript.test.jsx \
  src/components/JobDetails.test.jsx \
  src/integration/dashboard-flow.test.jsx

npm --prefix web test -- --poolOptions.threads.maxThreads=2

git diff --check -- \
  web/src/hooks/useJobStream.js \
  web/src/hooks/useJobStream.test.jsx \
  web/src/components/JobTranscript.jsx \
  web/src/components/JobTranscript.test.jsx \
  web/src/components/JobDetails.jsx \
  web/src/components/JobDetails.test.jsx \
  web/src/integration/dashboard-flow.test.jsx \
  web/src/styles/app.css
```

Confirm all checks pass. Confirm only allowed files changed during Phase 2.
Report changed files, RED and GREEN evidence, security checks, preserved existing
work, warnings, skipped checks, and remaining debt.
