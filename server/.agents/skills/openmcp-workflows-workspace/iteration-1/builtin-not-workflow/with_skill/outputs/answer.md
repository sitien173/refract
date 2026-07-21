# Use the built-in `implement` workflow

Do not create `.openmcp/workflows/*.yaml`; project-defined workflows are not
loaded.

Submit:

- `workflow`: `implement`
- `inputs.prompt`: `Fix the null-pointer bug in src/parser.py and run focused tests.`
- `inputs.commit_message`: `fix: prevent null pointer in parser`
- a stable context key such as `parser/null-pointer/implement`
- an optional configured `profile`

Wait for success, inspect the result, and integrate the successful implementation
when requested.
