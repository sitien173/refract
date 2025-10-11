#!/usr/bin/env bash
set -euo pipefail

SKILLS_DIR="${HOME}/.config/superpowers/skills"
SKILLS_REPO="https://github.com/obra/superpowers-skills.git"

# Check if skills directory exists and is a valid git repo
if [ -d "$SKILLS_DIR/.git" ]; then
    cd "$SKILLS_DIR"

    # Fetch upstream
    git fetch upstream 2>/dev/null || git fetch origin 2>/dev/null || true

    # Check if behind upstream
    LOCAL=$(git rev-parse @ 2>/dev/null || echo "")
    REMOTE=$(git rev-parse @{u} 2>/dev/null || echo "")

    if [ -n "$LOCAL" ] && [ -n "$REMOTE" ] && [ "$LOCAL" != "$REMOTE" ]; then
        echo "⚠️ New skills available from upstream. Ask me to use the updating-skills skill."
    fi

    exit 0
fi

# Skills directory doesn't exist or isn't a git repo - initialize it
echo "Initializing skills repository..."

# Handle migration from old installation
if [ -d "${HOME}/.config/superpowers/.git" ]; then
    echo "Found existing installation. Backing up..."
    mv "${HOME}/.config/superpowers/.git" "${HOME}/.config/superpowers/.git.bak"

    if [ -d "${HOME}/.config/superpowers/skills" ]; then
        mv "${HOME}/.config/superpowers/skills" "${HOME}/.config/superpowers/skills.bak"
        echo "Your old skills are in ~/.config/superpowers/skills.bak"
    fi
fi

# Clone the skills repository
mkdir -p "${HOME}/.config/superpowers"
git clone "$SKILLS_REPO" "$SKILLS_DIR"

cd "$SKILLS_DIR"

# Offer to fork if gh is installed
if command -v gh &> /dev/null; then
    echo ""
    echo "GitHub CLI detected. Would you like to fork superpowers-skills?"
    echo "Forking allows you to share skill improvements with the community."
    echo ""
    read -p "Fork superpowers-skills? (y/N): " -n 1 -r
    echo

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        gh repo fork obra/superpowers-skills --remote=true
        git remote add upstream "$SKILLS_REPO"
        echo "Forked! You can now contribute skills back to the community."
    else
        git remote add upstream "$SKILLS_REPO"
    fi
else
    # No gh, just set up upstream remote
    git remote add upstream "$SKILLS_REPO"
fi

echo "Skills repository initialized at $SKILLS_DIR"
