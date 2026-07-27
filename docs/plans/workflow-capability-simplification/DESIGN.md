# Workflow Capability Simplification

## Purpose

Remove target capability labels. Keep the three fixed workflows:
`consult`, `implement`, and `review`.

Capabilities currently duplicate profile routing. They are self-declared and
do not enforce backend behavior. Target policy remains responsible for model,
isolation, tools, and read-only execution.

## Decisions

- Keep fixed workflow names and MCP discovery.
- Replace workflow definitions with validated strings.
- Reject unknown workflow keys inside profiles.
- Remove capabilities from target configuration objects.
- Remove capabilities from new execution-plan snapshots.
- Remove capabilities from target API and dashboard models.
- Preserve scheduling, retries, contexts, and target policies.
- Do not add custom or project-defined workflows.

## Rejected alternatives

### Keep capabilities

This preserves redundant configuration and public fields. Capability labels do
not prove actual backend behavior or filesystem safety.

### Allow arbitrary workflow strings

This makes misspellings indistinguishable from new workflows. Workflow names
also identify durable context sessions. Dynamic names require new discovery,
task-guide validation, migration, and naming rules.

## Data flow

1. Submission validates one fixed workflow string.
2. The selected profile resolves that workflow.
3. The immutable plan snapshots selected targets.
4. Target policy controls backend execution.
5. Workflow remains the stored context role.

## Validation and errors

- Unknown submitted workflows fail immediately.
- Unknown profile workflow keys fail configuration loading.
- Missing profile mappings still fail plan resolution.
- Targets no longer declare semantic capabilities.
- Read-only enforcement remains independent.

## Compatibility

- Existing databases require no migration.
- Historical jobs remain readable.
- Old execution plans may contain extra capability fields.
- Plan parsing ignores those legacy fields.
- Existing TOML capability keys become inert.
- Config responses omit capabilities.
- Config writes remove retained capability keys.
- Target fingerprints change once after deployment.
- Native backend sessions may restart once.
- Stored text history remains available.

## Testing

- Verify all three fixed workflows still submit.
- Verify custom submitted workflows are rejected.
- Verify unknown profile workflow keys are rejected.
- Verify legacy plan snapshots still parse.
- Verify new plan snapshots omit capabilities.
- Verify target APIs omit capabilities.
- Verify the dashboard removes its capability column.
- Run Python, web, build, and packaging checks.
