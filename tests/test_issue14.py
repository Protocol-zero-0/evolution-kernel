"""Tests for Issue #14: k-branch parallel exploration."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from evolution_kernel.config import ConfigError, parse_config
from evolution_kernel.governor import ACCEPTED_BRANCH, Governor, RoleCommand


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def _git(args, cwd):
    r = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=False)
    if r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {r.stderr}")
    return r.stdout.strip()


def _bootstrap_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(["init"], repo)
    _git(["config", "user.email", "test@example.com"], repo)
    _git(["config", "user.name", "Test"], repo)
    (repo / "README.md").write_text("# target\n")
    src = repo / "src"
    src.mkdir(exist_ok=True)
    (src / ".gitkeep").write_text("")
    _git(["add", "-A"], repo)
    _git(["commit", "-m", "initial"], repo)


def _role(name: str) -> RoleCommand:
    return RoleCommand([sys.executable, str(FIXTURES / name)])


# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------

class TestParallelConfig(unittest.TestCase):

    def test_default_k_is_one(self):
        cfg = parse_config({"mission": "x"})
        self.assertEqual(cfg.parallel.k_branches, 1)

    def test_custom_k_parsed(self):
        cfg = parse_config({"mission": "x", "parallel": {"k_branches": 4}})
        self.assertEqual(cfg.parallel.k_branches, 4)

    def test_k_must_be_positive(self):
        with self.assertRaises(ConfigError):
            parse_config({"mission": "x", "parallel": {"k_branches": 0}})

    def test_k_must_be_int(self):
        with self.assertRaises(ConfigError):
            parse_config({"mission": "x", "parallel": {"k_branches": "two"}})


# ---------------------------------------------------------------------------
# Governor — parallel core behavior
# ---------------------------------------------------------------------------

class TestParallelGovernor(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.repo = self.base / "repo"
        self.ledger = self.base / "ledger"
        _bootstrap_repo(self.repo)
        self._saved_env: dict[str, str | None] = {}

    def tearDown(self):
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmp.cleanup()

    def _set_env(self, key: str, value: str) -> None:
        self._saved_env.setdefault(key, os.environ.get(key))
        os.environ[key] = value

    def _gov(
        self,
        executor: str = "executor_branch.py",
        evaluator: str = "evaluator_branch_fitness.py",
        allowed_paths=(),
    ) -> Governor:
        return Governor(
            target_repo=self.repo,
            ledger_dir=self.ledger,
            planner=_role("planner.py"),
            executor=_role(executor),
            evaluator=_role(evaluator),
            allowed_paths=allowed_paths,
        )

    # ---- Done-when #3 coverage ----

    def test_k_equal_one_matches_run_once(self):
        """k=1 must delegate to run_once and return identical result shape."""
        gov = self._gov()
        result = gov.run_once_parallel({"name": "t", "objective": "t"}, k=1)
        # Single-branch run_id allocator returns "0001".
        self.assertEqual(result.run_id, "0001")
        self.assertTrue(result.decision.accepted)
        # Only one run dir created.
        runs = sorted((self.ledger / "runs").iterdir())
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].name, "0001")

    def test_k_greater_than_one_creates_k_run_dirs(self):
        """k=3 spawns three independent run dirs in one round, each with full
        per-branch artifacts (planner_input, plan, evaluator_input, evaluation)."""
        self._set_env("EK_TEST_FITNESS_0001", "0.2")
        self._set_env("EK_TEST_FITNESS_0002", "0.9")
        self._set_env("EK_TEST_FITNESS_0003", "0.5")
        gov = self._gov()
        gov.run_once_parallel({"name": "t", "objective": "t"}, k=3)
        runs = sorted((self.ledger / "runs").iterdir())
        self.assertEqual([p.name for p in runs], ["0001", "0002", "0003"])
        for run_dir in runs:
            for artifact in (
                "planner_input.json", "plan.json",
                "executor_input.json", "executor_output.json",
                "evaluation.json", "decision.json", "reflection.json",
            ):
                self.assertTrue((run_dir / artifact).exists(),
                                f"missing {artifact} in {run_dir.name}")

    def test_highest_fitness_branch_is_accepted(self):
        """The branch with the highest fitness must be the one promoted."""
        self._set_env("EK_TEST_FITNESS_0001", "0.2")
        self._set_env("EK_TEST_FITNESS_0002", "0.9")
        self._set_env("EK_TEST_FITNESS_0003", "0.5")
        gov = self._gov()
        result = gov.run_once_parallel({"name": "t", "objective": "t"}, k=3)
        self.assertEqual(result.run_id, "0002")
        self.assertTrue(result.decision.accepted)
        winner_decision = json.loads(
            (self.ledger / "runs" / "0002" / "decision.json").read_text()
        )
        self.assertTrue(winner_decision["accepted"])
        # evolution/accepted now points at the winner's candidate commit.
        accepted_sha = _git(["rev-parse", ACCEPTED_BRANCH], self.repo)
        self.assertEqual(accepted_sha, winner_decision["candidate_commit"])

    def test_losing_branches_recorded_in_failed(self):
        """Non-winning branches land in ledger/failed/ with a "outranked by"
        reason that names the winner."""
        self._set_env("EK_TEST_FITNESS_0001", "0.2")
        self._set_env("EK_TEST_FITNESS_0002", "0.9")
        self._set_env("EK_TEST_FITNESS_0003", "0.5")
        gov = self._gov()
        gov.run_once_parallel({"name": "t", "objective": "t"}, k=3)
        failed = self.ledger / "failed"
        loser_files = sorted(p.name for p in failed.iterdir())
        self.assertEqual(loser_files, ["0001-summary.json", "0003-summary.json"])
        for fname in loser_files:
            data = json.loads((failed / fname).read_text())
            self.assertFalse(data["accepted"])
            self.assertIn("outranked by 0002", data["reason"])

    def test_all_worktrees_cleaned_up(self):
        """Every per-branch worktree must be removed after the round, even
        though their experiment branches stay around for audit."""
        self._set_env("EK_TEST_FITNESS_0001", "0.4")
        self._set_env("EK_TEST_FITNESS_0002", "0.7")
        self._set_env("EK_TEST_FITNESS_0003", "0.1")
        gov = self._gov()
        gov.run_once_parallel({"name": "t", "objective": "t"}, k=3)
        worktree_root = self.ledger / "worktrees"
        if worktree_root.exists():
            remaining = list(worktree_root.iterdir())
            self.assertEqual(remaining, [],
                             f"orphan worktrees: {[p.name for p in remaining]}")
        # All three experiment branches should still exist (only the checkout
        # is gone, not the audit trail).
        branches_blob = _git(["branch", "--list", "evolution/experiment/*"], self.repo)
        self.assertEqual(
            sorted(line.strip().lstrip("* ") for line in branches_blob.splitlines() if line.strip()),
            ["evolution/experiment/0001", "evolution/experiment/0002", "evolution/experiment/0003"],
        )

    def test_cost_and_tokens_summed_across_k_branches(self):
        """The aggregated cost/tokens returned for hard-stop bookkeeping must be
        the sum of all k per-branch evaluator reports."""
        self._set_env("EK_TEST_FITNESS_0001", "0.3")
        self._set_env("EK_TEST_FITNESS_0002", "0.8")
        self._set_env("EK_TEST_FITNESS_0003", "0.5")
        gov = self._gov()
        result = gov.run_once_parallel({"name": "t", "objective": "t"}, k=3)
        # evaluator_branch_fitness.py reports cost=0.01 and tokens=100 per branch.
        self.assertAlmostEqual(float(result.evaluation["cost_usd"]), 0.03, places=6)
        self.assertEqual(int(result.evaluation["tokens_used"]), 300)

    def test_partial_scope_violation_does_not_block_other_branches(self):
        """If one branch writes outside `allowed_paths` while siblings stay
        in-scope, the violator is rejected and the highest-fitness in-scope
        branch is still promoted normally."""
        self._set_env("EK_TEST_FITNESS_0001", "0.4")
        self._set_env("EK_TEST_FITNESS_0002", "0.9")  # violator
        self._set_env("EK_TEST_FITNESS_0003", "0.6")
        self._set_env("EK_TEST_OOB_RUN_ID", "0002")
        gov = self._gov(
            executor="executor_oob_for_run.py",
            evaluator="evaluator_src_fitness.py",
            allowed_paths=("src/",),
        )
        result = gov.run_once_parallel({"name": "t", "objective": "t"}, k=3)
        # 0003 has highest in-scope fitness (0.6); 0002's 0.9 was discarded.
        self.assertEqual(result.run_id, "0003")
        violator_eval = json.loads(
            (self.ledger / "runs" / "0002" / "evaluation.json").read_text()
        )
        self.assertEqual(violator_eval["reason"], "scope_violation")
        violator_decision = json.loads(
            (self.ledger / "failed" / "0002-summary.json").read_text()
        )
        self.assertIn("scope_violation", violator_decision["reason"])

    def test_no_branch_passes_means_accepted_unchanged(self):
        """When every branch fails hard gates, the accepted branch must not
        move and no winner is promoted."""
        # `evolution/accepted` is created lazily by the first run; track HEAD
        # before instead, which is what the kernel seeds the accepted branch
        # from on its very first invocation.
        before = _git(["rev-parse", "HEAD"], self.repo)
        self._set_env("EK_TEST_FITNESS_0001", "0")
        self._set_env("EK_TEST_FITNESS_0002", "0")
        self._set_env("EK_TEST_FITNESS_0003", "0")
        gov = self._gov()
        result = gov.run_once_parallel({"name": "t", "objective": "t"}, k=3)
        self.assertFalse(result.decision.accepted)
        after = _git(["rev-parse", ACCEPTED_BRANCH], self.repo)
        self.assertEqual(before, after)
        failed_files = sorted(p.name for p in (self.ledger / "failed").iterdir())
        self.assertEqual(
            failed_files,
            ["0001-summary.json", "0002-summary.json", "0003-summary.json"],
        )


# ---------------------------------------------------------------------------
# CLI integration — k=3 over 3 rounds (Done-when #4)
# ---------------------------------------------------------------------------

class TestParallelCliLoop(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.repo = self.base / "repo"
        self.ledger = str(self.base / "ledger")
        _bootstrap_repo(self.repo)

    def tearDown(self):
        self._tmp.cleanup()

    def test_k3_three_rounds_produces_9_runs_with_one_winner_each(self):
        config_path = self.base / "evolution.yml"
        config_path.write_text(f"""
mission: "parallel exploration"
parallel:
  k_branches: 3
hard_stops:
  max_iterations: 3
  max_consecutive_failures: 5
roles:
  planner:   ["python3", "{FIXTURES}/planner.py"]
  executor:  ["python3", "{FIXTURES}/executor_unique_marker.py"]
  evaluator: ["python3", "{FIXTURES}/evaluator_accept.py"]
""")
        from evolution_kernel.cli import main
        rc = main([
            "--config", str(config_path),
            "--repo", str(self.repo),
            "--ledger", self.ledger,
            "--loop",
        ])
        # 3 rounds × k=3 = 9 run dirs, halted by max_iterations.
        self.assertEqual(rc, 3)
        runs = sorted((Path(self.ledger) / "runs").iterdir())
        self.assertEqual(len(runs), 9)
        # Per round (3 sibling run_ids), exactly one accepted and two demoted.
        accepted_count = 0
        for run_dir in runs:
            decision = json.loads((run_dir / "decision.json").read_text())
            if decision["accepted"]:
                accepted_count += 1
        self.assertEqual(accepted_count, 3)
        # Per round, 2 demoted → 6 failed summaries total.
        failed = list((Path(self.ledger) / "failed").iterdir())
        self.assertEqual(len(failed), 6)


if __name__ == "__main__":
    unittest.main()
