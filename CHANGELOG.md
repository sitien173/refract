# Changelog

## Unreleased

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
