"""Demo executor: write a single file under src/ to satisfy the plan."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--input", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--worktree", required=True)
args = parser.parse_args()

worktree = Path(args.worktree)
target = worktree / "src" / "feature.py"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text("def feature() -> str:\n    return 'ok'\n", encoding="utf-8")
Path(args.output).write_text(
    json.dumps({"changed": ["src/feature.py"], "notes": "added minimal feature within scope"}, indent=2)
    + "\n",
    encoding="utf-8",
)
