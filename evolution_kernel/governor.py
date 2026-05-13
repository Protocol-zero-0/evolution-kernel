from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .config import EvidenceSource
from .observer import collect_observation, write_observation
from .scope import ScopeReport, check_scope


ACCEPTED_BRANCH = "evolution/accepted"


@dataclass(frozen=True)
class RoleCommand:
    argv: Sequence[str]


@dataclass(frozen=True)
class RunDecision:
    accepted: bool
    reason: str
    baseline_commit: str
    candidate_commit: str | None
    rollback_target: str


@dataclass(frozen=True)
class RunResult:
    run_id: str
    run_dir: Path
    worktree: Path
    decision: RunDecision
    evaluation: Mapping[str, Any]


class Governor:
    """Deterministic coordinator for one isolated evolution experiment."""

    def __init__(
        self,
        target_repo: Path | str,
        ledger_dir: Path | str,
        planner: RoleCommand,
        executor: RoleCommand,
        evaluator: RoleCommand,
        evidence_sources: Sequence[EvidenceSource] = (),
        allowed_paths: Sequence[str] = (),
        config_snapshot: Mapping[str, Any] | None = None,
        history_max_entries: int = 10,
    ) -> None:
        self.target_repo = Path(target_repo).resolve()
        self.ledger_dir = Path(ledger_dir).resolve()
        self.planner = planner
        self.executor = executor
        self.evaluator = evaluator
        self.evidence_sources = tuple(evidence_sources)
        self.allowed_paths = tuple(allowed_paths)
        self.config_snapshot = dict(config_snapshot) if config_snapshot else None
        self.history_max_entries = history_max_entries

    def run_once(self, goal: Mapping[str, Any], run_id: str | None = None, strategy: dict | None = None) -> RunResult:
        self._ensure_git_repo()
        self._ensure_accepted_branch()

        run_id = run_id or self._next_run_id()
        run_dir = self.ledger_dir / "runs" / run_id
        worktree = self.ledger_dir / "worktrees" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        worktree.parent.mkdir(parents=True, exist_ok=True)

        baseline_commit = self._git("rev-parse", ACCEPTED_BRANCH)
        branch = f"evolution/experiment/{run_id}"
        self._git("worktree", "add", "-B", branch, str(worktree), baseline_commit)

        try:
            self._write_json(run_dir / "goal.json", dict(goal))
            if self.config_snapshot is not None:
                self._write_json(run_dir / "config.json", self.config_snapshot)

            observation_path = run_dir / "observation.json"
            observation = collect_observation(self.evidence_sources, self.target_repo)
            write_observation(observation_path, observation)

            planner_input: dict = {
                "run_id": run_id,
                "goal": goal,
                "accepted_branch": ACCEPTED_BRANCH,
                "baseline_commit": baseline_commit,
                "worktree": str(worktree),
                "ledger_dir": str(self.ledger_dir),
                "observation_path": str(observation_path),
                "allowed_paths": list(self.allowed_paths),
                "history": self._build_history(),
            }
            if strategy is not None:
                planner_input["strategy"] = strategy
            self._write_json(run_dir / "planner_input.json", planner_input)
            self._run_role(self.planner, run_dir / "planner_input.json", run_dir / "plan.json", worktree)

            self._write_json(
                run_dir / "executor_input.json",
                {
                    "run_id": run_id,
                    "goal": goal,
                    "baseline_commit": baseline_commit,
                    "plan_path": str(run_dir / "plan.json"),
                    "worktree": str(worktree),
                },
            )
            self._run_role(
                self.executor,
                run_dir / "executor_input.json",
                run_dir / "executor_output.json",
                worktree,
            )

            candidate_commit = self._commit_candidate(worktree, run_id)
            (run_dir / "candidate_commit.txt").write_text(
                (candidate_commit or "") + "\n", encoding="utf-8"
            )
            # Patch must be captured against the actual candidate commit, not the
            # working tree before commit (untracked files would be invisible).
            if candidate_commit:
                patch = self._git_in(
                    worktree, "diff", "--binary", baseline_commit, candidate_commit
                )
                # `_run` strips trailing whitespace; restore the final newline
                # `git apply` requires for the patch to be replayable.
                if patch and not patch.endswith("\n"):
                    patch += "\n"
            else:
                patch = ""
            (run_dir / "patch.diff").write_text(patch, encoding="utf-8")

            scope_report = self._enforce_scope(worktree, baseline_commit, candidate_commit)
            if scope_report is not None and not scope_report.ok:
                evaluation = {
                    "hard_gates_passed": False,
                    "recommendation": "reject",
                    "reason": "scope_violation",
                    "violations": list(scope_report.violations),
                    "changed_files": list(scope_report.changed_files),
                    "allowed_paths": list(scope_report.allowed_paths),
                    "metrics": {},
                }
                self._write_json(run_dir / "evaluation.json", evaluation)
                decision = RunDecision(
                    accepted=False,
                    reason=f"scope_violation: {','.join(scope_report.violations)}",
                    baseline_commit=baseline_commit,
                    candidate_commit=candidate_commit,
                    rollback_target=baseline_commit,
                )
                self._write_json(run_dir / "decision.json", decision.__dict__)
            else:
                self._write_json(
                    run_dir / "evaluator_input.json",
                    {
                        "run_id": run_id,
                        "goal": goal,
                        "baseline_commit": baseline_commit,
                        "candidate_commit": candidate_commit,
                        "patch_path": str(run_dir / "patch.diff"),
                        "worktree": str(worktree),
                        "observation_path": str(observation_path),
                    },
                )
                self._run_role(
                    self.evaluator,
                    run_dir / "evaluator_input.json",
                    run_dir / "evaluation.json",
                    worktree,
                )
                evaluation = self._read_json(run_dir / "evaluation.json")
                decision = self._decide(evaluation, baseline_commit, candidate_commit)
                self._write_json(run_dir / "decision.json", decision.__dict__)

            if decision.accepted:
                self._git("branch", "-f", ACCEPTED_BRANCH, candidate_commit)

            self._record_accepted_commit()
            # Pull plan summary for history — more informative than decision.reason.
            plan_summary = ""
            try:
                plan_data = self._read_json(run_dir / "plan.json")
                plan_summary = str(plan_data.get("summary", ""))
            except Exception:
                pass
            self._write_json(
                run_dir / "reflection.json",
                {
                    "run_id": run_id,
                    "accepted": decision.accepted,
                    "reason": decision.reason,
                    "plan_summary": plan_summary,
                    "metrics": evaluation.get("metrics", {}),
                    "created_at": self._now(),
                },
            )
            if not decision.accepted:
                failed_dir = self.ledger_dir / "failed"
                failed_dir.mkdir(parents=True, exist_ok=True)
                self._write_json(failed_dir / f"{run_id}-summary.json", decision.__dict__)

            return RunResult(run_id, run_dir, worktree, decision, evaluation)
        finally:
            # Keep the experiment branch and ledger, but remove the mutable checkout.
            if worktree.exists():
                self._git("worktree", "remove", "--force", str(worktree))

    def run_once_parallel(
        self,
        goal: Mapping[str, Any],
        k: int,
        strategy: dict | None = None,
    ) -> RunResult:
        """Run `k` independent branches in one round, promote the highest-fitness
        survivor to `evolution/accepted`, demote the rest to `ledger/failed/`.

        `k <= 1` is delegated to `run_once` so single-branch callers retain the
        exact byte-for-byte behavior covered by the v0.2 + phase-2 test suite.
        Returned `RunResult.evaluation` carries the *summed* cost/tokens across
        all k branches so hard-stop accounting in the CLI loop remains correct.
        """
        if k <= 1:
            return self.run_once(goal, strategy=strategy)

        self._ensure_git_repo()
        self._ensure_accepted_branch()
        baseline_commit = self._git("rev-parse", ACCEPTED_BRANCH)

        # Allocate k run_ids up front by materializing each run_dir before the
        # next allocation, so _next_run_id observes the prior sibling.
        run_ids: list[str] = []
        for _ in range(k):
            rid = self._next_run_id()
            (self.ledger_dir / "runs" / rid).mkdir(parents=True, exist_ok=False)
            run_ids.append(rid)

        branches: list[dict] = []
        worktrees: list[Path] = []
        try:
            for rid in run_ids:
                br = self._run_single_branch(goal, rid, strategy, baseline_commit)
                branches.append(br)
                worktrees.append(br["worktree"])

            winner_idx = self._select_winner(branches)

            total_cost = 0.0
            total_tokens = 0
            for br in branches:
                ev = br["evaluation"]
                try:
                    total_cost += float(ev.get("cost_usd") or 0.0)
                except (TypeError, ValueError):
                    pass
                try:
                    total_tokens += int(ev.get("tokens_used") or 0)
                except (TypeError, ValueError):
                    pass

            winner_result: RunResult | None = None
            for i, br in enumerate(branches):
                is_winner = (winner_idx is not None and i == winner_idx)
                if is_winner:
                    fitness = float(br["evaluation"].get("fitness", 0.0))
                    decision = RunDecision(
                        accepted=True,
                        reason=f"k-branch winner: highest fitness {fitness:.4f}",
                        baseline_commit=baseline_commit,
                        candidate_commit=br["candidate_commit"],
                        rollback_target=baseline_commit,
                    )
                    self._git("branch", "-f", ACCEPTED_BRANCH, br["candidate_commit"])
                else:
                    if br["scope_violation"]:
                        reason = f"scope_violation: {','.join(br['violations'])}"
                    elif not br["candidate_commit"]:
                        reason = "executor produced no repo changes"
                    elif winner_idx is None:
                        reason = "hard gates failed or evaluator rejected candidate"
                    else:
                        reason = f"k-branch: outranked by {branches[winner_idx]['run_id']}"
                    decision = RunDecision(
                        accepted=False,
                        reason=reason,
                        baseline_commit=baseline_commit,
                        candidate_commit=br["candidate_commit"],
                        rollback_target=baseline_commit,
                    )

                self._write_json(br["run_dir"] / "decision.json", decision.__dict__)
                plan_summary = ""
                try:
                    plan_summary = str(self._read_json(br["run_dir"] / "plan.json").get("summary", ""))
                except Exception:
                    pass
                self._write_json(
                    br["run_dir"] / "reflection.json",
                    {
                        "run_id": br["run_id"],
                        "accepted": decision.accepted,
                        "reason": decision.reason,
                        "plan_summary": plan_summary,
                        "metrics": br["evaluation"].get("metrics", {}),
                        "fitness": float(br["evaluation"].get("fitness", 0.0)),
                        "created_at": self._now(),
                    },
                )
                if not decision.accepted:
                    failed_dir = self.ledger_dir / "failed"
                    failed_dir.mkdir(parents=True, exist_ok=True)
                    self._write_json(failed_dir / f"{br['run_id']}-summary.json", decision.__dict__)
                if is_winner:
                    aggregated = dict(br["evaluation"])
                    aggregated["cost_usd"] = total_cost
                    aggregated["tokens_used"] = total_tokens
                    winner_result = RunResult(br["run_id"], br["run_dir"], br["worktree"], decision, aggregated)

            self._record_accepted_commit()

            if winner_result is None:
                # No branch passed hard gates: return the first branch as the
                # round outcome (so CLI hard-stop bookkeeping still ticks),
                # carrying the summed cost across all attempted branches.
                br = branches[0]
                decision_dict = self._read_json(br["run_dir"] / "decision.json")
                aggregated = dict(br["evaluation"])
                aggregated["cost_usd"] = total_cost
                aggregated["tokens_used"] = total_tokens
                winner_result = RunResult(
                    br["run_id"],
                    br["run_dir"],
                    br["worktree"],
                    RunDecision(**decision_dict),
                    aggregated,
                )
            return winner_result
        finally:
            for wt in worktrees:
                if Path(wt).exists():
                    try:
                        self._git("worktree", "remove", "--force", str(wt))
                    except Exception:
                        pass

    def _run_single_branch(
        self,
        goal: Mapping[str, Any],
        run_id: str,
        strategy: dict | None,
        baseline_commit: str,
    ) -> dict:
        """Run plan→execute→evaluate for one branch without promotion.

        The returned dict carries everything `run_once_parallel` needs to rank,
        promote, and record a per-branch decision after all k branches finish.
        """
        run_dir = self.ledger_dir / "runs" / run_id
        worktree = self.ledger_dir / "worktrees" / run_id
        worktree.parent.mkdir(parents=True, exist_ok=True)
        branch = f"evolution/experiment/{run_id}"
        self._git("worktree", "add", "-B", branch, str(worktree), baseline_commit)

        self._write_json(run_dir / "goal.json", dict(goal))
        if self.config_snapshot is not None:
            self._write_json(run_dir / "config.json", self.config_snapshot)

        observation_path = run_dir / "observation.json"
        observation = collect_observation(self.evidence_sources, self.target_repo)
        write_observation(observation_path, observation)

        planner_input: dict = {
            "run_id": run_id,
            "goal": goal,
            "accepted_branch": ACCEPTED_BRANCH,
            "baseline_commit": baseline_commit,
            "worktree": str(worktree),
            "ledger_dir": str(self.ledger_dir),
            "observation_path": str(observation_path),
            "allowed_paths": list(self.allowed_paths),
            "history": self._build_history(),
        }
        if strategy is not None:
            planner_input["strategy"] = strategy
        self._write_json(run_dir / "planner_input.json", planner_input)
        self._run_role(self.planner, run_dir / "planner_input.json", run_dir / "plan.json", worktree)

        self._write_json(
            run_dir / "executor_input.json",
            {
                "run_id": run_id,
                "goal": goal,
                "baseline_commit": baseline_commit,
                "plan_path": str(run_dir / "plan.json"),
                "worktree": str(worktree),
            },
        )
        self._run_role(
            self.executor,
            run_dir / "executor_input.json",
            run_dir / "executor_output.json",
            worktree,
        )

        candidate_commit = self._commit_candidate(worktree, run_id)
        (run_dir / "candidate_commit.txt").write_text(
            (candidate_commit or "") + "\n", encoding="utf-8"
        )
        if candidate_commit:
            patch = self._git_in(worktree, "diff", "--binary", baseline_commit, candidate_commit)
            if patch and not patch.endswith("\n"):
                patch += "\n"
        else:
            patch = ""
        (run_dir / "patch.diff").write_text(patch, encoding="utf-8")

        scope_report = self._enforce_scope(worktree, baseline_commit, candidate_commit)
        scope_violation = False
        violations: list[str] = []
        if scope_report is not None and not scope_report.ok:
            evaluation: dict = {
                "hard_gates_passed": False,
                "recommendation": "reject",
                "reason": "scope_violation",
                "violations": list(scope_report.violations),
                "changed_files": list(scope_report.changed_files),
                "allowed_paths": list(scope_report.allowed_paths),
                "fitness": 0.0,
                "metrics": {},
            }
            self._write_json(run_dir / "evaluation.json", evaluation)
            scope_violation = True
            violations = list(scope_report.violations)
        else:
            self._write_json(
                run_dir / "evaluator_input.json",
                {
                    "run_id": run_id,
                    "goal": goal,
                    "baseline_commit": baseline_commit,
                    "candidate_commit": candidate_commit,
                    "patch_path": str(run_dir / "patch.diff"),
                    "worktree": str(worktree),
                    "observation_path": str(observation_path),
                },
            )
            self._run_role(
                self.evaluator,
                run_dir / "evaluator_input.json",
                run_dir / "evaluation.json",
                worktree,
            )
            evaluation = dict(self._read_json(run_dir / "evaluation.json"))
            # Back-compat: synthesize a fitness when the evaluator omitted one.
            if "fitness" not in evaluation:
                evaluation["fitness"] = 1.0 if evaluation.get("hard_gates_passed") else 0.0

        return {
            "run_id": run_id,
            "run_dir": run_dir,
            "worktree": worktree,
            "candidate_commit": candidate_commit,
            "evaluation": evaluation,
            "scope_violation": scope_violation,
            "violations": violations,
        }

    @staticmethod
    def _select_winner(branches: Sequence[dict]) -> int | None:
        """Pick the branch with the highest fitness among those that (1) produced
        a commit, (2) survived scope check, (3) passed hard gates, and (4) the
        evaluator recommended `accept` or `promote`. Ties broken by branch order
        so behavior is deterministic for tests."""
        scored: list[tuple[float, int]] = []
        for i, br in enumerate(branches):
            if not br["candidate_commit"]:
                continue
            if br["scope_violation"]:
                continue
            ev = br["evaluation"]
            if not bool(ev.get("hard_gates_passed", False)):
                continue
            rec = str(ev.get("recommendation", "")).lower()
            if rec not in {"accept", "promote"}:
                continue
            try:
                fitness = float(ev.get("fitness", 0.0))
            except (TypeError, ValueError):
                fitness = 0.0
            scored.append((fitness, i))
        if not scored:
            return None
        scored.sort(key=lambda pair: (-pair[0], pair[1]))
        return scored[0][1]

    def _build_history(self) -> list[dict]:
        """Scan ledger for past run reflections; return most recent N entries."""
        runs_dir = self.ledger_dir / "runs"
        if not runs_dir.exists():
            return []
        entries = []
        for run_dir in sorted(runs_dir.iterdir()):
            reflection = run_dir / "reflection.json"
            if not reflection.exists():
                continue
            try:
                data = self._read_json(reflection)
                entries.append({
                    "run_id": data.get("run_id", run_dir.name),
                    "accepted": data.get("accepted", False),
                    "summary": data.get("plan_summary") or data.get("reason", ""),
                    "metrics": data.get("metrics", {}),
                })
            except Exception:
                pass
        return entries[-self.history_max_entries:]

    def _decide(
        self,
        evaluation: Mapping[str, Any],
        baseline_commit: str,
        candidate_commit: str | None,
    ) -> RunDecision:
        if not candidate_commit:
            return RunDecision(False, "executor produced no repo changes", baseline_commit, None, baseline_commit)
        hard_gates_passed = bool(evaluation.get("hard_gates_passed", False))
        recommended = str(evaluation.get("recommendation", "")).lower()
        if hard_gates_passed and recommended in {"accept", "promote"}:
            return RunDecision(True, "hard gates passed and evaluator recommended promotion", baseline_commit, candidate_commit, baseline_commit)
        return RunDecision(False, "hard gates failed or evaluator rejected candidate", baseline_commit, candidate_commit, baseline_commit)

    def _enforce_scope(
        self,
        worktree: Path,
        baseline_commit: str,
        candidate_commit: str | None,
    ) -> ScopeReport | None:
        """Return a ScopeReport when allowed_paths is configured, else None.

        When no candidate commit was produced, scope is vacuously satisfied.
        """
        if not self.allowed_paths:
            return None
        if not candidate_commit:
            return ScopeReport(ok=True, changed_files=(), violations=(), allowed_paths=self.allowed_paths)
        names_blob = self._git_in(worktree, "diff", "--name-only", baseline_commit, candidate_commit)
        changed = tuple(line for line in names_blob.splitlines() if line.strip())
        return check_scope(changed, self.allowed_paths)

    def _commit_candidate(self, worktree: Path, run_id: str) -> str | None:
        if not self._git_in(worktree, "status", "--porcelain").strip():
            return None
        self._git_in(worktree, "add", "-A")
        # Inject identity so commit succeeds even when target repo has no
        # global git user.email / user.name configured.
        self._git_in(
            worktree,
            "-c", "user.email=evolution@kernel.local",
            "-c", "user.name=evolution-kernel",
            "commit", "-m", f"evolution experiment {run_id}",
        )
        return self._git_in(worktree, "rev-parse", "HEAD")

    def _run_role(self, role: RoleCommand, input_path: Path, output_path: Path, worktree: Path) -> None:
        argv = [
            *role.argv,
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--worktree",
            str(worktree),
        ]
        completed = subprocess.run(argv, cwd=worktree, text=True, capture_output=True, check=False)
        if completed.stdout:
            (output_path.parent / f"{output_path.stem}.stdout.txt").write_text(completed.stdout, encoding="utf-8")
        if completed.stderr:
            (output_path.parent / f"{output_path.stem}.stderr.txt").write_text(completed.stderr, encoding="utf-8")
        if completed.returncode != 0:
            raise RuntimeError(f"role failed ({argv[0]}): exit {completed.returncode}")
        if not output_path.exists():
            raise RuntimeError(f"role did not write expected output: {output_path}")

    def _ensure_git_repo(self) -> None:
        if not (self.target_repo / ".git").exists():
            raise ValueError(f"target_repo is not a git repository: {self.target_repo}")

    def _ensure_accepted_branch(self) -> None:
        exists = subprocess.run(
            ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{ACCEPTED_BRANCH}"],
            cwd=self.target_repo,
            check=False,
        )
        if exists.returncode != 0:
            head = self._git("rev-parse", "HEAD")
            self._git("branch", ACCEPTED_BRANCH, head)
        self._record_accepted_commit()

    def _record_accepted_commit(self) -> None:
        accepted_dir = self.ledger_dir / "accepted"
        accepted_dir.mkdir(parents=True, exist_ok=True)
        (accepted_dir / "current_commit.txt").write_text(
            self._git("rev-parse", ACCEPTED_BRANCH) + "\n",
            encoding="utf-8",
        )

    def _next_run_id(self) -> str:
        runs = self.ledger_dir / "runs"
        runs.mkdir(parents=True, exist_ok=True)
        existing = [p.name for p in runs.iterdir() if p.is_dir() and p.name.isdigit()]
        return f"{(max([int(x) for x in existing], default=0) + 1):04d}"

    def _git(self, *args: str) -> str:
        return self._run(["git", *args], self.target_repo)

    def _git_in(self, cwd: Path, *args: str) -> str:
        return self._run(["git", *args], cwd)

    def _run(self, argv: Sequence[str], cwd: Path) -> str:
        completed = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(f"command failed: {' '.join(argv)}\n{completed.stderr}")
        return completed.stdout.strip()

    def _read_json(self, path: Path) -> Mapping[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_json(self, path: Path, data: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()


def reset_ledger_worktrees(ledger_dir: Path | str) -> None:
    worktrees = Path(ledger_dir) / "worktrees"
    if worktrees.exists():
        shutil.rmtree(worktrees)

