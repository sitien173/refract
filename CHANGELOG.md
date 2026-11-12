# Changelog

## Unreleased

- The coordinator now decides whether a fix needs a re-review. Fixes for security, data loss, migration, concurrency, authentication, or public interface findings, and fixes that change more than the finding names, are re-reviewed. The coordinator closes other fixes itself and records the decision in `journal.md`. The review-fix loop allows one automatic fix cycle instead of two, then hands remaining blocking findings to the user. In autonomous runs, blocking findings still open after a second fix cycle are a hard stop.
- Each kind of test now runs once per phase. Implement workers run targeted tests per task and the `Done When` commands once at the end. The coordinator runs the declared commands once before review and passes the results to the reviewer. Reviewers run a test only to reproduce a suspected blocking finding, and open with the `# CODE QUALITY REVIEW` status block. After a fix, the coordinator reruns only the affected checks, then the full declared commands once when it finalizes the phase.

## 3.0.2 - 2026-11-12

- The SessionStart hook and skills name Refract MCP tools by the `refract` server instead of a host-specific prefix, so every host resolves them without colliding with same-named tools from other servers. Antigravity no longer receives the Claude Code tool name.
- Add `refract stop` and `refract restart` with optional force, and report the daemon PID in `refract status`.
- Opt-in product telemetry. It is off by default and follows `DO_NOT_TRACK=1`, then `REFRACT_TELEMETRY`, then `[telemetry] enabled`. Events queue in a local outbox and go to the fixed collector at `https://cf-api-gateway.sitienbmt.workers.dev/refract-collector`. Prompts, results, project paths, and target `args` and `env` values are never collected as payload fields, and error text is redacted for target values and paths, but it may still carry prompt or code fragments. `refract telemetry` shows the decision and the exact next batch. See the Telemetry section of `server/README.md`.
- Local usage stats from a `job_metrics` table kept for 365 days: work delegated, failover saves, tokens by backend, model, and target, and estimated cost from a price file that the daemon fetches every 24 hours and caches at `$REFRACT_HOME/pricing.toml`. The fetch ignores telemetry consent, sends no usage data, and `REFRACT_PRICING_FETCH=0` turns it off. A leftover `[pricing]` config section is ignored with a warning. `refract stats [--days N] [--json]` and `GET /dashboard/api/stats` serve them. Provider-prefixed and aliased model names merge into one row.
- Dashboard Insights view at `/dashboard/insights` with a 1, 7, 30, and 365 day window.
- Database schema 20 adds the `job_metrics` and `telemetry_outbox` tables and migrates schema 19 and 18 databases in place. Refract 3.0.1 and older refuse a schema 20 database and leave it unchanged, so keep a copy of `refract.db` before you upgrade if you may go back.
- Database schema 21 adds `job_metrics.profile` and migrates schema 20, 19, and 18 databases in place, backfilling the profile from jobs still stored. The Insights stats payload gains `work_delegated.breakdown`, a list of job counts by profile, workflow, target, and state. Refract versions that support only an older schema refuse a schema 21 database and leave it unchanged.
- Readable, project-grouped console rows in the dashboard: jobs show a `workflow · session` title with a `target · relative time · short id` meta line, organized into collapsible per-project sections.
- Dashboard Board and Targets grouping: the Board project selector lists project roots, 'All projects' organizes cards into collapsible per-project swimlanes, card details open in a centered modal dialog, and targets are grouped by backend with target and healthy counts.
- Dashboard Insights chart and breakdown improvements: continuous zero-filled daily ranges, labelled y axis with gridlines, window-thinned x-axis date labels, full-width legend, accessible hover and focus tooltips with roving tabindex for annual views, and an expanded breakdown table by profile, workflow, target, and state replacing the separate jobs by state table.
- `refract install -p <host>` and `refract uninstall -p <host>` install and remove the plugin for `claude`, `codex`, `agy`, and `pi` by running each host's own CLI, with `--scope`, `--dry-run`, and `--source`. The repository now ships a Codex marketplace manifest at `.agents/plugins/marketplace.json`.
- `refract install -p agy-ide` and `refract uninstall -p agy-ide` install and remove the plugin for the standalone Antigravity IDE by copying it to `~/.gemini/config/plugins/refract/` (`user`) or `<cwd>/.agents/plugins/refract/` (`project`), the one host Refract installs by writing files itself. `--source` must be a local path, `-p all` includes it only when the IDE is detected, and uninstall removes only a directory that carries Refract's ownership marker.
- The plugin now ships `plugin/plugin.json`, a copy of `.antigravity-plugin/plugin.json`, because the standalone Antigravity IDE loads a plugin only when `plugin.json` sits at its root.

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
