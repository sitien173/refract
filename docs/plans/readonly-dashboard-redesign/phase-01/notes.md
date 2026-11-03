<!-- refract-shared-version: 2.4.0 -->

# Phase 1 — Decision Notes

## Task 1

### Decisions made
- Parametrized deleted dashboard routes across GET, POST, PUT, DELETE methods to verify 404 responses.
- Enriched profiles test asserts absence of secret/internal fields (`system_prompt`, `args`).

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
  - RED: `cd server && uv run --no-sync pytest -v tests/test_dashboard.py -k "test_deleted_dashboard_routes_return_json_404 or test_profiles_endpoint_enriched_with_profile_config_data"` -> 20 failed (`AssertionError: assert 403 == 404`, `AssertionError: assert 200 == 404`, `AssertionError: assert 'profiles' in {'default': 'balanced', 'available': ['balanced']}`)
  - RED: `cd server && uv run --no-sync pytest -v tests/test_runtime.py -k "test_runtime_recovery_string_names_config_toml or test_job_submission_succeeds_without_runtime_mutations"` -> 2 failed (`AssertionError: assert 'Fix the project configuration in the dashboard.' == 'Fix the project configuration in .refract/config.toml.'`, `AssertionError: assert not hasattr(runtime, 'mutations')`)
  - RED: `cd server && uv run --no-sync pytest -v tests/test_server.py -k "test_server_task_guide_recovery_string_names_config_toml"` -> 1 failed (`AssertionError: assert 'Fix the project guidance or configuration in the dashboard.' == 'Fix the project guidance or configuration in .refract/config.toml.'`)
  - GREEN: pending implementation in tasks 2-4
- Root cause (bugfix only): none

## Task 2

### Decisions made
- Named the replacement reentrant lock attribute `self._lock = threading.RLock()` on `Runtime`.
- Retained `load_config_bytes` and `load_project_config(..., data=...)` in `config.py` because `tests/test_environment.py` is an active caller outside the allowed modification set.
- Deleted `_publish_project_configuration_locked` after confirming only deleted mutation code referenced it.

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
  - RED: `cd server && uv run --no-sync pytest -v tests/test_runtime.py -k "test_runtime_recovery_string_names_config_toml or test_job_submission_succeeds_without_runtime_mutations"` -> 2 failed (`AssertionError: assert 'Fix the project configuration in the dashboard.' == 'Fix the project configuration in .refract/config.toml.'`, `AssertionError: assert not hasattr(runtime, 'mutations')`)
  - GREEN: `cd server && uv run --no-sync pytest -v tests/test_runtime.py -k "test_runtime_recovery_string_names_config_toml or test_job_submission_succeeds_without_runtime_mutations"` -> 2 passed
- Root cause (bugfix only): none

## Task 3

### Decisions made
- Removed mutation models and unused mutation envelope fields (`source_path`, `current`, `references`) from `DashboardError` in `models.py`.
- Removed `csrf_token` from `DashboardState` and stripped its generation/cleanup in `server.py`.
- Enriched `GET /dashboard/api/profiles` with `_profile_config_data(runtime.catalog, runtime.catalog)["profiles"]`.
- Deleted mutation route registrars, task-guide registrar, `bootstrap`, `status`, and `configuration` routes from `dashboard.py`.
- Updated recovery string in `server.py` to point to `.refract/config.toml`.

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
  - RED: `cd server && uv run --no-sync pytest -v tests/test_server.py -k "test_server_task_guide_recovery_string_names_config_toml"` -> 1 failed (`AssertionError: assert 'Fix the project guidance or configuration in the dashboard.' == 'Fix the project guidance or configuration in .refract/config.toml.'`)
  - GREEN: `cd server && uv run --no-sync pytest -v tests/test_server.py -k "test_server_task_guide_recovery_string_names_config_toml"` -> 1 passed
- Root cause (bugfix only): none

## Task 4

### Decisions made
- Deleted mutation-only tests in `server/tests/test_dashboard.py` and `server/tests/test_dashboard_consolidation.py`.
- Removed `csrf_token` references and assertions from `server/tests/test_dashboard.py` and `server/tests/test_application_isolation.py`.
- Updated `server/tests/test_runtime.py` to test `runtime._lock` and write project configuration directly to `.refract/config.toml` rather than using deleted mutation APIs.
- Removed `tomlkit` dependency from `server/pyproject.toml` and manually pruned `tomlkit` entries from `server/uv.lock` ensuring `git diff` touches only `tomlkit`.
- Removed legacy pycache artifacts before running the acceptance grep check.

### Spec deviations
- Modified `server/tests/test_application_isolation.py` (outside the initial `Files` list) to remove assertions on `state.refract_dashboard.csrf_token` following explicit coordinator approval via `refract ask`.
- Verified grep acceptance check using `! grep -rnE --exclude-dir=dashboard_static 'config_mutation|ConfigurationMutation|tomlkit|csrf|\.mutations' src tests pyproject.toml uv.lock` per explicit coordinator approval via `refract ask` (the static bundle in `src/refract/dashboard_static` is out-of-scope for Phase 1 and rebuilt in later phases).

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - Task 1 tests GREEN verification:
    - `cd server && uv run --no-sync pytest -v tests/test_dashboard.py -k "test_deleted_dashboard_routes_return_json_404 or test_profiles_endpoint_enriched_with_profile_config_data"` -> 41 passed
    - `cd server && uv run --no-sync pytest -v tests/test_runtime.py -k "test_runtime_recovery_string_names_config_toml or test_job_submission_succeeds_without_runtime_mutations"` -> 2 passed
    - `cd server && uv run --no-sync pytest -v tests/test_server.py -k "test_server_task_guide_recovery_string_names_config_toml"` -> 1 passed
  - Full suite verification:
    - `cd server && uv run --no-sync pytest -q` -> 1201 passed, 23 skipped, 15 deselected in 36.59s
  - Grep verification:
    - `cd server && ! grep -rnE --exclude-dir=dashboard_static 'config_mutation|ConfigurationMutation|tomlkit|csrf|\.mutations' src tests pyproject.toml uv.lock` -> exit code 0
- Root cause (bugfix only): none

