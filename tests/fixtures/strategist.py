import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--input", required=True)
parser.add_argument("--output", required=True)
parser.add_argument("--worktree", required=True)
args = parser.parse_args()

Path(args.output).write_text(
    json.dumps({
        "stage": "fixture-stage",
        "next_milestone": "fixture milestone",
        "taboo_directions": ["do not break tests"],
    }, indent=2) + "\n",
    encoding="utf-8",
)
