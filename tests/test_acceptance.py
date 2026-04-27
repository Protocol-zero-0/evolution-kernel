"""End-to-end acceptance tests for issue #1 MVP requirements.

Each test maps directly to one of the six acceptance bullets in the issue:

1. accept advances ``evolution/accepted``
2. reject does not advance ``evolution/accepted``
3. an out-of-scope mutation is rejected and logged as ``scope_violation``
4. the observer produces ``observation.json`` from file + shell sources
5. hard stops block subsequent runs after the limit; ``reset`` re-enables them
6. the ledger contains every required artifact for one run
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from evolution_kernel import hard_stops
from evolution_kernel.config import EvidenceSource
from evolution_kernel.governor import ACCEPTED_BRANCH, Governor, RoleCommand


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def _git(args, cwd):
    completed = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed in {cwd}: {completed.stderr}")
    return completed.stdout.strip()


def _bootstrap_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(["init"], repo)
    _git(["config", "user.email", "test@example.com"], repo)
    _git(["config", "user.name", "Test User"], repo)
    (repo / "README.md").write_text("# target\n", encoding="utf-8")
    (repo / "metrics.json").write_text(json.dumps({"score": 0.5}) + "\n", encoding="utf-8")
    src = repo / "src"
    src.mkdir(exist_ok=True)
    (src / ".gitkeep").write_text("", encoding="utf-8")
    _git(["add", "-A"], repo)
    _git(["commit", "-m", "initial"], repo)


def _role(name: str) -> RoleCommand:
    return RoleCommand([sys.executable, str(FIXTURES / name)])


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.repo = self.base / "repo"
        self.ledger = self.base / "ledger"
        _bootstrap_repo(self.repo)

    def tearDown(self):
        self._tmp.cleanup()

    # ------- 1. accept advances evolution/accepted -----------------------------
    def test_accept_advances_accepted_branch(self):
        result = Governor(
            self.repo, self.ledger,
            _role("planner.py"), _role("executor.py"), _role("evaluator_accept.py"),
        ).run_once({"name": "accept"}, run_id="0001")
        self.assertTrue(result.decision.accepted)
        accepted_commit = _git(["rev-parse", ACCEPTED_BRANCH], self.repo)
        self.assertEqual(accepted_commit, result.decision.candidate_commit)

    # ------- 2. reject does not advance evolution/accepted ---------------------
    def test_reject_does_not_advance_accepted_branch(self):
        before = _git(["rev-parse", "HEAD"], self.repo)
        result = Governor(
            self.repo, self.ledger,
            _role("planner.py"), _role("executor.py"), _role("evaluator_reject.py"),
        ).run_once({"name": "reject"}, run_id="0001")
        self.assertFalse(result.decision.accepted)
        accepted_commit = _git(["rev-parse", ACCEPTED_BRANCH], self.repo)
        self.assertEqual(accepted_commit, before)

    # ------- 3. out-of-scope mutation is rejected as scope_violation ----------
    def test_scope_violation_is_rejected_and_logged(self):
        before = _git(["rev-parse", "HEAD"], self.repo)
        result = Governor(
            self.repo, self.ledger,
            _role("planner.py"), _role("executor_oob.py"), _role("evaluator_accept.py"),
            allowed_paths=("src/",),
        ).run_once({"name": "scope"}, run_id="0001")

        self.assertFalse(result.decision.accepted)
        self.assertTrue(result.decision.reason.startswith("scope_violation"))

        evaluation = json.loads((self.ledger / "runs" / "0001" / "evaluation.json").read_text(encoding="utf-8"))
        self.assertEqual(evaluation["reason"], "scope_violation")
        self.assertIn("README.md", evaluation["violations"])

        # accepted branch must not move on a scope violation
        self.assertEqual(_git(["rev-parse", ACCEPTED_BRANCH], self.repo), before)

    # ------- 4. observer produces observation.json from file + shell ----------
    def test_observer_writes_observation_with_file_and_shell(self):
        sources = (
            EvidenceSource(type="file", path="metrics.json"),
            EvidenceSource(type="shell", command="echo hello-observer"),
        )
        Governor(
            self.repo, self.ledger,
            _role("planner.py"), _role("executor.py"), _role("evaluator_accept.py"),
            evidence_sources=sources,
        ).run_once({"name": "observer"}, run_id="0001")

        obs_path = self.ledger / "runs" / "0001" / "observation.json"
        self.assertTrue(obs_path.exists())
        observation = json.loads(obs_path.read_text(encoding="utf-8"))
        kinds = [s["type"] for s in observation["sources"]]
        self.assertEqual(kinds, ["file", "shell"])
        self.assertIn("score", observation["sources"][0]["content"])
        self.assertIn("hello-observer", observation["sources"][1]["stdout"])

    # ------- 5. hard stops block then reset re-enables -------------------------
    def test_hard_stop_blocks_then_reset_allows(self):
        max_iterations = 5
        max_failures = 2
        state = hard_stops.load_state(self.ledger)
        # two consecutive failures
        for _ in range(2):
            state = hard_stops.record_outcome(
                state, accepted=False,
                max_iterations=max_iterations, max_consecutive_failures=max_failures,
            )
        hard_stops.save_state(self.ledger, state)

        allowed, reason = hard_stops.precheck(
            hard_stops.load_state(self.ledger), max_iterations, max_failures,
        )
        self.assertFalse(allowed)
        self.assertIn("max_consecutive_failures", reason)

        cleared = hard_stops.reset(self.ledger)
        self.assertTrue(cleared)

        allowed_again, _ = hard_stops.precheck(
            hard_stops.load_state(self.ledger), max_iterations, max_failures,
        )
        self.assertTrue(allowed_again)

    # ------- 6. ledger contains every required artifact -----------------------
    def test_ledger_contains_all_required_artifacts(self):
        sources = (EvidenceSource(type="shell", command="echo evidence"),)
        Governor(
            self.repo, self.ledger,
            _role("planner.py"), _role("executor.py"), _role("evaluator_accept.py"),
            evidence_sources=sources,
            allowed_paths=("EVOLUTION_MARKER.txt",),
            config_snapshot={"mission": "demo"},
        ).run_once({"name": "ledger"}, run_id="0001")

        run_dir = self.ledger / "runs" / "0001"
        required = [
            "goal.json",
            "config.json",
            "observation.json",
            "plan.json",
            "patch.diff",
            "candidate_commit.txt",
            "evaluation.json",
            "decision.json",
            "reflection.json",
        ]
        for name in required:
            self.assertTrue((run_dir / name).exists(), f"missing ledger artifact: {name}")

        commit = (run_dir / "candidate_commit.txt").read_text(encoding="utf-8").strip()
        self.assertTrue(commit, "candidate_commit.txt is empty")


if __name__ == "__main__":
    unittest.main()
