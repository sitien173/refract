# Changelog

## Unreleased

- Opt-in product telemetry. It is off by default and follows `DO_NOT_TRACK=1`, then `REFRACT_TELEMETRY`, then `[telemetry] enabled`. Events queue in a local outbox and go to `[telemetry] endpoint`. Prompts, results, project paths, and target `args` and `env` values are never collected as payload fields, and error text is redacted for target values and paths, but it may still carry prompt or code fragments. `refract telemetry` shows the decision and the exact next batch. See the Telemetry section of `server/README.md`.
- Local usage stats from a `job_metrics` table kept for 365 days: work delegated, failover saves, tokens by backend, model, and target, and estimated cost from the new `[pricing]` config. `refract stats [--days N] [--json]` and `GET /dashboard/api/stats` serve them.
- Dashboard Insights view at `/dashboard/insights` with a 1, 7, 30, and 365 day window.
- Database schema 20 adds the `job_metrics` and `telemetry_outbox` tables and migrates schema 19 and 18 databases in place. Refract 3.0.1 and older refuse a schema 20 database and leave it unchanged, so keep a copy of `refract.db` before you upgrade if you may go back.

## 3.0.1 - 2026-11-10

- Documentation site in `site/`, built with Jekyll and Just the Docs and deployed to GitHub Pages.
- `refract update` no longer reports an update forever after an editable clone install moves to a new version: it reinstalls the server when its package metadata version differs from the clone.
- `refract update --check` compares a Pi GitHub package against the version Pi checked out, not the server version.

## 3.0.0 - 2026-11-09

First public release.

- Three-gate workflow: brainstorm a design, write a phase plan, then execute and review each phase.
- Worker backends for Codex, Claude Code, Pi, and Antigravity.
- Profiles that map each workflow to an ordered list of targets, with a circuit breaker for unhealthy targets.
- Independent review on a different target from implementation.
- Parallel waves that run independent plan phases in separate Git worktrees.
- Durable jobs, sessions, and results in a local SQLite store.
- Worker questions to the Coordinator through `refract ask`.
- Live dashboard for transcripts, cancel, retry, and answer.
- Host plugin for Claude Code, Antigravity, Codex, and Pi.
