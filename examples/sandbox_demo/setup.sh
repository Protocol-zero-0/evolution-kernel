#!/usr/bin/env bash
# Bootstraps the PR7a sandbox demo:
#
#   1. Initialize a fresh git repo at $1 (default /tmp/sandbox-demo-target)
#   2. Copy bots/ into it and commit them on the demo target's first commit
#      so the role scripts are reachable inside every experiment worktree.
#
# After running this script you can launch the demo with:
#
#   evolution-kernel \
#     --config examples/sandbox_demo/evolution.yml \
#     --repo /tmp/sandbox-demo-target \
#     --ledger /tmp/sandbox-demo-ledger
#
set -euo pipefail
cd "$(dirname "$0")"

TARGET="${1:-/tmp/sandbox-demo-target}"

rm -rf "$TARGET"
mkdir -p "$TARGET"
cp -r target/bots "$TARGET/bots"
echo "# evolution-kernel · PR7a sandbox demo target" > "$TARGET/README.md"

cd "$TARGET"
git init -q
git -c user.email=demo@example.com -c user.name=demo add -A
git -c user.email=demo@example.com -c user.name=demo commit -q -m "demo target initial commit"

echo "demo target ready at: $TARGET"
echo "next:"
echo "  evolution-kernel --config examples/sandbox_demo/evolution.yml --repo $TARGET --ledger /tmp/sandbox-demo-ledger"
