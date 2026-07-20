# Adding a `cost` routing profile

## How OpenMCP config layers work

OpenMCP separates three concerns:

- **Targets** hold all backend execution config: `backend`, `model`, `profile`,
  `reasoning`, `args`, `capabilities`, etc.
- **Routes** declare required capabilities (`requires`) and a pool of `targets`.
- **Routing profiles** map the three built-in workflow roles
  (`implement`, `review`, `consult`) onto route IDs. A profile must map all
  three roles.

Your existing config already has:

- target `forge-primary` (codex, capability `code`)
- target `sentinel-primary` (pi reviewer, capability `review`)
- target `sage-primary` (pi consultant, capability `consult`)
- routes `forge`, `sentinel`, `sage`
- the `balanced` profile

To make a cheaper `cost` profile that only swaps the implement side, you do
**not** touch review or consult. You add:

1. A new codex target `forge-cost` using `model = "gpt-5-mini"`.
2. A new route `forge-cost` that requires the `code` capability and points at
   that target.
3. A new `cost` routing profile whose `implement` uses the new route, while
   `review` and `consult` keep pointing at the existing `sentinel` and `sage`
   routes.

Because config reloads before each submission, you can add this without a
restart. Do not put credentials in `args`.

## TOML to add to `~/.openmcp/config.toml`

```toml
# New cheaper codex target for the implement role.
[[targets]]
id = "forge-cost"
backend = "codex"
model = "gpt-5-mini"
capabilities = ["code"]

# Route that selects the cheaper target for code work.
[[routes]]
id = "forge-cost"
requires = ["code"]
targets = ["forge-cost"]

# Cost profile: cheap implement, unchanged review and consult.
[routing_profiles.cost]
implement = "forge-cost"
review = "sentinel"
consult = "sage"
```

## Notes

- `[[targets]]` and `[[routes]]` are array-of-tables, so appending these blocks
  adds to your existing lists rather than replacing them.
- The `cost` profile reuses your existing `sentinel` and `sage` routes verbatim,
  so review stays on `sentinel-primary` and consult stays on `sage-primary`.
- Select it per submission with `routing_profile = "cost"`, or set
  `default_routing_profile = "cost"` under `[server]` to make it the default.
- If you prefer the new target to mirror `forge-primary` behavior, you can add
  the same extras it uses, e.g. `profile = "mcp_execution"` and
  `args = ["--color", "never"]`. They are optional and were left out to keep the
  change minimal.
