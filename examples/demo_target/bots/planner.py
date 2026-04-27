"""Demo planner: emit a fixed plan that touches src/."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--input", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--worktree", required=True)
args = parser.parse_args()

payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
Path(args.output).write_text(
    json.dumps(
        {
            "run_id": payload["run_id"],
            "summary": "Add src/feature.py so the evaluator can confirm a within-scope mutation.",
            "allowed_paths": ["src/"],
            "expected_improvement": "evaluator should accept once src/feature.py exists",
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
