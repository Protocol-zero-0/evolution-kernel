from __future__ import annotations

import argparse
import json
from pathlib import Path

from .governor import Governor, RoleCommand


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one Evolution Kernel experiment.")
    parser.add_argument("--repo", required=True, help="Target git repository.")
    parser.add_argument("--ledger", required=True, help="Ledger directory.")
    parser.add_argument("--goal", required=True, help="Goal JSON file.")
    parser.add_argument("--planner", required=True, nargs="+", help="Planner command.")
    parser.add_argument("--executor", required=True, nargs="+", help="Executor command.")
    parser.add_argument("--evaluator", required=True, nargs="+", help="Evaluator command.")
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()

    goal = json.loads(Path(args.goal).read_text(encoding="utf-8"))
    result = Governor(
        target_repo=args.repo,
        ledger_dir=args.ledger,
        planner=RoleCommand(args.planner),
        executor=RoleCommand(args.executor),
        evaluator=RoleCommand(args.evaluator),
    ).run_once(goal, run_id=args.run_id)
    print(json.dumps({
        "run_id": result.run_id,
        "accepted": result.decision.accepted,
        "reason": result.decision.reason,
        "candidate_commit": result.decision.candidate_commit,
        "run_dir": str(result.run_dir),
    }, indent=2))


if __name__ == "__main__":
    main()

