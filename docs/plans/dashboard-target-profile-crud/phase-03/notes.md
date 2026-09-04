<!-- ccg-shared-version: 10.2.0 -->

# Phase 3 — Decision Notes

## Task 1

### Decisions made
- Defined strict models in `openmcp.models`: `WorkflowPolicyData`, `ProfileEditorData`, `ProfileEditorResponse`, `ProfileReference`, `ProfileListResponse`, `ProfileResponse`, `ProfileDeleteResponse`, `ProjectOverrideListResponse`, `ProjectOverrideResponse`, and `ProjectOverrideDeleteResponse`.
- `WorkflowPolicyData` defaults `max_attempts` to target count (or 1) and `timeout_s` to 0; forbids extra fields.
- `ProfileEditorData` normalizes whitespace-only `extends` to `None`; forbids extra fields; permits null workflow policies representing undeclared workflows.
- `ProfileEditorResponse` exposes `declared`, `inherited`, `effective`, and `sources` mappings for all built-in workflows.
- `ProjectOverrideDeleteResponse` includes optional `fallback` containing the resulting effective global profile fallback.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Responses distinguish declared, inherited, and effective workflow values across all four built-in workflows (`consult`, `implement`, `other`, `review`).

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `test_phase3_profile_editor_models` failed initially with `ImportError: cannot import name 'ProfileEditorData'`, then passed once models were defined and exported in `openmcp.models`.

## Task 2

### Decisions made
- Implemented global profile CRUD methods on `ConfigurationMutationService`: `read_profiles()`, `get_profile()`, `find_profile_references()`, `create_profile()`, `update_profile()`, and `delete_profile()`.
- Preserved existing string or array shorthand in TOML unless an edited workflow requires expansion (`timeout_s > 0` or custom `max_attempts`).
- Deletion is blocked if referenced by global daemon `default_profile`, registered project `default_profile`, global profile `extends`, or registered project profile `extends`.
- Reference checks scan declared ASTs without triggering effective policy evaluation.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Global profile mutations validate every registered project overlay before committing changes.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `test_global_profile_crud_and_references` failed initially before `ConfigurationMutationService` profile CRUD was implemented, then passed.

## Task 3

### Decisions made
- Implemented project override CRUD methods on `ConfigurationMutationService`: `read_project_overrides()`, `get_project_override()`, `create_project_override()`, `update_project_override()`, and `delete_project_override()`.
- Minimal project file creation: missing `.openmcp/config.toml` is created atomically on demand with only the new profile override.
- Deleting the last project override removes the empty `profiles` section to keep the configuration file clean.
- Override deletion calculates and returns the effective global fallback profile.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Project profile mutations operate independently with project-specific source revisions.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `test_project_override_crud_and_missing_file_creation` failed initially before override CRUD methods were implemented, then passed.

## Task 4

### Decisions made
- Registered 10 dashboard routes in `register_dashboard_routes` for global profiles and project overrides.
- Required loopback host and client for full editor reads; required loopback, same-origin CSRF, and `If-Match` for mutations.
- Updated `_jsonable` in `dashboard.py` to preserve `null` for undeclared workflows in profile editor responses.
- Added workflow normalization to `ProfileEditorData` supporting both nested `workflows` and top-level workflow keys while forbidding unknown fields.
- Added comprehensive API security, concurrency, inheritance, reference blocking, fallback, and compatibility tests in `tests/test_dashboard.py`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Undeclared workflows appear as `null` in JSON output, indicating undeclared rather than disabled.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `test_configuration_profiles_crud_and_references` and `test_project_profile_override_routes_crud_and_fallback` in `tests/test_dashboard.py` initially failed on missing top-level workflow normalization and self-extension inheritance, then passed.
