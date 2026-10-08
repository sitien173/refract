<!-- ccg-shared-version: 10.0.3 -->

# Phase 1 — Decision Notes

<!--
Worker Notes template. Append one `## Task <M>` block per task. Keep the file;
never overwrite earlier task blocks. Empty sub-sections = `- none`. Every task
gets a block even if all `none`.
-->

## Task 1

### Decisions made
- Mirrored `PiParams` and its subprocess wrapper, using Claude as the executable name and combined stdout/stderr line streaming.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Claude's print-mode JSON result is delivered one logical object per line as documented.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Added the Claude import/params smoke coverage; initial collection failed because `openmcp.backends.claude` did not exist, then the Claude-focused suite passed (8 passed).

## Task 2

### Decisions made
- Appended transport-owned flags after `params.args`, optionally added `--resume`, and always placed `--` immediately before the prompt.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Target arguments are already compiled before reaching this transport-only adapter.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: The argv assertion was part of the initial failing Claude smoke coverage; it passes in the focused suite (8 passed).

## Task 3

### Decisions made
- Kept the last `type=result` object, retained undecodable lines as diagnostics, and used the input session ID when the result omitted one.

### Spec deviations
- none

### Tradeoffs accepted
- Structured result errors are retained as the parsed result text while also forcing a fatal normalized result.

### Assumptions
- `result` values that are not strings can be represented as JSON text for the backend contract.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Success, last-result, error-result, diagnostics, and session fallback tests pass in the focused suite (8 passed).
- Root cause (bugfix only): An error result without a session initially retained the classifier's `warning` class; the result-error override now normalizes `warning`/`no_agent_messages` to `fatal_backend`.

## Task 4

### Decisions made
- Applied explicit failure overrides after shared classification so timeout, cancellation, and non-zero exit remain fatal even when partial agent output exists.

### Spec deviations
- none

### Tradeoffs accepted
- Timeout and unexpected subprocess errors use metadata-only local error text rather than exception strings that could contain argv.

### Assumptions
- `stream_shell_command_lines` remains the source of cancellation, timeout, and non-zero-status exceptions.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: Failure mapping tests for timeout, cancellation, missing CLI, bad cwd, and non-zero exit pass in the focused suite (8 passed).
- Root cause (bugfix only): none
