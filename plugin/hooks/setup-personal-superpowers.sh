#!/usr/bin/env bash
# Setup script for personal superpowers directory
# Creates personal superpowers directory with git repo for personal skills

set -euo pipefail

# Use PERSONAL_SUPERPOWERS_DIR if set, otherwise XDG_CONFIG_HOME/superpowers, otherwise ~/.config/superpowers
SUPERPOWERS_DIR="${PERSONAL_SUPERPOWERS_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/superpowers}"
SKILLS_DIR="${SUPERPOWERS_DIR}/skills"

# Check if already set up
if [[ -d "${SUPERPOWERS_DIR}/.git" ]] && [[ -d "${SKILLS_DIR}" ]]; then
    # Already set up, nothing to do
    exit 0
fi

# Create directory structure
mkdir -p "${SKILLS_DIR}"

# Create .gitignore
cat > "${SUPERPOWERS_DIR}/.gitignore" <<'EOF'
# Superpowers local data
search-log.jsonl
conversation-index/
conversation-archive/
EOF

# Create README
cat > "${SUPERPOWERS_DIR}/README.md" <<'EOF'
# My Personal Superpowers

Personal skills and techniques for Claude Code.

Learn more about Superpowers: https://github.com/obra/superpowers
EOF

# Initialize git repo if not already initialized
if [[ ! -d "${SUPERPOWERS_DIR}/.git" ]]; then
    cd "${SUPERPOWERS_DIR}"
    git init -q
    git add .gitignore README.md
    git commit -q -m "Initial commit: Personal superpowers setup"
fi

# Check for gh and recommend GitHub setup
if command -v gh &> /dev/null; then
    echo "github_cli_available=true"
else
    echo "github_cli_available=false"
fi

exit 0
