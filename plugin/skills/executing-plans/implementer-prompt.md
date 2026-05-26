# Implementer Prompt Template

Use when dispatching Codex or Gemini worker for one phase.

By default, write the prompt body to `docs/plans/<slug>/phase-<NN>/prompt.md` (zero-padded phase id) and pass that file path to the worker. Only inline the prompt in MCP `PROMPT` when it is one or two sentences with no context block.

**Absolute paths required.** Resolve `docs/plans/<slug>/...` to an absolute path before sending it through `mcp__openmcp__run`. Gemini (agy) does not reliably resolve relative paths against Claude's CWD and will scan the device looking for the file. Use forward slashes on Windows (e.g. `F:/projects/<repo>/docs/plans/<slug>/phase-01/prompt.md`). Pass the `cd` argument as an absolute path as well, and make every file path inside the prompt body (inputs, outputs, notes, journal, plan dir) absolute.

```text
External model call:
  target: mcp__openmcp__run with backend="codex" (back-side) or backend="agy" (front-side, Gemini)
  description: "Implement Phase N: [phase name]"
  cd: <ABSOLUTE repo root, e.g. F:/projects/<repo>>
  prompt: |
    Read your full task spec from: <ABSOLUTE>/docs/plans/<slug>/phase-<NN>/prompt.md
    Plan dir: <ABSOLUTE>/docs/plans/<slug>
    Phase dir: <ABSOLUTE>/docs/plans/<slug>/phase-<NN>
    Phase: <N>
    Owner: codex | gemini
    Follow every rule in the spec file. Emit the completion line when done.
    All file paths in this prompt and in the spec file are absolute — do not reinterpret them as relative.
```

## Prompt file contents (`docs/plans/<slug>/phase-<NN>/prompt.md`)

```markdown
You own one implementation phase with 2–4 related tasks.

## Original User Request
[one or two compressed sentences]

## Phase
[phase summary — one sentence]

## Tasks
- task-1: <one line>
- task-2: <one line>
- task-3: <one line>

## Context
[small snippets from existing files only — no pre-written implementation]

## Files
[flat list of file paths]

## Done When
- [acceptance criterion]
- [integration check command]

## Rules
- Edit files directly with your write tools; on-disk files are the source of truth.
- Do not duplicate file content in the response.
- Do not redesign the phase or produce a reference prototype.
- If anything is unclear, list it under CLARIFICATIONS NEEDED and stop.
- Context excerpts are reference only — never pre-write new file contents in the prompt.

## Per-Task Workflow (required)
For each task in order:
  1. Implement the task.
  2. `git add` only files you touched for this task and commit with message
     `phase-<N>.task-<M>: <one-line subject>`. Capture the commit hash.
  3. Append a `## Task <M>` block to `<ABSOLUTE>/docs/plans/<slug>/phase-<NN>/notes.md`
     with sub-sections: Decisions made (not in spec), Spec deviations, Tradeoffs
     accepted, Assumptions, Follow-ups for human. Use `- none` for empty sub-sections.
     If notes.md does not exist yet, create it with a `# Phase <N> — Decision Notes` heading first.
  4. Append this task's row to `## COMMITS` in your response.

## After All Tasks
- Append the full `# EXTERNAL RESPONSE` block (same content you return inline)
  under the `## External Response` heading of
  `<ABSOLUTE>/docs/plans/<slug>/phase-<NN>/journal.md`. Do not overwrite earlier sections.
- Emit the completion line as the final line of your reply (see Report Format).

## Report Format
# EXTERNAL RESPONSE

## META
- Phase: <N>
- Owner: codex | gemini
- SessionID: <your current session id>
- Started: <ISO8601 when you began the phase>
- Finished: <ISO8601 when you finished>
- Plan dir: docs/plans/<slug>
- Phase dir: docs/plans/<slug>/phase-<NN>

## SUMMARY
[one sentence]

## FILES MODIFIED
| Action  | Path     | Change |
|---------|----------|--------|
| Created | src/...  | ...    |
| Edited  | src/...  | ...    |

## COMMITS
- phase-<N>.task-1: <hash>  <subject>
- phase-<N>.task-2: <hash>  <subject>

## NOTES
- docs/plans/<slug>/phase-<NN>/notes.md  (## Task 1, ## Task 2, …)

## SPEC COMPLIANCE
- Meets Spec? YES | WITH_DEBT | NO
- Explanation: [one line]

## CLARIFICATIONS NEEDED
None (or list questions; emit and stop if any)

## NEXT
TASK_COMPLETE | CONTINUE_SESSION | HANDOVER_TO_CLAUDE

---
Phase <N> completed. Journal: docs/plans/<slug>/phase-<NN>/journal.md.
```

## Prompt discipline

- Default: prompt body lives in `phase-<NN>/prompt.md`; MCP `PROMPT` field is a pointer.
- All paths handed to MCP workers (the pointer, `cd`, and every file path inside the prompt body) must be absolute with forward slashes. Relative paths are forbidden — Gemini will mis-resolve them.
- Inline allowed only for trivial one- or two-sentence asks with no context.
- Same-phase fix: reuse `SESSION_ID`, send `FIX:` + delta files + delta context only. Fix still produces its own commit + (if it changes a decision) appended task-block in `notes.md`.
- One phase, one owner. Never send whole plan to worker.
