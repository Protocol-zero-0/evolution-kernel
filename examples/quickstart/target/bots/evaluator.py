"""Quickstart evaluator: accept iff ruff check src/ reports zero violations."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--input", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--worktree", required=True)
args = parser.parse_args()

proc = subprocess.run(
    [sys.executable, "-m", "ruff", "check", "src/"],
    cwd=args.worktree,
    capture_output=True,
    text=True,
)
clean = proc.returncode == 0

Path(args.output).write_text(
    json.dumps(
        {
            "hard_gates_passed": clean,
            "recommendation": "promote" if clean else "reject",
            "metrics": {
                "ruff_clean": float(clean),
                "fitness": 1.0 if clean else 0.0,
            },
            "ruff_output_tail": proc.stdout[-400:],
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
