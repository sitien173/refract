<!-- refract-shared-version: 2.4.0 -->

# Phase 1 — Decision Notes

## Task 1

### Decisions made
- Used an armed deadline in `test_timeout_kills_the_whole_process_group` so the timeout triggers after the test receives the child readiness signal and confirms the grandchild PID file exists.

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
  - RED: `PYTHONPATH=$PWD/src .venv/bin/python -c "import tempfile, time, sys; from pathlib import Path; from refract.backends._process import run_process; import asyncio; ..."` -> `FileNotFoundError: [Errno 2] No such file or directory: '/tmp/tmp0_j0egjp/grandchild.pid'`
  - GREEN: `for i in $(seq 20); do PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_transport.py || exit 1; done` -> `13 passed in each of 20 runs (20/20 passed)`
- Root cause (bugfix only): `test_timeout_kills_the_whole_process_group` previously started a fixed 0.5s timeout window from the beginning of `run_process`. Under full-suite CPU contention, child Python interpreter startup took up to 0.64s. `run_process` timed out and killed `spawn_and_sleep.py` before it created `grandchild.pid`. The fix introduces `ArmedDeadline` which arms the timeout only after `spawn_and_sleep.py` signals readiness via stdout, ensuring the grandchild process has started and its PID is written to disk before timeout kills the process group.


## Task 2

### Decisions made
- Checked `expected_question_id` inside `AskRegistry.deliver_answer` within `self._lock` before popping from `self._pending`.

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
  - RED: `PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_ask.py::test_deliver_answer_with_matching_and_mismatched_expected_question_id tests/test_ask.py::test_runtime_job_answer_with_expected_question_id` -> `AssertionError: assert not True` and `Failed: DID NOT RAISE OrchestrationError`
  - GREEN: `PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_ask.py` -> `17 passed in 1.18s`
- Root cause (bugfix only): none


## Task 3

### Decisions made
- Defined module constants `DASHBOARD_HEADER = "X-Refract-Dashboard"` and `DASHBOARD_HEADER_VALUE = "1"`.
- Set `Cache-Control: no-store` on all responses returned by the new action routes.
- Registered action routes in `register_dashboard_routes`.

### Spec deviations
- Modified `server/tests/test_dashboard.py` to update `test_routes_are_the_four_dashboard_routes_and_ask` (renamed to `test_routes_are_dashboard_routes_ask_and_actions`) to expect the three new action routes alongside the existing dashboard routes, as confirmed by coordinator via `refract ask`.

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: `PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dashboard_api.py` -> `5 failed in 0.25s (assert 404 == 403, assert 404 == 200, assert 404 == 503)`
  - GREEN: `PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dashboard_api.py` -> `5 passed in 0.20s`
- Root cause (bugfix only): none


## FIX 1

### Decisions made
- Extracted shared helper `_api_post_preamble` handling CSRF check, JSON body parse, runtime guard, and `job_id` extraction for POST action routes.
- Deleted redundant `elif exc.code == "invalid_request"` branch from `_map_orchestration_error`.
- In `_check_csrf`, wrapped `origin_split.port` in `try...except ValueError` returning 403 `csrf_rejected`.
- Required `question_id` to be a non-empty string in `_api_answer`, returning 400 `invalid_request` without calling runtime.
- Renamed path parameter from `{id}` to `{job_id}` across the three action routes and updated route-set test.
- In `ArmedDeadline` (`tests/test_transport.py`), removed unused inverted `__ge__` and added comment regarding reflected `__le__` comparison with `now >= deadline`; removed redundant fallback check in `test_timeout_kills_the_whole_process_group` and asserted `armed.deadline is not None`.

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
  - RED: `PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dashboard_api.py` -> `2 failed, 3 passed in 0.34s (ValueError on malformed port; assert 200 == 400 on missing question_id)`
  - RED: `PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dashboard.py::test_routes_are_dashboard_routes_ask_and_actions` -> `1 failed in 0.74s (AssertionError: route set mismatch on {id} vs {job_id})`
  - GREEN: `PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dashboard_api.py tests/test_ask.py tests/test_dashboard.py tests/test_mcp_schema_contract.py` -> `53 passed in 3.06s`
  - GREEN: `for i in $(seq 20); do PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_transport.py || exit 1; done` -> `13 passed in each of 20 runs (20/20 passed)`
  - GREEN: `PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider` -> `789 passed, 15 deselected in 42.03s`
- Root cause (bugfix only):
  - Finding 1: `_api_answer` previously treated `question_id` as optional and allowed missing/null/empty strings through to runtime. Fixed by requiring non-empty string `question_id` returning 400 `invalid_request` before any runtime invocation.
  - Finding 2: `urlsplit.port` raises `ValueError` for unparseable or out-of-range port strings in `Origin` header. Fixed by wrapping `origin_split.port` in `try...except ValueError` returning 403 `csrf_rejected`.
  - Finding 3: `ArmedDeadline` defined `__ge__` inverted and unused because Python reflects `now >= deadline` to `deadline <= now` (`__le__`). Removed redundant `grandchild is None and pid_file.exists()` fallback and asserted `armed.deadline is not None`.
  - Finding 4: Action routes used `{id}` instead of `{job_id}`, requiring fallback lookup. Standardized on `{job_id}`.
  - Finding 5: Common CSRF check, JSON parsing, runtime check, and `job_id` extraction duplicated across action routes. Extracted into `_api_post_preamble` and removed redundant `invalid_request` check in `_map_orchestration_error`.
