#!/usr/bin/env bash
set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Validate we're running from clank repository root
validate_clank_repo() {
  if [[ ! -d "skills/meta/installing-skills" ]]; then
    echo -e "${RED}Error: Not running from clank repository root${NC}"
    echo ""
    echo "Expected to be run from ~/.clank/clank/"
    echo ""
    echo "To install clank, clone to ~/.clank first:"
    echo "  ${GREEN}mkdir -p ~/.clank && cd ~/.clank${NC}"
    echo "  ${GREEN}gh repo fork obra/clank --clone${NC}"
    echo "  ${GREEN}cd clank${NC}"
    echo "  ${GREEN}./skills/meta/installing-skills/install.sh${NC}"
    exit 1
  fi
}

# Get absolute path to clank repo
get_repo_path() {
  if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS doesn't have realpath by default, use Python
    python3 -c "import os; print(os.path.realpath('.'))"
  else
    realpath .
  fi
}

# Backup existing skills directory if it exists
backup_existing_skills() {
  local skills_dir="$HOME/.claude/skills"

  if [[ -e "$skills_dir" ]]; then
    local timestamp=$(date +%Y-%m-%d-%H%M%S)
    local backup_path="${skills_dir}.backup.${timestamp}"

    echo -e "${YELLOW}Found existing ~/.claude/skills${NC}"
    echo -e "Backing up to: ${backup_path}"

    mv "$skills_dir" "$backup_path"
    echo -e "${GREEN}✓${NC} Backup created"
    echo ""
  fi
}

# No need to backup commands - we symlink individual files

# Create skills symlink
create_symlink() {
  local repo_path="$1"
  local skills_source="${repo_path}/skills"
  local skills_target="$HOME/.claude/skills"

  # Ensure ~/.claude directory exists
  mkdir -p "$HOME/.claude"

  echo "Creating skills symlink:"
  echo "  ${skills_target} → ${skills_source}"

  ln -s "$skills_source" "$skills_target"
  echo -e "${GREEN}✓${NC} Skills symlink created"
  echo ""
}

# Symlink individual commands
symlink_commands() {
  local repo_path="$1"
  local commands_source="${repo_path}/commands"
  local commands_target="$HOME/.claude/commands"

  # Check if commands directory exists in repo
  if [[ ! -d "$commands_source" ]]; then
    echo -e "${YELLOW}No commands directory in repo, skipping${NC}"
    echo ""
    return
  fi

  # Ensure ~/.claude/commands exists
  mkdir -p "$commands_target"

  echo "Symlinking commands:"

  # Symlink each command file
  for cmd in "$commands_source"/*.md; do
    if [[ -f "$cmd" && "$(basename "$cmd")" != "README.md" ]]; then
      cmd_name=$(basename "$cmd")
      ln -sf "$cmd" "$commands_target/$cmd_name"
      echo "  ${cmd_name}"
    fi
  done

  echo -e "${GREEN}✓${NC} Commands symlinked"
  echo ""
}

# Verify tools exist
verify_tools() {
  local skills_dir="$HOME/.claude/skills"
  local skills_search="${skills_dir}/getting-started/skills-search"

  if [[ -x "$skills_search" ]]; then
    echo -e "${GREEN}✓${NC} skills-search tool available"
    echo ""
  fi
}

# Verify installation
verify_installation() {
  local skills_dir="$HOME/.claude/skills"
  local commands_dir="$HOME/.claude/commands"

  echo "Verifying installation..."

  # Verify skills
  if [[ ! -L "$skills_dir" ]]; then
    echo -e "${RED}✗${NC} ~/.claude/skills is not a symlink"
    exit 1
  fi

  if [[ ! -f "$skills_dir/INDEX.md" ]]; then
    echo -e "${RED}✗${NC} INDEX.md not found in ~/.claude/skills"
    exit 1
  fi

  echo -e "${GREEN}✓${NC} Skills verified"

  # Verify commands were symlinked
  if [[ -d "$commands_dir" ]]; then
    cmd_count=$(find "$commands_dir" -type l -name "*.md" 2>/dev/null | wc -l)
    if [[ $cmd_count -gt 0 ]]; then
      echo -e "${GREEN}✓${NC} Commands verified ($cmd_count symlinked)"
    fi
  fi

  echo ""
}

# Print success message
print_success() {
  local repo_path="$1"

  echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${GREEN}Installation complete!${NC}"
  echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo ""
  echo -e "${YELLOW}NEXT STEP: Update ~/.claude/CLAUDE.md${NC}"
  echo ""
  echo "Add this to your CLAUDE.md:"
  echo ""
  cat "${repo_path}/skills/meta/installing-skills/CLAUDE_MD_PREAMBLE.md"
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  echo "Verify installation:"
  echo "  ${GREEN}ls -la ~/.claude/skills${NC}"
  echo "  ${GREEN}ls ~/.claude/commands/${NC}"
  echo "  ${GREEN}~/.claude/skills/getting-started/skills-search 'test.*driven'${NC}"
  echo ""
  echo "Repository location: ${repo_path}"
  echo ""
}

# Main installation flow
main() {
  echo ""
  echo "Clank Installation"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""

  validate_clank_repo

  local repo_path=$(get_repo_path)
  echo "Repository path: ${repo_path}"
  echo ""

  backup_existing_skills
  create_symlink "$repo_path"
  symlink_commands "$repo_path"
  verify_tools "$repo_path"
  verify_installation
  print_success "$repo_path"
}

main "$@"
