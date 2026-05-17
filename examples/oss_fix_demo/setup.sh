#!/usr/bin/env bash
# Bootstraps the v1.1 oss_fix_demo target.
#
#   1. Clone python-slugify v8.0.4 (1,106 LoC, MIT, no network deps at
#      runtime) into $1 (default /tmp/ek-oss-fix-target).
#   2. Copy local-deterministic bots/ into it and commit on the target's
#      first commit so the role scripts are reachable inside every
#      experiment worktree.
#
# Prereqs:
#   - `claude` CLI installed and signed in to a Claude Pro/Max account
#   - `ruff` installed (`pip install ruff`)
#
# After running this script:
#
#   evolution-kernel \
#     --config examples/oss_fix_demo/evolution.yml \
#     --repo /tmp/ek-oss-fix-target \
#     --ledger /tmp/ek-oss-fix-ledger \
#     --loop
#
set -euo pipefail
cd "$(dirname "$0")"

TARGET="${1:-/tmp/ek-oss-fix-target}"
SLUGIFY_TAG="v8.0.4"

rm -rf "$TARGET"
git clone --depth 1 --branch "$SLUGIFY_TAG" https://github.com/un33k/python-slugify.git "$TARGET"

# Drop the upstream .git so we start from a clean evolution-owned history.
rm -rf "$TARGET/.git"

cp -r bots "$TARGET/bots"

# python-slugify uses `from .special import *` / `from .slugify import *`
# as its public-API pattern. Ruff flags these as F403, but they are
# load-bearing: removing the star imports would break the package's
# documented surface. Pin the lint config to ignore F403 only.
cat > "$TARGET/pyproject.toml" <<'EOF'
# Added by examples/oss_fix_demo/setup.sh — pins ruff rules for the demo.
[tool.ruff]
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "W"]
ignore = ["F403"]   # star-imports are slugify's public-API pattern
EOF

cd "$TARGET"
git init -q -b main
git -c user.email=demo@example.com -c user.name=demo add -A
git -c user.email=demo@example.com -c user.name=demo commit -q -m "oss_fix_demo target: python-slugify ${SLUGIFY_TAG} + bots"

echo "oss_fix_demo target ready at: $TARGET"
echo ""
echo "next:"
echo "  evolution-kernel \\"
echo "    --config examples/oss_fix_demo/evolution.yml \\"
echo "    --repo $TARGET \\"
echo "    --ledger /tmp/ek-oss-fix-ledger \\"
echo "    --loop"
