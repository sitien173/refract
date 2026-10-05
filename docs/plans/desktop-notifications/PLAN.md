# Desktop Notifications Implementation Plan

## Objective

Send an opt-in native desktop notification through notify-py when a job reaches a terminal state.

## Confirmed Design

`docs/plans/desktop-notifications/DESIGN.md`

## Baseline

At plan base `refs/plans/desktop-notifications/base` (`500062c`), `uv run pytest -q` reports `432 passed, 3 deselected`.

A trial `uv lock` in a scratch copy resolved `notify-py 0.3.43`, `loguru 0.6.0`, `jeepney 0.9.0`, and `win32-setctime 1.2.0`. `from notifypy import Notify` imported on Python 3.12.13 with `DeprecationWarning` promoted to error.

## Scope

- Add `notify-py>=0.3.43,<0.4` as a required dependency.
- Add a global-only `[notifications]` table with `enabled = false` by default.
- Send one notification per transition into `succeeded`, `failed`, `cancelled`, or `interrupted`.
- Keep desktop-notification failures isolated from job state and the MCP `ResourceUpdated` publish.

## Non-goals

- Per-state filtering, icons, sounds, or notification actions.
- Dashboard `/settings` exposure or dashboard editing of the setting.
- Notifications for `queued` or `running`.
- Non-desktop channels.

**Commit:** `feat(notifications): add opt-in desktop notifications for terminal jobs`

### Phase 1: Notifications config and dependency

**Task Guide Input:** Non-UI repository implementation in Python. Add `notify-py>=0.3.43,<0.4` to `pyproject.toml` runtime dependencies and refresh `uv.lock`. Add a global-only `[notifications]` config table to `src/openmcp/config.py` with a frozen `NotificationsConfig(enabled: bool = False)` dataclass and a `DaemonConfig.notifications` field, parsed with the same strict-table pattern as `_logging_config`. Add config tests in `tests/test_config.py`. No runtime or notification-sending code.
**Goal:** `load_config` produces `DaemonConfig.notifications.enabled` from a validated global `[notifications]` table, and `notifypy` is installed in the project environment.
**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `src/openmcp/config.py`
- Modify: `tests/test_config.py`
**Tasks:**
1. Add `"notify-py>=0.3.43,<0.4"` to `[project].dependencies` in `pyproject.toml` and run `uv lock`.
2. In `src/openmcp/config.py`:
   - Add `NotificationsConfig` as a frozen slotted dataclass with `enabled: bool = False`.
   - Add `notifications: NotificationsConfig = field(default_factory=NotificationsConfig)` to `DaemonConfig`.
   - Add `"notifications"` to the allowed top-level sections in `_load_config_values`.
   - Add `_notifications_config(raw)`: `None` yields the default, a non-table raises `ValueError("[notifications] must be a TOML table")`, unknown keys raise `ValueError`, and a non-bool `enabled` raises `ValueError`.
   - Pass the result into `DaemonConfig`.
3. Add tests to `tests/test_config.py`:
   - Absent table yields `enabled is False`.
   - `enabled = true` yields `True`.
   - Unknown key, non-bool `enabled`, and non-table `notifications` each raise `ValueError`.
   - A project `.openmcp/config.toml` containing `[notifications]` is rejected.
**Acceptance Criteria:**
- `uv.lock` contains `notify-py` `0.3.43` and `loguru` `0.6.0`.
- `uv run python -c "from notifypy import Notify"` exits 0.
- A global config without `[notifications]` loads with `config.notifications.enabled is False`.
- A global config with `[notifications]\nenabled = true` loads with `config.notifications.enabled is True`.
- `[notifications]\nenabled = "yes"`, `[notifications]\nextra = 1`, and `notifications = 1` each make `load_config` raise `ValueError`.
- A project config with `[notifications]` raises `ValueError` naming unsupported project config sections.
- No file outside the phase file set changes.
**Reviewer Checklist:**
- `_notifications_config` mirrors `_logging_config` validation style and error wording.
- `isinstance(value, bool)` is used, so `enabled = 1` is rejected.
- `DaemonConfig` stays frozen and the new field has a default, so existing `DaemonConfig(...)` call sites in tests and code still construct.
- `uv.lock` changes only add `notify-py`, `loguru`, `jeepney`, and `win32-setctime`, and do not upgrade unrelated packages.
- No runtime, server, or dashboard file changes.
**Verification Checks:**
- `uv run python -c "from notifypy import Notify"`
- `uv run pytest tests/test_config.py -q`
- `uv run pytest -q`

### Phase 2: Terminal job desktop notifications

**Task Guide Input:** Non-UI repository implementation in Python. Create `src/openmcp/notifications.py` with `send_job_notification(job: JobView, project_alias: str) -> bool` wrapping notify-py `Notify`. In `src/openmcp/runtime.py`, extend `Runtime._notify_job_resource` with a second, independently guarded side effect after the existing MCP publish: when `self._catalog.notifications.enabled`, derive the job ID from the `openmcp://jobs/` URI, send only for `TERMINAL_STATES` via `asyncio.to_thread`, and log failures as `job.desktop_notification_failed`. Add tests in `tests/test_notifications.py` and `tests/test_execution.py` that patch the helper and never send a real notification.
**Goal:** With notifications enabled, every terminal transition sends exactly one desktop notification containing only state, project alias, `context_key`, workflow, and `target_id`, and failures never affect job state or MCP publication.
**Files:**
- Create: `src/openmcp/notifications.py`
- Create: `tests/test_notifications.py`
- Modify: `src/openmcp/runtime.py`
- Modify: `tests/test_execution.py`
**Tasks:**
1. Create `src/openmcp/notifications.py` with `send_job_notification(job, project_alias) -> bool`:
   - Construct `Notify()` and set `application_name = "OpenMCP"`.
   - Set the title to `f"OpenMCP job {job.state}"`.
   - Set the message to `f"{project_alias} / {job.context_key} / {job.workflow} / {job.target_id or '-'}"`.
   - Return `bool(notification.send(block=True))`.
2. In `Runtime._notify_job_resource`:
   - Before the first await, derive the job ID with `resource_uri.removeprefix("openmcp://jobs/")` and capture the job only if the live `_catalog.notifications.enabled` flag is true. Capture lookup failures for warning-only reporting after the MCP publish.
   - Keep the existing MCP publish `try` block unchanged.
   - Then return unless `self._catalog.notifications.enabled`.
   - Use the captured job and return if it is missing or its captured state is not in `TERMINAL_STATES`. Do not re-read the job after the await.
   - Load the project and return if it is missing.
   - Run `await asyncio.to_thread(send_job_notification, job, project.alias)` inside its own `try`.
   - Log a warning with `event: job.desktop_notification_failed` and `job_id` on a false result, a captured lookup failure, or any exception. Never re-raise into the caller.
3. Create `tests/test_notifications.py`, patching `openmcp.notifications.Notify`:
   - Assert the title, the message, and `send(block=True)`.
   - Assert an empty `target_id` renders `-`.
   - Assert the message omits prompt, result text, and error text.
4. Extend `tests/test_execution.py`, patching `openmcp.runtime.send_job_notification` and using a config with notifications enabled:
   - One call each for succeeded, failed, queued cancel, and startup recovery to `interrupted`.
   - No call for `queued` or `running`.
   - No call when disabled.
   - A helper that raises, and a helper that returns `False`, leave the job outcome and the MCP notifier URI list unchanged. Assert each warning's event and job ID.
   - A terminal publish paused during a concurrent retry still sends exactly one notification containing the captured terminal state.
   - Replacing `runtime._catalog` with `enabled` toggled changes behavior for the next job.
**Acceptance Criteria:**
- With notifications disabled, `send_job_notification` is never called and the existing MCP notification sequences in `tests/test_execution.py` are unchanged.
- With notifications enabled, a succeeded job, a failed job, a cancelled queued job, and a job recovered to `interrupted` at startup each produce exactly one helper call with that job's `JobView` and project alias.
- No helper call occurs on submit, start, or retry-to-queued transitions.
- A helper that raises or returns `False` produces a `job.desktop_notification_failed` warning, and the job's final state and the MCP notifier URI list equal the disabled-case values.
- The notification message equals `<alias> / <context_key> / <workflow> / <target_id or ->` and the title equals `OpenMCP job <state>`.
- No test sends a real OS notification.
- No file outside the phase file set changes.
**Reviewer Checklist:**
- The MCP publish runs before and independently of the desktop path. A desktop exception cannot skip or re-raise into the MCP path.
- The enabled flag is read from `self._catalog`, not `self.config`.
- `send` runs through `asyncio.to_thread`, never directly on the event loop.
- Only `state`, project alias, `context_key`, `workflow`, and `target_id` reach notify-py. No `prompt`, `result.text`, or `result.error`.
- The URI prefix matches `JOB_RESOURCE_URI_TEMPLATE` in `src/openmcp/models.py`.
- Tests patch at `openmcp.runtime.send_job_notification` and `openmcp.notifications.Notify`, not at notify-py internals.
**Verification Checks:**
- `uv run pytest tests/test_notifications.py tests/test_execution.py -q`
- `uv run pytest -q`

## Risks

- `notify-py 0.3.43` pins `loguru<=0.6.0,>=0.5.3`. A future dependency that needs a newer `loguru` would conflict. Owner: plan reviewer, re-check at each dependency bump.
- notify-py on Linux depends on a desktop notification service. Headless daemons log a warning per terminal job when enabled.
