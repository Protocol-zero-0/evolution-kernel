"""Executor fixture that writes EVOLUTION_MARKER.txt with content unique per
run_id, so every branch produces a real diff against the baseline (otherwise
later rounds would re-emit the prior winner's content and commit nothing)."""
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
run_id = payload["run_id"]
worktree = Path(args.worktree)
(worktree / "EVOLUTION_MARKER.txt").write_text(f"run={run_id}\n", encoding="utf-8")
Path(args.output).write_text(
    json.dumps({"changed": ["EVOLUTION_MARKER.txt"], "notes": run_id}, indent=2) + "\n",
    encoding="utf-8",
)
