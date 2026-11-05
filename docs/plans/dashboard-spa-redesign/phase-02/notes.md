<!-- refract-shared-version: 2.4.0 -->

# Phase 2 — Decision Notes

## Task 1

### Decisions made
- Implemented `encode_cursor` / `decode_cursor` using URL-safe base64 of JSON `[created_at, id]`.
- Implemented `job_summaries` with SQL filters applied before keyset pagination condition `(created_at < ? OR (created_at = ? AND id < ?))`, ordered by `created_at DESC, id DESC`, querying `limit + 1` to establish `next_cursor`.
- Implemented `job_filter_options` retrieving unfiltered distinct values across all jobs for states, workflows, targets, and projects.

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
  - RED: `PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_database.py tests/test_dashboard_api.py -k "summaries or get_jobs"` -> `5 failed, 14 deselected in 0.40s` (`AssertionError: 0 == 1` and `AssertionError: assert {} == {'states': ...}`)
  - GREEN: `PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dashboard_api.py tests/test_database.py tests/test_dashboard.py` -> `41 passed in 0.44s`
- Root cause (bugfix only): none

## Task 2

### Decisions made
- Implemented `Database.job_detail(job_id)` extracting exact allowlisted fields and result object with tokens dictionary matching `_TOKEN_COLUMNS`.
- Populated `pending_question` `{question_id, text}` from `runtime.ask_registry.get_pending(job_id)` or `None`.
- Ensured sensitive/forbidden keys (`token`, `future`, `deadline`, `execution_plan`, `execution_plan_json`, `pgid`) are not included at any depth.

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
  - RED: `PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dashboard_api.py -k "test_get_job_detail_contract_and_forbidden_keys"` -> `1 failed, 8 deselected in 0.29s` (`AssertionError: assert set() == {'created_at', ...}`)
  - GREEN: `PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dashboard_api.py tests/test_database.py tests/test_dashboard.py` -> `42 passed in 0.35s`
- Root cause (bugfix only): none

## Task 3

### Decisions made
- Implemented `_stream_events_bounded` iterating lines directly without calling `read()` or `readlines()`, stopping after 500 events plus 1 lookahead line.
- Enforced withholding of partial lines without trailing newline so they do not count toward `has_more`.
- Handled missing stream files with `available: false`, `has_more: false`, and empty events list.
- Exposed `GET /dashboard/api/targets` returning target and config health views via `model_dump()`.
- Registered `_api_fallback` for `/dashboard/api` and `/dashboard/api/{rest:path}` returning JSON 404 with `_api_error` envelope.
- Preserved existing HTML routes including `_events` and `/dashboard/jobs/{job_id}/output`.

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
  - RED: `PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dashboard_api.py -k "test_get_output or test_get_targets or test_api_fallback"` -> `5 failed, 1 passed, 9 deselected in 1.56s` (`KeyError: 'available'`, `KeyError: 'events'`, `AssertionError: assert {} == {'events': ...}`, `assert 200 == 400`, `AssertionError: assert ('targets' in {})`)
  - GREEN: `PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dashboard_api.py -k "test_get_output or test_get_targets or test_api_fallback"` -> `6 passed, 9 deselected in 0.49s`
- Root cause (bugfix only): none

## FIX 1

### Decisions made
- In `_stream_events_bounded`, built events as `{**payload, "seq": seq}` so the 1-based line number is authoritative over any payload `"seq"` field, and tracked `last_seq` across lines rather than reading back from event dicts.
- Converted GET route handlers (`_api_get_jobs`, `_api_get_job_detail`, `_api_get_job_output`, `_api_get_targets`) to plain synchronous functions so `_loopback_route` offloads them via `run_sync` rather than running blocking SQLite or disk I/O directly on the event loop.
- Opened the stream file with `errors="replace"` to prevent invalid UTF-8 bytes from raising 500 errors.
- Documented fallback route behavior for wrong HTTP methods on registered API endpoints and verified that `POST /dashboard/api/jobs` returns JSON 404 `not_found`.
- Factored repeated runtime active checks into `_api_runtime` helper, registered `_api_fallback` directly, and set `unchanged="Nothing was modified."` across read endpoints.

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
  - RED: `PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dashboard_api.py -k "test_get_output_authoritative_seq_and_invalid_utf8 or test_api_fallback"` -> `2 failed, 14 deselected in 0.57s` (`UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff` and `AssertionError: assert 'No dashboard data was changed.' == 'Nothing was modified.'`)
  - GREEN: `PYTHONPATH=$PWD/src .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_dashboard_api.py -k "test_get_output_authoritative_seq_and_invalid_utf8 or test_api_fallback"` -> `2 passed, 14 deselected in 0.60s`
- Root cause (bugfix only): Line number ordering in dict unpacking allowed stream event payload `"seq"` to overwrite stream sequence numbers; stream decoding did not specify `errors="replace"`; handlers performed blocking calls directly within coroutines on the loop.
