---
name: Setting Up Personal Superpowers
description: Automatic setup of ~/.config/superpowers/ for personal skills, optional GitHub repo creation
when_to_use: Runs automatically on first session. Reference when helping users with personal skills setup.
version: 1.0.0
languages: bash
---

# Setting Up Personal Superpowers

## Overview

Personal superpowers directory is automatically set up on your first session. It provides a place to create and manage your own skills alongside the core superpowers library.

**Default location:** `~/.config/superpowers/`

**Customizable via:**
- `PERSONAL_SUPERPOWERS_DIR` environment variable (highest priority)
- `XDG_CONFIG_HOME` environment variable (if set, uses `$XDG_CONFIG_HOME/superpowers`)
- Falls back to `~/.config/superpowers`

**Structure:**
```
~/.config/superpowers/
  ├── .git/                # Git repository
  ├── .gitignore           # Ignores logs and indexes
  ├── README.md            # About your personal superpowers
  ├── skills/              # Your personal skills
  │   └── your-skill/
  │       └── SKILL.md
  ├── search-log.jsonl     # Skill search history (not tracked)
  └── conversation-index/  # Conversation search index (not tracked)
```

## How It Works

The SessionStart hook runs `hooks/setup-personal-superpowers.sh` which:

1. Checks if `~/.config/superpowers/.git/` and `~/.config/superpowers/skills/` exist
2. If not, creates directory structure
3. Initializes git repository
4. Creates `.gitignore`, `README.md`
5. Makes initial commit
6. Checks for `gh` CLI availability

If GitHub CLI is available and no remote exists, you'll see a recommendation to create a public GitHub repo.

## Creating GitHub Repository

When prompted, you can create a public `personal-superpowers` repo:

```bash
cd ~/.config/superpowers
gh repo create personal-superpowers --public --source=. --push
gh repo edit --add-topic superpowers
```

**Why public?** Superpowers are best when everyone can learn from them!

**Privacy:** If you prefer private or local-only:
- **Private:** Use `--private` instead of `--public`
- **Local-only:** Just use the local git repo without pushing to GitHub

## What Gets Tracked

**.gitignore includes:**
- `search-log.jsonl` - Your skill search history
- `conversation-index/` - Conversation search index
- `conversation-archive/` - Archived conversations

**Everything else is tracked**, including:
- Your personal skills in `skills/`
- README.md
- Any additional documentation you add

## Personal vs Core Skills

**Search order:**
1. `~/.config/superpowers/skills/` (personal)
2. `${CLAUDE_PLUGIN_ROOT}/skills/` (core)

**Personal skills shadow core skills** - if you have `~/.config/superpowers/skills/testing/test-driven-development/SKILL.md`, it will be used instead of the core version.

The `find-skills` tool automatically searches both locations with deduplication.

## Writing Skills

See skills/meta/writing-skills for how to create new skills.

All personal skills are written to `~/.config/superpowers/skills/`.

## Sharing Skills

See skills/meta/sharing-skills for how to contribute skills back to the core superpowers repository.

## Custom Location

To use a different location for your personal superpowers:

```bash
# In your shell rc file (.bashrc, .zshrc, etc)
export PERSONAL_SUPERPOWERS_DIR="$HOME/my-superpowers"

# Or use XDG_CONFIG_HOME
export XDG_CONFIG_HOME="$HOME/.local/config"  # Will use $HOME/.local/config/superpowers
```

## Manual Setup

If auto-setup fails or you need to set up manually:

```bash
# Use your preferred location
SUPERPOWERS_DIR="${PERSONAL_SUPERPOWERS_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/superpowers}"
mkdir -p "$SUPERPOWERS_DIR/skills"
cd "$SUPERPOWERS_DIR"
git init
cat > .gitignore <<'EOF'
search-log.jsonl
conversation-index/
conversation-archive/
EOF

cat > README.md <<'EOF'
# My Personal Superpowers

Personal skills and techniques for Claude Code.

Learn more about Superpowers: https://github.com/obra/superpowers
EOF

git add .gitignore README.md
git commit -m "Initial commit: Personal superpowers setup"

# Optional: Create GitHub repo
gh repo create personal-superpowers --public --source=. --push
gh repo edit --add-topic superpowers
```

## Troubleshooting

**Setup failed during SessionStart:**
File a bug at https://github.com/obra/superpowers/issues

**Personal skills not being found:**
- Check `~/.config/superpowers/skills/` exists
- Verify skill has `SKILL.md` file
- Run `${CLAUDE_PLUGIN_ROOT}/scripts/find-skills` to see if it appears

**GitHub push failed:**
- Check `gh auth status`
- Verify repo was created: `gh repo view personal-superpowers`
- Try manual push: `cd ~/.config/superpowers && git push -u origin main`

## Multi-CLI Support

The personal superpowers directory is CLI-agnostic. It works with:
- Claude Code (current)
- OpenAI Codex CLI (future)
- Gemini CLI (future)

Each CLI installs its own base superpowers, but they all read from the same `~/.config/superpowers/skills/` for personal skills.
