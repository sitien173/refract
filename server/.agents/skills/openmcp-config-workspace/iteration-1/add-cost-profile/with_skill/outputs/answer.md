# Adding a `cost` routing profile

## What you asked for

A cheaper `cost` profile that:

- runs `implement` on a **new** codex target using model `gpt-5-mini`,
- keeps `review` on your existing `sentinel` route (`sentinel-primary`),
- keeps `consult` on your existing `sage` route (`sage-primary`).

## How OpenMCP models this

OpenMCP resolves work in three separate layers, and you should not collapse them:

1. **Target** owns provider execution (backend + model). The cheaper model is a
   new target, not a tweak to `forge-primary`. That keeps your existing
   `balanced` profile and its target untouched.
2. **Route** owns a capability requirement plus a pool of eligible targets. The
   new target needs its own route so a profile can point at it.
3. **Routing profile** maps the `implement` / `review` / `consult` roles onto
   route IDs.

So the change is three additions: one target, one route, and one profile. Review
and consult reuse the routes you already have (`sentinel`, `sage`), so nothing
about your reviewer or consultant changes.

Notes:

- Targets are **global only** and live in `~/.openmcp/config.toml`, which is
  exactly where you are adding this.
- All three roles are mapped in the new profile. Omitting a role would leave jobs
  for that role unroutable.
- No secrets, no `args`, `host` stays on loopback. The model is set through the
  first-class `model` field, as required.
- This is a config reload change: it takes effect on the **next submission**. No
  daemon restart is needed (restarts are only for host/port/workers/logging).
- To make `cost` the default for submissions that omit a profile, set
  `default_routing_profile = "cost"` under `[daemon]`. That was not requested, so
  it is left alone and `balanced` stays the default.

## TOML to add to `~/.openmcp/config.toml`

```toml
# New cheaper implementer target (codex, gpt-5-mini).
[[targets]]
id = "forge-mini"
backend = "codex"
model = "gpt-5-mini"
capabilities = ["code"]

# Route that pools only the new cheaper target.
[[routes]]
id = "forge-mini"
requires = ["code"]
targets = ["forge-mini"]

# Cost profile: cheap implement, unchanged review and consult.
[routing_profiles.cost]
implement = "forge-mini"
review = "sentinel"
consult = "sage"
```
