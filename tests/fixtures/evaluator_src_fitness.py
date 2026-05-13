"""Evaluator fixture used with the partial-scope-violation parallel test.

Looks for src/marker.txt (which executor_oob_for_run.py writes for in-scope
branches) and reads the fitness float from it.
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

marker = Path(args.worktree) / "src" / "marker.txt"
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
            "cost_usd": 0.02,
            "tokens_used": 200,
        },
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
