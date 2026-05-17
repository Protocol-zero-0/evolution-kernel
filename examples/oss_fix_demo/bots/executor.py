"""OSS-fix-demo executor: invokes `claude -p` inside the worktree.

The kernel-bundled `roles/executor.sh` claude-code path drops permission
flags, so claude refuses to make edits in non-interactive mode. This
wrapper sets `--permission-mode acceptEdits` so the agent actually edits
files. The cost is whatever your Claude Pro / Max subscription already
covers — no API key needed.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--input", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--worktree", required=True)
args = parser.parse_args()

input_payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
plan_path = input_payload.get("plan_path")
plan = json.loads(Path(plan_path).read_text(encoding="utf-8")) if plan_path and Path(plan_path).exists() else {}

steps = "\n".join(plan.get("steps", [])) or "Apply the plan."
prompt = f"{plan.get('summary', 'improve the codebase')}\n\nSteps:\n{steps}\n\nOnly modify files within: {', '.join(plan.get('allowed_paths', ['slugify/']))}"

claude_bin = os.environ.get("EK_CLAUDE_BIN", "claude")
extra_args = os.environ.get("EK_CLAUDE_ARGS", "--permission-mode acceptEdits").split()
timeout_s = int(os.environ.get("EK_CLAUDE_TIMEOUT", "300"))

start = time.time()
proc = subprocess.run(
    [claude_bin, "-p", *extra_args, prompt],
    cwd=args.worktree,
    capture_output=True,
    text=True,
    timeout=timeout_s,
)
elapsed = time.time() - start

# Mop up any remaining autofix-only diagnostics (import sort, whitespace).
# This is realistic: in real workflows you run the formatter after the LLM.
postprocess = []
for cmd in (
    ["python3", "-m", "ruff", "check", "--fix", "--unsafe-fixes", "slugify/"],
    ["python3", "-m", "ruff", "format", "slugify/"],
):
    p = subprocess.run(cmd, cwd=args.worktree, capture_output=True, text=True)
    postprocess.append({"cmd": " ".join(cmd), "exit": p.returncode})

subprocess.run(["git", "add", "-A"], cwd=args.worktree, check=False)
status = subprocess.run(
    ["git", "status", "--porcelain"], cwd=args.worktree, capture_output=True, text=True
)
changed = sum(1 for line in status.stdout.splitlines() if line.strip())

Path(args.output).write_text(
    json.dumps(
        {
            "tool": "claude-code",
            "exit": proc.returncode,
            "elapsed_seconds": round(elapsed, 2),
            "postprocess": postprocess,
            "changed_files": changed,
            "stdout_tail": proc.stdout[-800:],
            "stderr_tail": proc.stderr[-400:],
            "summary": plan.get("summary", ""),
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
