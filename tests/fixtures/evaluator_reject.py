from __future__ import annotations

import argparse
import json
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("--input", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--worktree", required=True)
args = parser.parse_args()

Path(args.output).write_text(
    json.dumps(
        {
            "hard_gates_passed": False,
            "recommendation": "reject",
            "metrics": {"fitness": 0.0},
            "regressions": ["forced rejection fixture"],
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)

