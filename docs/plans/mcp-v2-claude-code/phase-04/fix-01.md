# Phase 4 Fix 1: Blocking specification findings

Continue the preserved Phase 4 tree. Read prompt.md, notes.md, journal.md, and this fix batch. Original acceptance criteria and restrictions remain authoritative. Do not reset or replay the phase. This file is Coordinator-owned and read-only to the worker.

## Coordinator evidence

Fresh original checks passed: focused 225 passed in 62.09s; full 529 passed, 3 deselected in 35.47s; git diff --check passed. The version-only uv.lock change is correct and all implementation paths match the approved set.

The actual-client diagnostic `/tmp/mcp-v2-phase4-spec-probes.py` ran with both existing SDK interpreters. Exact tool listing, negative-timeout invalid_request JSON, and unknown-job JSON passed. The same script reproduced B1-B3 below under both SDK 2.0.0 and 2.3.0. These blocking results override the worker's Meets Spec YES. No implementation checkpoint or quality review has occurred.

## Blocking batch

### B1: SDK coercion bypasses invalid_request

- server.py:636-642 validates the already-coerced integers, not the original tool arguments.
- Actual clients accept timeout_s=true, result_offset=true, and timeout_s="0" as normal successful calls for a terminal job. Both SDKs reproduce this despite integer input schemas.
- Reject schema-violating values before dispatch. Use the existing Pydantic/SDK seam with the smallest correction; do not add a separate schema-validation framework.
- Also cover the Boolean fresh_session parameter against numeric/string coercion, and prove malformed submission arguments cannot mutate or enqueue work.
- Actual-client regressions must return pure invalid_request JSON with isError, retryable=false, and schema-correction next_action under both existing SDKs. Preserve valid defaults and ordinary calls.

### B2: Terminal paging can fail to advance

- server.py:158-181 halves end to start. If the empty page fits while one remaining code point cannot, it returns text="" and next_offset equal to the requested offset.
- With the isolated known terminal job containing two emoji and a context_key of length 8470, the diagnostic returned empty text, next_offset=0, and two remaining code points. Repeating the call cannot finish.
- A terminal response with remaining text must return at least one code point and a strictly increasing next_offset, or response_too_large. Preserve normal empty/EOF reads and exact offsets.
- Add boundary regressions for metadata that fits alone but cannot fit the next escaped/non-ASCII code point. Continue to test complete serialized character/byte bounds and exact reassembly.

### B3: Concurrent canonical resolution overwrites the winner's alias

- runtime.py:321 calls Database.upsert_project. That existing API rechecks the root and updates the existing project's alias; it does not necessarily raise IntegrityError.
- The diagnostic inserts root/alias winner using a second real Database connection immediately before the original upsert. resolve_project(..., alias="loser") returns the winning ID but changes both returned and stored alias to loser.
- Preserve the existing canonical project's identity and alias when another insertion wins. Make the decision atomic using existing transaction/constraint patterns within allowed files. Do not change database.py, add an abstraction, or rely only on a mock raising IntegrityError when the real API does not.
- Add a deterministic regression using actual SQLite connection behavior. The original probe's injected insertion demonstrates the old race; adapt regression synchronization if a correct transaction serializes the insertion.

### B4: Complete the declared contract evidence

- The current tests verify only a subset of annotations and error families. Original Done When requires every documented expected error family, recursive privacy scans for every tool output, and bounded errors/applied-mutation semantics.
- Add minimum table-driven actual-client coverage for those missing requirements. Exercise real expected runtime paths where applicable rather than proving only an injected arbitrary error code.
- Check all seven annotations, every parameter description, absence of duplicated structured content, privacy of success/error payloads, and actual request-ID presence for unexpected errors.
- Cover submit, retry, and cancel overflow after application, retaining the root ID and the applied outcome, plus complete cancellation/dependency metadata handling. Preserve all scheduling and desktop behavior.

## Scope and verification

Allowed changes for this fix only:
- src/openmcp/server.py
- src/openmcp/runtime.py
- tests/test_server.py
- tests/test_runtime.py
- phase-04/notes.md and phase-04/journal.md, worker-owned sections only

All other files are read-only, including this fix file and all coordinator artifacts. The source scope is a subset of the original phase scope. A truly necessary additional path is BLOCKED rather than silently changed.

Record RED before each production correction, then fresh GREEN. Wrap commands in timeout --kill-after=5s 180s. Rerun the complete original focused and full commands, both existing-SDK actual-client checks, the affected edge probes, and git diff --check. Do not install/upgrade dependencies, change environments, write Git, invoke OpenMCP, restart the daemon, or inspect live/global configuration/database/auth/session data.

Return the full ERP with exact paths, commands, exits, counts, and limitations. Append it without replacing earlier consultation, approval, failure, or coordinator evidence. TASK_COMPLETE requires all original criteria and this batch to pass.
