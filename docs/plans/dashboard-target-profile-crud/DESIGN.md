# Dashboard Target and Profile CRUD Design

## Purpose

Allow local OpenMCP operators to create, inspect, update, and delete targets and
profiles through the dashboard. Persist changes in existing TOML configuration
files while preserving operator formatting and activating valid changes
immediately.

This design supersedes the target and profile editing non-goals in
`docs/plans/admin-configuration-dashboard/DESIGN.md`. MCP clients still cannot
mutate configuration.

## Users

Platform engineers and local OpenMCP operators are the primary users.

## Decisions

- Edit global targets and profiles.
- Edit project profile overrides from Project Detail.
- Preserve the existing TOML schema.
- Use `tomlkit` for surgical document changes.
- Create a minimal project `.openmcp/config.toml` when needed.
- Validate before committing any file change.
- Atomically replace one configuration file per mutation.
- Reload and publish configuration immediately.
- Keep target and profile identifiers immutable.
- Block deletion while declarations reference the resource.
- Require loopback access, matching origin, and CSRF protection.
- Use document revisions for optimistic concurrency.
- Expose every supported target and workflow policy field.

## Architecture

Add one backend `ConfigMutationService`. Dashboard handlers delegate all TOML
inspection and mutation to this service. Handlers never edit TOML nodes.

The service owns:

- Global target CRUD.
- Global profile CRUD.
- Project profile override CRUD.
- TOML syntax-tree changes.
- Candidate validation.
- Registered-project compatibility validation.
- Reference discovery.
- Atomic replacement and rollback.
- Runtime catalog publication.

Each mutation follows this transaction:

1. Acquire the configuration mutation lock.
2. Resolve the permitted canonical source path.
3. Read the exact source bytes and calculate their revision.
4. Compare the revision with the client's expected revision.
5. Parse the document with `tomlkit`.
6. Apply one resource-level change.
7. Serialize and validate the complete candidate configuration.
8. Validate registered project overlays when global state changes.
9. Recheck the source revision before replacement.
10. Atomically replace the source file.
11. Reload and publish the resulting runtime configuration.
12. Return the changed entity and new revision.

The lock spans validation, replacement, and runtime publication. Job planning
and configuration reloads must use the same synchronization boundary. This
prevents disk-new and runtime-old observations.

## Configuration Sources

Global mutations edit the daemon configuration at
`runtime.catalog.config_path`.

Project override mutations edit:

```text
<registered-project-root>/.openmcp/config.toml
```

When the project file is absent, the service creates `.openmcp` and a minimal
valid file containing only the requested declaration. It does not add unrelated
defaults, settings, or comments.

Existing paths must be regular files. Reject directories, symbolic links, and
other non-regular paths.

## TOML Preservation

Use `tomlkit` as a syntax-tree editor rather than a normalized serializer.
Preserve:

- Comments.
- Definition order.
- Key order.
- Quoting.
- Unrelated whitespace where supported.
- Unrelated sections.
- Existing profile shorthand.
- Existing legacy target key spelling.

Locate targets by `id` within `[[targets]]`. Change only fields whose semantic
values changed. Leave absent default-valued fields absent unless the operator
explicitly changes them.

Preserve workflow declarations as strings, target arrays, or inline policy
objects when their current form remains sufficient. Expand only the edited
workflow when its policy requires `max_attempts` or `timeout_s`.

Continue accepting legacy target `profile`. Preserve that key when editing an
existing target. Emit `backend_profile` for new targets. Never emit both keys.

## API

Keep existing runtime-oriented read contracts unchanged:

```text
GET /dashboard/api/targets
GET /dashboard/api/profiles
```

Add editor-specific resources:

```text
GET    /dashboard/api/configuration/targets
POST   /dashboard/api/configuration/targets
PUT    /dashboard/api/configuration/targets/{target_id}
DELETE /dashboard/api/configuration/targets/{target_id}

GET    /dashboard/api/configuration/profiles
POST   /dashboard/api/configuration/profiles
PUT    /dashboard/api/configuration/profiles/{profile_id}
DELETE /dashboard/api/configuration/profiles/{profile_id}

GET    /dashboard/api/projects/{project_id}/profile-overrides
POST   /dashboard/api/projects/{project_id}/profile-overrides
PUT    /dashboard/api/projects/{project_id}/profile-overrides/{profile_id}
DELETE /dashboard/api/projects/{project_id}/profile-overrides/{profile_id}
```

Editor reads and mutations require loopback access. Responses use
`Cache-Control: no-store` because editable target values include system prompts
and backend arguments.

Every editor response includes a document `revision` and an HTTP `ETag`.
Mutations require `If-Match`. The revision is the SHA-256 hash of the exact
source bytes.

Use strict Pydantic request models with unknown fields forbidden. Existing
configuration loading remains the authoritative semantic validator.

## Target Model

The target editor exposes every supported field:

```json
{
  "id": "primary",
  "backend": "codex",
  "model": "",
  "backend_profile": "",
  "reasoning": "",
  "system_prompt": "",
  "isolated": false,
  "read_only": false,
  "args": [],
  "max_concurrency": 1
}
```

Target identifiers cannot change during updates. Renaming requires coordinated
reference rewriting and remains excluded.

Arguments remain an ordered string list. The dashboard never parses shell text.
Server validation continues enforcing backend restrictions, reserved arguments,
strict booleans, and positive concurrency.

## Profile Model

Editor responses separate local declarations from effective policies:

```json
{
  "id": "balanced",
  "extends": null,
  "workflows": {
    "consult": null,
    "implement": {
      "targets": ["primary", "fallback"],
      "max_attempts": 2,
      "timeout_s": 900
    },
    "other": null,
    "review": null
  }
}
```

All built-in workflows appear in editor responses. A `null` workflow means the
scope does not declare it. It does not mean disabled.

Responses also include effective values, inherited values, declaration sources,
and available targets. The frontend displays these values but never reconstructs
inheritance rules.

Project endpoints edit only project declarations. Removing a project declaration
is named `Remove override` because the matching global profile may become
effective.

## Validation

Validate candidate bytes through the existing configuration semantics. Avoid a
second independent schema implementation.

Validation covers:

- Required target fields.
- Backend-specific restrictions.
- Reserved target arguments.
- Positive concurrency.
- Known workflow names.
- Ordered target references.
- Attempt and timeout constraints.
- Unknown target references.
- Missing profile parents.
- Profile inheritance cycles.
- Global and project default profiles.
- Effective project configuration.

A global mutation validates every registered project overlay against the
candidate global catalog. Reject changes that would invalidate any registered
project.

## Optimistic Concurrency

Document-level concurrency protects external formatting and unrelated edits.
Entity-level versions are insufficient because external editors can change
comments, ordering, defaults, or references.

Mutation behavior:

- Return `428 revision_required` when `If-Match` is absent.
- Return `409 configuration_conflict` when the revision is stale.
- Include the current revision in conflict responses.
- Never silently retry against newer content.
- Preserve the frontend draft after conflicts.

Global and project files have independent revisions.

## Atomic Replacement and Rollback

Write candidate bytes to a temporary file within the source directory:

1. Preserve the existing file mode.
2. Write UTF-8 candidate bytes.
3. Flush and `fsync` the temporary file.
4. Replace the source using `os.replace`.
5. Synchronize the parent directory where supported.

A requested operation changes only one file. Multi-file transactions are not
required.

If runtime publication fails after replacement:

1. Confirm the source still matches the candidate revision.
2. Atomically restore the exact original bytes.
3. Reload the original catalog.
4. Return `500 configuration_commit_failed`.

If restoration cannot be proven, report uncertain configuration state. Never
claim the original file or runtime remained unchanged.

## Runtime Reload

A successful global mutation updates:

- The runtime catalog.
- Executor configuration.
- Configuration health and revision timestamps.
- Target runtime views.
- Project catalog caches.

A successful project mutation invalidates that project's resolved catalog and
returns its newly resolved configuration.

Running and queued jobs retain their submitted execution-plan snapshots. New
submissions use the new catalog. A changed target naturally receives a new
execution identity where current planning rules require it.

## Deletion and References

Before deleting a target, scan:

- Every global profile declaration and workflow.
- Every registered project profile declaration and workflow.

Before deleting a profile, scan:

- Global `default_profile`.
- Project `default_profile` values.
- Global profile `extends` values.
- Project profile `extends` values.

Referenced resources return `409 referenced` with structured references:

```json
{
  "code": "referenced",
  "references": [
    {
      "scope": "project",
      "project_id": "project-id",
      "profile_id": "quality",
      "workflow": "review"
    }
  ]
}
```

Historical, running, and queued jobs do not block deletion because their plans
contain configuration snapshots.

Removing a project override may proceed when the resulting global fallback is
valid. The response and confirmation preview the effective change.

Only registered projects participate in authoritative reference scanning.
Unregistered repositories remain outside runtime referential integrity.

## Dashboard Experience

### Targets

Add `Create target` to the Targets page. Selecting a target retains the existing
runtime inspector and adds `Edit target` and `Delete target` actions.

The form exposes every target field. Ordered repeatable controls edit `args`.
Runtime health polling continues independently while a form is open.

### Profiles

Add `Create profile` to the Profiles page. The selected-profile inspector shows:

- Parent profile.
- Declared workflows.
- Effective workflows.
- Source provenance.
- Edit and delete actions.

Each workflow editor provides a declaration toggle, ordered target list,
`max_attempts`, `timeout_s`, and an effective-policy preview.

### Project Detail

Add `Create override`, `Edit override`, and `Remove override` within Project
Detail. Display declared project values beside inherited and effective values.
Removal confirmation shows the resulting global fallback.

### Form State

Dirty editors suspend automatic replacement of form data. Polling may continue
for independent runtime status.

Saving displays these states:

1. Saving configuration.
2. Reloading runtime.
3. Saved and active.

A conflict preserves the draft and offers `Reload current configuration`. The
frontend never overwrites a dirty draft automatically.

## Security Boundary

Reuse the dashboard's loopback client, loopback host, matching origin, and CSRF
checks for every mutation. Apply loopback restrictions to full editor reads as
well.

Do not expose target or profile mutation through MCP tools. Connected agents
must not change execution isolation, read-only policy, prompts, backend
arguments, or routing.

Sensitive target values must not appear in:

- Existing summary endpoints.
- Runtime status payloads.
- Tables.
- Notifications.
- Generic errors.
- Logs.

## Errors

| Status | Code | Meaning |
| --- | --- | --- |
| `403` | `forbidden` | Loopback, origin, or CSRF validation failed |
| `404` | `not_found` | Resource or project does not exist |
| `409` | `configuration_conflict` | Source changed after editor loading |
| `409` | `referenced` | Another declaration blocks deletion |
| `422` | `configuration_invalid` | Candidate configuration failed validation |
| `428` | `revision_required` | `If-Match` is absent |
| `500` | `configuration_commit_failed` | Replacement, reload, or rollback failed |

Every error states what happened, what remained unchanged when known, and how to
recover. Errors never include system prompts or backend arguments.

## Compatibility and Migration

Existing TOML files require no migration. Existing dashboard read responses
remain unchanged. New editor routes are additive.

Continue supporting existing target keys and profile declaration forms. Do not
normalize an entire file during an edit.

No database migration is required.

## Testing

Backend tests cover:

- Every target field.
- Complete workflow policies.
- Global and project inheritance.
- Comments, ordering, quoting, and multiline values.
- Byte-identical unrelated regions.
- Localized shorthand expansion.
- Legacy target key preservation.
- Missing project file creation.
- Invalid candidate rejection.
- Stale revisions and external edits.
- Concurrent mutations.
- Global validation against registered projects.
- Global and project reference reporting.
- Atomic replacement and file-mode preservation.
- Reload failure rollback.
- Executor and catalog refresh.
- Existing execution-plan preservation.

Security tests cover remote clients, non-loopback hosts, mismatched origins,
invalid CSRF tokens, missing revisions, cache headers, and sensitive-value
redaction.

Frontend tests cover:

- Target creation, editing, and deletion.
- Ordered argument editing.
- Complete profile workflow editing.
- Ordered failover targets.
- Project override creation and removal.
- Dirty draft preservation.
- Revision conflicts.
- Validation error placement.
- Reference-blocked deletion.
- Runtime health polling during editing.
- Keyboard and screen-reader access.

## Success Criteria

- Operators manage global targets and profiles locally.
- Operators manage project profile overrides from Project Detail.
- Unrelated TOML content and formatting remain preserved.
- Invalid changes never replace the active configuration.
- Valid changes become active without daemon restart.
- External edits cannot be silently overwritten.
- Referenced resources cannot be deleted accidentally.
- Existing jobs remain isolated from later changes.
- Sensitive execution values remain within protected editor responses.

## Non-goals

- Target or profile renaming.
- Cascading deletion.
- Raw TOML editing.
- Draft or staging sessions.
- Database-backed target or profile storage.
- Remote dashboard authentication.
- Editing unregistered project files.
- Task-guidance editing.
- Provider credential management.
