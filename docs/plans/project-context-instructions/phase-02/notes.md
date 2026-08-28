<!-- ccg-shared-version: 10.1.0 -->

# Phase 2 — Decision Notes

## Task 1 — Backward-compatible instruction serialization on `ExecutionPlan`

### Decisions made
- Added `instruction: str = ""` as the final field on the frozen `ExecutionPlan`
  dataclass with a default, so existing positional constructions (none exist
  outside `planning.py`) and equality comparisons for legacy plans are
  unaffected. All internal constructions pass it positionally.
- `execution_plan_data` always emits `"instruction": plan.instruction`, so every
  new plan persisted by this version carries the key.
- `parse_execution_plan` reads `data.get("instruction", "")`, so a plan JSON
  written by the previous version (no `instruction` key) parses with an empty
  instruction. A present non-string value raises
  `ValueError("Execution plan instruction must be a string")`.
- `target_execution_key` hashes `_target_data(target)` only; the new plan field
  is not part of the hash, so existing session continuity and target health rows
  still resolve.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- A legacy plan written by the previous version is exactly today's
  `execution_plan_data` output without the `instruction` key; the default-empty
  read covers that shape and any older shape missing the key.

### Follow-ups for human
- none

### Test evidence
- RED: `test_plan_instruction_round_trips`, `test_legacy_plan_without_instruction_defaults_to_empty`, `test_plan_rejects_non_string_instruction[*]`, and `test_target_execution_key_ignores_plan_instruction` all failed with `TypeError`/`AssertionError` before the change.
- GREEN: `uv run pytest tests/test_planning.py -q` -> `17 passed`.

## Task 2 — Snapshot the stored instruction during submission

### Decisions made
- `Runtime.submit` reads `self.database.context_instruction(project.id, workflow)`
  inside the existing `try` block, immediately before resolving the plan, so the
  instruction is read once at submission time and never re-read during
  execution.
- The read passes the instruction into `resolve_execution_plan(..., instruction)`
  as a keyword-defaulted parameter (`instruction: str = ""`), so existing
  callers in tests and config code that call `resolve_execution_plan` without an
  instruction are unchanged.
- The snapshot lives in the persisted `execution_plan_json`, so a later
  `context_init` cannot change a queued job; execution parses the plan from the
  job record (`execution.py:216`), never from the instruction store.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- An empty stored instruction (no row) snapshots as `""`, which Phase 3 will
  treat as "add no flag".

### Follow-ups for human
- none

### Test evidence
- RED: `test_submitted_job_snapshots_stored_instruction`,
  `test_submitted_job_without_instruction_snapshots_empty`, and
  `test_context_init_after_submit_does_not_change_queued_plan` failed before the
  runtime change.
- GREEN: `uv run pytest tests/test_planning.py tests/test_server.py -q` ->
  `42 passed, 4 failed` (4 pre-existing, see Task 3).

## Task 3 — Round-trip, legacy parsing, validation, and queued-job immutability tests

### Decisions made
- Added planning tests for: instruction round-trip through
  `execution_plan_data`/`parse_execution_plan`; legacy payload without the
  `instruction` key defaulting to `""`; non-string instruction values (`1`,
  `None`, list, dict) rejected; `target_execution_key` identical with and
  without an instruction.
- Added server tests for: a submitted job carrying the stored submission-time
  instruction in its persisted plan; a submitted job with no instruction
  snapshotting `""`; and a `context_init` call landing between submit and
  execution leaving the queued job's plan unchanged while the store updates.
- Verified via `rg` that `src/openmcp/execution.py` and `src/openmcp/drivers.py`
  never touch the context-instruction store, so the instruction is read once at
  submission and never re-read during execution.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- The four `test_server.py` failures
  (`test_mcp_exposes_direct_job_contract`,
  `test_job_wait_bounds_public_timeout[None-30/0-30/45-30]`) are pre-existing on
  the base commit (verified by stash in Phase 1) and out of scope for this
  phase.

### Follow-ups for human
- Pre-existing `job_wait` timeout-default mismatch (`_MCP_WAIT_TIMEOUT_S = 300`
  vs tests expecting 30) remains from before this phase; recommend a separate
  scoped change.

### Test evidence
- RED: new tests failed before implementation (Task 1/2 RED listed above).
- GREEN:
  - `uv run pytest tests/test_planning.py tests/test_server.py -q` ->
    `42 passed, 4 failed` (4 pre-existing).
  - `uv run pytest -q` -> `194 passed, 4 failed, 3 deselected`; the failing set
    is identical to the base commit's set, so the phase adds 10 passing tests
    with zero regressions.
