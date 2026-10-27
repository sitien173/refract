# Shared Retry Policies Implementation Plan

**Status:** Approved for execution on `main`; baseline verification passed at `ef9f219`. Phases 1 and 2 passed specification and independent quality review. The user accepted Phase 2 with a waiver for missing historical RED evidence. Phase 3 is next.
**Design:** `docs/plans/shared-retry-policies/DESIGN.md`
**Commit:** `feat(retry): add shared target retry policies`

## Scope and Execution Boundary

Implement the confirmed shared-policy design in three sequential phases. Each implementation phase requires specification validation and independent review.

The user authorized execution on `main` despite unfinished telemetry plan acceptance. Preserve that plan and its existing commits. The user approved the consultation clarifications and the narrow Phase 2 telemetry correction.

Preserve every pre-existing change. Do not edit the telemetry plan. Do not stash, reset, commit, or incorporate its unfinished changes.

## Prerequisites

1. Waiting for telemetry completion was explicitly waived by the user. Leave its plan untouched.
2. Confirm no project job remains active and reconcile repository state.
3. Require a clean attached branch before creating the plan base anchor.
4. Use existing telemetry code as the baseline without consolidating its plan.
5. Consultation `556ea624-0f44-4357-a0af-c75eb8e1b03e` completed. Approved clarifications: unknown replay safety blocks retries; overflow recovery invocations are separate from policy attempts; each manual retry receives a fresh policy budget; Phase 2 includes a narrow telemetry rollover correction.
6. Run every verification command below against that clean baseline. Record results. If a baseline fails, stop and revise Phase 1 to repair it with user-approved scope.
7. The verified plan base is `refs/plans/shared-retry-policies/base` at `ef9f219`. Preserve that anchor.
8. Plan approval is confirmed. Resolve task guidance during execution.

Commands were not run during authoring. Execution baseline verification passed at `ef9f219`; exact counts are recorded in phase-01/journal.md. These commands remain fresh verification requirements for each phase.

## Route

- Sequence per phase: implement, validate, checkpoint, review.
- Implement profile: resolve from execution-time task guidance.
- Review profile: resolve from execution-time task guidance.
- No provider, target, or model is pinned.
- Create phase prompt, notes, and journal files only during execution.
- Finish with the plan-level commit after all phase reviews pass.

### Phase 1: Validated policies and durable execution snapshots

**Task Guide Input:** Implement global `retryPolicies` and optional target `retryPolicy` references. Resolve shared policies into immutable submission snapshots. Preserve legacy configuration, legacy persisted plans, target identity, and project overlay behavior. Use tests first. Do not implement retry execution or dashboard editing yet.

**Goal:** Submitted jobs retain validated retry settings independently of later configuration edits.

**Files:**
- Modify: `server/src/refract/config.py`
- Modify: `server/src/refract/planning.py`
- Modify: `server/src/refract/config_inspection.py`
- Modify: `server/tests/test_config.py`
- Modify: `server/tests/test_planning.py`
- Modify: `server/tests/test_config_inspection.py`
- Modify: `server/tests/test_runtime.py`

**Tasks:**
1. Add immutable retry policy data and strict global parsing. Validate counts, lists, unknown fields, references, and unsupported target-local retry declarations. Preserve the registry through project overlays.
2. Resolve policy values into execution plans. Parse old snapshots with retries disabled; round-trip new snapshots without consulting live configuration.
3. Separate retry snapshot data from target execution identity. Add regression coverage proving policy-only edits preserve existing keys and sessions. Sanitize new configuration errors.

**Acceptance Criteria:**
- Two targets can reference one policy.
- Missing policy sections and references preserve no-retry behavior.
- Zero permits no retries; two represents two additional attempts.
- Negative, boolean, fractional, and string counts fail validation.
- Malformed lists, empty rules entries, unknown fields, and dangling references fail validation.
- Empty rule lists remain valid.
- Old execution-plan JSON remains readable.
- Queued jobs retain their resolved settings after policy edits or deletion.
- Retry-only changes do not alter existing target execution keys.
- Configuration diagnostics do not expose operator-provided error patterns.

**Reviewer Checklist:**
- Inspect the global config section allowlist and project overlay copy path.
- Check serialization and parsing agree on policy values and defaults.
- Verify unchanged keys against pre-change target identity fixtures.
- Confirm malformed persisted retry data is rejected, not silently disabled.

**Verification Checks:**
- `cd server && uv run --extra dev pytest tests/test_config.py tests/test_planning.py tests/test_config_inspection.py tests/test_runtime.py`

### Phase 2: Bounded silent retries with replay protection

**Task Guide Input:** Execute the snapshotted policy within one job on the selected target. Retry only normalized transient failures that pass replay guards and code-or-pattern matching. Preserve context recovery, cancellation, capacity accounting, circuit probes, streams, ask tokens, sessions, and cumulative telemetry. Do not switch targets automatically or alter manual fallback semantics. Use fake drivers and tests first.

**Goal:** Eligible failures recover without exposing intermediate terminal job failures.

**Files:**
- Modify: `server/src/refract/execution.py`
- Modify: `server/tests/test_execution.py`
- Modify: `server/src/refract/telemetry.py`
- Modify: `server/tests/test_telemetry.py`
- Modify: `server/tests/test_target_capacity.py`
- Modify: `server/tests/test_runtime.py`

**Tasks:**
1. Add policy matching and a bounded same-target retry loop. Keep context-overflow recovery separate. Check cancellation before each additional invocation.
2. Preserve sequential attempt records, stream boundaries, ask-token cleanup, target capacity, probe ownership, and final-only health accounting. Store a successful turn once.
3. Add deterministic end-to-end regressions for success after failure, exhaustion, exclusions, cancellation, recovery, resource cleanup, telemetry, and existing fallback metadata.

**Acceptance Criteria:**
- `retryAttempt = 9` never exceeds ten policy attempts. Existing context-overflow recovery can add internal driver invocations.
- Each explicit manual retry receives a fresh policy budget; durable attempt numbering remains cumulative.
- Success stops additional attempts immediately.
- Disabled policies and unmatched rules invoke the target once.
- Exact code matches OR case-insensitive error substrings permit retries.
- Empty rule lists allow otherwise eligible transient failures.
- Rules cannot promote fatal, cancelled, context-overflow, or replay-blocked results.
- Tool activity and unknown replay safety block automatic replay. Final-only execution requires trustworthy replay-safety evidence.
- Arbitrary exceptions are not reclassified as transient failures.
- Cancellation stops remaining retries and releases all acquired resources.
- Intermediate failures do not terminate the job or send terminal notifications.
- Exhaustion preserves existing final failure and coordinator fallback metadata.
- The retry budget does not change existing context-overflow recovery behavior.
- Target capacity and circuit probes do not leak or admit concurrent half-open probes.
- Telemetry includes all retry consumption without double counting, including manual-to-automatic retry rollover when the next attempt reports no usage.
- Only the final successful response becomes a stored conversation turn.

**Reviewer Checklist:**
- Inspect every cancellation, exception, and exhaustion exit.
- Check semaphore and probe ownership throughout the retry sequence.
- Verify fatal-error and replay guards run before custom matching.
- Confirm intermediate failures cannot poison health before retries complete.
- Inspect stream attempt identities and telemetry totals across invocations.
- Confirm existing timeout and target fallback behavior remains unchanged.

**Verification Checks:**
- `cd server && uv run --extra dev pytest tests/test_execution.py tests/test_telemetry.py tests/test_target_capacity.py tests/test_runtime.py`

### Phase 3: Dashboard round trips and operator documentation

**Task Guide Input:** Expose and preserve target retry policy names through existing dashboard read and mutation models. Add a simple optional named-reference field to the target editor. Validate names server-side and preserve policy definitions through unrelated edits. Do not add policy CRUD or a new dashboard screen. Document the complete configuration and safety contract. Use tests first.

**Goal:** Operators can safely edit target policy references without losing shared configuration.

**Files:**
- Modify: `server/src/refract/models.py`
- Modify: `server/src/refract/config_mutation.py`
- Modify: `server/tests/test_config_mutation.py`
- Modify: `server/tests/test_mcp_schema_contract.py`
- Modify: `server/web/src/components/TargetEditor.jsx`
- Modify: `server/web/src/components/ConfigEditorSafety.test.jsx`
- Modify: `server/web/src/screens/Targets.test.jsx`
- Modify: `server/README.md`

**Tasks:**
1. Add optional policy-reference data to existing target models and serializers. Round-trip it through creation, editing, clearing, and reload paths. Retain source comments, policy tables, and revision-conflict protection.
2. Add the target editor field and regression tests. Display validation failures without discarding drafts or changing existing configuration.
3. Document shared examples, retry-count semantics, OR matching, defaults, exclusions, logging, costs, and unchanged fallback behavior. Run final server, dashboard, and build checks.

**Acceptance Criteria:**
- Existing targets without references remain editable.
- A valid reference survives API and dashboard round trips.
- Clearing the reference disables automatic retries.
- Unknown names fail without mutating configuration or discarding drafts.
- Editing unrelated target fields preserves the reference and shared policy tables.
- Creating or deleting a target does not delete shared policies.
- Conflict reload preserves the freshly loaded reference.
- Documentation uses `retryPolicies`, `retryPolicy`, and `retryAttempt` consistently.
- No new policy management screen, dependencies, or unrelated UI changes appear.
- Generated dashboard assets are produced by the verified build, not handwritten.

**Reviewer Checklist:**
- Inspect model field aliases and TOML serialization for exact public names.
- Check initial form, submit payload, and conflict-reload paths.
- Verify existing strict API models accept the additive field correctly.
- Check shared configuration remains intact after mutation rejection.
- Confirm examples describe normalized errors without promising backend-specific codes.

**Verification Checks:**
- `cd server && uv run --extra dev pytest tests/test_config_mutation.py tests/test_mcp_schema_contract.py`
- `cd server/web && npm test -- src/components/ConfigEditorSafety.test.jsx src/screens/Targets.test.jsx`
- `cd server && uv run --extra dev pytest`
- `cd server/web && npm test`
- `cd server/web && npm run build`

## Final Acceptance

All three phases require fresh validation and independent review. Record exact verification evidence and any assigned debt in phase journals. Consolidate only this plan's checkpoints into the stated Conventional Commit. Never absorb unfinished telemetry work.

No live backend probes or daemon restarts are included. Execution is explicitly authorized; completion still requires verification and review.
