# Gemini Base Prompt Templates

> Invoke via `mcp__gemini__gemini`.
> All prompts in English.
> Keep prompts narrow.

## Prompt Discipline

Follow these rules when filling in the template below:

- `{hydrated_context}` contains excerpts from **existing files only**. Never pre-write new file contents here.
- For greenfield or scaffold tasks with no relevant existing code: set `{hydrated_context}` to the existing directory structure only (e.g. `ls` output), or omit it entirely.
- `{hydrated_context}` **limit**: 300 tokens (hard — over this means you are over-specifying; narrow before sending).
- Tier 1 initial-call prompts: **target** ≤ 1500 tokens.
- Tier 2 same-phase follow-up prompts: **target** ≤ 400 tokens (deltas only).
- Tier 3 cross-phase continuation prompts: **target** ≤ 600 tokens.
- "Target" = soft goal; if you exceed it, narrow the phase or shrink hydrated snippets. "Limit" = hard ceiling; do not exceed.
- `{compressed_user_request}` is one or two sentences — the what and the constraint, not the how.
- `{task_summary}` is the phase summary sentence verbatim — not a re-expanded spec.
- `{file_list}` is a flat list of file paths — not file contents.
- Fold context references into `{hydrated_context}` instead of sending a separate context-refs section.
- `Done When` replaces separate `Success Criteria` and `Reviewer Checklist` sections.
- Use at most 2 Tier-2 follow-ups per phase. If the phase still fails after that, re-scope or escalate.
- Let Gemini decide implementation details. It knows standard patterns for common UI stacks.
- Use Gemini only for UI-heavy phases. If the MCP call fails, output `BLOCKED`; do not retry or switch executors.

**Anti-pattern (do not do this):**
```
## Hydrated Context
### App.tsx
export default function App() { return <div className="...">...</div> }
### tailwind.config.ts
const config: Config = { content: [...], theme: { extend: {} } }
```

**Correct — greenfield task:**
```
## Hydrated Context
Existing directory: src/ is empty. Tailwind and Vite are already configured.
```

**Correct — modification task:**
```
## Hydrated Context
- src/components/Button.tsx: uses `variant` prop with "primary" | "ghost" union type
- Color tokens defined in tailwind.config.ts under theme.extend.colors
```

## Tier 1: Initial Call

```text
## Task
{compressed_user_request}

## Phase
TASK_ID: {task_id}
SESSION_POLICY: FRESH
{task_summary}

## Context
{hydrated_context}

## Files
{file_list}

## Done When
- [ ] {done_when_items}

## Response Protocol
Use exactly this structure:

# EXTERNAL RESPONSE PROTOCOL v1.1

## SUMMARY
One-sentence summary of what you did.

## FILES MODIFIED
| Action  | File Path          | Description of Change |
|---------|--------------------|-----------------------|
| Created | src/...            | ...                   |
| Edited  | src/...            | ...                   |

## CONTEXT ARTIFACTS
Optional reusable artifacts discovered or updated during execution.

## SPEC COMPLIANCE
- Meets Spec? YES / WITH_DEBT / NO
- Explanation: ...

## CLARIFICATIONS NEEDED
None (or list questions)

## NEXT STEPS / CONTINUATION
TASK_COMPLETE / CONTINUE_SESSION / HANDOVER_TO_CLAUDE
```

## Tier 2: Same-Phase Follow-Up

```text
SESSION_ID: {session_id}
FIX: {fix}
DELTA_FILES: {delta_files}
DELTA_CONTEXT: {delta_context}
Respond using ERP v1.1
```

## Tier 3: Cross-Phase Continuation

```text
SESSION_ID: {session_id}
SESSION_POLICY: CONTINUE
PHASE: {task_id}

## New Phase
{task_summary}

## New/Changed Files
{delta_files}

## Delta Context
{delta_context}

## Done When
- [ ] {done_when_items}

Respond using ERP v1.1
```

## Narrow Analysis Template

```text
## Question
{narrow_question}

## Files
{file_list}

## Response Protocol
Output exactly: ## ANALYSIS (<=120 words) → ## ISSUES (<=3) → ## VERDICT (one line).
```
