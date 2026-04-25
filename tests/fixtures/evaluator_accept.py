from __future__ import annotations

import argparse
import json
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("--input", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--worktree", required=True)
args = parser.parse_args()

marker_exists = (Path(args.worktree) / "EVOLUTION_MARKER.txt").exists()
Path(args.output).write_text(
    json.dumps(
        {
            "hard_gates_passed": marker_exists,
            "recommendation": "promote" if marker_exists else "reject",
            "metrics": {"marker_exists": float(marker_exists), "fitness": 1.0 if marker_exists else 0.0},
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)

