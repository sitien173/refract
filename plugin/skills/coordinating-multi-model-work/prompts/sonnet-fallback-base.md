# Sonnet Fallback Prompt Template

> Invoke via `Agent` tool with `model: "sonnet"`.
> Used when Gemini fails once and Codex is not viable, or when Codex fails after one retry.
> Subagent edits files directly using Edit/Write/Bash tools.

## Phase Implementation Template

```text
## Original User Request
{compressed_user_request}

## Phase Context Bundle
TASK_ID: {task_id}

## Context Refs
{context_refs}

## Hydrated Context
{hydrated_context}

## CP1 Phase Summary
{task_summary}

## Files
{file_list}

## Success Criteria
{success_criteria}

## Reviewer Checklist
{reviewer_checklist}

## Integration Checks
{integration_checks}

## Instructions
You are a fallback implementation worker. The primary MCP route failed or was not viable, so you are implementing this phase directly.

Rules:
- Read each file before editing it.
- Use the Edit tool for targeted changes, Write tool for new files.
- Run the integration checks via Bash when done.
- Report what you changed and whether the integration checks passed.
- Do not create documentation, tests, or refactors beyond what the success criteria require.
- Do not add comments, type annotations, or error handling beyond scope.
```
