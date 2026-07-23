<!-- ccg-shared-version: 7.4.0 -->

# Phase 2 — Decision Notes

<!--
Append one `## Task <M>` block per task. Keep earlier task blocks.
Empty sub-sections use `- none`.
-->

## Task 1

### Decisions made
- Keep workflow names and capabilities unchanged.
- Make validation return only the normalized prompt.

### Spec deviations
- none

### Tradeoffs accepted
- The unused workflow argument remains for the existing validator call shape.

### Assumptions
- Prompt validation continues to reject empty and whitespace-only input.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Workflow tests failed on `writes` and the old validator arity. After simplifying definitions and validation, 2 focused tests passed.

## Task 2

### Decisions made
- Remove commit messages from runtime and database method signatures.
- Omit the physical column from inserts so SQLite supplies its default.

### Spec deviations
- none

### Tradeoffs accepted
- Schema v5 detection and legacy extraction retain historical commit-message handling.

### Assumptions
- Existing schema v5 databases remain readable without rewriting their columns.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Runtime and database signature tests initially found both parameters. After API and insert changes, 2 focused tests passed.

## Task 3

### Decisions made
- Remove `commit_message` from the MCP function signature.
- Preserve all other job submission properties and routing.

### Spec deviations
- none

### Tradeoffs accepted
- The database compatibility column remains physically present.

### Assumptions
- FastMCP derives the public schema from the function signature.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: MCP schema coverage initially found `commit_message`. After removing the tool parameter, the focused contract test passed.

## Task 4

### Decisions made
- Update execution fixtures to use prompt-only submission.
- Preserve workflow names, capabilities, profiles, and target routing.

### Spec deviations
- none

### Tradeoffs accepted
- Existing historical migration fixtures continue to include commit-message data.

### Assumptions
- Empty compatibility values remain represented by the physical schema default.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Affected workflow, server, execution, and database tests were updated for the new APIs. The required suite passed 58 tests.

## Task 5

### Decisions made
- Document directory registration and prompt-only submission.
- Add explicit coverage that new jobs use the empty column default.

### Spec deviations
- none

### Tradeoffs accepted
- Legacy commit-message migration references remain until Phase 3.

### Assumptions
- `commit_message` search results limited to database schema and migration code are intentional.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Database default coverage passed. Full suite passed 136 tests, with 2 live tests deselected. Source search returned only four allowed database references.

## Task 6

### Decisions made
- Correct only the README capability label.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Existing directory-execution wording remains unchanged elsewhere.

### Follow-ups for human
- none

### Test evidence
- Documentation-only fix verified with the required 58-test suite and source search. Four allowed database compatibility references remain.
