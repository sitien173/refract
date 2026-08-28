<!-- ccg-shared-version: 10.1.0 -->

# Phase 4 — Decision Notes

## Task 1 — Reusable context-file materialization, exclusion, and cleanup helpers

### Decisions made
- New module `src/openmcp/context_files.py` with:
  - `MANAGED_MARKER = "<!-- openmcp-context-instruction v1 -->"` — the header
    marker; cleanup and sweep delete only files whose content starts with it.
  - `git_repository_root(path)` — resolves the worktree root via
    `git rev-parse --show-toplevel` with a scrubbed environment; returns `None`
    only for a confirmed "not a git repository", raises (fails closed) on any
    other Git error or an empty result.
  - `is_tracked(root, path)` — uses `git ls-files --stage -- <relpath>` and
    checks stdout membership, which is true even when the file is deleted from
    the working tree but still in the index (verified empirically: a deleted
    file in the index still lists its stage entry).
  - `managed_exclude_block(relpath)` — delimited block
    `# BEGIN openmcp-context-instruction: <relpath>\n/<relpath>\n# END ...`,
    anchored to the repository root so `git check-ignore` confirms it from any
    linked worktree.
  - `_ensure_exclude` — appends the block to `$GIT_COMMON_DIR/info/exclude`
    resolved through Git (never a hard-coded `.git/info/exclude`), writes once
    (idempotent by begin-marker lookup), preserves unrelated content verbatim,
    and serializes concurrent updates with a module-level `threading.Lock`.
  - `_confirm_excluded` — verifies with `git check-ignore` that the generated
    path is actually ignored.
  - `materialize_context_file(root, target, instruction)` and
    `cleanup_context_file(root, target)` returning the paths created/removed.
- All internal Git calls run through `_git()` which scrubs
  `GIT_DIR`, `GIT_WORK_TREE`, `GIT_COMMON_DIR`, `GIT_INDEX_FILE`,
  `GIT_OBJECT_DIRECTORY`, `GIT_ALTERNATE_OBJECT_DIRECTORIES`,
  `GIT_CEILING_DIRECTORIES`, `GIT_DISCOVERY_ACROSS_FILESYSTEM`, and
  `GIT_NAMESPACE` from the environment so a worker cannot redirect them.

### Spec deviations
- none

### Tradeoffs accepted
- The materialize/cleanup/sweep helpers are codex-specific today (they compose
  `AGENTS.md` into `AGENTS.override.md`) but the marker, tracked check, exclude
  writer, cleanup, and sweep are filename-agnostic so Phase 5 can reuse them for
  agy's `GEMINI.md` unchanged.

### Assumptions
- A "not a git repository" verdict from `git rev-parse --show-toplevel` is the
  only case treated as non-Git; every other failure (bad path, permission,
  corrupt repo) raises.

### Follow-ups for human
- none

### Test evidence
- RED: `tests/test_context_files.py` failed to collect with
  `ModuleNotFoundError: No module named 'openmcp.context_files'`.
- GREEN: `uv run pytest tests/test_context_files.py -q` -> `22 passed`.

## Task 2 — Wrap codex attempts and sweep managed leftovers during startup

### Decisions made
- `TargetExecutor.execute` materializes the codex file per attempt: inside the
  attempt's try block, for `target.backend == "codex" and plan.instruction`,
  call `materialize_context_file(cwd, cwd / "AGENTS.override.md",
  plan.instruction)`. A `ValueError` (tracked, foreign, symlink, hardlink,
  directory, or exclude failure) returns `REQUEST_FATAL` with the error text.
- Cleanup runs in a `finally` block (and also in the driver-exception handler)
  so the file is removed on success, failure, timeout, cancellation, and driver
  exceptions. Cleanup is synchronous and never masks the driver outcome; a
  cleanup error is logged via `_cleanup_materialized`.
- `Runtime.start` calls `_sweep_project_context_files()` after interrupting
  active jobs, sweeping `AGENTS.override.md` for every registered project
  (persisted in the database) before the scheduler starts. Per-project
  exceptions are caught and logged so daemon start never fails on a sweep.
- The REQUEST_FATAL return happens before `last` is assigned, so the
  attempt-finished event is not emitted for refused materialization — matching
  the "job fails REQUEST_FATAL" contract.

### Spec deviations
- none

### Tradeoffs accepted
- The sweep runs at daemon start only (not before each job), matching the phase
  task "sweep marker-bearing leftovers for a project on daemon start"; the
  per-attempt materialize/cleanup pair handles the steady state, and a crash
  between write and cleanup is covered by the next daemon start.

### Assumptions
- `plan.instruction` is `""` for jobs without a stored instruction, so no file
  is written for uninstructed codex jobs and argv stays unchanged.

### Follow-ups for human
- none

### Test evidence
- RED: 13 new `tests/test_execution.py` phase-4 tests failed before the
  execution/runtime wiring existed (initially `TypeError` from the test helper,
  then assertion failures; all resolved as GREEN below).
- GREEN: `uv run pytest tests/test_execution.py -q` -> `49 passed`.

## Task 3 — Composition, Git safety, linked worktrees, refusal paths, and cleanup tests

### Decisions made
- `_compose_codex_content` builds bytes: marker + instruction + root
  `AGENTS.md` read verbatim as bytes, so a foreign-encoded `AGENTS.md` is
  preserved exactly. Without a root `AGENTS.md`, the file contains the
  instruction only.
- `_refuse_existing_target` refuses symlinks (could point at a tracked or
  foreign file), directories, hardlinked regular files (`st_nlink > 1`), and
  untracked files that do not carry the managed marker. A leftover marker file
  is overwritten (unlinked before the exclusive create) rather than refused.
- The exclusive create uses `open("xb")` so a foreign file appearing between
  validation and write fails rather than being overwritten.
- `cleanup_context_file` deletes only a regular non-symlink file whose content
  starts with the marker; foreign, symlink, and directory targets are never
  touched (verified by dedicated tests).
- `sweep_context_files` skips Git entirely when no candidate exists (verified
  by monkeypatching `subprocess.run` and asserting zero calls), then deletes
  only untracked marker-bearing files, leaving tracked and foreign files alone.
- Test coverage: composition with/without `AGENTS.md`, Git-invisibility in the
  main checkout and a linked worktree, exclude block written once and
  preserving unrelated content, cleanup on success/failure/timeout/
  cancellation/driver-exception, REQUEST_FATAL for tracked and foreign targets
  leaving files byte-identical, leftover-marker overwrite, non-Git project
  materializing with a warning, startup sweep removing managed leftovers and
  leaving tracked files alone, `git check-ignore` confirmation from both
  worktrees, and exclusive-create semantics.

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
- RED: new tests failed before implementation (module missing, helper errors).
- GREEN:
  - `uv run pytest tests/test_context_files.py tests/test_execution.py -q` ->
    `71 passed`.
  - `uv run pytest -q` -> `241 passed, 4 failed, 3 deselected`; the failing set
    is identical to the base commit's set, so the phase adds 35 passing tests
    (22 context_files + 13 execution) with zero regressions.

## Fix — Pre-commit defect correction (subdirectory root composition and non-Git refusal)

### Decisions made
- `materialize_context_file` now keeps the supplied project root in
  `project_root` and resolves `repo_root` (Git top-level) only for index and
  exclusion operations. Composition (`_compose_codex_content`) and the
  "nothing to deliver" check (`project_root / "AGENTS.md"`) use the project
  root, so a project rooted in a repository subdirectory inlines its own
  `AGENTS.md`, not the repo-level one.
- The tracked check and exclusion operations (`is_tracked`, `_ensure_exclude`,
  `_confirm_excluded`) use `repo_root` with the path relative to the Git
  top-level, preserving the original Git-safety behavior.
- `_refuse_existing_target` is now applied identically in Git and non-Git
  projects before any replacement: symlink, directory, hardlink, and foreign
  file refusals run even when the project root is not a repository. The
  leftover-marker overwrite (unlink before exclusive create) now runs only
  after refusal, so a foreign file is never unlinked in a non-Git project.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- The project root and the target are always inside the same repository; if
  they were not, `_relative` would raise, failing closed.

### Follow-ups for human
- none

### Test evidence
- RED: added regression tests that failed on the pre-fix code:
  `test_materialize_composes_from_project_root_in_repo_subdirectory`
  (inlined repo-level guidance instead of project-level),
  `test_materialize_nothing_to_deliver_checks_project_root_in_subdirectory`
  (delivered a file when the project had no `AGENTS.md` but the repo did),
  `test_non_git_materialize_refuses_foreign_file_and_preserves_it`,
  `test_non_git_materialize_refuses_symlink_target`,
  `test_non_git_materialize_refuses_directory_target`,
  `test_non_git_materialize_refuses_hardlink_target`,
  `test_non_git_materialize_overwrites_marker_leftover`,
  `test_non_git_materialize_composes_project_agents`.
- GREEN: `uv run pytest tests/test_context_files.py tests/test_execution.py -q`
  -> `79 passed`; `uv run pytest -q` -> `249 passed, 4 failed, 3 deselected`
  (the 4 failures are the pre-existing `job_wait` set, identical to the base
  commit).

## Fix — Review finding: inode-safe replacement (HIGH)

### Decisions made
- Removed the pathname-based leftover overwrite (`target.unlink()` before
  `open("xb")`) that let a replacement race delete a foreign or tracked file
  swapped in after validation.
- Added `_open_managed_for_replacement(target)`: opens the existing regular
  single-link file with `O_RDWR | O_NOFOLLOW` (when the platform supports it),
  then validates through that same descriptor — `os.fstat` single-link check,
  `os.read` marker prefix check — before returning the fd. `O_NOFOLLOW`
  rejects a swapped-in symlink with `ELOOP`, which is surfaced as `ValueError`.
- Added `_replace_managed_file(target, content)`: truncates (`os.ftruncate`),
  writes, and `os.fsync`s through the validated descriptor, then closes it.
  The pathname is never unlinked or re-opened for mutation after the
  descriptor validation, so a concurrent rename to a foreign or tracked file
  cannot be deleted or modified.
- Added `_write_target(target, content, *, present)`: dispatches to
  `_replace_managed_file` when `present` (existing managed leftover) or to an
  exclusive `open("xb")` create (with `fsync`) when absent. `present` is
  re-evaluated at write time so the two branches race correctly: an absent
  path claims it with `O_EXCL`; a present path is validated and rewritten
  through the descriptor.
- `materialize_context_file` now calls `_write_target` instead of the
  unlink-then-create sequence, and its comment documents that the pathname
  pre-check (`_refuse_existing_target`) is a fast check while the descriptor
  validation in `_write_target` is authoritative.

### Spec deviations
- none

### Tradeoffs accepted
- `O_NOFOLLOW` is not available on all platforms (e.g., some Windows builds);
  on those platforms the post-open `os.path.islink` re-check still refuses a
  symlink that was swapped in before the open. The marker check through the
  descriptor remains the authoritative guard everywhere.

### Assumptions
- A single-link regular file whose content starts with the marker is
  sufficient proof the inode is ours to rewrite, matching the previous
  pathname-based validation but now bound to the descriptor.

### Follow-ups for human
- none

### Test evidence
- RED: added `test_replacement_race_swapped_foreign_path_is_neither_modified_nor_deleted`
  and `test_replacement_race_swapped_tracked_path_is_neither_modified_nor_deleted`;
  the tracked variant initially failed because the swap committed a file while
  the managed exclude block was already in effect (fixed with `git add -f`).
- GREEN: `uv run pytest tests/test_context_files.py tests/test_execution.py -q`
  -> `81 passed`; `uv run pytest -q` -> `251 passed, 4 failed, 3 deselected`
  (the 4 failures are the pre-existing `job_wait` set, identical to the base
  commit).

## Fix — Review cycle 2: inode-bound replacement and quarantine cleanup (HIGH)

### Decisions made
- Finding 1 (existing-file replacement can accept a race-swapped tracked marker
  file): replacement is now bound to the exact prevalidated inode.
  `_refuse_existing_target` returns `(st_dev, st_ino)` of the validated managed
  leftover; `_open_managed_for_replacement(target, expected)` opens with
  `O_NOFOLLOW` and fails closed unless `_fd_identity(fd) == expected`.
  `_replace_managed_file` then rechecks Git tracking of the original path
  (`_recheck_tracked_after_open`) before any truncation or write. A tracked
  marker file swapped in after the earlier index check is refused either by the
  identity check (different inode) or the tracking recheck (same inode now
  staged), and is never modified.
- Finding 2 (cleanup reads by pathname then unlinks by pathname): cleanup and
  sweep now use a shared quarantine flow. `_quarantine_candidate` atomically
  `os.rename`s the candidate to a unique same-directory quarantine path
  (`.NAME.openmcp-quarantine-PID-INDEX`, bounded retry on collisions).
  `_validate_quarantined` checks at the quarantine path that the file is a
  regular single-link file (`stat.S_ISREG`, `st_nlink == 1`) carrying the
  managed marker and that the original path is untracked. Only the quarantined
  managed inode is deleted. Non-managed or tracked content is restored to the
  original path without overwriting another path; when restoration is
  impossible (the original path was concurrently claimed) the quarantined bytes
  are preserved at the quarantine path and a `ValueError` reports the failure
  rather than deleting data.
- The startup sweep reuses the same `_quarantine_flow`, so it gets identical
  race safety.

### Spec deviations
- none

### Tradeoffs accepted
- `_quarantine_candidate` uses `os.rename` (atomic on POSIX); on Windows the
  move is not guaranteed atomic but remains a same-directory rename, and the
  post-move validation still protects against path swaps.
- The quarantine name includes the PID and an index, so parallel jobs in one
  project cannot collide; the bounded retry (100) prevents infinite spin on
  persistent `OSError`.

### Assumptions
- `(st_dev, st_ino)` is a stable inode identity on the filesystems OpenMCP
  targets; this matches the existing hardlink-hazard refusal which already
  relies on `st_nlink`.

### Follow-ups for human
- none

### Test evidence
- RED: new regression tests were added for tracked marker swaps and
  cleanup/sweep path swaps and passed only after the fix; the prior
  pathname-based cleanup would have deleted or modified swapped content.
- GREEN:
  - `uv run pytest tests/test_context_files.py -q` -> `38 passed`.
  - `uv run pytest tests/test_context_files.py tests/test_execution.py -q` ->
    `87 passed`.
  - `uv run pytest -q` -> `257 passed, 4 failed, 3 deselected` (the 4 failures
    are the pre-existing `job_wait` set, identical to the base commit).
