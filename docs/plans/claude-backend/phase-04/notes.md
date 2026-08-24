<!-- ccg-shared-version: 10.0.3 -->

# Phase 4 — Decision Notes

<!--
Executed directly by the coordinator. Documentation work is not routed through
OpenMCP.
-->

## Task 1

### Decisions made
- Documented the Claude Code flag surface as groups, matching the Pi section's
  format rather than the flat table used for agy and codex. The surface is large
  enough that a flat table would dominate the document.
- Added an explicit "Execution model" group so `--bg`, `--worktree`, and `--tmux`
  are visible in the available-flags table and again in the unsupported list.

### Spec deviations
- none

### Tradeoffs accepted
- The grouped table names flags without describing each one. The reasons that
  matter to an operator are in the ownership statement and the unsupported table
  below it.

### Assumptions
- `claude --help` on 2.1.220 is the authoritative surface.

### Follow-ups for human
- none

### Test evidence
- Every documented flag was read from `claude --help` at 2.1.220 in this
  environment.
- Root cause (bugfix only): the first draft listed `--system-prompt-file` and
  `--append-system-prompt-file` as available. Neither is a listed option. Both
  appear only inside the `--bare` description, which references them as
  `--system-prompt[-file]`. Removed rather than documented on that basis.

## Task 2

### Decisions made
- Rebuilt the ASCII architecture diagram with computed column centers instead of
  hand-editing it. Adding a fourth box by hand left the connector columns
  misaligned with the labels.
- Renamed "Pi Target Isolation" to "Target Isolation" and added the claude
  fields. Leaving the pi-only heading would have stated something false once
  claude gained the same two fields.

### Spec deviations
- Renaming that heading was not in the phase task list. It is a one-word change
  that prevents the section from being wrong.

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- Diagram alignment generated programmatically; adapter centers are columns 8,
  23, 38, and 53.

## Task 3

### Decisions made
- Added two claude targets, one implement and one review, and a `claude_impl`
  profile extending `base`. The default profile `base` is unchanged.
- Used the model aliases `opus` and `sonnet`, which `--model` documents as
  accepted alongside full model names.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- `reasoning` values `high` and `medium` are valid `--effort` levels. Confirmed
  against `claude --help`.

### Follow-ups for human
- none

### Test evidence
- The README TOML block was extracted, written to a temporary `OPENMCP_HOME`,
  and loaded with `uv run openmcp doctor`. Exit 0, 25 targets, and both claude
  targets resolved to `/home/ngosi/.local/bin/claude`.
- No `args` array in the example contains a credential.
