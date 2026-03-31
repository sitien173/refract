# Gemini Base Prompt Templates

> Invoke via `mcp__gemini__gemini` (required: `PROMPT`; optional: `sandbox`, `SESSION_ID`, `model`).
> All prompts in English. Every template ends with the Response Protocol block.
> Gemini has an effective context limit of ~32k tokens — keep prompts focused.

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
1. Component structure and composition patterns
2. User interaction and feedback
3. Visual consistency and responsive design
4. Rendering performance
5. Accessibility (keyboard, screen reader, contrast)

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

## User-Visible Behavior
{user_feedback}

Note: Use your CLI tools to read the file at the specified location.

## Required
1. Which component/module is affected
2. Root cause (not symptoms)
3. Fix as unified diff patch

## Response Protocol
FIRST: Read Serena memory 'global/response_protocol' for full format rules.
FALLBACK: You respond to an orchestrator agent, NOT a human. NO thinking narration, NO restating context.
Output: ## ANALYSIS (root cause in ≤200 words) → ## DIFF (fix as changed hunks only) → ## ISSUES (≤5) → ## VERDICT (one sentence).
```

## Code Review Template

```
## Files
{file_list_with_line_ranges}

## Changes
{change_summary}

Note: Use your CLI tools to read the files at the specified locations.

## Review Focus
1. Component design — single responsibility, reusability, props API
2. UX — loading/error/empty states, interaction smoothness
3. Styles — design system compliance, responsive breakpoints, conflicts
4. Performance — unnecessary re-renders, memo usage, resource loading
5. Accessibility — semantic HTML, ARIA, keyboard operability

## Response Protocol
FIRST: Read Serena memory 'global/response_protocol' for full format rules.
FALLBACK: You respond to an orchestrator agent, NOT a human. NO thinking narration, NO restating context.
Output: ## VERDICT (APPROVE|CHANGES_REQUESTED) → ## FINDINGS ([Critical|Important|Minor] file:line — description) → ## SUGGESTED_FIXES (diff patches).
```

## Component Implementation Template

```
## Component
{component_requirements}

## Design Reference
{design_reference}

## Tech Stack
Framework: {framework}
Styling: {styling}
State: {state_management}

## Requirements
1. Single responsibility, clear props API with types
2. Handle loading, error, and empty states
3. Support keyboard and screen readers
4. Responsive across breakpoints

## Response Protocol
FIRST: Read Serena memory 'global/response_protocol' for full format rules.
FALLBACK: You respond to an orchestrator agent, NOT a human. NO thinking narration, NO restating context.
Output: ## APPROACH (≤100 words) → ## DIFF (component code as unified diff) → ## VERIFY (how to test visually) → ## ISSUES (limitations/risks).
```

## UI Design Evaluation Template

```
## Proposal
{design_proposal}

## Constraints
{constraints}

## Evaluate
1. Visual hierarchy — information priority, emphasis, guidance
2. Interaction — operation flow, feedback, mental models
3. Responsive — breakpoint adaptation, touch targets, content priority
4. Consistency — design system compliance, pattern reuse

## Response Protocol
FIRST: Read Serena memory 'global/response_protocol' for full format rules.
FALLBACK: You respond to an orchestrator agent, NOT a human. NO thinking narration, NO restating context.
Output: ## ANALYSIS (≤200 words) → ## ISSUES (design problems with fixes, ≤5) → ## VERDICT (one sentence).
```

## Test Generation Template

```
## Component Under Test
File: {file_path}
Lines: {start_line}-{end_line}
Framework: {test_framework}

Note: Use your CLI tools to read the file at the specified location.

## Coverage Scope
1. Rendering — component mounts correctly
2. Interaction — user actions produce expected results
3. State — state transitions work correctly
4. Boundaries — edge cases and invalid props
5. Accessibility — a11y compliance

## Response Protocol
FIRST: Read Serena memory 'global/response_protocol' for full format rules.
FALLBACK: You respond to an orchestrator agent, NOT a human. NO thinking narration, NO restating context.
Output: ## APPROACH (≤100 words) → ## DIFF (test code as unified diff) → ## VERIFY (commands to run tests) → ## ISSUES (uncovered scenarios).
```
