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
(worktree / "EVOLUTION_MARKER.txt").write_text("sandbox mutation\n", encoding="utf-8")
Path(args.output).write_text(
    json.dumps({"changed": ["EVOLUTION_MARKER.txt"], "notes": "wrote repo-local marker"}, indent=2) + "\n",
    encoding="utf-8",
)

