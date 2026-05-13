"""Sandbox-demo planner: plans an in-scope write to EVOLUTION_MARKER.txt."""
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
            "summary": "Write EVOLUTION_MARKER.txt inside the worktree to prove the in-scope path works under sandbox.",
            "allowed_paths": ["EVOLUTION_MARKER.txt"],
            "expected_improvement": "Marker exists after executor runs.",
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
