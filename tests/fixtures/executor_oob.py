"""Test fixture: executor that writes a file outside any reasonable allowed_paths.

Used to exercise mutation-scope enforcement in acceptance tests.
"""
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
(worktree / "README.md").write_text("# mutated outside scope\n", encoding="utf-8")
Path(args.output).write_text(
    json.dumps({"changed": ["README.md"], "notes": "intentionally out-of-bounds for scope test"}, indent=2)
    + "\n",
    encoding="utf-8",
)
