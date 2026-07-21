# Add the `cost` profile

Append this to global `~/.openmcp/config.toml`:

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

Profiles map workflows directly to targets. The current default is unchanged;
pass `profile="cost"` to `job_submit` when desired. Call `reload` afterward to
validate and activate the target and profile for subsequent jobs.
