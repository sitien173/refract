# Target Environments Design

**Status:** Confirmed 2026-10-27
**Consultation:** Failed without usable advice; continued locally. Refract consultation `e32076ca-0f39-4578-8741-c0f9eec1456e` returned a generic error. The user approved the design and directory name after that failure.

## Purpose

Configure shared environment sets and target-local variables. Support global configuration and project configuration without leaking credentials into job storage.

## Users and Success Criteria

Refract operators configure backend processes through TOML. Shared sets avoid duplicated credentials and endpoints. Each target receives its own effective environment. Projects can override shared sets and target environments without changing unrelated target policy.

Success requires deterministic precedence, interpolation, project isolation, sanitized errors, restart support, and backward compatibility. Existing dashboard edits preserve environment declarations without exposing their values.

## Constraints and Non-Goals

Use existing configuration loaders and subprocess environment transport. Add no dependencies. Do not modify process-wide `os.environ`.

Configuration files remain operator-managed and may contain plaintext secrets. Memory-only means no additional environment values or templates in job snapshots, events, telemetry, dashboard responses, or logs. It does not prevent child processes from reading their environment. Arbitrary provider output redaction is outside this change.

No new dashboard controls, secret vault, encrypted snapshots, dotenv files, shell expansion, command substitution, variable deletion, or general project target-policy overrides. No live provider probes or daemon deployment.

## Chosen Approach

Keep environment declarations in configuration catalogs. Resolve them in memory before target execution. Persist no environment values or templates in execution plans. Restarted queued jobs and explicit retries use current configuration for their environments, while retaining existing snapshotted non-environment target policy.

Rejected: plaintext job snapshots would store credentials. Rejected: encrypted snapshots require key management beyond this feature.

### Configuration

Global `config.toml`:

```toml
[envs.aws_bedrock_gemini]
GEMINI_API_KEY = "example-placeholder"
GOOGLE_GEMINI_BASE_URL = "https://example.com/gemini"
VAR_ENV = "${GEMINI_API_KEY}"

[[targets]]
id = "primary"
backend = "pi"
envs_vars = ["aws_bedrock_gemini"]
envs = { TARGET_LABEL = "primary" }
```

Project `.refract/config.toml`:

```toml
[envs.aws_bedrock_gemini]
GOOGLE_GEMINI_BASE_URL = "https://project.example.com/gemini"

[[targets]]
id = "primary"
envs_vars = ["aws_bedrock_gemini"]
envs = { TARGET_LABEL = "project-primary" }
```

`envs_vars` is an ordered list of shared-set names. `envs` is a string-to-string TOML table. Omitting either field retains existing behavior. An empty string is a legitimate value, not a deletion marker.

Project shared sets merge with global sets by name and key. Project values win matching keys. Project-only sets are allowed. Global declarations must reference globally defined sets; project target overrides can select project-only sets.

Project `[[targets]]` entries require an existing global target `id`. Only `id`, `envs_vars`, and `envs` are allowed. Omitted `envs_vars` inherits the global selection; an explicit list replaces it, including `[]`. Project target-local keys merge over global target-local keys. Empty local tables do not delete inherited keys. Reject unknown target identifiers and duplicate project target entries.

## Architecture and Data Flow

1. `config.py` validates shared sets and target declarations. Catalogs retain declarations, not exported process environments.
2. `load_project_config` builds independent merged sets and target overrides. It must not mutate the global catalog or another project's catalog. Existing profile resolution continues against the same target identifiers.
3. The execution boundary obtains current project environment declarations by stored target `id`. It preserves the stored target backend, arguments, retry policy, and other execution policy. It must not substitute an entire current target for the stored target.
4. Start from an inherited environment copy. Apply selected shared sets in listed order, then target-local values. Project merging occurs before these layers. Thus target-local values still override project shared-set values.
5. Resolve configured templates against the final merged namespace. References to inherited-only values return those values literally. Never recursively interpret inherited values as templates. Forward references work independent of TOML declaration order.
6. Pass the resolved overrides through the existing driver and `BackendParams.env` path. Add daemon-generated ask variables last. Reject configured `REFRACT_ASK_*` keys and references so configuration cannot capture or replace ask credentials.
7. Resolve once per selected target execution before session preparation. Keep that in-memory binding stable for its automatic retries and session recovery. Later explicit retries and restarted queued jobs resolve current configuration again. Release per-execution bindings at termination; do not create an unbounded job-secret cache.

Persist only non-secret structural metadata needed to identify environment-enabled jobs. A version marker or boolean distinguishes new jobs from historical plans. Do not persist group contents, target-local contents, resolved values, or interpolation templates. Historical plans without environment metadata retain their original no-configured-environment behavior.

Include opaque global/project configuration revision context in environment-enabled session identity. Never derive a public fingerprint directly from a resolved secret. Prevent sessions crossing projects or reusing incompatible environment configurations. Preserve historical identity when environment configuration is absent. Existing target capacity limits must not multiply when environments differ.

If the stored target no longer exists in current configuration, fail environment-enabled execution with a sanitized configuration error. Do not silently run without its configured environment. Environment-free historical plans need no current target lookup.

## Errors and Edge Cases

Validate set mappings, selection lists, string values, and environment keys. Reject empty keys, `=` in keys, and NUL bytes in keys or values. Preserve valid empty values and case-sensitive names. Do not silently coerce numbers or booleans to strings.

`${NAME}` references the final merged value. Missing references and cycles fail before launching a worker. A direct self-reference is a cycle; it does not implicitly read an overwritten inherited value. `$${NAME}` produces literal `${NAME}`. `$$` produces literal `$`. Bare `$NAME` is literal. Reject unterminated or empty `${...}` references without echoing their contents. No shell or command execution occurs.

Errors use structural messages consistent with `sanitize_config_error`. Never echo values, templates, or arbitrary user-controlled identifiers. Environment errors must not become generic provider retries or poison provider health.

Global loading validates declaration structure and shared-set references. Resolve project-dependent interpolation only after project merging, at execution. Unselected shared sets do not contribute values or interpolation dependencies.

Backend discovery and structured-mode probes keep existing daemon-environment behavior. Target-configured `PATH` affects the launched subprocess, not CLI discovery. Document that limitation rather than expanding discovery and cache semantics.

Dashboard read models and mutation responses omit environment contents. Existing TOML mutations preserve shared-set tables, selections, target-local tables, and comments when editing unrelated fields. Maintain compare-and-swap revision validation and project validation.

## Migration

Existing configurations need no changes. Existing plans without environment metadata remain readable. New environment-enabled plans use a non-secret marker so restart and explicit retry can rebind current project environments. No database schema migration or environment-value backfill is required.

Configuration reload changes future bindings. Running target executions retain their current in-memory binding. Exact historical environment replay after restart is intentionally unsupported.

## Testing

Use failing regression tests before production changes. Cover global declarations, project set merging, per-target overlays, list replacement, empty values, and invalid structures. Cover forward references, inherited references, escaping, unknown references, cycles, and protected ask keys.

Test real subprocess environment transport with fake backend commands, without live providers. Test concurrent projects, separate targets, automatic retries, session recovery, explicit retries, queued restart, target removal, and configuration rotation. Confirm that `os.environ` stays unchanged.

Use distinctive synthetic secret markers. Assert their absence from persisted plan JSON, database events, logs generated by environment handling, API responses, dashboard models, and mutation errors. Confirm snapshot policy remains immutable except for the approved current-environment rebinding. Verify old plan parsing and environment-free execution identities remain unchanged.

Add dashboard mutation preservation tests and run the existing non-live server suite. No live credentials are required.

## Risks and Open Questions

- Environment changes can change authentication, endpoints, and subprocess behavior. Treat configuration authors as trusted operators.
- Project files can already influence worker execution through profiles. This feature also grants environment control; document that operators must review project configuration.
- Memory-only environment state intentionally trades exact restart replay for reduced credential persistence.
- Existing unrelated active plan artifacts describe retry-policy and telemetry work. Preserve them; reconcile jobs again before execution.
- Consultation failed. Independent specification and quality review remain mandatory during implementation.
- No unresolved user-facing design questions remain. Implementation must stop for clarification if these constraints cannot be met without expanding scope.
