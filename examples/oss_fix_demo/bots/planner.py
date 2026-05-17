"""OSS-fix-demo planner: emits a canned ruff-cleanup plan. No LLM call."""
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

payload = json.loads(Path(args.input).read_text(encoding="utf-8"))

# Snapshot the current ruff diagnostics so the LLM executor sees concrete
# violations to fix rather than a generic "clean up the code" prompt.
proc = subprocess.run(
    [sys.executable, "-m", "ruff", "check", "slugify/"],
    cwd=args.worktree,
    capture_output=True,
    text=True,
)
ruff_report = proc.stdout[-3000:] or proc.stderr[-500:]

Path(args.output).write_text(
    json.dumps(
        {
            "run_id": payload["run_id"],
            "summary": "Drive ruff to zero violations on slugify/ by editing the files directly. Do not change runtime behaviour.",
            "steps": [
                "Read each ruff diagnostic below and edit the offending file to remove the violation.",
                "Acceptable fixes: add `# noqa` is NOT allowed; mark unused imports as explicit re-exports (e.g. `__version__ as __version__`) or delete them; remove unused variables; fix comparisons.",
                "Do not run ruff yourself — just edit the files. The evaluator will re-run ruff afterward.",
                "",
                "Ruff diagnostics:",
                ruff_report,
            ],
            "allowed_paths": ["slugify/"],
            "expected_improvement": "ruff check slugify/ exits 0.",
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
