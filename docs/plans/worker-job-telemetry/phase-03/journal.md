<!-- refract-shared-version: 2.0.0 -->

# Phase 3 Journal: Bounded session telemetry and capability evidence

## META
- Plan: docs/plans/worker-job-telemetry/PLAN.md
- Implementation Profile: implement
- Review Profile: base
- Implementation Jobs: c5fd69fa-f7a8-4be1-b94c-6d059d79e850; 8fa71336-a493-4f56-8558-d94316dbb6de
- Review Job: 8c5dce8b-665d-4253-842a-65b833242b7e
- Started: 2026-10-26
- Finished: pending

## Implementation Response

- Initial ERP TASK_COMPLETE. Declared files match diff. Fresh suite 711 passed, 15 deselected.
- Coordinator specification failed: unbounded discovery, invented scalar token_count schema, unsafe baselines, stale identity/context, Agy provenance, unsupported documentation claims.
- Fix cycle 1 ERP TASK_COMPLETE. Inspected declared diff. Speculative cumulative parsing removed, discovery limits added, invalidation and provenance improved.
- Remaining requirement: verified Codex token_count capacity/context enrichment was removed, not implemented. Public protocol evidence fetched through tvly from https://raw.githubusercontent.com/openai/codex/main/codex-rs/protocol/src/protocol.rs. It defines TokenUsageInfo with total_token_usage and last_token_usage objects plus model_context_window. TokenUsage total_tokens differs from cumulative totals. Main-branch evidence is not an installed-version guarantee.
- Coordinator verification of cycle 1: 716 passed, 15 deselected.
- Specification cycle 2 job a22db1a2-dd19-4f78-84ce-6ce42213ac44 used available profile openai after earlier implementation lacked evidence. Returned TASK_COMPLETE. Five declared files matched inspected diff.
- Fresh full coordinator check at f1501fb: `cd server && uv run pytest` passed, 717 passed, 15 deselected, 124.13 seconds.
- No live probes were authorized or run. Runtime capability remains explicitly unverified.

## Quality Review

Independent job `8c5dce8b-665d-4253-842a-65b833242b7e` returned FAIL. Reviewed refs/plans/worker-job-telemetry/phase-03/base..f1501fb6642d96488eb81404bfafaf85ed2ac335. Coordinator confirmed server tree and HEAD unchanged after review.

1. Codex null invalidation observations do not clear persisted context. Execution record_context_snapshot ignores null components. Backend local becomes null while execution retains 1060/64000. Add explicit invalidation contract and running-metadata regression. Paths: codex.py:72–85; execution.py:529–540; telemetry.py:322–336.
2. Turn consumption overwrites verified response-local context after rollout poll. Verified 1060 becomes 5700 retaining old capacity. Keep verified snapshot precedence and test integrated parser. Path: codex.py:656–718.
3. Changed session ID resets file but retains old context without emitting clear. Missing new file leaves 1060/64000 attributed incorrectly. Clear local and persisted context. Path: codex.py:56–62.
4. Descriptor identity verified during discovery is discarded before later pathname stat. A replacement can bypass ownership validation; malformed/missing session header can leave trust intact. Carry verified descriptor identity forward and require matching metadata on consumed descriptor. Path: codex.py:146–173,197–205,242–253,288–297.
5. Prefix-only reads publish historical snapshots then stop permanently at 1 MiB without clearing them. Newer compaction/model events may remain unread. Reconcile latest state within bounds or mark unavailable; test large resumed rollout. Path: codex.py:234–235,252–266,317–323.

Live-probe limitations are not blockers. Two automatic specification fix cycles exhausted. Further fixes require user authorization. Explicit persisted invalidation may require execution.py and test_execution.py beyond original Phase 3 allowed file set; approve that narrowly with additional cycle.

## Review Result
- Spec Status: FAIL
- Quality Status: FAIL
- Phase outcome: BLOCKED
- Debt: none. Correctness blockers cannot be accepted as debt.
- Next: authorize additional Phase 3 fix/review cycle including narrow execution invalidation changes.

## Final Checkpoint
- Phase base ref: refs/plans/worker-job-telemetry/phase-03/base
- Phase implementation ref: pending
- State checkpoint: temporary commit
