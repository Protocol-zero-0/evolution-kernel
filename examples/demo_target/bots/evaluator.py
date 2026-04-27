"""Demo evaluator: pass when src/feature.py exists, fail otherwise."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--input", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--worktree", required=True)
args = parser.parse_args()

ok = (Path(args.worktree) / "src" / "feature.py").exists()
Path(args.output).write_text(
    json.dumps(
        {
            "hard_gates_passed": ok,
            "recommendation": "promote" if ok else "reject",
            "metrics": {"feature_present": float(ok), "fitness": 1.0 if ok else 0.0},
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
