from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from evolution_kernel import Governor, RoleCommand


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def run(argv, cwd):
    completed = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise AssertionError(f"command failed: {' '.join(argv)}\n{completed.stderr}")
    return completed.stdout.strip()


class GovernorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.repo = self.base / "repo"
        self.ledger = self.base / "ledger"
        self.repo.mkdir()
        run(["git", "init"], self.repo)
        run(["git", "config", "user.email", "test@example.com"], self.repo)
        run(["git", "config", "user.name", "Test User"], self.repo)
        (self.repo / "README.md").write_text("# target\n", encoding="utf-8")
        run(["git", "add", "-A"], self.repo)
        run(["git", "commit", "-m", "initial"], self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def role(self, name):
        return RoleCommand([sys.executable, str(FIXTURES / name)])

    def test_promotes_candidate_on_acceptance(self):
        result = Governor(
            self.repo,
            self.ledger,
            self.role("planner.py"),
            self.role("executor.py"),
            self.role("evaluator_accept.py"),
        ).run_once({"name": "test"}, run_id="0001")

        self.assertTrue(result.decision.accepted)
        accepted = run(["git", "rev-parse", "evolution/accepted"], self.repo)
        self.assertEqual(accepted, result.decision.candidate_commit)
        self.assertTrue((self.ledger / "runs" / "0001" / "patch.diff").exists())
        self.assertTrue((self.ledger / "runs" / "0001" / "decision.json").exists())
        self.assertFalse((self.ledger / "worktrees" / "0001").exists())

    def test_rejects_candidate_without_moving_accepted_branch(self):
        governor = Governor(
            self.repo,
            self.ledger,
            self.role("planner.py"),
            self.role("executor.py"),
            self.role("evaluator_reject.py"),
        )
        before = run(["git", "rev-parse", "HEAD"], self.repo)
        result = governor.run_once({"name": "test"}, run_id="0001")

        self.assertFalse(result.decision.accepted)
        accepted = run(["git", "rev-parse", "evolution/accepted"], self.repo)
        self.assertEqual(accepted, before)
        self.assertTrue((self.ledger / "failed" / "0001-summary.json").exists())

    def test_ledger_contains_role_handoff_files(self):
        Governor(
            self.repo,
            self.ledger,
            self.role("planner.py"),
            self.role("executor.py"),
            self.role("evaluator_accept.py"),
        ).run_once({"name": "test"}, run_id="0001")

        run_dir = self.ledger / "runs" / "0001"
        expected = [
            "planner_input.json",
            "plan.json",
            "executor_input.json",
            "executor_output.json",
            "evaluator_input.json",
            "evaluation.json",
            "decision.json",
            "reflection.json",
            "observation.json",
            "candidate_commit.txt",
        ]
        for filename in expected:
            self.assertTrue((run_dir / filename).exists(), filename)
        decision = json.loads((run_dir / "decision.json").read_text(encoding="utf-8"))
        self.assertEqual(decision["rollback_target"], decision["baseline_commit"])

    def test_ledger_contains_observation_and_candidate_commit(self):
        Governor(
            self.repo,
            self.ledger,
            self.role("planner.py"),
            self.role("executor.py"),
            self.role("evaluator_accept.py"),
        ).run_once({"name": "test"}, run_id="0001")

        run_dir = self.ledger / "runs" / "0001"
        self.assertTrue((run_dir / "observation.json").exists())
        self.assertTrue((run_dir / "candidate_commit.txt").exists())

    def test_scope_violation_rejects_without_calling_evaluator(self):
        # executor writes EVOLUTION_MARKER.txt; allowed_paths only allows "src/"
        result = Governor(
            self.repo,
            self.ledger,
            self.role("planner.py"),
            self.role("executor.py"),
            self.role("evaluator_accept.py"),
            allowed_paths=["src/"],
        ).run_once({"name": "test"}, run_id="0001")

        self.assertFalse(result.decision.accepted)
        self.assertEqual(result.decision.reason, "scope_violation")
        decision = json.loads(
            (self.ledger / "runs" / "0001" / "decision.json").read_text(encoding="utf-8")
        )
        self.assertIn("violated_paths", decision)
        self.assertTrue(len(decision["violated_paths"]) > 0)
        # evaluator was NOT called — no evaluation.json
        self.assertFalse((self.ledger / "runs" / "0001" / "evaluation.json").exists())

    def test_observation_injected_into_planner_input(self):
        from evolution_kernel.config import EvidenceSource
        sources = (EvidenceSource(type="shell", command="echo hello-obs"),)
        Governor(
            self.repo,
            self.ledger,
            self.role("planner.py"),
            self.role("executor.py"),
            self.role("evaluator_accept.py"),
            observation_sources=sources,
        ).run_once({"name": "test"}, run_id="0001")

        planner_input = json.loads(
            (self.ledger / "runs" / "0001" / "planner_input.json").read_text(encoding="utf-8")
        )
        self.assertIn("observation", planner_input)
        obs_sources = planner_input["observation"]["sources"]
        self.assertTrue(any("hello-obs" in s.get("stdout", "") for s in obs_sources))


if __name__ == "__main__":
    unittest.main()

