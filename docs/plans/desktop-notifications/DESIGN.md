# Desktop Notifications Design

**Status:** Confirmed 2026-10-05
**Consultation:** consult job `ebeba6f0-150a-4d57-b678-a9454e5dbe81` succeeded; recommended the Runtime hook, `asyncio.to_thread` sending, and reading the live `_catalog`.

## Purpose

Send a native desktop notification through notify-py when an OpenMCP job reaches a terminal state, so the user knows a long job ended without watching the dashboard or an MCP client.

## Users and Success Criteria

Users: a developer running the OpenMCP daemon on their own desktop session.

Success criteria:

- With `[notifications] enabled = true`, exactly one notification is sent per transition into `succeeded`, `failed`, `cancelled`, or `interrupted`.
- This includes queued cancellation and startup recovery to `interrupted`.
- No notification is sent for `queued` or `running`.
- With the table absent or `enabled = false`, behavior is unchanged and no `Notify` object is created.
- A notification failure never changes job state and never suppresses the MCP `ResourceUpdated` publish.
- Notification content contains only state, project alias, `context_key`, workflow, and `target_id`.

## Constraints and Non-Goals

Constraints:

- `notify-py` is a required runtime dependency: `notify-py>=0.3.43,<0.4`.
- The `[notifications]` table is global only, in `$OPENMCP_HOME/config.toml`. Project `.openmcp/config.toml` keeps rejecting it.
- Prompt, result text, and error text never reach the notification helper.
- The `JobNotifier` contract `Callable[[str], Awaitable[None]]` is unchanged.

Non-goals:

- Per-state filtering, custom icons, sounds, or notification actions.
- Exposing notification settings in the dashboard `/settings` response or editing them through the dashboard.
- Notifications for non-terminal transitions.
- Remote or non-desktop channels such as email, Slack, or webhooks.

## Chosen Approach

Add a second, independently guarded side effect in `Runtime._notify_job_resource`, after the existing MCP publish. Delegate the notify-py call to a new helper `openmcp.notifications.send_job_notification`.

Rejected alternatives:

- Terminal branches in `JobRunner.run`: misses startup recovery at `runtime.py:104-110` and queued cancellation at `runtime.py:174-183`.
- Composed notifier in `server._lifespan`: needs a closure over the runtime for DB and config access and does not apply to direct `Runtime` use.

## Architecture and Data Flow

1. `pyproject.toml`: add `notify-py>=0.3.43,<0.4` to `[project].dependencies`; refresh `uv.lock`.
2. `src/openmcp/config.py`:
   - Add a frozen `NotificationsConfig` dataclass with `enabled: bool = False`.
   - Add a `DaemonConfig.notifications` field defaulting to `NotificationsConfig()`.
   - Allow `"notifications"` in the top-level section set in `_load_config_values`.
   - Add `_notifications_config(raw)`, following the `_logging_config` pattern: require a table, reject unknown keys, and require `enabled` to be a bool.
3. `src/openmcp/notifications.py`, new:
   - `send_job_notification(job: JobView, project_alias: str) -> bool` builds `Notify()` with `application_name = "OpenMCP"`.
   - Title: `OpenMCP job <state>`.
   - Message: `<project_alias> / <context_key> / <workflow> / <target_id or "-">`.
   - Returns `notification.send(block=True)`.
4. `src/openmcp/runtime.py`, `Runtime._notify_job_resource(resource_uri)`:
   1. When the live `_catalog.notifications.enabled` flag is true, derive the job ID from `openmcp://jobs/` and capture the persisted `JobView` before the first await. Capture lookup exceptions without suppressing the MCP publish.
   2. Run the existing MCP publish in its own `try` block, unchanged.
   3. Return if the live `_catalog.notifications.enabled` flag is false.
   4. Use the captured job, not a post-await database lookup. Return if it is missing or its captured state is not in `TERMINAL_STATES`.
   5. Load the project; use its alias.
   6. `ok = await asyncio.to_thread(send_job_notification, job, alias)`.
   7. Log `job.desktop_notification_failed` at warning level with `job_id` when `ok` is false or any exception is raised. Report captured lookup exceptions only after MCP publication. Never re-raise into the caller.

The pre-await snapshot prevents a concurrent retry from resetting a terminal job to `queued` before desktop delivery. A coordinator reproduction on 2026-10-05 observed zero sends instead of one when MCP publication paused during a retry.

All terminal paths already reach `_notify_job_resource`: `JobRunner` through the injected notifier at `runtime.py:66-70`, startup recovery at `runtime.py:109`, and queued cancellation at `runtime.py:182`.

## Errors and Edge Cases

- Notifications disabled: return before any job lookup or `Notify` construction.
- `send` returns false or raises: notify-py runs the backend in an internal thread, so backend exceptions often surface only as a false return. Both cases are logged and swallowed.
- Headless Linux with no session D-Bus: same as a failed send; log only.
- `asyncio.to_thread` is required because `send(block=True)` joins notify-py's internal thread for up to 35 seconds.
- Job or project row missing at notification time: skip without logging a failure.
- Empty `target_id`, for example on a queued cancel or an early failure: render `-`.
- Invalid `[notifications]` config, meaning a non-table, an unknown key, or a non-bool `enabled`: `load_config` raises `ValueError`. Existing startup and reload error handling applies.
- Config reload: `enabled` is read from `self._catalog`, which reload replaces at `runtime.py:316-338`. A toggle takes effect from the next notification.

## Migration

None. Existing configs have no `[notifications]` table and default to disabled. No database change.

## Testing

No test sends a real OS notification.

- `tests/test_config.py`:
  - Absent table yields `enabled = False`.
  - `enabled = true` parses.
  - An unknown key, a non-bool `enabled`, and a non-table value are rejected.
  - Project config rejects `[notifications]`.
- `tests/test_notifications.py`, new: patch `openmcp.notifications.Notify`.
  - Assert the title and message format.
  - Assert prompt, result, and error text are absent.
  - Assert an empty `target_id` renders `-`.
- `tests/test_execution.py`: patch `openmcp.runtime.send_job_notification`.
  - Enabled: exactly one call each for succeeded, failed, queued cancel, and startup interrupted.
  - No call for queued or running transitions.
  - Disabled: no call.
  - A helper that raises or returns false leaves the job outcome and the MCP notification list unchanged.
  - A catalog reload toggling `enabled` changes behavior for the next job.
- Verification command: `uv run pytest`.

## Risks and Open Questions

Risks:

- New transitive dependencies: `loguru`, and `jeepney` on Linux. They are accepted because `notify-py` is a required dependency.
- notify-py may add a few hundred milliseconds of thread work per terminal job. It runs off the event loop.
- The URI parsing in `_notify_job_resource` depends on the fixed `JOB_RESOURCE_URI_TEMPLATE` form in `models.py`. A template change would require updating the prefix.

Open questions: none.
