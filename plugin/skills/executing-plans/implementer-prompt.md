# Implementer Prompt Template

Use when dispatching Codex or Gemini worker for one phase.

By default, write the prompt body to `docs/plans/<slug>/prompts/phase-<N>.md` (or per-task `phase-<N>.task-<M>.md` for fan-out) and pass that file path to the worker. Only inline the prompt in MCP `PROMPT` when it is one or two sentences with no context block.

```text
External model call:
  target: mcp__codex__codex (back-side) or mcp__gemini__gemini (front-side)
  description: "Implement Phase N: [phase name]"
  prompt: |
    Read your full task spec from: docs/plans/<slug>/prompts/phase-<N>.md
    Plan dir: docs/plans/<slug>
    Phase: <N>
    Owner: codex | gemini
    Follow every rule in the spec file. Emit the completion line when done.
```

## Prompt file contents (`docs/plans/<slug>/prompts/phase-<N>.md`)

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
  3. Write `docs/plans/<slug>/notes/phase-<N>.task-<M>.md` (decision note)
     with sections: Decisions made (not in spec), Spec deviations, Tradeoffs
     accepted, Assumptions, Follow-ups for human. Use `- none` for empty sections.
  4. Append this task's row to `## COMMITS` in your response.

## After All Tasks
- Write `docs/plans/<slug>/responses/phase-<N>.md` containing the full
  `# EXTERNAL RESPONSE` block (same content you return inline).
- Emit the completion line as the final line of your reply (see Report Format).

## Report Format
# EXTERNAL RESPONSE

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

## SPEC COMPLIANCE
- Meets Spec? YES | WITH_DEBT | NO
- Explanation: [one line]

## CLARIFICATIONS NEEDED
None (or list questions)

## NEXT
TASK_COMPLETE | CONTINUE_SESSION | HANDOVER_TO_CLAUDE

---
Phase <N> completed. Commit hashes: ["<hash1>", "<hash2>"]. SessionID: "<id>". Note files: ["docs/plans/<slug>/notes/phase-<N>.task-1.md", ...]. Response file: docs/plans/<slug>/responses/phase-<N>.md.
```

## Prompt discipline

- Default: prompt body lives in `prompts/phase-<N>.md`; MCP `PROMPT` field is a pointer.
- Inline allowed only for trivial one- or two-sentence asks with no context.
- Same-phase fix: reuse `SESSION_ID`, send `FIX:` + delta files + delta context only. Fix still produces its own commit + (if it changes a decision) appended note section.
- One phase, one owner. Never send whole plan to worker.
