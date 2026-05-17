#!/usr/bin/env bash
# Bootstraps the v1.1 quickstart target.
#
#   1. Initialize a fresh git repo at $1 (default /tmp/ek-quickstart-target)
#   2. Copy target/ contents (src + bots + pyproject) in and commit on the
#      target's first commit, so the role scripts and lint config are
#      reachable inside every experiment worktree.
#
# After running this script:
#
#   evolution-kernel \
#     --config examples/quickstart/evolution.yml \
#     --repo /tmp/ek-quickstart-target \
#     --ledger /tmp/ek-quickstart-ledger \
#     --loop
#
set -euo pipefail
cd "$(dirname "$0")"

TARGET="${1:-/tmp/ek-quickstart-target}"

rm -rf "$TARGET"
mkdir -p "$TARGET"
cp -r target/. "$TARGET/"
echo "# evolution-kernel · v1.1 quickstart target" > "$TARGET/README.md"

cd "$TARGET"
git init -q -b main
git -c user.email=demo@example.com -c user.name=demo add -A
git -c user.email=demo@example.com -c user.name=demo commit -q -m "quickstart target initial commit"

echo "quickstart target ready at: $TARGET"
echo ""
echo "next:"
echo "  evolution-kernel \\"
echo "    --config examples/quickstart/evolution.yml \\"
echo "    --repo $TARGET \\"
echo "    --ledger /tmp/ek-quickstart-ledger \\"
echo "    --loop"
