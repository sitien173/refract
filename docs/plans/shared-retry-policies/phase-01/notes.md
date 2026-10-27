# Phase 1: Decision Notes

## Task 1

### Decisions made
- Defined `RetryPolicy` frozen dataclass with `retry_attempt: int = 0`, `error_codes: tuple[str, ...] = ()`, and `error_patterns: tuple[str, ...] = ()`.
- Added `retry_policy: str = ""` to `TargetConfig` and `retry_policies: dict[str, RetryPolicy] = field(default_factory=dict)` to `DaemonConfig`.
- Accepted `retryPolicies` in global TOML section allowlist and preserved `retry_policies` across project overlays.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `server/tests/test_config.py` had 21 failures with `Unsupported config sections: ['retryPolicies']` and `AttributeError: 'DaemonConfig' object has no attribute 'retry_policies'`; passed 88 tests after adding `_retry_policies` parser and configuration dataclass fields.
- Root cause (bugfix only): - none

## Task 2

### Decisions made
- Resolved target retry policies into `ExecutionPlan.retry_policies` dictionary and exposed `ExecutionPlan.retry_policy(target_id: str) -> RetryPolicy`.
- Validated persisted execution plan snapshots fail closed on malformed values and dangling policy references.
- Serialized `retry_policies` in `execution_plan_data` when present and handled legacy plans without retry sections as disabled retries.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `server/tests/test_planning.py` had 16 failures with `AttributeError: 'ExecutionPlan' object has no attribute 'retry_policies'` and unraised `ValueError` on malformed persisted data; passed 30 tests after implementing snapshot resolution and parse validation.
- Root cause (bugfix only): - none

## Task 3

### Decisions made
- Decoupled `target_execution_key` calculation from `_target_data` via dedicated `_target_identity_data` hashing only historical fields.
- Verified exact literal pre-change target execution key fixture `primary:fcb7f648a676a587` remains identical across policy-only edits.
- Sanitized configuration diagnostics to eliminate operator-provided error patterns, policy identifiers, and declaration contents.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  1. Sanitizer characterization: Tested against original `config_inspection.py` from base `a3eb8b0`. Unhandled retry policy diagnostics (`Retry policy 'SECRET_POLICY' has unsupported settings`, `Target 'SECRET_TARGET' references unknown retry policy`, etc.) fell through to `"Invalid configuration"`, failing `assert sanitized == expected`. Adding `_retry_policy_config_error` and `_target_config_error` rules produced expected clean sanitization across all 8 assertions with zero `SECRET_` tokens exposed.
  2. Identity key characterization: Tested against baseline `TargetConfig` at `a3eb8b0` lacking `retry_policy`. Adding `retry_policy: str = ""` coupled to `_target_data/asdict` altered historical key `primary:fcb7f648a676a587` to `primary:bee39699a04620cc`, and `retryPolicy="transient"` altered it to `primary:5d07857ff1490e01`. Decoupling `target_execution_key` to hash strictly historical fields restored literal fixture `primary:fcb7f648a676a587` and preserved session lookup `assert runtime.database.session(...) == 'sess_historical_123'` across configuration reloads.
- Root cause (bugfix only): - none

## Specification Batch 1 Corrections

### Decisions made
- Replaced mutable dictionary in `ExecutionPlan.retry_policies` with an immutable `MappingProxyType` snapshot isolated from caller mappings via defensive copy in `__post_init__`.
- Enforced canonical snake_case persisted retry policy schema (`retry_attempt`, `error_codes`, `error_patterns`); rejected dual camel aliases (`retryAttempt`, `errorCodes`, `errorPatterns`) and explicit persisted `null`.
- Removed unrequested `retry_policy` alias on targets in `config.py` in favor of documented `retryPolicy` only, rejecting unsupported settings.
- Removed orphaned `asdict` import from `planning.py` and eliminated EOF trailing blank lines across test files.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - `test_execution_plan_retry_policies_is_immutable_and_isolated`: RED with `Failed: DID NOT RAISE TypeError` when modifying `plan.retry_policies["transient"] = ...`; GREEN after `MappingProxyType` wrapping.
  - `test_plan_rejects_malformed_persisted_retry_data`: RED with unraised `ValueError` on persisted camel aliases `retryAttempt`, `errorCodes`, `errorPatterns`, and `retryPolicy` on target; GREEN after restricting allowed persisted schema to canonical snake_case.
  - `test_plan_rejects_explicit_null_retry_policies`: RED with `Failed: DID NOT RAISE ValueError` on `retry_policies=None`; GREEN after checking `if "retry_policies" in data` and failing closed on non-dict.
  - `test_target_rejects_unrequested_retry_policy_alias`: RED when `retry_policy` was accepted; GREEN after explicitly rejecting `retry_policy` in target parser.
  - `git diff --check`: RED with 4 EOF trailing blank line errors; GREEN with exit code 0 after cleanup.
- Root cause (bugfix only): - none

## Specification Batch 2 Corrections

### Decisions made
- Fixed fail-closed invariant in `parse_execution_plan`: absent `retry_policies` in serialized plans defaults to `{}` and still validates that no targets contain new `retry_policy` references.
- Updated `resolve_execution_plan` to fail closed if a target references an unknown retry policy instead of omitting it.
- Updated `ExecutionPlan.retry_policy(target_id)` to raise `ValueError` on dangling references instead of silently returning default `RetryPolicy()`.
- Preserved genuine legacy execution plan parsing where neither `retry_policies` nor target references are present.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - `test_plan_rejects_missing_retry_policies_when_target_references_policy`: RED with `Failed: DID NOT RAISE ValueError` when deleting top-level `retry_policies` from a plan with `primary` referencing `transient`; GREEN after parsing empty registry and validating references.
  - `test_retry_policy_accessor_rejects_dangling_reference`: RED with `Failed: DID NOT RAISE ValueError` when accessing policy for target with dangling reference; GREEN after explicit membership check raising `ValueError`.
  - `test_resolve_execution_plan_rejects_dangling_reference`: RED with `Failed: DID NOT RAISE ValueError` when resolving plan with unknown target retry policy; GREEN after explicit validation raising `ValueError`.
- Root cause (bugfix only): - none
