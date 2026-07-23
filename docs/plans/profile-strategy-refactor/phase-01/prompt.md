## Original User Request
Execute the profile-strategy-refactor plan one phase at a time through the
canonical OpenMCP gates.

## Phase
Require explicit daemon configuration and remove fabricated defaults and legacy
profile-routing aliases.

## Tasks
- task-1: Remove default factories and legacy-routes machinery from config loading.
- task-2: Require explicit targets, profiles, and a valid default profile.
- task-3: Remove routing-profile migration from the config writer.
- task-4: Update documentation, tests, and helpers for strict configuration.

## Context
`src/openmcp/config.py` currently fabricates targets and profiles and carries
legacy routes through both global and project loading. Phase 1 removes those
paths while retaining the current per-profile completeness check. The target
`profile` to `backend_profile` rename remains out of scope. Phase 2 will add
explicit inheritance and partial profiles.

## Files
- `src/openmcp/config.py`
- `src/openmcp/config_writer.py`
- `README.md`
- `CLI_ARGUMENTS.md`
- `tests/test_smoke.py`
- `tests/test_config.py`
- `tests/orchestration_helpers.py`
- `docs/plans/profile-strategy-refactor/phase-01/notes.md`
- `docs/plans/profile-strategy-refactor/phase-01/journal.md`

## Done When
- Missing `config.toml` raises a clear error.
- Missing or empty `[targets]` or `[profiles]` raises a clear error.
- Missing or unknown `[daemon].default_profile` raises a clear error.
- Per-profile workflow completeness remains enforced.
- No removed defaults, routes, aliases, or legacy selections remain in `src/`.
- `python -m pytest tests/test_config.py tests/test_smoke.py tests/test_planning.py`
- `python -m pytest`
- `rg -n "routing_profiles|legacy_selections|_default_targets|_default_profiles|_default_legacy_routes|include_defaults" src`

## Rules
Follow the supplied worker contract. Stay within scope. Maintain this phase's
`notes.md` and `journal.md`.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
