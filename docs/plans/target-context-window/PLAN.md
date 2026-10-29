# Target Context Window Implementation Plan

**Design:** [DESIGN.md](DESIGN.md)
**Status:** All three phases accepted. Execution authorized by goal `mvszzbsy-8oqe2d`. Final revision is retained at `refs/plans/target-context-window/impl`.
**Base:** `refs/plans/target-context-window/base`
**Commit:** `feat(telemetry): support configured target context windows`

## Scope

Implement the approved configuration override and qualified telemetry fallback.
Leave `docs/plans/worker-job-telemetry/` and unrelated files untouched.
Use existing measurement metadata and durable JSON storage.
No database migration, new dependency, or live probe is required.

## Route

- Sequence: implement -> review, for each phase.
- Implement Profile: selected through task guidance during execution.
- Review Profile: selected through task guidance during execution.
- Reason: configuration, lifecycle, and dashboard changes require separate checks.
- Done When: all phase criteria and fresh verification checks pass.

Profiles are deliberately unpinned. Obtain guidance when execution starts.
Use `target-context-window` as the execution context key.
Apply test-driven development within every implementation phase.
Run independent read-only review after each validated implementation checkpoint.
Reconcile the existing active telemetry plan before execution.
This plan neither resumes nor completes that separate work.

## Baseline

Baseline revision: `391e679a05f0ccf05f7644d7f3db9986efca70a0`.
Fresh baseline checks completed successfully in task `baae75ac5`:

- `cd server && uv run pytest -q`: 1216 passed, 23 skipped, 15 deselected.
- `cd server/web && npm test`: 273 passed across 22 files.
- `cd server/web && npm run build -- --outDir /tmp/refract-target-context-window-baseline`: exit 0.

Existing React test warnings did not fail the checks.
Environment warnings concerned an ignored external virtualenv and SSL_CERT_DIR.
Skipped and deselected tests are not claimed as verified.
Commands run from the repository root unless stated otherwise.
The isolated build did not modify tracked dashboard assets.

### Phase 1: Preserve configured capacity throughout target configuration

**Task Guide Input:** Add optional positive-integer `contextWindow` to global targets and target-editor APIs. Preserve, clear, inspect, serialize, and snapshot the setting without changing worker session identity. Cover existing configurations and persisted plans lacking the field. No telemetry calculation or UI changes yet.

**Goal:** Execution plans retain validated, execution-time target capacity.

**Files:**
- Modify: `server/src/refract/config.py`
- Modify: `server/src/refract/models.py`
- Modify: `server/src/refract/config_mutation.py`
- Modify: `server/src/refract/dashboard.py`
- Modify: `server/src/refract/planning.py`
- Modify: `server/src/refract/runtime.py`
- Modify: `server/tests/test_runtime.py`
- Modify: `server/tests/test_config.py`
- Modify: `server/tests/test_config_mutation.py`
- Modify: `server/tests/test_dashboard.py`
- Modify: `server/tests/test_planning.py`

**Tasks:**
1. Add parser and editor-model validation with regression tests.
2. Update target projections and mutation round trips.
3. Persist capacity in execution-plan targets, outside session identity.
4. Preserve environment-bound sessions across capacity-only edits.

Review-driven scope addition: `runtime.py` and `test_runtime.py` are required because environment-bound sessions also incorporate global configuration revisions. Capacity-only changes must not rotate those revisions. Real environment changes must still invalidate sessions.

**Acceptance Criteria:**
- TOML and editor APIs accept `contextWindow = 200000`.
- Reject zero, negatives, floats, booleans, and strings.
- Omitted TOML capacity remains `None` internally.
- Omitted update payload preserves existing capacity.
- Explicit null removes the TOML key without unrelated changes.
- Create, list, read, update, and runtime inspection retain capacity.
- Persisted execution plans retain capacity across configuration reloads.
- Historical execution plans without capacity still load unchanged.
- Capacity-only changes do not change `target_execution_key`.
- Environment restrictions and retry-policy behavior remain unchanged.

**Reviewer Checklist:**
- Inspect every TargetConfig reconstruction for dropped capacity.
- Confirm `contextWindow` public spelling and strict validation.
- Confirm absent fields preserve historical snapshot compatibility.
- Keep capacity out of session/process identity and secrets.

**Verification Checks:**
- `cd server && uv run pytest -q`

### Phase 2: Resolve and persist qualified context telemetry

**Task Guide Input:** Bind configured capacity to the selected execution target. Reuse context measurements to implement configured-capacity override, provider usage precedence, and estimated job-input-plus-output fallback. Preserve cumulative accounting, retries, compaction invalidation, target changes, live updates, terminal metadata, and historical persistence. No frontend arithmetic or backend CLI changes.

**Goal:** Live and terminal telemetry consistently report resolved capacity and remaining percentage.

**Files:**
- Modify: `server/src/refract/telemetry.py`
- Modify: `server/src/refract/execution.py`
- Modify: `server/tests/test_telemetry.py`
- Modify: `server/tests/test_execution.py`
- Modify: `server/tests/test_streaming_backends.py`
- Modify: `server/tests/test_result_metadata.py`
- Modify: `server/tests/test_database.py`

**Tasks:**
1. Add failing precedence, missing-data, and bounds tests.
2. Resolve measurements centrally with configured capacity and quality propagation.
3. Bind lifecycle configuration and preserve resolved telemetry through existing persistence.
4. Verify terminal paths, restart restoration, and public metadata.

**Acceptance Criteria:**
- Configured capacity overrides conflicting provider capacity.
- Provider capacity remains usable when configuration is absent.
- Capacity-only state survives serialization before token events.
- Provider context usage always supersedes cumulative fallback usage.
- Fallback requires known input and output totals, including valid zeros.
- Fallback usage equals job input plus output, excluding extra cache additions.
- Fallback usage and remaining percentage have quality `estimated`.
- Configured capacity has source `target_config` and quality `reported`.
- Provider usage with configured capacity derives remaining percentage.
- Recompute conflicting provider percentages against configured capacity.
- Unknown usage with an override leaves remaining unavailable.
- Remaining percentage is clamped to 0 through 100 and rounded to two decimals.
- Usage above capacity remains visible without truncating usage itself.
- New attempts and target changes invalidate stale provider context.
- Target changes replace or remove the configured override.
- Compaction preserves configured capacity and enables qualified fallback.
- Existing consumption deduplication and completeness remain unchanged.
- Finalization, failures, and cancellation retain resolved measurements.
- Reloaded historical telemetry ignores subsequent configuration edits.
- Existing grouped metadata remains valid without parallel field aliases.

**Reviewer Checklist:**
- Check raw provider context remains distinguishable from fallback values.
- Prevent fallback snapshots from becoming authoritative provider observations.
- Inspect `_safe_telemetry_dump` for capacity-only state loss.
- Inspect hydration and merge ordering for stale context resurrection.
- Confirm target attribution and late-event handling remain correct.
- Confirm no frontend-only or read-time configuration resolution exists.

**Verification Checks:**
- `cd server && uv run pytest -q`

### Phase 3: Expose capacity editing and explain telemetry estimates

**Task Guide Input:** Add optional target context capacity editing, preserve blank/clear semantics, and explain estimated context measurements in JobDetails using server-provided quality/source metadata. Document configuration precedence and consumption limitations. Preserve editor conflict safety, accessible labels, and existing historical rendering.

**Goal:** Operators configure capacity and distinguish estimated remaining context.

**Files:**
- Modify: `server/web/src/components/TargetEditor.jsx`
- Modify: `server/web/src/components/JobDetails.jsx`
- Modify: `server/web/src/screens/Targets.test.jsx`
- Modify: `server/web/src/components/ConfigEditorSafety.test.jsx`
- Modify: `server/web/src/components/JobDetails.test.jsx`
- Modify: `server/README.md`

**Tasks:**
1. Test and implement an optional labeled positive-integer editor input.
2. Test estimated telemetry explanation and existing quality/source rendering.
3. Document `contextWindow`, override precedence, fallback, and limitations.

**Acceptance Criteria:**
- Creation and editing send `contextWindow` as an integer.
- Blank input sends explicit null to clear capacity.
- Invalid numbers do not become zero or rounded integers.
- Existing values hydrate correctly without overwriting dirty drafts.
- Existing conflict, revision, and reload protections remain intact.
- Estimated usage and remaining show an explicit estimated indicator.
- Visible explanatory text identifies cumulative job input plus output.
- Explanation notes possible overcounting across turns, retries, and compaction.
- Provider snapshots are not mislabeled as cumulative estimates.
- Capacity without usage displays unavailable remaining, not 100%.
- Legacy jobs and absent capacity still render safely.
- UI renders server values without reimplementing the formula.
- Documentation includes a valid `[[targets]]` example and optional clearing behavior.
- Build output is isolated; tracked packaged assets remain unchanged.

**Reviewer Checklist:**
- Check input labeling, strict validation, and blank clearing.
- Check quality badges for both usage and remaining percentage.
- Check truthful distinction between capacity and consumed tokens.
- Check README statements match the configured override policy.

**Verification Checks:**
- `cd server && uv run pytest -q`
- `cd server/web && npm test`
- `cd server/web && npm run build -- --outDir /tmp/refract-target-context-window-baseline`

## Completion

Fresh verification and both reviews are required per phase.
Approval of this plan authorizes execution only when explicitly requested.
Consolidate validated checkpoints under the single plan commit message.
Do not claim actual context occupancy from cumulative token estimates.
