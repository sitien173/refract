# Completion Checklist
- For doc/workflow changes, verify consistency with `rg` across README, CLAUDE.md, `superpowers-ccg.md`, and affected `skills/` files.
- For code or workflow changes that touch behavior, run the relevant `tests/claude-code/run-skill-tests.sh` command when feasible.
- Review `git diff` for only the intended files before finalizing.
- Do not overwrite unrelated workspace changes; this repo may already be dirty when work starts.