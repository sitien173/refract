# Add the `cost` profile

Edit global `~/.openmcp/config.toml`. Add one target and map the three built-in
workflows directly to target IDs:

```toml
[[targets]]
id = "forge-mini"
backend = "codex"
model = "gpt-5-mini"
capabilities = ["code"]

[profiles.cost]
implement = "forge-mini"
review = "sentinel-primary"
consult = "sage-primary"
```

This leaves the existing default unchanged. Select it with
`job_submit(profile="cost")`, or set `default_profile = "cost"` under
`[daemon]` if it should become the default.

No credentials belong in target configuration. After saving, call `reload` and
check `success` and `restart_required`. Target/profile changes apply to new jobs
without a daemon restart; running jobs retain their saved plans.
