"""Evolution Kernel command-line entry point.

The CLI shape mirrors the suggested form in the project's MVP brief:

    python -m evolution_kernel.cli \
        --config examples/evolution.yml \
        --repo /path/to/target-repo \
        --ledger /tmp/evolution-ledger

Two extra modes are supported alongside this primary form:

* ``--goal goal.json`` runs the legacy direct-flags loop (no observer / scope /
  hard-stops) so the original golden-case tests keep working unchanged.
* ``--reset`` clears the persisted hard-stop state for the given ledger and
  exits — used to re-enable a halted loop after a human review.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
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
    parser.add_argument("--repo", help="Target git repository (required unless --reset)")
    parser.add_argument("--ledger", required=True, help="Ledger directory")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--config", dest="config_path", help="Path to evolution.yml")
    mode.add_argument("--goal", help="Path to legacy goal JSON (no observer/scope/hard-stops)")
    parser.add_argument("--planner", nargs="+", help="Planner argv (overrides config.roles.planner)")
    parser.add_argument("--executor", nargs="+", help="Executor argv (overrides config.roles.executor)")
    parser.add_argument("--evaluator", nargs="+", help="Evaluator argv (overrides config.roles.evaluator)")
    parser.add_argument("--run-id", default=None)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear the persisted hard-stop state for --ledger and exit.",
    )

    args = parser.parse_args(argv)

    if args.reset:
        return _cmd_reset(args)

    if not args.repo:
        parser.error("--repo is required (unless --reset is given)")
    if not (args.config_path or args.goal):
        parser.error("either --config or --goal must be provided")

    if args.config_path:
        cfg = load_config(args.config_path)
        return _run_with_config(args, cfg)
    return _run_legacy(args)


def _cmd_reset(args: argparse.Namespace) -> int:
    cleared = hard_stops.reset(args.ledger)
    print(json.dumps(
        {"reset": cleared, "ledger": str(Path(args.ledger).resolve())},
        indent=2,
        sort_keys=True,
    ))
    return 0


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
        # Even when blocked, leave an audit record so the ledger covers every
        # invocation, not just the ones that actually ran the loop.
        _record_halted(args.ledger, state, why)
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


def _record_halted(
    ledger_dir: str,
    state: hard_stops.HardStopState,
    reason: str | None,
) -> None:
    halted_dir = Path(ledger_dir) / "halted"
    halted_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    record = {
        "halted_at": ts,
        "reason": reason,
        "iterations": state.iterations,
        "consecutive_failures": state.consecutive_failures,
    }
    # Suffix with sequence number to avoid collisions within the same second.
    base = halted_dir / f"{ts}.json"
    target = base
    n = 1
    while target.exists():
        target = halted_dir / f"{ts}-{n}.json"
        n += 1
    target.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
