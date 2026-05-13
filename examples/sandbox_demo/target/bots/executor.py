"""Sandbox-demo executor.

This role intentionally tries to write *two* files in one run:

1. ``EVOLUTION_MARKER.txt`` inside the worktree — the legitimate change.
2. ``/tmp/sandbox-leak-<run_id>.txt`` outside the worktree — a planted
   "escape attempt" so the operator can observe firejail blocking it.

Both writes are wrapped in try/except, so the role itself always exits 0
and records what happened in its JSON output. With ``sandbox.enabled: true``
the outside write must fail with an OSError ("Read-only file system") and
no leak file is left on disk. With the sandbox disabled the leak file does
get written — which is precisely the prior behavior PR7a was filed to fix.
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

# Operator can override the escape target so they can clean it up easily.
escape_target = Path(
    os.environ.get("SANDBOX_DEMO_ESCAPE", f"/tmp/sandbox-leak-{run_id}.txt")
)

inside_ok = False
inside_err = None
try:
    (worktree / "EVOLUTION_MARKER.txt").write_text(
        f"run={run_id}\n", encoding="utf-8"
    )
    inside_ok = True
except OSError as exc:
    inside_err = f"{type(exc).__name__}: {exc}"

outside_ok = False
outside_err = None
try:
    escape_target.parent.mkdir(parents=True, exist_ok=True)
    escape_target.write_text(f"escape from run {run_id}\n", encoding="utf-8")
    outside_ok = True
except OSError as exc:
    outside_err = f"{type(exc).__name__}: {exc}"

Path(args.output).write_text(
    json.dumps(
        {
            "changed": ["EVOLUTION_MARKER.txt"] if inside_ok else [],
            "inside_write_ok": inside_ok,
            "inside_error": inside_err,
            "outside_write_ok": outside_ok,
            "outside_error": outside_err,
            "escape_target": str(escape_target),
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
