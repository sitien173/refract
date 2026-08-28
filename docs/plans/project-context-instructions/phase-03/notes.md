<!-- ccg-shared-version: 10.1.0 -->

# Phase 3 — Decision Notes

## Task 1 — Thread instructions through target execution and driver argv compilation

### Decisions made
- `DriverRegistry.execute` gained a keyword-defaulted `instruction: str = ""`
  parameter, passed straight into `_target_args(target, instruction)`. Existing
  callers (tests, other drivers) are unchanged because of the default.
- `TargetExecutor.execute` passes `instruction=plan.instruction` on the
  `drivers.execute` call inside the attempt loop, so each attempt compiles argv
  from the same snapshotted plan value. A retry that selects a different backend
  recompiles argv for that backend with the instruction.
- `_target_args` keeps `validate_target_args` as the first step over the
  operator-supplied `target.args` only; the instruction is appended afterwards
  and never passes through operator-arg validation.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- `plan.instruction` is always a string (`""` when unset), so the
  `if instruction:` guard in `_target_args` is sufficient to decide whether to
  emit the append flag.

### Follow-ups for human
- none

### Test evidence
- RED: `test_retry_attempts_recompile_argv_per_backend` failed before the
  runtime/execution threading existed.
- GREEN: `uv run pytest tests/test_execution.py -q` -> `36 passed`.

## Task 2 — Append `--append-system-prompt` for claude and pi only

### Decisions made
- In `_target_args`, the pi branch appends `--append-system-prompt
  <instruction>` after `--approve`/isolation flags, `--system-prompt`,
  `--tools`, `--model`, and `--thinking`, i.e. after all target arguments and
  policy-derived flags, so a target cannot displace it.
- The claude branch appends the same pair after `--safe-mode`,
  `--strict-mcp-config`, `--system-prompt`, `--tools`, `--model`, and `--effort`.
- agy and codex branches return before any instruction handling, so they are
  unaffected.
- An empty instruction adds no flag, so every backend's argv is byte-identical
  to today's output for empty instructions.
- The instruction is never logged in full; the pi/claude backends log argument
  counts (`args=%d`) and `prompt_len` only. Verified by grep that no backend or
  logging module prints the instruction contents.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- `--append-system-prompt` is repeatable and additive in both harnesses
  (verified in DESIGN.md harness research), so appending after any target
  `--system-prompt` composes rather than replaces.

### Follow-ups for human
- none

### Test evidence
- RED: `test_driver_appends_system_prompt_for_instructed_backend[claude|pi]`,
  `test_driver_appends_system_prompt_for_isolated_backend[claude|pi]`,
  `test_driver_ignores_instruction_for_other_backends[agy|codex]`,
  `test_driver_empty_instruction_preserves_argv[all 4]`, and
  `test_target_args_appends_instruction_after_operator_args` failed before the
  `_target_args` change.
- GREEN: all pass after `_target_args` and `DriverRegistry.execute` changes.

## Task 3 — Document and test normal, isolated, empty, and unaffected backend behavior

### Decisions made
- Added driver-level tests in `tests/test_execution.py` using the existing
  monkeypatch pattern (swap the backend `execute` with a capture) that assert:
  - claude and pi (normal and isolated) receive `--append-system-prompt
    <instruction>` as the final pair;
  - isolated claude keeps `--safe-mode` and isolated pi keeps
    `--no-context-files` alongside the append flag;
  - agy and codex argv never contain the append flag regardless of instruction;
  - an empty instruction produces argv identical to today's output for all four
    backends;
  - `_target_args` appends the instruction after operator args (pi example:
    `("--verbose", "--approve", "--append-system-prompt", "follow the plan")`);
  - a retry across two backends recompiles argv per attempt, with
    `instruction` present on each selected backend.
- Documented the injection mechanism in `CLI_ARGUMENTS.md` for both the Pi and
  Claude sections: the append flag is emitted after target args, survives
  `--no-context-files` / `--safe-mode`, an empty instruction adds no flag, and
  the instruction is never logged in full.

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
- RED: new driver tests failed before implementation (listed in Tasks 1-2).
- GREEN:
  - `uv run pytest tests/test_execution.py -q` -> `36 passed` (24 pre-existing
    + 12 new).
  - `uv run pytest -q` -> `206 passed, 4 failed, 3 deselected`; the failing set
    is identical to the base commit's set, so the phase adds 12 passing tests
    with zero regressions.
