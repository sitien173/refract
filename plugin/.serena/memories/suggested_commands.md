# Suggested Commands

## Testing
```bash
# Run all fast tests (recommended)
./tests/claude-code/run-skill-tests.sh

# Run integration tests (slow, 10–30 minutes)
./tests/claude-code/run-skill-tests.sh --integration

# Run a single test file
./tests/claude-code/run-skill-tests.sh --test <test-file>.sh

# With verbose output
./tests/claude-code/run-skill-tests.sh --verbose

# Custom timeout (seconds)
./tests/claude-code/run-skill-tests.sh --timeout 1800
```

## Git (Unix syntax via Git Bash on Windows)
```bash
git status
git log --oneline -10
git diff
git add <files>
git commit -m "type: message"
git push
```

## Exploring Skills
```bash
ls skills/
cat skills/<skill-name>/SKILL.md
```

## Plugin Metadata
```bash
cat .claude-plugin/plugin.json     # version, name, description
cat .claude-plugin/marketplace.json
```

## No build step needed — this is a Markdown/Bash/JS plugin, not a compiled app.
