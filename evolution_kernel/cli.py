"""Evolution Kernel command-line entry point.

Two subcommands:

* ``run`` executes one experiment. The full MVP loop (observer + scope +
  hard-stops) is enabled by passing ``--config evolution.yml``. The legacy
  ``--goal goal.json`` form is preserved so the original role-fixture tests
  keep working without any extra plumbing.
* ``reset`` clears the persisted hard-stop state for a ledger.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from . import hard_stops
from .config import EvolutionConfig, load_config
from .governor import Governor, RoleCommand


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="evolution-kernel",
        description="Run one Evolution Kernel experiment under MVP constraints.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Run one experiment")
    run_p.add_argument("--repo", required=True, help="Target git repository")
    run_p.add_argument("--ledger", required=True, help="Ledger directory")
    mode = run_p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--config", dest="config_path", help="Path to evolution.yml")
    mode.add_argument("--goal", help="Path to legacy goal JSON (no observer/scope/hard-stops)")
    run_p.add_argument("--planner", nargs="+", help="Planner argv (overrides config.roles.planner)")
    run_p.add_argument("--executor", nargs="+", help="Executor argv (overrides config.roles.executor)")
    run_p.add_argument("--evaluator", nargs="+", help="Evaluator argv (overrides config.roles.evaluator)")
    run_p.add_argument("--run-id", default=None)

    reset_p = sub.add_parser("reset", help="Clear persistent hard-stop state for a ledger")
    reset_p.add_argument("--ledger", required=True)

    args = parser.parse_args(argv)
    if args.cmd == "reset":
        return _cmd_reset(args)
    return _cmd_run(args)


def _cmd_reset(args: argparse.Namespace) -> int:
    cleared = hard_stops.reset(args.ledger)
    print(json.dumps(
        {"reset": cleared, "ledger": str(Path(args.ledger).resolve())},
        indent=2,
        sort_keys=True,
    ))
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    if args.config_path:
        cfg = load_config(args.config_path)
        return _run_with_config(args, cfg)
    return _run_legacy(args)


def _run_with_config(args: argparse.Namespace, cfg: EvolutionConfig) -> int:
    planner = tuple(args.planner) if args.planner else cfg.roles.planner
    executor = tuple(args.executor) if args.executor else cfg.roles.executor
    evaluator = tuple(args.evaluator) if args.evaluator else cfg.roles.evaluator
    if not (planner and executor and evaluator):
        print(
            "error: planner/executor/evaluator must be defined in config.roles or via flags",
            file=sys.stderr,
        )
        return 2

    state = hard_stops.load_state(args.ledger)
    allowed, why = hard_stops.precheck(
        state,
        cfg.hard_stops.max_iterations,
        cfg.hard_stops.max_consecutive_failures,
    )
    if not allowed:
        print(json.dumps({"halted": True, "reason": why}, indent=2, sort_keys=True))
        return 3

    goal = {"name": cfg.mission, "objective": cfg.mission}
    governor = Governor(
        target_repo=args.repo,
        ledger_dir=args.ledger,
        planner=RoleCommand(list(planner)),
        executor=RoleCommand(list(executor)),
        evaluator=RoleCommand(list(evaluator)),
        evidence_sources=cfg.evidence_sources,
        allowed_paths=cfg.mutation_scope.allowed_paths,
        config_snapshot=cfg.raw,
    )
    result = governor.run_once(goal, run_id=args.run_id)
    new_state = hard_stops.record_outcome(
        state,
        accepted=result.decision.accepted,
        max_iterations=cfg.hard_stops.max_iterations,
        max_consecutive_failures=cfg.hard_stops.max_consecutive_failures,
    )
    hard_stops.save_state(args.ledger, new_state)
    _print_result(result, halted=new_state.halted, halt_reason=new_state.halt_reason)
    return 0


def _run_legacy(args: argparse.Namespace) -> int:
    if not (args.planner and args.executor and args.evaluator):
        print(
            "error: --planner, --executor, --evaluator are required in legacy --goal mode",
            file=sys.stderr,
        )
        return 2
    goal = json.loads(Path(args.goal).read_text(encoding="utf-8"))
    governor = Governor(
        target_repo=args.repo,
        ledger_dir=args.ledger,
        planner=RoleCommand(args.planner),
        executor=RoleCommand(args.executor),
        evaluator=RoleCommand(args.evaluator),
    )
    result = governor.run_once(goal, run_id=args.run_id)
    _print_result(result)
    return 0


def _print_result(result, *, halted: bool = False, halt_reason: str | None = None) -> None:
    payload = {
        "run_id": result.run_id,
        "accepted": result.decision.accepted,
        "reason": result.decision.reason,
        "candidate_commit": result.decision.candidate_commit,
        "run_dir": str(result.run_dir),
    }
    if halted:
        payload["halted"] = True
        payload["halt_reason"] = halt_reason
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
