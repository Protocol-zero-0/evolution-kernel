"""Quickstart executor: shells out to ruff inside the worktree. No LLM."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--input", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--worktree", required=True)
args = parser.parse_args()

worktree = Path(args.worktree)

steps: list[dict] = []
for cmd in (
    [sys.executable, "-m", "ruff", "check", "--fix", "--unsafe-fixes", "src/"],
    [sys.executable, "-m", "ruff", "format", "src/"],
):
    proc = subprocess.run(cmd, cwd=worktree, capture_output=True, text=True)
    steps.append(
        {
            "cmd": " ".join(cmd),
            "exit": proc.returncode,
            "stdout_tail": proc.stdout[-400:],
            "stderr_tail": proc.stderr[-400:],
        }
    )

# Stage everything so the governor sees a non-empty diff.
subprocess.run(["git", "add", "-A"], cwd=worktree, check=False)
status = subprocess.run(
    ["git", "status", "--porcelain"], cwd=worktree, capture_output=True, text=True
)
changed = sum(1 for line in status.stdout.splitlines() if line.strip())

Path(args.output).write_text(
    json.dumps({"steps": steps, "changed_files": changed}, indent=2) + "\n",
    encoding="utf-8",
)
