# Use built-in jobs instead of `triage.yaml`

OpenMCP does not load project-defined workflow YAML, so do not create
`.openmcp/workflows/triage.yaml`.

Express the sequence with built-in jobs:

1. Submit `consult` (or `review` when inspecting existing code) to identify the
   required changes.
2. Submit `implement` with a prompt containing those findings and a
   `commit_message`.
3. Submit `review` with the implementation job as `parent_job_id` to verify the
   committed result.
4. If verification passes, integrate the implementation job. If fixes are
   required, submit another `implement` based on the latest implementation state
   and integrate that successful fix.

Use stable context keys such as `triage/analysis`, `triage/implement`, and
`triage/review`. Select configured profiles per job, not providers or targets.
