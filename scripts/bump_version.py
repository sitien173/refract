#!/usr/bin/env python3
"""Bump the Refract version in every target file and print release notes."""
import datetime
import re
import sys
from pathlib import Path

SOURCE = "server/pyproject.toml"
V = r"(?P<v>\d+\.\d+\.\d+)"
EOL = r"(?=\r?$)"
SHARED = rf"^<!-- refract-shared-version: {V} -->{EOL}"
JSON = rf'^\s*"version": "{V}"'

TARGETS = [
    (SOURCE, rf'^version = "{V}"{EOL}'),
    ("server/uv.lock", rf'^name = "refract"\r?\nversion = "{V}"{EOL}'),
    ("package.json", JSON),
    ("plugin/package.json", JSON),
    (".claude-plugin/marketplace.json", JSON),
    ("plugin/.claude-plugin/plugin.json", JSON),
    ("plugin/.codex-plugin/plugin.json", JSON),
    ("plugin/.antigravity-plugin/plugin.json", JSON),
    ("sonar-project.properties", rf"^sonar\.projectVersion={V}{EOL}"),
    ("README.md", rf"^# Refract {V}{EOL}"),
    ("server/README.md", rf"^Version {V} ·"),
    ("server/CLI_ARGUMENTS.md", rf"^Refract {V} ·"),
    ("plugin/shared/erp.md", SHARED),
    ("plugin/shared/journal-template.md", SHARED),
    ("plugin/shared/notes-template.md", SHARED),
    ("plugin/shared/worker-contract.md", SHARED),
]
CHANGELOG = "CHANGELOG.md"
UNRELEASED = re.compile(r"^## Unreleased(?=\r?$)", re.M)


def _read(path: Path) -> str:
    with path.open(encoding="utf-8", newline="") as handle:
        return handle.read()


def _write(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def _bump(version: str, part: str) -> str:
    major, minor, patch = (int(x) for x in version.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def _plan_bump(root: Path, part: str, today: str):
    """Return (new_version, edits, errors). edits is a list of (rel, new_text, description)."""
    errors = []
    texts = {}
    for rel in [t[0] for t in TARGETS] + [CHANGELOG]:
        try:
            texts[rel] = _read(root / rel)
        except OSError as exc:
            errors.append(f"{rel}: cannot read ({exc.strerror})")
    if errors:
        return None, [], errors

    source = re.search(TARGETS[0][1], texts[SOURCE], re.M)
    if not source:
        return None, [], [f"{SOURCE}: version line not found"]
    current = source.group("v")
    new = _bump(current, part)

    edits = []
    for rel, pattern in TARGETS:
        matches = list(re.finditer(pattern, texts[rel], re.M))
        if len(matches) != 1:
            errors.append(f"{rel}: expected exactly one version match, found {len(matches)}")
        elif matches[0].group("v") != current:
            errors.append(f"{rel}: holds {matches[0].group('v')}, expected {current}")
        else:
            text = texts[rel]
            start, end = matches[0].span("v")
            edits.append((rel, text[:start] + new + text[end:], f"{current} -> {new}"))

    changelog = texts[CHANGELOG]
    headings = list(UNRELEASED.finditer(changelog))
    if len(headings) != 1:
        errors.append(f"{CHANGELOG}: expected exactly one '## Unreleased' line, found {len(headings)}")
    else:
        body = re.split(r"^## ", changelog[headings[0].end():], maxsplit=1, flags=re.M)[0]
        if not body.strip():
            errors.append(f"{CHANGELOG}: '## Unreleased' has no entries")
        else:
            nl = "\r\n" if changelog[headings[0].end():].startswith("\r\n") else "\n"
            start = headings[0].start()
            text = changelog[:start] + f"## Unreleased{nl}{nl}## {new} - {today}" + changelog[headings[0].end():]
            edits.append((CHANGELOG, text, f"## Unreleased -> ## {new} - {today}"))
    return new, edits, errors


def _bump_command(root: Path, part: str, dry_run: bool, today: str) -> int:
    new, edits, errors = _plan_bump(root, part, today)
    if errors:
        for message in errors:
            print(message, file=sys.stderr)
        return 1
    for rel, text, description in edits:
        if not dry_run:
            _write(root / rel, text)
        print(f"{rel}: {description}")
    print(new)
    return 0


def _notes_command(root: Path, version: str) -> int:
    try:
        changelog = _read(root / CHANGELOG)
    except OSError as exc:
        print(f"{CHANGELOG}: cannot read ({exc.strerror})", file=sys.stderr)
        return 1
    heading = re.search(rf"^## {re.escape(version)} - \S[^\r\n]*(?=\r?$)", changelog, re.M)
    if not heading:
        print(f"{CHANGELOG}: no section for version {version}", file=sys.stderr)
        return 1
    body = re.split(r"^## ", changelog[heading.end():], maxsplit=1, flags=re.M)[0].strip()
    if not body:
        print(f"{CHANGELOG}: section {version} is empty", file=sys.stderr)
        return 1
    print(body)
    return 0


def main(argv, root=None, today=None) -> int:
    root = Path(root) if root is not None else Path(__file__).resolve().parent.parent
    args = list(argv)
    if len(args) == 2 and args[0] == "notes":
        return _notes_command(root, args[1])
    dry_run = "--dry-run" in args
    rest = [a for a in args if a != "--dry-run"]
    if len(rest) != 1 or rest[0] not in ("patch", "minor", "major"):
        print("usage: bump_version.py <patch|minor|major> [--dry-run] | notes <version>", file=sys.stderr)
        return 2
    today = today or datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    return _bump_command(root, rest[0], dry_run, today)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
