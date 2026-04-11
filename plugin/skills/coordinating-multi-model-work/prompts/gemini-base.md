# Gemini Base Prompt Templates

> Invoke via `mcp__gemini__gemini`.
> All prompts in English.
> Keep prompts narrow.

## Prompt Discipline

Follow these rules when filling in the template below:

- `{hydrated_context}` contains excerpts from **existing files only**. Never pre-write new file contents here.
- For greenfield or scaffold tasks with no relevant existing code: set `{hydrated_context}` to the existing directory structure only (e.g. `ls` output), or omit it entirely.
- Keep `{hydrated_context}` under ~300 tokens. Exceeding this means you are over-specifying.
- `{compressed_user_request}` is one or two sentences — the what and the constraint, not the how.
- `{task_summary}` is the CP1 Task Summary sentence verbatim — not a re-expanded spec.
- `{file_list}` is a flat list of file paths — not file contents.
- Let Gemini decide implementation details. It knows standard patterns for common UI stacks.

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

## Bounded Implementation Template

```text
## Original User Request
{compressed_user_request}

## Task Context Bundle
TASK_ID: {task_id}

## Context Refs
{context_refs}

## Hydrated Context
{hydrated_context}

## CP1 Task Summary
{task_summary}

## Files
{file_list}

## Success Criteria
{success_criteria}

## Verify
{verify_command}

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

## FILE CONTENTS
For each file listed in FILES MODIFIED, return either:
1. the complete final file content (preferred), or
2. a unified diff patch if full content is impractical.

## CONTEXT ARTIFACTS
Optional reusable artifacts discovered or updated during execution.

## SPEC COMPLIANCE
- Meets Spec? YES / PARTIAL / NO
- Explanation: ...

## CLARIFICATIONS NEEDED
None (or list questions)

## NEXT STEPS / CONTINUATION
TASK_COMPLETE / CONTINUE_SESSION / HANDOVER_TO_CLAUDE
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
