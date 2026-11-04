<!-- refract-shared-version: 2.4.0 -->

# Phase 1 — Decision Notes

## Task 1

### Decisions made
- none

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
  - RED: `bash plugin/tests/test-contracts.sh` -> `Traceback (most recent call last): File "<stdin>", line 136, in <module> AssertionError`
  - GREEN: `bash plugin/tests/test-session-start.sh && bash plugin/tests/test-contracts.sh && bash plugin/tests/test-stats.sh` -> `session-start tests passed; contract tests passed; stats tests passed`
- Root cause (bugfix only): Commit `38f97c55` removed the "Reported successful output recovery" section from `tool-contract.md` while `test-contracts.sh` still checked its presence and contents.

## Task 2

### Decisions made
- Rejected a top-level `langfuse` configuration key before generic unsupported-section validation.

### Spec deviations
- Task incomplete: tracing removal, dependency and lockfile updates are not done.

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- Config errors are sanitized to `Invalid configuration` by the existing configuration-loading boundary; preserving the required removal message may require updating the sanitizer, which is outside the declared file set.

### Test evidence
- RED -> GREEN:
  - RED: `PYTHONPATH=$PWD/server/src /home/ngosi/projects/refract/server/.venv/bin/python -m pytest -q -p no:cacheprovider server/tests/test_config.py::test_langfuse_config_section_is_rejected_with_removal_message` -> failed as intended: `DID NOT RAISE ValueError`.
  - GREEN: Not achieved. After the config edit, the test still fails because the exposed exception message is `Invalid configuration` and does not match the required `langfuse`/`removed` message. An intermediate collection attempt also exposed stale imports of the removed Langfuse config; those imports and obsolete Langfuse config tests were removed from `test_config.py`.
- Root cause (bugfix only): Existing load-config sanitization hides specific config error text.

## Task 3

### Decisions made
- none

### Spec deviations
- Not started.

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: none
  - GREEN: none
- Root cause (bugfix only): none

## Resumed Batch — 2026-11-04

### Decisions made
- Allow-listed only the constant `[langfuse]` removal diagnostic in `sanitize_config_error`, as clarified; no config values are included.

### Spec deviations
- Tasks 2 and 3 remain incomplete; the full Done When checks do not pass.

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- Continue removing tracing references and dashboard assets/routes/tests, then update documentation and rerun the full checks.

### Test evidence
- RED -> GREEN:
  - RED: `PYTHONPATH=$PWD/server/src /home/ngosi/projects/refract/server/.venv/bin/python -m pytest -q -p no:cacheprovider server/tests/test_config.py::test_langfuse_config_section_is_rejected_with_removal_message` -> failed because sanitized message was `Invalid configuration`.
  - GREEN: same command after the exact fixed-message sanitizer allow-list -> `1 passed in 0.17s`.
- Full Done When checks:
  - Plugin command `bash plugin/tests/test-session-start.sh && bash plugin/tests/test-contracts.sh && bash plugin/tests/test-stats.sh` -> all three passed.
  - Server suite `cd server && PYTHONPATH=$PWD/src /home/ngosi/projects/refract/server/.venv/bin/python -m pytest -q -p no:cacheprovider` -> collection failed with 13 errors, chiefly stale imports of removed `LangfuseConfig` and observability; other stale dashboard test modules remain.
  - `! git grep -niE 'langfuse|observability' -- server/src server/tests server/pyproject.toml` -> failed; many required removal references remain.
  - `cd server && uv lock` -> resolved 61 packages; no uv.lock diff was produced (the pyproject optional extra remains).
- Root cause (bugfix only): Existing sanitizer defaulted the fixed removal message to `Invalid configuration`; stale tracer imports now make the server suite uncollectable after partial config model removal.

## Resumed Batch — Final implementation — 2026-11-04

### Decisions made
- Following coordinator approval, removed only the frontend package-version read/assertion from `plugin/tests/test-contracts.sh`; `server/web/` is deleted permanently.
- Kept MCP diagnostic-reporting documentation while removing the React dashboard and API documentation.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- The final implementation supersedes the incomplete status recorded in the prior resumed batch; historical evidence above is retained.

### Follow-ups for human
- none

### Test evidence
- Task 2 RED -> GREEN:
  - RED: `PYTHONPATH=$PWD/server/src /home/ngosi/projects/refract/server/.venv/bin/python -m pytest -q -p no:cacheprovider server/tests/test_config.py::test_langfuse_config_section_is_rejected_with_removal_message` -> initially failed because the config error was sanitized to `Invalid configuration`.
  - GREEN: After allow-listing only the fixed removal message in `sanitize_config_error`, the rejection is covered by `test_removed_tracing_config_section_names_removal`; final server suite passed.
  - `cd server && uv lock` -> resolved 43 packages and removed `langfuse` and its OpenTelemetry/HTTP dependency chain from `uv.lock`.
- Task 3 RED -> GREEN:
  - RED: Loopback POST test run before implementation -> not applicable; retained `/ask` behavior was covered by existing implementation. New HTTP-level loopback and non-loopback tests were added before deleting the other dashboard routes.
  - GREEN: `cd server && PYTHONPATH=$PWD/src /home/ngosi/projects/refract/server/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dashboard.py` -> `2 passed`.
- Final Done When checks:
  - `bash plugin/tests/test-session-start.sh && bash plugin/tests/test-contracts.sh && bash plugin/tests/test-stats.sh` -> all passed.
  - `cd server && PYTHONPATH=$PWD/src /home/ngosi/projects/refract/server/.venv/bin/python -m pytest -q -p no:cacheprovider` -> `1067 passed, 15 deselected`.
  - `! git grep -niE 'langfuse|observability' -- server/src server/tests server/pyproject.toml` -> passed.
  - `test ! -e server/web`, `test ! -e server/src/refract/dashboard_static`, and `git diff --check` -> passed.
- Root cause (bugfix only): none

## FIX Cycle 1 — 2026-11-04

### Decisions made
- Restored route-level `/ask` validation, auth, answering/conflict, non-loopback, and DNS-rebinding coverage using the minimal Starlette route app and real `AskRegistry` where required.
- Restored the requested execution characterization tests from the phase base with tracing removed; renamed the retry-stream test and helper to avoid tracing terminology.
- Preserved telemetry and transcript documentation while removing references to the deleted React UI and API routes.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- `cd server && PYTHONPATH=$PWD/src /home/ngosi/projects/refract/server/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dashboard.py` -> `8 passed`.
- `cd server && PYTHONPATH=$PWD/src /home/ngosi/projects/refract/server/.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_execution.py::test_stored_target_policy_survives_current_policy_changes tests/test_execution.py::test_real_adapter_observations_through_execution_persist_reported_consumption_alongside_derived_context tests/test_execution.py::test_retry_sequential_streams_and_ask_tokens tests/test_execution.py::test_retry_unknown_observation_blocks_replay` -> `11 passed` (includes all parametrized backend/streaming cases).
- Final server suite: `cd server && PYTHONPATH=$PWD/src /home/ngosi/projects/refract/server/.venv/bin/python -m pytest -q -p no:cacheprovider` -> `1085 passed, 15 deselected`.
- Final plugin checks: `bash plugin/tests/test-session-start.sh && bash plugin/tests/test-contracts.sh && bash plugin/tests/test-stats.sh` -> all passed.
- `! git grep -niE 'langfuse|observability' -- server/src server/tests server/pyproject.toml` -> passed.
- `! git grep -nE 'server/web|dashboard_static' -- .github sonar-project.properties` -> passed.
- `git diff --check` -> passed.
- Root cause (bugfix only): none
