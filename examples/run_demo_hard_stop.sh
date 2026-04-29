#!/usr/bin/env bash
# Demonstrates hard stop behavior:
#   - Uses evaluator_reject so every run fails
#   - max_consecutive_failures: 2 means the 3rd attempt is blocked
#   - Then resets and shows the run is allowed again
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEMO_TARGET="$SCRIPT_DIR/demo-target"
LEDGER="/tmp/ek-hardstop-ledger"

_setup_repo() {
  cd "$DEMO_TARGET"
  rm -rf .git
  git init
  git config user.email "demo@example.com"
  git config user.name "Demo User"
  git add -A
  git commit -m "initial"
  cd "$REPO_ROOT"
}

_run() {
  local run_id="$1"
  echo ""
  echo "--- Run $run_id ---"
  python3 -m evolution_kernel.cli \
    --config "$SCRIPT_DIR/evolution.yml" \
    --repo "$DEMO_TARGET" \
    --ledger "$LEDGER" \
    --planner   python3 "$REPO_ROOT/tests/fixtures/planner.py" \
    --executor  python3 "$REPO_ROOT/tests/fixtures/executor.py" \
    --evaluator python3 "$REPO_ROOT/tests/fixtures/evaluator_reject.py" \
    --run-id "$run_id" && true
  echo "state.json: $(cat $LEDGER/state.json)"
}

echo "=== Hard Stop Demo ==="
echo "Config: max_consecutive_failures=2"
echo "All runs use evaluator_reject — every run will be rejected."
echo ""

echo "=== Resetting ledger ==="
rm -rf "$LEDGER"

echo ""
echo ">>> Run 1: expect rejected (consecutive_failures=1)"
_setup_repo
_run 0001

echo ""
echo ">>> Run 2: expect rejected (consecutive_failures=2)"
_setup_repo
_run 0002

echo ""
echo ">>> Run 3: expect BLOCKED by hard stop"
_setup_repo
python3 -m evolution_kernel.cli \
  --config "$SCRIPT_DIR/evolution.yml" \
  --repo "$DEMO_TARGET" \
  --ledger "$LEDGER" \
  --planner   python3 "$REPO_ROOT/tests/fixtures/planner.py" \
  --executor  python3 "$REPO_ROOT/tests/fixtures/executor.py" \
  --evaluator python3 "$REPO_ROOT/tests/fixtures/evaluator_reject.py" \
  --run-id 0003 2>&1 || echo "^^^ Hard stop triggered as expected"

echo ""
echo ">>> Resetting hard stop state..."
python3 -m evolution_kernel.cli --reset --ledger "$LEDGER"
echo "state.json after reset: $(cat $LEDGER/state.json)"

echo ""
echo ">>> Run 4: after reset, use evaluator_accept — expect accepted"
_setup_repo
python3 -m evolution_kernel.cli \
  --config "$SCRIPT_DIR/evolution.yml" \
  --repo "$DEMO_TARGET" \
  --ledger "$LEDGER" \
  --planner   python3 "$REPO_ROOT/tests/fixtures/planner.py" \
  --executor  python3 "$REPO_ROOT/tests/fixtures/executor.py" \
  --evaluator python3 "$REPO_ROOT/tests/fixtures/evaluator_accept.py" \
  --run-id 0004
echo "state.json: $(cat $LEDGER/state.json)"

echo ""
echo "=== Hard Stop Demo complete ==="
