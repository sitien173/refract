#!/usr/bin/env bash
# Cross-platform hook dispatcher.
# Self-resolves script dir via $0 — works under Claude Code (${CLAUDE_PLUGIN_ROOT})
# and Antigravity CLI (${ANTIGRAVITY_PLUGIN_ROOT}) without depending on either var.
#
# Usage: run-hook.sh <script-name> [args...]

set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "run-hook.sh: missing script name" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_NAME="$1"
shift

exec "${SCRIPT_DIR}/${SCRIPT_NAME}" "$@"
