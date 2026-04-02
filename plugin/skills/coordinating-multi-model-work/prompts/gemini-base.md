# Gemini Base Prompt Templates

> Invoke via `mcp__gemini__gemini`.
> All prompts in English.
> Keep prompts narrow.

## Bounded Implementation Template

```text
## Original User Request
{user_request}

## Context Package
{context_package}

## CP1 Task Summary
{task_summary}

## Files
{file_list}

## Success Criteria
{success_criteria}

## Verify
{verify_command}

## Response Protocol
FIRST: Read Serena memory 'global/response_protocol' for full format rules.
FALLBACK: Use exactly this structure:

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
FIRST: Read Serena memory 'global/response_protocol' for full format rules.
FALLBACK: Output ## ANALYSIS (<=120 words) → ## ISSUES (<=3) → ## VERDICT (one line).
```
