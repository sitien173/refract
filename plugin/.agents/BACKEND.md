<!-- ccg-shared-version: 5.2.3 -->
# BACKEND.md — Backend Engineering Rules

Domain rules for server-side work: APIs, business logic, databases, infra, CI/CD, scripts, and tests. Extends the global AGENTS.md — global rules always apply.

## 1. API Design

- Design the contract before the implementation. State the endpoint, method, request/response shapes, and error cases first.
- Follow the conventions already in the codebase (REST/RPC/GraphQL style, naming, envelope format, pagination scheme). Never introduce a second convention.
- Validate all input at the boundary. Reject early with specific, actionable error messages — never let bad data reach business logic.
- Return correct status codes and stable, machine-readable error shapes (`{code, message, details}` or whatever the codebase uses).
- Breaking changes require versioning or explicit sign-off. Additive changes (new optional fields) are preferred.
- Never leak internals in responses: stack traces, SQL, internal IDs, infra hostnames.

## 2. Business Logic

- Keep domain logic out of controllers/handlers and out of the ORM layer. Handlers parse and delegate; services decide.
- Make functions deterministic where possible — inject time, randomness, and I/O so logic is testable.
- Idempotency by default for anything retried: webhooks, queue consumers, payment operations, cron jobs.
- Fail loudly on invariant violations; fail gracefully on expected external errors. Know which is which before writing the `try/catch`.
- No silent catch-and-continue. Every swallowed error must be logged with context, and you must justify why execution continues.

## 3. Database

- Schema changes go through migrations — always reversible or with a stated rollback plan, never hand-edited.
- Migrations must be safe on live data: no long table locks, backfill in batches, add-column-then-backfill-then-constrain.
- Every query against a large table must use an index. State which index a new query relies on; add one if missing.
- No N+1 queries. Batch, join, or preload — and say which you chose.
- Wrap multi-statement writes in transactions. Keep transactions short; never hold one across network calls.
- Constraints belong in the database (FK, unique, not-null, check), not only in application code.
- Never destructive operations (`DROP`, `DELETE` without `WHERE`, `TRUNCATE`) without explicit user confirmation.

## 4. Security

- Parameterized queries only — string-built SQL is forbidden.
- Secrets come from env/secret managers. Never hardcode, never log, never commit. Check diffs for leaked secrets before committing.
- Authn ≠ authz: verify *who* and *whether allowed* on every protected path. Default deny.
- Hash passwords with the codebase's established KDF (bcrypt/argon2). Never invent crypto.
- Treat all external input as hostile: file uploads, headers, webhook payloads, query params, third-party API responses.

## 5. Errors, Logging, Observability

- Structured logs (key-value/JSON) with request/correlation IDs. No `print` debugging left behind.
- Log at the right level: `error` = needs action, `warn` = degraded but handled, `info` = business events, `debug` = development only.
- Never log secrets, tokens, passwords, or full PII.
- Timeouts and retry-with-backoff on every external call. No unbounded retries; no infinite waits.
- Surface failures where operators will see them — metric, alert, or log — not just a return value.

## 6. Infra, CI/CD, Scripts

- Infra changes are code: declarative, reviewed, reproducible. No manual console changes presented as the solution.
- CI must stay green and fast. A new pipeline step needs a stated purpose and an expected runtime.
- Scripts must be safe to rerun: idempotent, with `--dry-run` for anything destructive, `set -euo pipefail` in bash.
- Pin dependency versions. Justify every new dependency — prefer stdlib or what's already installed.
- Never deploy, push to protected branches, or touch production data without explicit user instruction.

## 7. Server-Side Tests

- New logic ships with tests. Bug fixes ship with a regression test that fails before the fix and passes after.
- Test behavior through public interfaces, not implementation details. Refactors should not break tests.
- Cover the error paths and edge cases — the happy path is the easy 20%.
- Tests are isolated and order-independent: no shared mutable state, no reliance on external services. Fake/stub at the boundary.
- Don't mock what you own; don't hit what you don't own.
- Run the relevant test suite before declaring work done. "It compiles" is not done.

## <RULES> — Hard rules

- No string-built SQL. No hardcoded secrets. No destructive DB/infra operations without explicit confirmation.
- Every migration is reversible or has a written rollback plan.
- Every external call has a timeout.
- Every bug fix has a regression test.
- Don't claim completion until the tests you ran are listed and passing.
