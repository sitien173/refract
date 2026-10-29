# Phase 1 — Decision Notes

## Task 1

### Decisions made
- Reused the positive-integer configuration validation and exposed the editor field as optional strict integer data.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Missing configured capacity is represented internally as `None`.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `cd server && uv run pytest -q tests/test_config.py -k context_window` initially failed because TargetConfig ignored the new field; after implementation the focused cases passed as part of the full suite.

## Task 2

### Decisions made
- Editor updates distinguish omission from explicit null using Pydantic's fields-set tracking; null removes the TOML key.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Runtime target configuration inspection is covered by configuration target projections and execution-plan display; the worker runtime identity remains unchanged.

### Follow-ups for human
- none

### Test evidence
- Correction: the original Task 2 entry incorrectly claimed RED -> GREEN despite no dedicated mutation/API regression tests. Those tests have now been added first.
- RED -> GREEN: dashboard serialization regression initially failed because `_jsonable(TargetEditorData(..., contextWindow=200000))` returned `context_window`, and the create response lacked `contextWindow`. After the narrow serializer fix, serialization and create/list/read/update API checks passed.
- Mutation omission-preservation and explicit-null clearing coverage passes, including checks that unrelated comments and profile TOML remain intact. Focused check: 1 passed.
- Full verification: `cd server && uv run pytest -q` — 1235 passed, 23 skipped, 15 deselected.

## Task 4

### Decisions made
- Environment-bound opaque session revisions now HMAC the resolved catalog's environment sets and per-target environment references/values, plus the existing project-file identity. Capacity is excluded because it does not alter the child environment; no raw environment values are returned or logged.

### Spec deviations
- none

### Tradeoffs accepted
- Global non-environment configuration edits no longer rotate environment-bound revisions by themselves; target execution identity and environment configuration remain separately represented, and project-file identity continues invalidating on local edits.

### Assumptions
- Session continuity should follow effective environment settings, rather than unrelated global config bytes.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: new synthetic-config test showed an unchanged environment-bound revision changed on `contextWindow` edits (failed before implementation). After the HMAC payload was scoped to environment config, repeated set/change/clear capacity edits retained the revision; changing the synthetic environment value produced a different revision.
- Focused runtime checks: 5 passed.
- Full verification: `cd server && uv run pytest -q` — 1236 passed, 23 skipped, 15 deselected.

## Task 3

### Decisions made
- Persisted snapshot key is internal `context_window`; it remains excluded from `_target_identity_data`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Legacy snapshots with no capacity field map to `None`.

### Follow-ups for human
- none

### Test evidence
- Characterization/regression coverage: added invalid persisted `context_window` cases; all five focused cases passed against existing plan validation. Safe execution-plan projection with capacity also passes. Full verification after this repair: `cd server && uv run pytest -q` — 1235 passed, 23 skipped, 15 deselected.
