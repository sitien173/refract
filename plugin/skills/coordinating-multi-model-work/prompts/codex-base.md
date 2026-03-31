# Codex Base Prompt Templates

> Invoke via `mcp__codex__codex` (required: `PROMPT`, `cd`; optional: `sandbox`, `SESSION_ID`, `model`).
> All prompts in English. Every template ends with the Response Protocol block.

## Response Protocol Block (append to ALL prompts)

```
## Response Protocol
FIRST: Read Serena memory 'global/response_protocol' for full format rules.
FALLBACK: You respond to an orchestrator agent, NOT a human. NO thinking narration, NO restating context, NO full file rewrites. Use the output format below.
```

---

## Analysis Template

```
## Context
{task_context}

## Code Location
File: {file_path}
Lines: {start_line}-{end_line}

Note: Use your CLI tools to read the file at the specified location.

## Focus
1. Algorithm correctness and boundary handling
2. Data flow through the system
3. Performance (time/space complexity, bottlenecks)
4. Security (input validation, access control, data protection)

## Response Protocol
FIRST: Read Serena memory 'global/response_protocol' for full format rules.
FALLBACK: You respond to an orchestrator agent, NOT a human. NO thinking narration, NO restating context, NO full file rewrites.
Output: ## ANALYSIS (≤200 words, bullets) → ## DIFF (changed hunks only) → ## ISSUES (≤5, one line each) → ## VERDICT (one sentence).
```

## Debugging Template

```
## Bug
{bug_description}

## Location
File: {file_path}
Lines: {start_line}-{end_line}

## Error
{error_message}

Note: Use your CLI tools to read the file at the specified location.

## Required
1. Root cause (not symptoms)
2. Causation chain (direct → indirect → root)
3. Fix as unified diff patch

## Response Protocol
FIRST: Read Serena memory 'global/response_protocol' for full format rules.
FALLBACK: You respond to an orchestrator agent, NOT a human. NO thinking narration, NO restating context.
Output: ## ANALYSIS (root cause in ≤200 words) → ## DIFF (fix as changed hunks only) → ## ISSUES (prevention measures, ≤5) → ## VERDICT (one sentence).
```

## Code Review Template

```
## Files
{file_list_with_line_ranges}

## Changes
{change_summary}

Note: Use your CLI tools to read the files at the specified locations.

## Review Focus
1. Correctness — logic errors, boundary conditions, error handling
2. Performance — N+1 queries, unnecessary allocations, complexity
3. Security — injection, validation, data protection
4. Maintainability — naming, structure, DRY

## Response Protocol
FIRST: Read Serena memory 'global/response_protocol' for full format rules.
FALLBACK: You respond to an orchestrator agent, NOT a human. NO thinking narration, NO restating context.
Output: ## VERDICT (APPROVE|CHANGES_REQUESTED) → ## FINDINGS ([Critical|Important|Minor] file:line — description) → ## SUGGESTED_FIXES (diff patches).
```

## Implementation Template

```
## Task
{task_description}

## Code Location
File: {file_path}
Lines: {start_line}-{end_line}

Note: Use your CLI tools to read the file at the specified location.

## Requirements
1. {requirement_1}
2. {requirement_2}
3. {requirement_3}

## Response Protocol
FIRST: Read Serena memory 'global/response_protocol' for full format rules.
FALLBACK: You respond to an orchestrator agent, NOT a human. NO thinking narration, NO restating context.
Output: ## APPROACH (≤100 words) → ## DIFF (changed hunks only) → ## VERIFY (commands to run) → ## ISSUES (limitations/risks).
```

## Design Evaluation Template

```
## Proposal
{design_proposal}

## Constraints
{constraints}

## Evaluate
1. Architecture — component division, dependencies, design principles
2. Scalability — extensibility, future requirements, over-engineering risk
3. Reliability — failure handling, data consistency
4. Feasibility — technical challenges, dependency risks

## Response Protocol
FIRST: Read Serena memory 'global/response_protocol' for full format rules.
FALLBACK: You respond to an orchestrator agent, NOT a human. NO thinking narration, NO restating context.
Output: ## ANALYSIS (≤200 words) → ## ISSUES (risks with mitigations, ≤5) → ## VERDICT (one sentence).
```

## Test Generation Template

```
## Code Under Test
File: {file_path}
Lines: {start_line}-{end_line}
Framework: {test_framework}

Note: Use your CLI tools to read the file at the specified location.

## Coverage Scope
1. Normal paths
2. Boundary conditions
3. Error handling
4. Edge cases

## Response Protocol
FIRST: Read Serena memory 'global/response_protocol' for full format rules.
FALLBACK: You respond to an orchestrator agent, NOT a human. NO thinking narration, NO restating context.
Output: ## APPROACH (≤100 words) → ## DIFF (test code as unified diff) → ## VERIFY (commands to run tests) → ## ISSUES (uncovered scenarios).
```
