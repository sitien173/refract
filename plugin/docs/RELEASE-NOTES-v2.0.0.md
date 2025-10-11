# Superpowers v2.0.0 Release Notes

## Breaking Changes

This is a **major architectural change** that separates skills from the plugin into a standalone repository.

### What Changed

**Skills Repository Separation:**
- All skills and scripts have been extracted to a new repository: [obra/superpowers-skills](https://github.com/obra/superpowers-skills)
- The plugin is now a minimal shim that clones and manages the skills repository
- Skills are installed to `~/.config/superpowers/skills/` instead of being bundled with the plugin
- Users can now fork the skills repository and contribute improvements back to the community

**Environment Variable Change:**
- `CLAUDE_PLUGIN_ROOT` has been replaced with `SUPERPOWERS_SKILLS_ROOT`
- **Action Required:** If you have any custom skills or scripts that reference `${CLAUDE_PLUGIN_ROOT}`, you must update them to use `${SUPERPOWERS_SKILLS_ROOT}`

## Migration

**Automatic Migration:**
The plugin automatically handles migration from previous installations:
- On first run with v2.0.0, the initialization script detects old installations
- Your old `.git` directory is backed up to `.git.bak`
- Your old `skills/` directory is backed up to `skills.bak` (in case you have custom modifications)
- The new skills repository is cloned to `~/.config/superpowers/skills/`

**What You Need To Do:**
1. Update the plugin to v2.0.0
2. Start a new Claude Code session - the migration happens automatically
3. If you had custom skills in the old location, you'll find them in `~/.config/superpowers/skills.bak`
4. Move any custom skills to the new skills repository structure

## Fork Workflow

The new architecture enables a community-driven workflow for skill development:

### Contributing Skills

1. **During Initial Setup:**
   - If you have GitHub CLI (`gh`) installed, you'll be prompted to fork the skills repository
   - Forking allows you to push changes and submit pull requests

2. **Making Contributions:**
   ```bash
   cd ~/.config/superpowers/skills
   # Make your changes to skills
   git add .
   git commit -m "Describe your changes"
   git push origin main  # Push to your fork
   # Create PR via GitHub web UI or gh CLI
   ```

3. **Syncing Upstream:**
   - The plugin checks for upstream updates on each session start
   - When updates are available, you'll see: "⚠️ New skills available from upstream"
   - Use the `pulling-updates-from-skills-repository` skill to sync your local repository

### If You Didn't Fork Initially

You can fork the repository manually later:
```bash
cd ~/.config/superpowers/skills
gh repo fork obra/superpowers-skills --remote=true
git remote add upstream https://github.com/obra/superpowers-skills.git
```

## New Skills

**pulling-updates-from-skills-repository:**
- Syncs your local skills repository with upstream changes
- Handles stashing/unstashing of uncommitted work
- Helps resolve merge conflicts
- Preserves your local modifications

## Installation

### New Installation
1. Install the superpowers plugin v2.0.0
2. Start a Claude Code session
3. The skills repository is automatically cloned to `~/.config/superpowers/skills/`
4. Optionally fork the repository when prompted (requires GitHub CLI)

### Updating From Previous Version
1. Update the plugin to v2.0.0
2. Start a Claude Code session - migration happens automatically
3. Check `~/.config/superpowers/skills.bak` for any custom skills you had
4. Migrate custom skills to the new repository structure

## Architecture Details

**Plugin Responsibilities:**
- Clone the skills repository on first run
- Check for upstream updates on session start
- Set the `SUPERPOWERS_SKILLS_ROOT` environment variable
- Register hooks that load skills from the local repository
- Notify users when upstream updates are available

**Skills Repository Responsibilities:**
- Contain all skills, scripts, and documentation
- Accept community contributions via pull requests
- Maintain independent versioning
- Enable users to customize and extend skills locally

**Benefits:**
- Skills can be updated independently of the plugin
- Community can contribute skills without plugin repository access
- Users can experiment with skills in a standard git workflow
- Easier to maintain and version control skills separately
- Clear separation of concerns between plugin infrastructure and skill content

## File Structure Changes

**Old Structure (bundled with plugin):**
```
superpowers/
├── skills/
│   ├── getting-started/
│   └── ...
└── scripts/
    ├── find-skills
    └── skill-run
```

**New Structure (separate repository):**
```
~/.config/superpowers/skills/  (cloned from obra/superpowers-skills)
└── skills/
    ├── using-skills/
    │   ├── find-skills
    │   ├── skill-run
    │   └── SKILL.md
    ├── meta/
    │   └── pulling-updates-from-skills-repository/
    └── ...
```

## Troubleshooting

**Skills repository not cloning:**
- Check your internet connection
- Verify Git is installed and accessible
- Try cloning manually: `git clone https://github.com/obra/superpowers-skills.git ~/.config/superpowers/skills`

**Custom skills not working:**
- Update path references from `${CLAUDE_PLUGIN_ROOT}` to `${SUPERPOWERS_SKILLS_ROOT}`
- Ensure scripts are executable: `chmod +x your-script.sh`
- Check that skills are in the correct directory structure

**Merge conflicts when updating:**
- Use the `pulling-updates-from-skills-repository` skill - it helps resolve conflicts
- Or manually resolve: `cd ~/.config/superpowers/skills && git status`

**Fork not created:**
- Install GitHub CLI: `brew install gh` (macOS) or see [GitHub CLI installation](https://cli.github.com/)
- Authenticate: `gh auth login`
- Fork manually: `gh repo fork obra/superpowers-skills --remote=true`

## Links

- **Skills Repository:** https://github.com/obra/superpowers-skills
- **Plugin Repository:** https://github.com/obra/superpowers
- **Skills Repository v1.0.0:** https://github.com/obra/superpowers-skills/releases/tag/v1.0.0
- **Report Issues:** https://github.com/obra/superpowers/issues

## Credits

This architectural change enables the superpowers community to collaboratively improve and extend skills. Thank you to all future contributors!

---

**For Plugin Developers:**

If you're building tools that interact with superpowers:
- Use `SUPERPOWERS_SKILLS_ROOT` environment variable to locate skills
- Default location: `~/.config/superpowers/skills/`
- Skills repository: https://github.com/obra/superpowers-skills
- Tool paths:
  - find-skills: `${SUPERPOWERS_SKILLS_ROOT}/skills/using-skills/find-skills`
  - skill-run: `${SUPERPOWERS_SKILLS_ROOT}/skills/using-skills/skill-run`
