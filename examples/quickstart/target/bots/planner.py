"""Quickstart planner: emits a canned 'run ruff --fix' plan. No LLM."""
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
            "summary": "Drive ruff to zero violations on src/.",
            "steps": [
                "ruff check --fix --unsafe-fixes src/",
                "ruff format src/",
            ],
            "allowed_paths": ["src/"],
            "expected_improvement": "ruff check src/ exits 0.",
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
