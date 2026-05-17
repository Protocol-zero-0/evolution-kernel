"""OSS-fix-demo evaluator: accept iff ruff check slugify/ reports zero violations."""
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
    [sys.executable, "-m", "ruff", "check", "slugify/"],
    cwd=args.worktree,
    capture_output=True,
    text=True,
)
clean = proc.returncode == 0

# Count remaining violations from the "Found N errors." footer if present.
remaining = 0
for line in proc.stdout.splitlines():
    if line.startswith("Found ") and "error" in line:
        try:
            remaining = int(line.split()[1])
        except (ValueError, IndexError):
            pass

Path(args.output).write_text(
    json.dumps(
        {
            "hard_gates_passed": clean,
            "recommendation": "promote" if clean else "reject",
            "metrics": {
                "ruff_clean": float(clean),
                "ruff_violations_remaining": remaining,
                "fitness": 1.0 if clean else 1.0 / (1.0 + remaining),
            },
            "ruff_output_tail": proc.stdout[-800:],
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
