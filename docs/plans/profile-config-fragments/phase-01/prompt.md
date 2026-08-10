## Original User Request

Complete the profile-config-fragments plan.

## Phase

Build the effective global catalog from validated fragments.

## Tasks

- Add source-aware direct-child, case-sensitive `*.config.toml` discovery beside the global config.
- Permit only `[[targets]]` and `[profiles.*]`, validating all fragments before main-file overrides.
- Reject deterministic fragment conflicts with one `ConfigFragmentConflictWarning` and `ValueError`.
- Overlay complete main definitions and preserve current validation behavior.
- Add focused regression tests in `tests/test_config.py`.

## Context

Follow Phase 1 in `docs/plans/profile-config-fragments/PLAN.md` and the confirmed design. The earlier consultation is recorded as OpenMCP job `805c2171-bc7e-4159-aaec-2879d84cce28`.

## Files

- `src/openmcp/config.py`
- `tests/test_config.py`
- `docs/plans/profile-config-fragments/phase-01/notes.md`
- `docs/plans/profile-config-fragments/phase-01/journal.md`

## Done When

- Every Phase 1 acceptance criterion in `PLAN.md` is met.
- `uv run pytest tests/test_config.py -q` passes.
- `uv run pytest tests/test_planning.py tests/test_smoke.py -q` passes.
- `git diff --check` passes.

## Rules

Follow the supplied worker contract. Stay within scope. Maintain this phase's `notes.md` and `journal.md`.

## Response Format

Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
