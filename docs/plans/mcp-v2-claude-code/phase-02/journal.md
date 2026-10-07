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
- Finished: pending

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

Worker appends the full ERP response here.

## Coordinator Verification

Pending.

## Quality Review

Pending.

## Review Result

- Spec Status: PENDING
- Quality Status: PENDING
- Debt: none

## Final Checkpoint

- Phase base ref: refs/plans/mcp-v2-claude-code/phase-02/base, a8e6b27445d3cf3e0ef199e085e5383e5fc73d69. Created at the clean finalized prompt checkpoint; object and ancestry checks passed.
- Phase implementation ref: refs/plans/mcp-v2-claude-code/phase-02/impl
- Plan commit ref: pending
- State checkpoint: pending
