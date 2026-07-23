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
explicit inheritance and partial profiles. Consultation identified import-time
`load_config()` in `server.py`, dashboard defaults, and strict-config test
fixtures as direct consumers. Defer daemon config loading until startup so a
clean-environment import remains valid. Reject removed aliases rather than
silently ignoring them.

## Files
- `src/openmcp/config.py`
- `src/openmcp/config_writer.py`
- `src/openmcp/server.py`
- `src/openmcp/dashboard_static/app.js`
- `README.md`
- `CLI_ARGUMENTS.md`
- `tests/test_smoke.py`
- `tests/test_config.py`
- `tests/test_logging.py`
- `tests/test_dashboard.py`
- `tests/test_server.py`
- `tests/orchestration_helpers.py`
- `docs/plans/profile-strategy-refactor/phase-01/notes.md`
- `docs/plans/profile-strategy-refactor/phase-01/journal.md`

## Done When
- Missing `config.toml` raises a clear error.
- Missing or empty `[targets]` or `[profiles]` raises a clear error.
- Missing or unknown `[daemon].default_profile` raises a clear error.
- Per-profile workflow completeness remains enforced.
- Importing `openmcp.server` does not load daemon configuration.
- Dashboard validation requires a non-empty default profile.
- Global and project legacy aliases are rejected clearly.
- No removed defaults, routes, aliases, or legacy selections remain in `src/`.
- `python -m pytest tests/test_config.py tests/test_logging.py tests/test_dashboard.py tests/test_server.py tests/test_smoke.py tests/test_planning.py`
- `python -m pytest`
- `! rg -n "routing_profiles|default_routing_profile|legacy_selections|_legacy_routes|_default_targets|_default_profiles|_default_legacy_routes|include_defaults" src tests README.md CLI_ARGUMENTS.md`

## Rules
Follow the supplied worker contract. Stay within scope. Maintain this phase's
`notes.md` and `journal.md`.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
