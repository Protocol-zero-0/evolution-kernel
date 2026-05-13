"""Evaluator fixture that reads the per-branch fitness hint set by the executor.

The hint is the float written into EVOLUTION_MARKER.txt by executor_branch.py.
hard_gates_passed = (fitness > 0), so tests can mark a branch as "failing gates"
by setting EK_TEST_FITNESS_<run_id>=0.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("--input", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--worktree", required=True)
args = parser.parse_args()

marker = Path(args.worktree) / "EVOLUTION_MARKER.txt"
fitness = 0.0
if marker.exists():
    line = marker.read_text(encoding="utf-8").strip()
    if line.startswith("fitness="):
        try:
            fitness = float(line.split("=", 1)[1])
        except ValueError:
            fitness = 0.0

passes = fitness > 0
Path(args.output).write_text(
    json.dumps(
        {
            "hard_gates_passed": passes,
            "recommendation": "promote" if passes else "reject",
            "fitness": fitness,
            "reason": f"fitness={fitness}",
            "metrics": {"fitness": fitness},
            "cost_usd": 0.01,
            "tokens_used": 100,
        },
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
