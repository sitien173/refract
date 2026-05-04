#!/usr/bin/env bash
# Test: skill structure guardrails for concise, discoverable SKILL.md entry points
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

export REPO_ROOT

echo "=== Test: skill structure guards ==="
echo ""

python <<'PY'
import os
import re
import sys
from pathlib import Path

repo = Path(os.environ["REPO_ROOT"])
skill_files = sorted((repo / "skills").glob("*/SKILL.md"))
failures: list[str] = []

name_re = re.compile(r"^[a-z0-9-]{1,64}$")
xml_re = re.compile(r"<[^>]+>")
first_or_second_person = re.compile(r"\b(I|I'm|I can|we can|you can use|you should use|use this to)\b", re.IGNORECASE)
windows_path_re = re.compile(r"[A-Za-z0-9_.-]+\\\\[A-Za-z0-9_.-]+")
local_md_link_re = re.compile(r"\[[^\]]+\]\((?!https?://)([^)]+\.md)\)")
required_sections = ("## Use When", "## Workflow", "## Hard Rules", "## References")
require_compact_contract = os.environ.get("REQUIRE_COMPACT_CONTRACT") == "1"

if not skill_files:
    failures.append("No skills/*/SKILL.md files found")

for path in skill_files:
    rel = path.relative_to(repo).as_posix()
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    if len(lines) > 120:
        failures.append(f"{rel}: exceeds 120-line SKILL.md budget ({len(lines)} lines)")

    if not lines or lines[0] != "---":
        failures.append(f"{rel}: missing opening YAML frontmatter fence")
        continue

    try:
        close_idx = lines[1:].index("---") + 1
    except ValueError:
        failures.append(f"{rel}: missing closing YAML frontmatter fence")
        continue

    frontmatter = "\n".join(lines[1:close_idx])
    name_match = re.search(r"^name:\s*['\"]?([^'\"\n]+)['\"]?\s*$", frontmatter, re.MULTILINE)
    description_match = re.search(r"^description:\s*['\"]?(.+?)['\"]?\s*$", frontmatter, re.MULTILINE)

    if not name_match:
        failures.append(f"{rel}: missing name frontmatter")
    else:
        name = name_match.group(1).strip()
        if not name_re.match(name):
            failures.append(f"{rel}: name must be lowercase letters, numbers, hyphens, max 64 chars")
        if "claude" in name or "anthropic" in name:
            failures.append(f"{rel}: name must not contain reserved words claude/anthropic")

    if not description_match:
        failures.append(f"{rel}: missing description frontmatter")
    else:
        description = description_match.group(1).strip()
        if not description:
            failures.append(f"{rel}: description must be non-empty")
        if len(description) > 1024:
            failures.append(f"{rel}: description exceeds 1024 characters")
        if xml_re.search(description):
            failures.append(f"{rel}: description must not contain XML tags")
        if first_or_second_person.search(description):
            failures.append(f"{rel}: description should be third person, not first/second person")

    if windows_path_re.search(text):
        failures.append(f"{rel}: contains Windows-style backslash path")

    compact_sections_present = [section for section in required_sections if section in text]
    adopted_compact_contract = any(section in text for section in required_sections[:3])
    if (require_compact_contract or adopted_compact_contract) and len(compact_sections_present) != len(required_sections):
        missing = ", ".join(section for section in required_sections if section not in text)
        failures.append(f"{rel}: compact contract missing {missing}")

    for link in local_md_link_re.findall(text):
        if "\\" in link:
            failures.append(f"{rel}: link uses Windows path separators: {link}")
        normalized = link.split("#", 1)[0]
        parts = [part for part in normalized.split("/") if part]
        allowed_direct = (
            len(parts) <= 2
            or (len(parts) == 3 and parts[0] == "skills")
            or (len(parts) == 2 and parts[0] in {"references", "examples"})
        )
        if not allowed_direct:
            failures.append(f"{rel}: local markdown link is deeper than one direct reference level: {link}")

if failures:
    print("  [FAIL] Skill structure guard violations:")
    for failure in failures:
        print(f"    - {failure}")
    sys.exit(1)

print("  [PASS] Frontmatter, line budget, path, and direct-reference guards passed")
print("  [PASS] Compact contract is enforced for skills that opt into Use When/Workflow/Hard Rules/References")
PY

echo ""
echo "=== Skill structure guard tests passed ==="
