import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--input", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--worktree", required=True)
args = parser.parse_args()

Path(args.output).write_text(
    json.dumps({"goal_reached": False, "confidence": 0.0, "reason": "fixture: never reached"}, indent=2) + "\n",
    encoding="utf-8",
)
