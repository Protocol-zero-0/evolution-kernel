from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


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
        *,
        observation_sources: Sequence[Any] | None = None,
        allowed_paths: Sequence[str] | None = None,
    ) -> None:
        self.target_repo = Path(target_repo).resolve()
        self.ledger_dir = Path(ledger_dir).resolve()
        self.planner = planner
        self.executor = executor
        self.evaluator = evaluator
        self._observation_sources = observation_sources
        self._allowed_paths = tuple(allowed_paths) if allowed_paths else ()

    def run_once(self, goal: Mapping[str, Any], run_id: str | None = None) -> RunResult:
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

            # Collect evidence before planning (worktree is already checked out at this point)
            observation: dict[str, Any] = {}
            if self._observation_sources:
                from .observer import Observer
                observation = Observer().run(self._observation_sources, worktree, run_dir)
            else:
                observation = {"sources": []}
                self._write_json(run_dir / "observation.json", observation)

            self._write_json(
                run_dir / "planner_input.json",
                {
                    "run_id": run_id,
                    "goal": goal,
                    "accepted_branch": ACCEPTED_BRANCH,
                    "baseline_commit": baseline_commit,
                    "worktree": str(worktree),
                    "ledger_dir": str(self.ledger_dir),
                    "observation": observation,
                },
            )
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

            if self._allowed_paths:
                violated = self._check_scope(worktree)
                if violated:
                    decision = RunDecision(
                        False, "scope_violation", baseline_commit, None, baseline_commit
                    )
                    (run_dir / "candidate_commit.txt").write_text("", encoding="utf-8")
                    self._write_json(
                        run_dir / "decision.json",
                        {**decision.__dict__, "violated_paths": violated, "scope_violation": True},
                    )
                    self._write_json(
                        run_dir / "reflection.json",
                        {
                            "run_id": run_id,
                            "accepted": False,
                            "reason": "scope_violation",
                            "metrics": {},
                            "created_at": self._now(),
                        },
                    )
                    return RunResult(run_id, run_dir, worktree, decision, {})

            patch = self._git_in(worktree, "diff", "--binary")
            (run_dir / "patch.diff").write_text(patch, encoding="utf-8")
            candidate_commit = self._commit_candidate(worktree, run_id)
            (run_dir / "candidate_commit.txt").write_text(
                (candidate_commit or "") + "\n", encoding="utf-8"
            )

            self._write_json(
                run_dir / "evaluator_input.json",
                {
                    "run_id": run_id,
                    "goal": goal,
                    "baseline_commit": baseline_commit,
                    "candidate_commit": candidate_commit,
                    "patch_path": str(run_dir / "patch.diff"),
                    "worktree": str(worktree),
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
            self._write_json(
                run_dir / "reflection.json",
                {
                    "run_id": run_id,
                    "accepted": decision.accepted,
                    "reason": decision.reason,
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

    def _check_scope(self, worktree: Path) -> list[str]:
        """Return paths changed outside allowed_paths. Empty list means no violation."""
        lines = self._git_in(worktree, "status", "--porcelain").splitlines()
        changed: list[str] = []
        for line in lines:
            if len(line) < 4:
                continue
            # porcelain format: "XY filename" or "XY old -> new" (rename)
            name_part = line[3:]
            parts = name_part.split(" -> ")
            changed.append(parts[-1].strip())
        return [
            f for f in changed
            if not any(f.startswith(p) for p in self._allowed_paths)
        ]

    def _commit_candidate(self, worktree: Path, run_id: str) -> str | None:
        if not self._git_in(worktree, "status", "--porcelain").strip():
            return None
        self._git_in(worktree, "add", "-A")
        self._git_in(worktree, "commit", "-m", f"evolution experiment {run_id}")
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

