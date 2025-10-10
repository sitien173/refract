---
name: Sharing Skills
description: Contribute personal skills back to core superpowers via fork, branch, and PR
when_to_use: When you have a personal skill that would benefit others and want to contribute it to the core superpowers library
version: 1.0.0
languages: bash
---

# Sharing Skills

## Overview

Contribute personal skills from `~/.config/superpowers/skills/` back to the core superpowers repository.

**Workflow:** Fork → Clone to temp → Sync → Branch → Copy skill → Commit → Push → PR

## When to Share

**Share when:**
- Skill applies broadly (not project-specific)
- Pattern/technique others would benefit from
- Well-tested and documented
- Follows skills/meta/writing-skills guidelines

**Keep personal when:**
- Project-specific or organization-specific
- Experimental or unstable
- Contains sensitive information
- Too narrow/niche for general use

## Prerequisites

- `gh` CLI installed and authenticated
- Personal skill exists in `~/.config/superpowers/skills/your-skill/`
- Skill has been tested (see skills/meta/writing-skills for TDD process)

## Sharing Workflow

### 1. Fork Core Repository

```bash
# Check if you already have a fork
gh repo view YOUR_USERNAME/superpowers 2>/dev/null || gh repo fork obra/superpowers
```

### 2. Clone to Temporary Directory

```bash
# Create temp directory for contribution
temp_dir=$(mktemp -d)
cd "$temp_dir"
git clone git@github.com:YOUR_USERNAME/superpowers.git
cd superpowers
```

### 3. Sync with Upstream

```bash
# Add upstream if not already added
git remote add upstream https://github.com/obra/superpowers 2>/dev/null || true

# Fetch and merge latest from upstream
git fetch upstream
git checkout main
git merge upstream/main
git push origin main
```

### 4. Create Feature Branch

```bash
# Branch name: add-skillname-skill
skill_name="your-skill-name"
git checkout -b "add-${skill_name}-skill"
```

### 5. Copy Skill from Personal Repo

```bash
# Copy skill directory from personal superpowers
cp -r ~/.config/superpowers/skills/your-skill-name/ superpowers/skills/

# Verify it copied correctly
ls -la superpowers/skills/your-skill-name/
```

### 6. Commit Changes

```bash
# Add and commit
git add superpowers/skills/your-skill-name/
git commit -m "Add ${skill_name} skill

$(cat <<'EOF'
Brief description of what this skill does and why it's useful.

Tested with: [describe testing approach]
EOF
)"
```

### 7. Push to Your Fork

```bash
git push -u origin "add-${skill_name}-skill"
```

### 8. Create Pull Request

```bash
# Create PR using gh CLI
gh pr create \
  --repo obra/superpowers \
  --title "Add ${skill_name} skill" \
  --body "$(cat <<'EOF'
## Summary
Brief description of the skill and what problem it solves.

## Testing
Describe how you tested this skill (pressure scenarios, baseline tests, etc.).

## Context
Any additional context about why this skill is needed and how it should be used.
EOF
)"
```

### 9. Cleanup

```bash
# Remove temp directory after PR is created
cd ~
rm -rf "$temp_dir"
```

## Complete Example

Here's a complete example of sharing a personal skill called "async-patterns":

```bash
# 1. Fork if needed
gh repo view $(gh api user --jq .login)/superpowers 2>/dev/null || gh repo fork obra/superpowers

# 2-3. Clone and sync
temp_dir=$(mktemp -d) && cd "$temp_dir"
gh repo clone $(gh api user --jq .login)/superpowers
cd superpowers
git remote add upstream https://github.com/obra/superpowers 2>/dev/null || true
git fetch upstream
git checkout main
git merge upstream/main
git push origin main

# 4. Create branch
git checkout -b "add-async-patterns-skill"

# 5. Copy skill
cp -r ~/.config/superpowers/skills/async-patterns/ superpowers/skills/

# 6. Commit
git add superpowers/skills/async-patterns/
git commit -m "Add async-patterns skill

Patterns for handling asynchronous operations in tests and application code.

Tested with: Multiple pressure scenarios testing agent compliance."

# 7. Push
git push -u origin "add-async-patterns-skill"

# 8. Create PR
gh pr create \
  --repo obra/superpowers \
  --title "Add async-patterns skill" \
  --body "## Summary
Patterns for handling asynchronous operations correctly in tests and application code.

## Testing
Tested with multiple application scenarios. Agents successfully apply patterns to new code.

## Context
Addresses common async pitfalls like race conditions, improper error handling, and timing issues."

# 9. Cleanup
cd ~ && rm -rf "$temp_dir"
```

## After PR is Merged

Once your PR is merged:

**Option 1: Keep personal version**
- Useful if you want to continue iterating locally
- Your personal version will shadow the core version
- Can later delete personal version to use core

**Option 2: Delete personal version**
```bash
# Remove from personal repo to use core version
rm -rf ~/.config/superpowers/skills/your-skill-name/
cd ~/.config/superpowers
git add skills/your-skill-name/
git commit -m "Remove your-skill-name (now in core)"
git push
```

## Troubleshooting

**"gh: command not found"**
- Install GitHub CLI: https://cli.github.com/
- Authenticate: `gh auth login`

**"Permission denied (publickey)"**
- Check SSH keys: `gh auth status`
- Set up SSH: https://docs.github.com/en/authentication

**"Skill already exists in core"**
- You're creating a modified version
- Consider different skill name or shadow the core version in personal repo

**PR merge conflicts**
- Rebase on latest upstream: `git fetch upstream && git rebase upstream/main`
- Resolve conflicts
- Force push: `git push -f origin your-branch`

## Multi-Skill Contributions

**Do NOT batch multiple skills in one PR.**

Each skill should:
- Have its own feature branch
- Have its own PR
- Be independently reviewable

**Why?** Individual skills can be reviewed, iterated, and merged independently.

## Related Skills

- **skills/meta/writing-skills** - How to create well-tested skills
- **skills/meta/setting-up-personal-superpowers** - Initial setup of personal repo
