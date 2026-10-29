---
name: setting-up-refract
description: Install the Refract daemon, scan local worker CLIs, and write config.toml targets and profiles.
disable-model-invocation: true
---

# Setting Up Refract

## Role

This skill owns first-time Refract setup: daemon install, backend scan, and
the global `config.toml`. Backend names, detection commands, and field rules
live in [`../../setup/backends.md`](../../setup/backends.md); read it before
step 2. `coordinating-multi-model-work` owns everything after the daemon
answers.

## Constraints

- Config lives at `$REFRACT_HOME/config.toml`, default `~/.refract/config.toml`.
- Ask one question per message with two to four bounded choices.
- Write only targets for backends the scan found.
- Back up an existing config to `config.toml.bak-<YYYYMMDD>` before any write,
  and show the full new file for approval first.
- Keep credentials in each CLI's own login or in `[envs.<name>]`.

## Workflow

Each step ends on its stated completion criterion.

1. **State.** Check for an existing config, a Refract checkout, and a
   reachable daemon: the `project_resolve` tool responds. Done when each is
   recorded as present or absent. With an existing config, ask: extend it,
   replace it, or stop.
2. **Scan.** Run every detect command in `backends.md`, then `--version` on
   each hit. Done when every backend is marked found or missing, with version.
   Zero found: list the four CLIs, stop, and ask the user to install one.
3. **Models.** For each found backend, run its listing command. Done when the
   user has picked the models to use per backend.
4. **Targets.** Propose one target per role the user wants: code, review,
   consult. Name ids `<backend>-<model>-<reasoning>-<role>`. Default review
   targets to `isolated = true` and `read_only = true` where supported. Done
   when the user confirms the target list.
5. **Profiles.** Propose `[profiles.base]` mapping `implement`, `review`, and
   `consult`. Review uses a target other than the implement target when one
   exists, so review stays independent. Offer extra profiles that `extends =
   "base"` and override one workflow. Add `other` only on request. Set
   `[daemon].default_profile = "base"`. Done when the user confirms.
6. **Write.** Assemble `[daemon]`, `[[targets]]`, and `[profiles.*]`. Keep
   daemon defaults unless the user asked otherwise. Done when the approved
   file is on disk.
7. **Install.** Skip when step 1 found a checkout. Otherwise confirm Python
   3.12 or newer and `uv`, then:

   ```bash
   git clone https://github.com/sitien173/refract
   cd refract/server && uv sync --all-extras
   ```

   Done when `uv run refract --help` succeeds in `server/`.
8. **Verify.** Run `uv run refract doctor` in `server/`. Done when it exits 0:
   home writable and every target executable resolved. On failure, fix the
   named target or path and rerun.
9. **Serve.** Ask before starting `uv run refract serve` as a background
   process. For a non-default host or port, the user exports `REFRACT_URL`
   before restarting the client. Done when `project_resolve` on the current
   Git root succeeds and `task_guide` lists the configured profiles.

## Edge Cases

- **Per-project override.** The user wants a different default profile for
  one repository: write `.refract/config.toml` there with `default_profile`
  and optional `[profiles.*]`. Project `[[targets]]` entries may only overlay
  `id`, `envs_vars`, and `envs` of existing global targets.
- **Doctor config error.** `refract doctor` prints `Configuration error:`:
  fix the named key and rerun step 8.
- **Daemon already running.** It reloads targets and profiles on the next
  tool call after the file changes; skip step 9 and confirm with
  `task_guide`. A `[daemon]` host or port change needs a restart: ask first,
  since active jobs would be interrupted.
