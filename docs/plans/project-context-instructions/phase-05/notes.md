<!-- ccg-shared-version: 10.1.0 -->

# Phase 5 — Decision Notes

## Task 1 — Generalize Phase 4 helpers for agy `GEMINI.md` without composition

### Decisions made
- Renamed `_compose_codex_content` to `_compose_content(instruction, root,
  kind)` where `kind` is `"codex"` or `"agy"`. Codex composes the instruction
  followed by the root `AGENTS.md` inlined verbatim (because
  `AGENTS.override.md` shadows `AGENTS.md` within a directory); agy writes the
  instruction only, because agy loads `GEMINI.md` and `AGENTS.md` additively
  and no composition is ever applied.
- `materialize_context_file(root, target, instruction, *, kind="codex")`
  gained the `kind` keyword with a default of `"codex"`, so all existing
  callers and tests are unchanged. An unknown `kind` raises `ValueError`.
- The "nothing to deliver" early return is now `not instruction` (for both
  kinds); an empty instruction never creates a file. This is a strict
  generalization of the previous codex-only check (empty instruction AND no
  `AGENTS.md`).
- All Phase 4 safety machinery — `_IndexLock`, `_refuse_existing_target`,
  `_ensure_exclude`, `_confirm_excluded`, `_write_target`, `_Quarantine`,
  `cleanup_context_file`, `sweep_context_files` — is reused unchanged for agy;
  only the payload composition and the target filename differ.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- A `GEMINI.md` carrying the managed marker plus the instruction is sufficient
  for agy to receive the instruction, matching the verified harness behavior
  in DESIGN.md (agy reads `GEMINI.md` additively).

### Follow-ups for human
- none

### Test evidence
- RED: `test_materialize_agy_gemini_contains_instruction_only`,
  `test_materialize_agy_unknown_kind_rejected`,
  `test_materialize_agy_gemini_git_invisible`,
  `test_materialize_agy_refuses_tracked_gemini`,
  `test_materialize_agy_refuses_foreign_gemini`,
  `test_cleanup_agy_gemini_removes_target_and_preserves_payload`,
  `test_sweep_agy_gemini_removes_managed_leftover`,
  `test_cleanup_agy_gemini_restores_foreign_race_swap` failed before the
  `kind` generalization existed.
- GREEN: `uv run pytest tests/test_context_files.py -q` -> `51 passed`.

## Task 2 — Route agy attempts and startup sweeping through shared safety machinery

### Decisions made
- `TargetExecutor.execute` now materializes for both file backends under the
  same per-attempt try/finally: `kind="codex"` writes
  `AGENTS.override.md`; `kind="agy"` writes `GEMINI.md`. Both return
  `REQUEST_FATAL` on a `ValueError` (tracked, foreign, symlink, hardlink,
  directory, or exclude failure) and both clean up in the `finally` and
  driver-exception paths, so success, failure, timeout, cancellation, and
  driver exceptions all remove the generated file.
- `Runtime._sweep_project_context_files` now sweeps both `AGENTS.override.md`
  and `GEMINI.md` per registered project at daemon start, with per-filename
  exception isolation.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- `plan.instruction` is `""` for uninstructed jobs, so neither file is written
  for an uninstructed agy or codex job.

### Follow-ups for human
- none

### Test evidence
- RED: `test_agy_attempt_materializes_instruction_only_gemini`,
  `test_agy_tracked_gemini_fails_request_fatal`,
  `test_agy_foreign_gemini_fails_request_fatal`,
  `test_startup_sweep_removes_agy_gemini_leftover` failed before the
  execution/runtime routing existed.
- GREEN: `uv run pytest tests/test_execution.py -q` -> `53 passed`.

## Task 3 — Document `context_init`, its resource, and every backend mechanism

### Decisions made
- README: added a "Project Context Instructions" section documenting
  `context_init(project_id, workflow, instruction)` (empty instruction clears;
  instruction snapshotted into the immutable execution plan at submission),
  the `openmcp://projects/{project_id}/context_instructions` resource, and a
  per-backend injection table covering Claude (`--append-system-prompt`,
  survives `--safe-mode`), Pi (`--append-system-prompt`, survives
  `--no-context-files`), Codex (`AGENTS.override.md` with `AGENTS.md` inlined
  verbatim), and agy (`GEMINI.md` instruction-only, additive). Also added
  `context_init` to the MCP tool table and the Key Features list.
- CLI_ARGUMENTS.md: documented the codex `AGENTS.override.md` mechanism
  (composition, marker, exclusion, cleanup, REQUEST_FATAL) and the agy
  `GEMINI.md` mechanism (instruction-only, additive, marker, exclusion,
  cleanup, REQUEST_FATAL). Updated the agy section to state that new sessions
  (no stored conversation ID) are created with `--new-project` — Backlog B-001
  added this, so the original plan's "inert until a known agy project"
  limitation is resolved and the docs describe current behavior instead.
- The pi and claude sections already documented their `--append-system-prompt`
  injection from Phase 3; no change was needed there.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- The prompt explicitly states Backlog B-001 already added `--new-project` for
  new agy sessions, verified in `agy.py:172-175` (new session without
  `SESSION_ID` appends `--new-project`; resumed sessions use `--conversation`).
  The DESIGN.md "Open item: agy project registration" is therefore obsolete and
  the documentation records current behavior rather than the old limitation.

### Follow-ups for human
- The DESIGN.md "Open item" section still describes the pre-B-001 limitation;
  it is not part of the declared file set for this phase and was left as a
  documentation note for the plan owner.

### Test evidence
- No new tests for prose; the phase verification commands pass:
  - `uv run pytest tests/test_context_files.py tests/test_execution.py -q` ->
    `104 passed`.
  - `uv run pytest -q` -> `274 passed, 4 failed, 3 deselected` (the 4 failures
    are the pre-existing `job_wait` set, identical to the base commit).
