"""Fixture executor that tries to write one marker inside the worktree and
one marker outside it. The outside write is the canonical "escape attempt"
used by PR7a tests to assert that the sandbox blocks OOB writes at the OS
level (not after the fact).

Both writes are wrapped in try/except so the executor itself always exits
zero and produces a structured --output JSON describing what happened. The
test then inspects both the JSON and the on-disk state.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("--input", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--worktree", required=True)
args = parser.parse_args()

payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
run_id = payload["run_id"]
worktree = Path(args.worktree)

# Escape target is provided via env so the test can place it anywhere; default
# falls back to /tmp so this fixture is also usable interactively.
escape_target = Path(
    os.environ.get("ESCAPE_TARGET", f"/tmp/sandbox-escape-{run_id}.txt")
)

inside_path = worktree / "EVOLUTION_MARKER.txt"
inside_ok: bool
inside_err: str | None = None
try:
    inside_path.write_text(f"run={run_id}\n", encoding="utf-8")
    inside_ok = True
except OSError as exc:
    inside_ok = False
    inside_err = f"{type(exc).__name__}: {exc}"

outside_ok: bool
outside_err: str | None = None
try:
    escape_target.parent.mkdir(parents=True, exist_ok=True)
    escape_target.write_text(f"escape from run {run_id}\n", encoding="utf-8")
    outside_ok = True
except OSError as exc:
    outside_ok = False
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

# Always exit 0 — the test inspects the JSON to determine sandbox behavior.
sys.exit(0)
