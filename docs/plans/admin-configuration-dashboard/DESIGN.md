# OpenMCP Admin Configuration Dashboard

## Purpose

Build a FlowForge-branded administration dashboard for OpenMCP operators. The
dashboard explains effective configuration, profile resolution, target health,
configuration validity, and job behavior.

Target configurations, global profiles, and project overrides are editable.
Context instructions are also editable through the dashboard.
Daemon network and scheduler options remain managed on disk.

## Users

Platform engineers and local OpenMCP operators are the primary users.

## Scope

The initial dashboard provides:

- Daemon and scheduler status.
- Configuration health and revision identity.
- Registered project visibility.
- Global and project-resolved profiles.
- Target configuration and health.
- Runtime setting reload behavior.
- Task-guidance visibility.
- Context instruction editing.
- Job configuration revision visibility.

Core daemon options remain externally managed on disk.
Target, profile, and override declarations support dashboard mutations.

## Information Architecture

```text
OpenMCP
├── Overview
├── Projects
│   └── Selected project
│       ├── Effective configuration
│       ├── Profile resolution
│       ├── Task guidance
│       ├── Context instructions
│       └── Jobs
├── Targets
├── Profiles
├── Runtime settings
└── Configuration health
```

Project is the primary context selector. Project selection controls effective
profile resolution, task guidance, context instructions, and job history.

## Configuration Classification

Every configuration field displays one classification.

| Classification | Meaning |
| --- | --- |
| Live | Reloaded before the relevant operation |
| Restart required | Applied after restarting the daemon |
| Editable | Database-backed dashboard editing |
| Repository sourced | Loaded from project files |

Current reload behavior is:

| Configuration | Behavior |
| --- | --- |
| Targets and profiles | Reloaded before job submission |
| Project profile overrides | Reloaded before job submission |
| Task guidance | Reloaded when guidance is requested |
| Context instructions | Mutable through runtime persistence |
| Host and port | Restart required |
| Worker count | Restart required |
| History limits | Restart required |
| Logging | Restart required |

## FlowForge Design System

Use the FlowForge product shell and account-management patterns.

- Import `colors_and_type.css` before custom styles.
- Use Libre Franklin throughout.
- Use the gray canvas and white working panels.
- Use the standard 200px sidebar and 64px top bar.
- Use account-style tabs for project sections.
- Use 44px table headers and 56px table rows.
- Use 48px production form fields.
- Use 660px modals for focused editing.
- Prefer borders over shadows for ordinary structure.
- Reserve green for primary actions, selection, and success.
- Reserve blue for links, focus, and interaction cues.
- Pair status color with a Lucide icon and label.
- Avoid gradients, decorative blobs, and decorative animation.

| Dashboard area | FlowForge pattern |
| --- | --- |
| Main navigation | Product sidebar |
| Project context | Top-bar selector |
| Project sections | Account-style tabs |
| Targets and profiles | Dense data grids |
| Configuration details | Docked inspector |
| Health failures | Semantic alerts |
| Reload behavior | Status badges |
| Context editing | 660px modal |
| Job history | Dense data grid |

## Screens

### Overview

Show:

- Daemon status.
- Active and queued jobs.
- Configuration health.
- Current configuration revision.
- Registered project count.
- Unhealthy target count.
- Recent configuration failures.

Summary values link to filtered operational views.

### Projects

Use a dense data grid with:

- Alias.
- Repository path.
- Default profile.
- Profile source.
- Active jobs.
- Last activity.
- Configuration status.

Selecting a project opens its workspace.

### Project Workspace

Use these tabs:

- Effective configuration.
- Profile resolution.
- Task guidance.
- Context instructions.
- Jobs.

The top bar shows the project alias and root path.

### Effective Configuration

Show declared and resolved values together.

```text
Workflow    Declared Profile    Effective Target    Source
consult     consult             opus-consult        Global
implement   project-default     claude-worker       Project
review      review              opus-review         Global
```

The inspector explains inheritance and override sources.

### Profile Resolution

Show profiles as expandable table rows. Each row exposes:

- Parent profile.
- Declared workflows.
- Inherited workflows.
- Effective targets.
- Attempt limits.
- Timeouts.
- Configuration source.

Self-extension against the global snapshot must remain explicit.

### Targets

Show:

- Identifier.
- Backend.
- Model.
- Isolation status.
- Read-only status.
- Maximum concurrency.
- Active jobs.
- Health.

Do not expose provider credentials.

### Runtime Settings

Group settings by reload behavior.

```text
Live Configuration
Targets
Profiles
Default profile

Restart Required
Host
Port
Worker count
History limits
Logging
```

Each row shows its source file and revision.

### Configuration Health

Show:

- Parse status.
- Last attempted load.
- Last successful load.
- Current content hash.
- File modification time.
- Last load failure.
- Last-known-good revision.
- Affected operations.
- Recovery guidance.

Daemon status and configuration health remain separate.

### Context Instructions

Show one row per built-in workflow. Supported actions are:

- Add instruction.
- Edit instruction.
- Clear instruction.

Editing uses the existing runtime behavior. Confirmation states that changes
apply only to future jobs.

### Jobs

Show each job's configuration revision and execution-plan snapshot. This
explains why jobs submitted at different times may resolve differently.

## Architecture

```text
FlowForge Dashboard
        |
        | dashboard HTTP API
        v
OpenMCP Starlette Application
        |
        ├── Runtime status
        ├── Configuration inspection
        ├── Project resolution
        ├── Target health
        ├── Job history
        └── Context instruction mutation
        |
        ├───────────────┐
        v               v
Configuration Files   SQLite
```

Serve the dashboard through the existing Starlette application. Use dedicated
HTTP routes and structured Pydantic response models.

Do not expose configuration-file mutation through MCP tools. Connected agents
must never modify target isolation, read-only policy, system prompts, backend
arguments, or profile routing.

## Read API

The dashboard requires read endpoints for:

- Daemon status.
- Configuration health.
- Runtime settings.
- Targets.
- Profiles.
- Registered projects.
- Project-resolved configuration.
- Task guidance.
- Context instructions.
- Jobs and execution plans.

The backend performs profile inheritance resolution and source attribution. The
frontend must not reconstruct those rules.

## Configuration Health

Configuration loading records:

- Last successful load time.
- Last attempted load time.
- Current revision hash.
- File modification time.
- Parse status.
- Last error.
- Last-known-good revision.

A malformed configuration must not appear healthy. The dashboard may show:

```text
Daemon: Running
Configuration: Invalid
Job submission: Blocked
```

## Revision Identity

Compute a stable content hash for every loaded configuration source.

```text
ConfigRevision
├── content hash
├── modification time
├── source path
├── loaded time
└── validity
```

Every newly submitted job records the revision used to build its execution-plan
snapshot. Existing jobs use an empty revision identifier and display
`Configuration revision unavailable`.

In-flight jobs remain isolated from later configuration changes. The dashboard
states:

> Configuration changes affect newly submitted jobs only.

## Project Resolution

The project configuration endpoint returns:

- Global default profile.
- Project default profile.
- Global profile declarations.
- Project profile declarations.
- Resolved workflow mappings.
- Value sources.
- Task-guidance source.
- Context instructions.

## Context Instruction Mutation

The dashboard mutation endpoint calls existing runtime behavior. It supports:

- Replace instruction.
- Clear instruction.
- Expected current value.
- Updated response value.

Expected-value comparison prevents accidental overwrites.

## File-Managed Configuration

The dashboard never writes:

- Global `config.toml`.
- Project `.openmcp/config.toml`.
- Global `task_guide.json`.
- Project `.openmcp/task_guide.json`.

Operators continue editing those files externally.

## Security Boundary

Dashboard mutation routes require explicit administrative protection. Remote
daemon administration is excluded.

Mutation must not become an MCP tool. An MCP client able to edit target policy
could weaken isolation, enable additional tools, inject system prompts, or add
backend arguments.

Read responses must omit unnecessary system-prompt content and other sensitive
execution details.

## Status Refresh

Poll status and active jobs every five seconds. Preserve displayed data during
refresh failures. Refresh configuration views after revision changes.

Use existing resource subscriptions when practical. Additional real-time
transport is not required initially.

## Errors

| Condition | Dashboard response |
| --- | --- |
| Unknown project | Not-found state |
| Invalid configuration | Persistent error alert |
| Missing source file | Configuration-health error |
| Context conflict | Refresh and retry warning |
| Permission failure | Disabled action and explanation |
| Runtime unavailable | Connection error with retry |
| Invalid instruction | Inline validation |

Every error states what happened, what remains unchanged, and how to recover.

Use stable skeleton rows for initial loading. Preserve existing data during
refresh failures.

## Migration

Existing configuration files require no migration.

The database adds configuration revision fields to jobs. Existing jobs receive
an empty revision identifier.

## Responsive Behavior

Desktop is the primary platform. On smaller screens:

- Collapse the sidebar before content compresses.
- Preserve table column widths.
- Allow horizontal table scrolling.
- Stack toolbar controls when required.
- Fit modals within the viewport.
- Keep modal footer actions visible.

Do not convert configuration tables into cards.

## Accessibility

- Preserve visible blue focus rings.
- Support complete keyboard navigation.
- Give icon-only buttons accessible names.
- Pair status icons with text labels.
- Provide programmatic validation summaries.
- Associate data cells with table headers.
- Announce asynchronous status changes.
- Keep primary touch actions at least 44px high.

## Testing

Unit coverage includes:

- Revision hashing.
- Configuration-health transitions.
- Reload classification.
- Profile source attribution.
- Inheritance resolution serialization.
- Context expected-value comparison.
- Sensitive-field omission.

Integration coverage includes:

- Valid global configuration inspection.
- Invalid configuration health reporting.
- Project override resolution.
- Task-guidance source reporting.
- Context instruction replacement.
- Context instruction conflicts.
- Job revision persistence.
- Dashboard route authorization.

The primary end-to-end flow is:

```text
Open dashboard
→ select project
→ inspect resolved profile
→ compare declared and effective targets
→ edit context instruction
→ submit a new job
→ verify instruction and revision
```

Additional end-to-end coverage includes broken configuration, restart-required
labels, unhealthy targets, existing jobs without revisions, and keyboard-only
navigation.

## Success Criteria

- Operators identify invalid configuration immediately.
- Operators understand effective profile routing.
- Global and project sources remain distinguishable.
- Every new job identifies its configuration revision.
- Context instructions remain safely editable.
- Target and profile mutations activate immediately.
- Registered project reference checks guard deletions.
- Unregistered external projects cannot be scanned.
- In-flight jobs remain isolated from changes.

## Non-goals

- Editing raw TOML directly.
- Editing task-guidance files.
- Approval workflows.
- Configuration rollback.
- Multi-operator collaboration.
- Real-time collaborative editing.
- Provider credential management.
- Remote daemon administration.
- Replacing MCP clients.
- Restarting the daemon automatically.
