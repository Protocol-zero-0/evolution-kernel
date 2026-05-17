"""Evolution Kernel command-line entry point.

Usage:

    # Run once:
    evolution-kernel --config examples/evolution.yml --repo /path/to/repo --ledger /tmp/ledger

    # Run until hard stops trigger (multi-round loop):
    evolution-kernel --config examples/evolution.yml --repo /path/to/repo --ledger /tmp/ledger --loop

    # Reset hard-stop state:
    evolution-kernel --ledger /tmp/ledger --reset
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from . import hard_stops
from .config import EvolutionConfig, load_config
from .governor import Governor, RoleCommand


def main(argv: Sequence[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] == "init":
        from .init_wizard import main as _init_main
        return _init_main(raw[1:])
    parser = argparse.ArgumentParser(
        prog="evolution-kernel",
        description="Run Evolution Kernel experiments.",
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
    parser.add_argument("--loop", action="store_true", help="Run until hard stops trigger (multi-round).")
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


def _make_governor(args: argparse.Namespace, cfg: EvolutionConfig) -> Governor:
    planner = tuple(args.planner) if args.planner else cfg.roles.planner
    executor = tuple(args.executor) if args.executor else cfg.roles.executor
    evaluator = tuple(args.evaluator) if args.evaluator else cfg.roles.evaluator
    if not (planner and executor and evaluator):
        print(
            "error: planner/executor/evaluator must be defined in config.roles or via flags",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return Governor(
        target_repo=args.repo,
        ledger_dir=args.ledger,
        planner=RoleCommand(list(planner)),
        executor=RoleCommand(list(executor)),
        evaluator=RoleCommand(list(evaluator)),
        evidence_sources=cfg.evidence_sources,
        allowed_paths=cfg.mutation_scope.allowed_paths,
        config_snapshot=cfg.raw,
        history_max_entries=cfg.history.max_entries,
        sandbox=cfg.sandbox,
    )


def _run_with_config(args: argparse.Namespace, cfg: EvolutionConfig) -> int:
    try:
        governor = _make_governor(args, cfg)
    except SystemExit as e:
        return int(e.code)

    goal = {"name": cfg.mission, "objective": cfg.mission}

    if args.loop:
        return _run_loop(args, cfg, governor, goal)

    # Single run
    state = hard_stops.load_state(args.ledger)
    allowed, why = hard_stops.precheck(
        state,
        cfg.hard_stops.max_iterations,
        cfg.hard_stops.max_consecutive_failures,
        max_total_usd=cfg.hard_stops.max_total_usd,
        max_total_tokens=cfg.hard_stops.max_total_tokens,
    )
    if not allowed:
        _record_halted(args.ledger, state, why)
        print(json.dumps({"halted": True, "reason": why}, indent=2, sort_keys=True))
        return 3

    k = cfg.parallel.k_branches
    if k > 1:
        result = governor.run_once_parallel(goal, k=k)
    else:
        result = governor.run_once(goal, run_id=args.run_id)
    cost_usd, tokens_used = _safe_cost(result.evaluation)
    new_state = hard_stops.record_outcome(
        state,
        accepted=result.decision.accepted,
        max_iterations=cfg.hard_stops.max_iterations,
        max_consecutive_failures=cfg.hard_stops.max_consecutive_failures,
        cost_usd=cost_usd,
        tokens_used=tokens_used,
        max_total_usd=cfg.hard_stops.max_total_usd,
        max_total_tokens=cfg.hard_stops.max_total_tokens,
    )
    hard_stops.save_state(args.ledger, new_state)
    _print_result(result, halted=new_state.halted, halt_reason=new_state.halt_reason)
    return 0


def _run_loop(
    args: argparse.Namespace,
    cfg: EvolutionConfig,
    governor: Governor,
    goal: dict,
) -> int:
    """Run until hard stops trigger or goal is reached."""
    iteration = 0
    pending_strategy: dict | None = None

    while True:
        state = hard_stops.load_state(args.ledger)
        allowed, why = hard_stops.precheck(
            state,
            cfg.hard_stops.max_iterations,
            cfg.hard_stops.max_consecutive_failures,
            max_total_usd=cfg.hard_stops.max_total_usd,
            max_total_tokens=cfg.hard_stops.max_total_tokens,
        )
        if not allowed:
            _record_halted(args.ledger, state, why)
            print(json.dumps({"halted": True, "reason": why}, indent=2, sort_keys=True))
            return 3

        k = cfg.parallel.k_branches
        if k > 1:
            result = governor.run_once_parallel(goal, k=k, strategy=pending_strategy)
        else:
            result = governor.run_once(goal, strategy=pending_strategy)
        pending_strategy = None
        iteration += 1

        cost_usd, tokens_used = _safe_cost(result.evaluation)
        new_state = hard_stops.record_outcome(
            state,
            accepted=result.decision.accepted,
            max_iterations=cfg.hard_stops.max_iterations,
            max_consecutive_failures=cfg.hard_stops.max_consecutive_failures,
            cost_usd=cost_usd,
            tokens_used=tokens_used,
            max_total_usd=cfg.hard_stops.max_total_usd,
            max_total_tokens=cfg.hard_stops.max_total_tokens,
        )
        hard_stops.save_state(args.ledger, new_state)
        _print_result(result, halted=new_state.halted, halt_reason=new_state.halt_reason)

        if result.decision.accepted and cfg.goal_evaluator.enabled and cfg.roles.goal_evaluator:
            if _check_goal_reached(cfg, result):
                print(json.dumps({"goal_reached": True, "halted": False}, indent=2, sort_keys=True))
                return 0

        if cfg.strategist.enabled and cfg.roles.strategist and iteration % cfg.strategist.every_n_rounds == 0:
            pending_strategy = _invoke_strategist(cfg, result, iteration)

        if new_state.halted:
            _record_halted(args.ledger, new_state, new_state.halt_reason)
            return 3


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


def _safe_cost(evaluation: dict) -> tuple[float, int]:
    """Extract cost fields defensively; return (0.0, 0) on any parse error."""
    try:
        cost_usd = float(evaluation.get("cost_usd") or 0.0)
    except (TypeError, ValueError):
        cost_usd = 0.0
    try:
        tokens_used = int(evaluation.get("tokens_used") or 0)
    except (TypeError, ValueError):
        tokens_used = 0
    return cost_usd, tokens_used


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
        "total_usd": state.total_usd,
        "total_tokens": state.total_tokens,
    }
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


def _check_goal_reached(cfg: EvolutionConfig, result) -> bool:
    input_path = result.run_dir / "goal_eval_input.json"
    output_path = result.run_dir / "goal_evaluation.json"
    input_data = {
        "mission": cfg.mission,
        "latest_evaluation": dict(result.evaluation),
    }
    input_path.write_text(json.dumps(input_data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    argv = [
        *cfg.roles.goal_evaluator,
        "--input", str(input_path),
        "--output", str(output_path),
        "--worktree", str(result.run_dir),
    ]
    completed = subprocess.run(argv, text=True, capture_output=True, check=False)
    if completed.returncode != 0 or not output_path.exists():
        return False
    try:
        data = json.loads(output_path.read_text(encoding="utf-8"))
        return bool(data.get("goal_reached", False))
    except (json.JSONDecodeError, OSError):
        return False


def _invoke_strategist(cfg: EvolutionConfig, result, iteration: int) -> dict | None:
    input_path = result.run_dir / "strategist_input.json"
    output_path = result.run_dir / "strategy.json"
    input_data = {
        "mission": cfg.mission,
        "current_round": iteration,
        "latest_evaluation": dict(result.evaluation),
    }
    input_path.write_text(json.dumps(input_data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    argv = [
        *cfg.roles.strategist,
        "--input", str(input_path),
        "--output", str(output_path),
        "--worktree", str(result.run_dir),
    ]
    completed = subprocess.run(argv, text=True, capture_output=True, check=False)
    if completed.returncode != 0 or not output_path.exists():
        return None
    try:
        return json.loads(output_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
