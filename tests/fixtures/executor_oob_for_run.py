"""Executor fixture that writes out-of-scope files for a specific run_id only.

Used by the parallel scope-violation test: one branch violates scope while
others stay in-bounds. The "bad" run_id is selected via EK_TEST_OOB_RUN_ID.
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
worktree = Path(args.worktree)

bad_run_id = os.environ.get("EK_TEST_OOB_RUN_ID", "")
if run_id == bad_run_id:
    (worktree / "OUT_OF_SCOPE.txt").write_text("forbidden\n", encoding="utf-8")
else:
    # Stay inside scope: write into allowed src/ subtree.
    src = worktree / "src"
    src.mkdir(exist_ok=True)
    fitness = os.environ.get(f"EK_TEST_FITNESS_{run_id}", "0.5")
    (src / "marker.txt").write_text(f"fitness={fitness}\n", encoding="utf-8")

Path(args.output).write_text(
    json.dumps({"changed": [], "notes": f"branch {run_id}"}, indent=2) + "\n",
    encoding="utf-8",
)
