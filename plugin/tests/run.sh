#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"${repo_root}/tests/test-session-start.sh"
"${repo_root}/tests/test-contracts.sh"

if command -v claude >/dev/null 2>&1; then
    claude plugin validate "$repo_root"
fi
