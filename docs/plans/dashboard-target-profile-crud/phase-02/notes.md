<!-- ccg-shared-version: 10.2.0 -->

# Phase 2 — Decision Notes

## Task 1

### Decisions made
- Request and response models defined in `openmcp.models`: `TargetReference`, `TargetEditorData`, `TargetListResponse`, `TargetResponse`, and `TargetDeleteResponse`.
- `TargetEditorData` forbids extra fields (`model_config = ConfigDict(extra="forbid")`) and normalizes legacy `profile` to `backend_profile` while rejecting ambiguous mixed input.
- `DashboardError` was extended to accept optional `references: list[dict[str, Any]] | None = None`.

### Spec deviations
- none

### Tradeoffs accepted
- Input normalization accepts `profile` as an alias for `backend_profile` on payload parsing to accommodate existing callers, but serializes only `backend_profile` on target outputs.

### Assumptions
- Target model fields expose all 10 supported fields: `id`, `backend`, `model`, `backend_profile`, `reasoning`, `system_prompt`, `isolated`, `read_only`, `args`, and `max_concurrency`.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `TargetEditorData.model_validate({"id": "t", "extra": 1})` fails with `ValidationError` (extra fields forbidden); valid payloads succeed with defaults populated.

## Task 2

### Decisions made
- Implemented `read_targets`, `get_target`, `find_target_references`, `create_target`, `update_target`, and `delete_target` on `ConfigurationMutationService`.
- Both `read_targets` and `get_target` derive editor content and revision from a single source read (`_regular_source`), eliminating double-read discrepancies.
- Reference scanning scans current parsed global profile declarations directly from `document` (parsing disk source if not provided) and registered projects' `.openmcp/config.toml` declarations; existing, queued, or historical jobs do not block deletion.
- Target updates forbid target identifier renames (`data.id == target_id`).
- Existing legacy `profile` key is preserved on update; newly created targets emit `backend_profile` only.
- Referenced deletions raise `ConfigurationMutationError(code="referenced", references=...)` containing structured references.

### Spec deviations
- none

### Tradeoffs accepted
- Scanning checks registered database projects only; unregistered repositories are excluded from runtime referential integrity.

### Assumptions
- Deleting an unreferenced target removes it from `document["targets"]` and triggers candidate validation and runtime catalog reload through `commit_document`.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - Initial test run failed before fixing field substring match in `test_create_target_emits_backend_profile_only_and_preserves_unrelated` and `create_job` arguments in `test_delete_target_blocked_by_global_and_project_declarations_ignores_jobs`.
  - Review fix added `test_read_targets_and_get_target_single_source_read` confirming exactly 1 source read per inspection.
  - Review fix added `test_delete_target_scans_current_parsed_global_declarations` proving newly added global references block deletion even when missing from in-memory catalog.
  - Review fix added `test_delete_target_unreferenced_in_current_document_succeeds_even_if_stale_catalog_had_reference` proving deleted references allow target deletion even when in-memory catalog had stale references.
  - Review fix added `test_find_target_references_with_explicit_document` proving declaration parsing on custom documents.
  - All 72 unit tests in `tests/test_config_mutation.py` pass.

## Task 3

### Decisions made
- Registered `/dashboard/api/configuration/targets` (GET, POST) and `/dashboard/api/configuration/targets/{target_id}` (GET, PUT, DELETE) in `dashboard.py` before wildcard handlers.
- Full editor reads require loopback host and client (`_authorized_editor_read`).
- Mutations require loopback host, client, matching origin, CSRF token (`_authorized_mutation`), and `If-Match` header.
- Editor responses set `Cache-Control: no-store` and `ETag: f'"{revision}"'`.
- Missing `If-Match` returns 428 `revision_required`; stale revision returns 409 `configuration_conflict` with `current`; referenced deletion returns 409 `referenced` with `references`; validation failure returns 422 `configuration_invalid`.
- Route handlers contain zero direct TOML manipulation, delegating entirely to `runtime.mutations`.

### Spec deviations
- none

### Tradeoffs accepted
- Error sanitization via `sanitize_config_error` strips sensitive prompt text and raw argument values from all mutation error messages returned to clients.

### Assumptions
- The existing runtime `/dashboard/api/targets` endpoint remains intact and unchanged.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `test_configuration_target_error_redaction` verified that secret system prompt text is omitted from 422 responses and sanitized error envelopes match specification.

## Task 4

### Decisions made
- Added API security, concurrency, redaction, reference blocking, and compatibility tests in `tests/test_config_mutation.py` and `tests/test_dashboard.py`.
- Verified that remote clients and mismatched origins receive 403 Forbidden on both editor reads and mutations.
- Verified that existing `/dashboard/api/targets` endpoint returns unmodified runtime view without sensitive fields.

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
  - `uv run pytest tests/test_config_mutation.py tests/test_dashboard.py -q`: 96 passed.
  - `uv run pytest tests/test_server.py tests/test_runtime.py -q`: 42 passed.
  - `uv run pytest -q`: 396 passed.
