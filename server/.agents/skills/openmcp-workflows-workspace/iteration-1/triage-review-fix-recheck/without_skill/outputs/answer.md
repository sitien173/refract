# Use an OpenMCP job chain

Custom `.openmcp/workflows/*.yaml` files are unsupported. Use the built-in
sequence `consult -> implement -> review` instead.

Give each job a precise prompt and context key. Pass the successful
implementation job to review through `parent_job_id`. Integrate the
implementation only after review passes. If review requires changes, run a new
`implement` fix job and integrate that approved implementation.
