#!/usr/bin/env bash
set -euo pipefail

repo=/home/nytr/nssmitty
cd "$repo"

./test.sh
./check.sh
git diff --check

if [[ "${1:-}" != "--pre-marker" && ! -s .antigravity-complete ]]; then
    echo "completion marker is missing or empty" >&2
    exit 1
fi

if [[ -n "$(git status --porcelain --untracked-files=all)" ]]; then
    echo "working tree is not clean" >&2
    git status --short >&2
    exit 1
fi

echo "completion verification passed"
