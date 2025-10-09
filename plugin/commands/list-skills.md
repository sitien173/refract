---
description: List all available skills by name
---

Run this command to see what skills exist:

```bash
find ${CLAUDE_PLUGIN_ROOT}/skills -name "SKILL.md" -type f | sed 's|.*/skills/||; s|/SKILL.md||' | sort
```

This shows skill paths like `testing/test-driven-development` without loading descriptions.

Use skills-search when you need to find something specific.
