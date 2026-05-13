"""Executor fixture for k-branch tests.

Writes EVOLUTION_MARKER.txt with a per-run "fitness hint" so a sibling evaluator
fixture can score branches differently within the same round. The hint comes
from an environment variable looked up by run_id, so each branch in a parallel
round can be assigned its own fitness from the test setup.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("--input", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--worktree", required=True)
args = parser.parse_args()

payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
run_id = payload["run_id"]
fitness = os.environ.get(f"EK_TEST_FITNESS_{run_id}", "0.5")

worktree = Path(args.worktree)
(worktree / "EVOLUTION_MARKER.txt").write_text(f"fitness={fitness}\n", encoding="utf-8")
Path(args.output).write_text(
    json.dumps({"changed": ["EVOLUTION_MARKER.txt"], "notes": f"branch {run_id}"}, indent=2) + "\n",
    encoding="utf-8",
)
