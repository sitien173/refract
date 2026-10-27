# Phase 3: Decision Notes

## Task 1

### Decisions made
- Added `retryPolicy: str = Field(default="", alias="retry_policy")` with `@property def retry_policy(self) -> str` and `populate_by_name=True` on `TargetEditorData`.
- Added field validator normalizing `None` and whitespace to empty string `""` on `TargetEditorData.retryPolicy`.
- Added model validator rejecting mixed conflicting keys `retryPolicy` and `retry_policy` on `TargetEditorData`.
- Exposed `retryPolicy` from `target_to_editor_data` for both `TargetConfig` dataclass and TOML target tables.
- Emitted `retryPolicy` in `_new_target_table` when present, omitting it when empty.
- Implemented `_update_target_retry_settings` to update `retryPolicy` when non-empty, and remove `retryPolicy` and legacy `retry_policy` keys when cleared to empty string, avoiding dangling empty policy reference.
- Verified candidate validation against `resolve_global_catalog` rejects unknown retry policy names with `configuration_invalid` before committing changes to disk.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `cd server && uv run --extra dev pytest tests/test_config_mutation.py -k "retry_policy"` had 8 failures: `ValidationError: Extra inputs are not permitted [type=extra_forbidden, input_value='transient', input_type=str]` and `AttributeError: 'TargetEditorData' object has no attribute 'retryPolicy'`. Passed 8 tests after implementing `TargetEditorData.retryPolicy` and mutation helpers. Verified full test target with `cd server && uv run --extra dev pytest tests/test_config_mutation.py tests/test_mcp_schema_contract.py` passing 73 tests.
- Root cause (bugfix only): - none

## Task 2

### Decisions made
- Added `retryPolicy: ''` to `initialForm` state in `TargetEditor.jsx`.
- Initialized form with `retryPolicy: target.retryPolicy || target.retry_policy || ''` in `TargetEditor.jsx`.
- Trimmed and passed `retryPolicy: formData.retryPolicy.trim()` into `targetPayload` in `TargetEditor.jsx`.
- Updated `handleReloadConfiguration` in `TargetEditor.jsx` to apply `retryPolicy: item.retryPolicy || item.retry_policy || ''`.
- Added input for `Retry policy` (`id="target-retry-policy"`, label "Retry policy", placeholder "e.g. transient, network-flake") within `target-editor-grid` in `TargetEditor.jsx`.
- Updated existing `Targets.test.jsx` create target test to expect `retryPolicy: ''` in payload.
- Added comprehensive regressions in `Targets.test.jsx` covering loading, editing, submitting, clearing, draft preservation on rejection, and conflict reload preservation of `retryPolicy`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `cd server/web && npm test -- src/screens/Targets.test.jsx -t retryPolicy` failed with `Unable to find a label with the text of: /Retry policy/i`. Passed all 4 retryPolicy tests and all 18 suite tests after adding the `Retry policy` input and payload handling to `TargetEditor.jsx`. Full web suite `cd server/web && npm test` passed all 21 test files (246 tests).
- Root cause (bugfix only): - none

## Task 3

### Decisions made
- Documented shared retry policy configuration examples and schema in `server/README.md`.
- Documented `retryAttempt` count semantics, defaulting to 0, `retryAttempt = 9` allowing ten attempts, separate context-overflow internal recovery bounds, and fresh budgets on manual retries.
- Documented rule matching using exact codes or case-insensitive substrings against normalized transient failures only, with empty lists permitting eligible failures.
- Documented safety exclusions: fatal errors, cancellations, context overflows, replay-blocked failures, observed tool activity, and unknown replay safety.
- Documented observability through sequential attempt logs and transcripts, single turn persistence for the final successful response, and cumulative token consumption and costs.
- Documented same-target routing without automatic target switching and unchanged manual fallback semantics.
- Documented TOML-managed global definitions without dedicated policy CRUD screen, and target editor roundtrip, validation, and draft safety.
- Built production dashboard static assets via `npm run build` directly producing tracked assets in `server/src/refract/dashboard_static`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- Documentation/build verification, TDD not applicable to prose: verified all 5 prompt test suites and build passed with 0 errors (`cd server && uv run --extra dev pytest tests/test_config_mutation.py tests/test_mcp_schema_contract.py` [73 passed], `cd server/web && npm test -- src/components/ConfigEditorSafety.test.jsx src/screens/Targets.test.jsx` [32 passed], `cd server && uv run --extra dev pytest` [821 passed], `cd server/web && npm test` [246 passed], `cd server/web && npm run build` [built in 3.13s], `git diff --check` [clean]).
- Root cause (bugfix only): - none
