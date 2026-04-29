from __future__ import annotations

import argparse
import json
from pathlib import Path

from .governor import Governor, RoleCommand
from .hard_stop import HardStopGuard
from .config import load_config, HardStopConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one Evolution Kernel experiment.")
    parser.add_argument("--config", default=None, help="YAML config file (evolution.yml).")
    parser.add_argument("--repo", default=None, help="Target git repository.")
    parser.add_argument("--ledger", required=True, help="Ledger directory.")
    parser.add_argument("--goal", default=None, help="Goal JSON file (overrides config mission).")
    parser.add_argument("--planner", nargs="+", default=None, help="Planner command (overrides config).")
    parser.add_argument("--executor", nargs="+", default=None, help="Executor command (overrides config).")
    parser.add_argument("--evaluator", nargs="+", default=None, help="Evaluator command (overrides config).")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--reset", action="store_true", help="Reset hard stop state and exit.")
    args = parser.parse_args()

    ledger_dir = Path(args.ledger)

    if args.reset:
        HardStopGuard(ledger_dir, HardStopConfig()).reset()
        print(json.dumps({"reset": True, "ledger": str(ledger_dir)}, indent=2))
        return

    if args.repo is None:
        parser.error("--repo is required when not using --reset")

    cfg = load_config(Path(args.config)) if args.config else None

    # Resolve goal
    if args.goal:
        goal = json.loads(Path(args.goal).read_text(encoding="utf-8"))
    elif cfg:
        goal = {"mission": cfg.mission}
    else:
        parser.error("--goal is required when --config is not provided")

    # Resolve roles: CLI args override config
    def _role(cli_arg, cfg_attr):
        if cli_arg:
            return RoleCommand(cli_arg)
        if cfg and cfg.roles:
            return RoleCommand(getattr(cfg.roles, cfg_attr))
        parser.error(f"--{cfg_attr} is required when roles are not defined in --config")

    planner = _role(args.planner, "planner")
    executor = _role(args.executor, "executor")
    evaluator = _role(args.evaluator, "evaluator")

    # Resolve optional features from config
    observation_sources = cfg.evidence_sources if cfg else None
    allowed_paths = list(cfg.mutation_scope.allowed_paths) if cfg else None
    hard_stop_cfg = cfg.hard_stops if cfg else HardStopConfig()

    guard = HardStopGuard(ledger_dir, hard_stop_cfg)
    guard.check()

    result = Governor(
        target_repo=args.repo,
        ledger_dir=args.ledger,
        planner=planner,
        executor=executor,
        evaluator=evaluator,
        observation_sources=observation_sources if observation_sources else None,
        allowed_paths=allowed_paths if allowed_paths else None,
    ).run_once(goal, run_id=args.run_id)

    guard.record(result.decision.accepted)

    print(json.dumps({
        "run_id": result.run_id,
        "accepted": result.decision.accepted,
        "reason": result.decision.reason,
        "candidate_commit": result.decision.candidate_commit,
        "run_dir": str(result.run_dir),
    }, indent=2))


if __name__ == "__main__":
    main()
