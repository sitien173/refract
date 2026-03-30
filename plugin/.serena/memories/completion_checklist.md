# Completion Checklist

When a task is complete in superpowers-ccg:

## For Skill Changes
1. [ ] Failing test written BEFORE implementation (`./tests/claude-code/run-skill-tests.sh --test <test>.sh`)
2. [ ] Test passes after implementation
3. [ ] All fast tests still pass (`./tests/claude-code/run-skill-tests.sh`)
4. [ ] Skill frontmatter `name` and `description` are accurate
5. [ ] `superpowers-cccg.md` updated if skill reference tables changed

## For Any Change
1. [ ] Run fast tests: `./tests/claude-code/run-skill-tests.sh`
2. [ ] Verify output manually (evidence, not assumptions)
3. [ ] Commit with descriptive message (`type: description`)

## Iron Laws — Never Skip
- No production/skill code without a failing test first
- No completion claims without running verification and reading output
- No fixes without root cause investigation first
