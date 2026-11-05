#!/usr/bin/env python3
"""SessionStart hook for refract plugin."""

import json
import os
import sys

plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

COMPACT_CONTEXT = f"""
You are Coordinator. Follow the workflow described by the skills below.

Load refract:using-refract skill, your introduction to using skills.
Read refract:coordinating-multi-model-work skill before any Plan, Execute,
or Review action on coordinated work. Route external workers only when that
skill requires them. Prefer guidance returned by mcp__plugin_refract_refract__list.
User instructions override the workflow.

Bundled worker contracts:
- {plugin_root}/shared/worker-contract.md
- {plugin_root}/shared/erp.md
- {plugin_root}/shared/notes-template.md
- {plugin_root}/shared/journal-template.md"""


def wrap(context):
    return f"<EXTREMELY_IMPORTANT>\n{context}\n</EXTREMELY_IMPORTANT>"


if sys.argv[1:2] == ["--antigravity"]:
    plugin_repo_root = os.path.dirname(plugin_root)
    antigravity_context = (
        f"{COMPACT_CONTEXT}\n\n"
        f"When {plugin_root} is available in your workspace context, treat it as your own plugin directory "
        f"and reference {plugin_root} only to invoke plugin skills and read bundled contracts. "
        f"Do not treat {plugin_repo_root} or {plugin_root} as a project to work on."
    )
    payload = {"injectSteps": [{"systemMessage": {"systemMessage": wrap(antigravity_context)}}]}
else:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": wrap(COMPACT_CONTEXT),
        }
    }

print(json.dumps(payload, indent=2))
