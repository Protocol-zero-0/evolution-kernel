#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEMO_TARGET="$SCRIPT_DIR/demo-target"
LEDGER="/tmp/ek-demo-ledger"

echo "=== Setting up demo target repo (fresh) ==="
cd "$DEMO_TARGET"
rm -rf .git
git init
git config user.email "demo@example.com"
git config user.name "Demo User"
git add -A
git commit -m "initial"

echo "=== Resetting ledger ==="
rm -rf "$LEDGER"

echo "=== Running evolution ==="
cd "$REPO_ROOT"
python3 -m evolution_kernel.cli \
  --config "$SCRIPT_DIR/evolution.yml" \
  --repo "$DEMO_TARGET" \
  --ledger "$LEDGER" \
  --planner python3 "$REPO_ROOT/tests/fixtures/planner.py" \
  --executor python3 "$REPO_ROOT/tests/fixtures/executor.py" \
  --evaluator python3 "$REPO_ROOT/tests/fixtures/evaluator_accept.py" \
  --run-id 0001

echo ""
echo "=== Ledger run/0001 contents ==="
ls "$LEDGER/runs/0001/"

echo ""
echo "=== decision.json ==="
cat "$LEDGER/runs/0001/decision.json"

echo ""
echo "=== observation.json ==="
cat "$LEDGER/runs/0001/observation.json"

echo ""
echo "=== candidate_commit.txt ==="
cat "$LEDGER/runs/0001/candidate_commit.txt"

echo ""
echo "=== Demo complete ==="
