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
- Spec Status: PASS
- Quality Status: PASS
- Phase outcome: DONE
- Debt: none
- User authorized additional cycle with narrow execution invalidation scope.
- Implementation `9020ee32-ac57-4dcd-a997-54a6408cbff6` returned TASK_COMPLETE, five declared files matched diff.
- Fresh coordinator full Python check: 722 passed, 15 deselected, 124.43 seconds at tree checkpoint `22d42a0`.
- Independent re-review `e5111532-4408-4275-89ac-cac0d2a78cc3`: FAIL, two remaining correctness blockers.
  1. codex.py:253–257,721–725,743–750: turn.completed immediately repopulates context after budget exhaustion. Exhausted collector plus input 5000/output 700/reasoning 100 yields 5600 rather than null. Suppress fallback context and emitted observations after exhaustion; test integrated parser and persistence.
  2. codex.py:243–246,274–291: same-inode truncation resets offset without revoking header_verified. Token-only shortened file supplies 990 used/200000 capacity without owner header. Revoke and revalidate header on truncation; regression required.
- Reviewer confirmed persisted invalidation, normal rollout precedence, session switch, and different-inode discovery replacement are addressed.
- User authorized narrow final cycle. Implementation job `a1aa9b23-b8d0-481e-9513-410b670db9c4` returned TASK_COMPLETE; four declared files match inspected diff.
- RED and GREEN evidence in notes Task 6. Source delta: revoke header_verified on truncation; guard both fallback context paths with budget_exhausted.
- Fresh coordinator check at `cee6b69`: `cd server && uv run pytest` passed, 724 passed, 15 deselected, 127.77 seconds.
- Independent review `adb85142-6224-4deb-890e-10cb2c6a94b1`: PASS. Both remaining blockers fixed; no introduced blockers. No implementation or Git changes from reviewer.
- Accepted limitation: runtime availability/timing remains unverified because live probes are not authorized. Unsupported Pi/Agy capacities remain unavailable.
- Next: Execute Phase 4.

## Final Checkpoint
- Phase base ref: refs/plans/worker-job-telemetry/phase-03/base
- Phase implementation ref: refs/plans/worker-job-telemetry/phase-03/impl
- State checkpoint: temporary commit
