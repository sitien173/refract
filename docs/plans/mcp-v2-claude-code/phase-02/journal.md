<!-- ccg-shared-version: 11.0.6 -->

# Phase 2 Journal: Dependency persistence, access classes, and reader capacity

## META

- Plan: docs/plans/mcp-v2-claude-code/PLAN.md
- Implementation Profile: implement
- Consultation Profile: consult
- Review Profile: review
- Consultation Job: bef3d5f7-d880-4f80-83fa-b8cc36abdfa5; follow-up 3dd972c7-b2de-4dda-a44b-c824570dc29e succeeded after the approved retry
- Implementation Job: pending
- Review Job: pending
- Started: 2026-10-07
- Finished: 2026-10-07T16:17:32+07:00

## Setup and Guidance

- Pre-phase Git: main, clean at 92c5ed0fbbcd2bdf91ee3620e95286aa2cbde1fa.
- Authoritative plan base: refs/plans/mcp-v2-claude-code/base, 491e043dedc0263900e137f9a85fbf781e00530f.
- Phase 1 implementation: refs/plans/mcp-v2-claude-code/phase-01/impl, 44c5a55f70d260fe358956aa6564334a5c067e4d.
- No active or queued jobs. Daemon running, PID 482030, startup Wed 2026-10-07 14:01:37 +07 unchanged.
- Task guide called once for Phase 2. The v1 tool accepts only project_id; the complete phase request is recorded in PLAN.md Task Guide Input and this phase's prompt.md.
- Selected guide recommendations: architecture/risk consultation uses consult/consult; non-UI repository implementation uses implement/implement; independent quality review uses review/review.
- Catalog advertises all selected profiles and workflows. Missing mapping remains a hard route failure, not permission to substitute.
- Consult required because migration atomicity and adapter enforcement affect correctness and write safety.
- User approved continued waits after normal timeouts for all plan jobs; failures, unresolved questions, and bounds still block.
- No daemon restart or global runtime configuration change is permitted before Phase 7.

## Consultation

### Initial consult

- Job: bef3d5f7-d880-4f80-83fa-b8cc36abdfa5. Job state succeeded; advisory status BLOCKED.
- First 300-second wait returned running. User's existing continued-wait approval applied; the next wait used the verified 3600-second cap and returned the terminal result.
- Confirmed next migration version, atomic dependency validation and insertion, foreign keys and unique-pair/reverse-index requirements, immutable snapshot derivation, strict positive integer helper, and pending-restart mutation behavior.
- The missing tests/test_drivers.py path and unavailable search/documentation tools prevented verification of native enforcement. Advice was not treated as PASS, and no implementation was submitted.
- Git stayed at ae03a312cd8ac49abeb9cb8c15b7d065aa5d0aa1. Only the coordinator's recorded consultation reference changed; no source or test edits were made.

### Coordinator evidence and follow-up

- tgrep located the real isolation and transport cases in tests/test_smoke.py. Read-only context, not an additional allowed edit.
- Installed help and version plus Context7 documentation were inspected. Exact native restrictions, explicit-extension escape, and conservative custom-argv limitation are recorded in consult-evidence.md.
- Minimum proposal: only the proven isolated, read-only native target subset with no raw custom arguments may establish verified enforcement; every other or mixed fallback plan remains exclusive. Existing invocation behavior and valid configuration remain unchanged.
- A resumed read-only consult must verify that this subset and the existing immutable snapshot representation fit the declared nine-file scope before implementation.
- Daemon restart and global configuration changes remain prohibited.

### Follow-up transport failure

- Job: 3dd972c7-b2de-4dda-a44b-c824570dc29e, terminal failed after one attempt. No advice text was returned.
- Native streaming transport rejected a completed text block that changed after it had already streamed. The exact transport diagnostic remains in the private job record; no execution identity is copied here.
- Reconciliation: HEAD f548246c4a22fba9ccfd1b96a4d7562b56ff2445 unchanged; only the coordinator's .handover.md job reference changed. No production/test changes; project active list empty; daemon still PID 482030 with the original Phase 1 start timestamp.
- Handover was BLOCKED pending recovery. The user explicitly selected one unchanged retry. The existing route, prompt, immutable job plan, and nine-file later implementation set still hold. No Phase 2 base or implementation job had been created. No further automatic retry was approved.

### Accepted follow-up

- The one approved job_retry and one 3600-second wait returned job state succeeded with advisory status PASS. The job record reports four underlying execution attempts; the coordinator made one retry call.
- Read-only reconciliation passed at fd5af88c2ecef019462b91a3924d1824906d08d3: clean attached main, no production/test changes, no active project job, unchanged daemon PID/start timestamp.
- Accepted API: pure static DriverRegistry.supports_verified_read_only(target). Verified only for the documented native adapter with isolated=True, read_only=True, and empty raw args; all other cases false. No executable probe or transport change.
- Accepted API: derive_access_mode(plan) evaluates every selected immutable target, requires a nonempty selection, and returns parallel_read only when all qualify. Existing snapshot format suffices. Do not ignore fallbacks beyond attempt count.
- Accepted regressions cover unsafe primaries/fallbacks, advisory-only and unknown adapters, unisolated targets, raw custom arguments, snapshot round trips/catalog replacement, workflow independence, and an empty selection. Existing explicit-extension rejection and custom argv invocation remain unchanged.
- Consultation now reports no remaining user clarification or documentation gap. Its verified recommendations are copied into prompt.md. Migration/configuration advice from the initial consult remains adopted. Runtime/scheduler/MCP consumer wiring remains Phase 3 or later.

## Implementation Response

# EXTERNAL RESPONSE
## META
- Phase: Phase 2 — Dependency persistence, access classes, and reader capacity
- Started: 2026-10-07 (time not recorded)
- Finished: 2026-10-07T16:17:32+07:00
- Plan dir: docs/plans/mcp-v2-claude-code
- Pre-job HEAD: 05372c9f06bbe62b662042a685e36e1c831e89c9
- Authoritative phase base: a8e6b27445d3cf3e0ef199e085e5383e5fc73d69

## SUMMARY
Added schema v12 job access classes and immutable dependencies, conservative immutable-plan classification, and strictly positive startup-bound `max_project_readers` configuration with mutation validation.

## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Modify | `src/openmcp/database.py` | Add v12 migration, access mode storage, atomic dependency creation, and forward/reverse lookups |
| Modify | `src/openmcp/planning.py` | Derive access mode across every target in the saved plan |
| Modify | `src/openmcp/drivers.py` | Add conservative verified native read-only capability check |
| Modify | `src/openmcp/config.py` | Add positive integer reader capacity with default 1 |
| Modify | `tests/test_database.py` | Cover migration, constraints, atomic validation/insertion, and reverse lookup |
| Modify | `tests/test_planning.py` | Cover capability and plan-derived classification safety cases |
| Modify | `tests/test_config.py` | Cover default, positive setting, and strict type/range rejection |
| Modify | `tests/test_config_mutation.py` | Verify global mutation validation accepts valid and rejects invalid values |
| Modify | `docs/plans/mcp-v2-claude-code/phase-02/notes.md` | Record per-task decisions and exact RED/GREEN evidence |
| Modify | `docs/plans/mcp-v2-claude-code/phase-02/journal.md` | Record implementation response and verification |

## NOTES
- `docs/plans/mcp-v2-claude-code/phase-02/notes.md` — Task 1, Task 2, Task 3.
- The coordinator-owned `docs/plans/mcp-v2-claude-code/.handover.md` also appeared modified in `git status`; I did not edit it.

## TESTS RUN
- Task 1 RED: `uv run --extra dev pytest tests/test_database.py -q -k 'v11_migrates_existing_jobs_as_exclusive or create_job_with_dependencies'` -> 2 failed, 23 deselected. Failures: `assert 11 == 12`; `AttributeError: 'Database' object has no attribute 'create_job_with_dependencies'`.
- Task 1 GREEN: same focused command -> 2 passed, 23 deselected; `uv run --extra dev pytest tests/test_database.py -q` -> 25 passed.
- Task 2 RED: `uv run --extra dev pytest tests/test_planning.py -q -k 'verified_read_only or access_mode'` -> 6 failed, 11 deselected. Failures identified missing `DriverRegistry.supports_verified_read_only` and missing `derive_access_mode`.
- Task 2 GREEN: `uv run --extra dev pytest tests/test_planning.py -q -k 'verified_read_only or access_mode or empty_programmatic_selection'` -> 7 passed, 10 deselected.
- Task 3 RED: `uv run --extra dev pytest tests/test_config.py tests/test_config_mutation.py -q -k 'max_project_readers'` -> 7 failed, 132 deselected. Valid setting was rejected as unsupported; default field was absent; invalid values did not reach positive-integer validation.
- Task 3 GREEN: same focused command -> 7 passed, 132 deselected.
- Required phase suite: `uv run --extra dev pytest tests/test_database.py tests/test_planning.py tests/test_config.py tests/test_config_mutation.py -q` -> 184 passed in 2.38s.
- Full suite: `uv run --extra dev pytest -q` -> 500 passed, 3 deselected in 28.65s.
- `git diff --check` -> exit 0, no output.

## SPEC COMPLIANCE
- Meets Spec? YES — Phase 2 persistence, classification, configuration, and regression checks passed. Phase 3 consumer wiring remains out of scope; no live acceptance was performed.

## CLARIFICATIONS NEEDED
None

## NEXT
TASK_COMPLETE

## Automatic Fix Cycle 1

# EXTERNAL RESPONSE
## META
- Phase: Phase 2 — Specification/evidence fix cycle 1 of 2
- Started: 2026-10-07 (time not recorded)
- Finished: 2026-10-07T16:27:13+07:00
- Plan dir: docs/plans/mcp-v2-claude-code
- Pre-job HEAD: 05372c9f06bbe62b662042a685e36e1c831e89c9
- Original phase base: a8e6b27445d3cf3e0ef199e085e5383e5fc73d69

## SUMMARY
Fixed transaction-boundary finding S1 and added native Pi argument evidence for S2 without changing the already-correct conservative production classification.

## FILES MODIFIED
| Action | Path | Change |
|---|---|---|
| Modify | `src/openmcp/database.py` | Begin an explicit immediate transaction before dependency parent reads |
| Modify | `tests/test_database.py` | Assert parent reads are transactional and test rollback for later invalid parent and injected link failure |
| Modify | `tests/test_planning.py` | Cover accepted Pi export, install, and raw tool override args, round-trip, and exclusive classification |
| Modify | `docs/plans/mcp-v2-claude-code/phase-02/notes.md` | Record corrected evidence and fix-cycle test results |
| Modify | `docs/plans/mcp-v2-claude-code/phase-02/journal.md` | Record fix-cycle response |

## NOTES
- `phase-02/notes.md` — Review Fix Cycle 1, including exact RED/GREEN and Pi CLI evidence.
- The pre-existing worker implementation changes and coordinator bookkeeping were preserved. The coordinator-owned `.handover.md` remains untouched.

## TESTS RUN
- S1 RED: `uv run --extra dev pytest tests/test_database.py -q -k 'create_job_with_dependencies_is_atomic_and_supports_reverse_lookup'` -> 1 failed, 24 deselected. `assert parent_read_transactions == [True, True]` observed `[False, False]`.
- S1 GREEN: same command -> 1 passed, 24 deselected.
- S2 characterization: `uv run --extra dev pytest tests/test_planning.py -q -k 'pi_eager_write_and_raw_tool_args'` -> 3 passed, 20 deselected on the unchanged production classifier; evidence gap confirmed, so no production change was appropriate.
- Required phase suite: `uv run --extra dev pytest tests/test_database.py tests/test_planning.py tests/test_config.py tests/test_config_mutation.py -q` -> 187 passed in 2.31s.
- Full suite: `uv run --extra dev pytest -q` -> 503 passed, 3 deselected in 29.74s.
- `git diff --check` -> exit 0, no output.

## SPEC COMPLIANCE
- Meets Spec? YES — parent validation and all inserts now share an explicit transaction; the required native-argument evidence is present. No access-class semantics or invocation behavior changed.

## CLARIFICATIONS NEEDED
None

## NEXT
TASK_COMPLETE

## Coordinator Verification

- Implementation job 4bf699e3-50a7-4b54-ac62-efcaf1fc10b9 returned TASK_COMPLETE. The first 300-second wait returned running; the approved continued wait returned succeeded.
- HEAD remained 05372c9f06bbe62b662042a685e36e1c831e89c9. Changed paths matched the worker declaration and approved scope, plus the coordinator-owned job reference. config_mutation.py needed no edit because existing candidate-loader validation accepts the added setting; mutation tests passed.
- The actual baseline schema version is 11, verified from the recorded source diff. Migration 12 correctly follows it. The consultation's version 8 statement was inaccurate and is not adopted.
- Fresh focused suite: 184 passed in 2.06s. Fresh full suite: 500 passed, 3 deselected in 29.62s. git diff --check passed.
- Blocking Spec finding S1: SQLite trace showed parent SELECT with in_transaction=False, followed by BEGIN at the job INSERT. Dependency validation and insertion therefore do not share one transaction. Require an explicit transaction before parent reads and a deterministic transaction-boundary regression.
- Blocking evidence finding S2: the prompt explicitly requires valid export/install/raw-tool-override cases to round-trip and remain exclusive. Existing new tests cover verbose/system-prompt but not those eager-write cases. Add the missing scoped regressions without changing invocation or accepted configuration.
- No checkpoint created before resolving these findings. Automatic fix cycle 1 of 2. Daemon PID 482030 and startup unchanged.
- Fix job 57227d7d-027c-481c-b755-c3c3dc4e053e returned TASK_COMPLETE. Inspected final diff: explicit BEGIN IMMEDIATE precedes parent SELECTs, the trace regression asserts both parent reads are transactional, and later invalid-parent/link failures roll back. Valid export/install/raw-tool arguments round-trip unchanged and remain exclusive. S1 and S2 resolved.
- Fresh fix verification at the unchanged implementation tree: 187 focused tests passed in 2.12s; 503 full tests passed, 3 deselected in 28.75s; git diff --check passed. Allowed worker and coordinator path ownership matched. No active project job and live daemon unchanged.
- Optional Phase 3 background retrieval was stopped before returning any findings; it is not evidence. No source investigation ran while it was in flight. Phase 3 can use the known source/test paths at its own consultation gate.
- Spec PASS. Independent quality review remains pending.

## Quality Review

Pending.

## Review Result

- Spec Status: PASS
- Quality Status: PENDING
- Debt: none

## Final Checkpoint

- Phase base ref: refs/plans/mcp-v2-claude-code/phase-02/base, a8e6b27445d3cf3e0ef199e085e5383e5fc73d69. Created at the clean finalized prompt checkpoint; object and ancestry checks passed.
- Phase implementation ref: refs/plans/mcp-v2-claude-code/phase-02/impl
- Plan commit ref: pending
- State checkpoint: pending
