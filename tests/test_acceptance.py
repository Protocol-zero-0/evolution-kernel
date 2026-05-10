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
    def test_hard_stop_blocks_then_reset_allows_via_cli(self):
        """End-to-end: drive the real CLI so the persistent state path is exercised.

        Plan: a config with max_consecutive_failures=1 + a rejecting evaluator
        means run #1 runs, run #2 must be halted. After --reset, run #3 runs
        again. Every step asserts CLI exit code + stdout shape.
        """
        # Build a minimal config that points the rejecting evaluator at our repo.
        cfg_path = self.base / "evolution.yml"
        cfg_path.write_text(
            "mission: hard-stop e2e\n"
            "evidence_sources:\n"
            "  - type: shell\n"
            "    command: \"echo hs\"\n"
            "mutation_scope:\n"
            "  allowed_paths: []\n"  # no mutations are allowed -> always reject
            "hard_stops:\n"
            "  max_iterations: 10\n"
            "  max_consecutive_failures: 1\n"
            f"roles:\n"
            f"  planner:   [\"{sys.executable}\", \"{FIXTURES / 'planner.py'}\"]\n"
            f"  executor:  [\"{sys.executable}\", \"{FIXTURES / 'executor.py'}\"]\n"
            f"  evaluator: [\"{sys.executable}\", \"{FIXTURES / 'evaluator_reject.py'}\"]\n",
            encoding="utf-8",
        )

        def _cli(*extra: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                [sys.executable, "-m", "evolution_kernel.cli", *extra],
                cwd=ROOT, text=True, capture_output=True, check=False,
            )

        # Run #1: should run, return rejection (executor produces no changes
        # because allowed_paths is empty + evaluator_reject also rejects).
        r1 = _cli(
            "--config", str(cfg_path),
            "--repo", str(self.repo),
            "--ledger", str(self.ledger),
            "--run-id", "0001",
        )
        self.assertEqual(r1.returncode, 0, f"run1 unexpected exit: {r1.stderr}")

        # Run #2: should be halted by max_consecutive_failures=1.
        r2 = _cli(
            "--config", str(cfg_path),
            "--repo", str(self.repo),
            "--ledger", str(self.ledger),
            "--run-id", "0002",
        )
        self.assertEqual(r2.returncode, 3, f"run2 was not halted: {r2.stdout}")
        out2 = json.loads(r2.stdout)
        self.assertTrue(out2["halted"])
        self.assertIn("max_consecutive_failures", out2["reason"])
        # Halt event must be recorded in the ledger so it can be reviewed later.
        halted_files = list((self.ledger / "halted").glob("*.json"))
        self.assertGreaterEqual(len(halted_files), 1, "halted ledger entry missing")

        # Reset clears the state and run #3 runs again.
        r_reset = _cli("--reset", "--ledger", str(self.ledger))
        self.assertEqual(r_reset.returncode, 0)
        self.assertTrue(json.loads(r_reset.stdout)["reset"])

        r3 = _cli(
            "--config", str(cfg_path),
            "--repo", str(self.repo),
            "--ledger", str(self.ledger),
            "--run-id", "0003",
        )
        self.assertEqual(r3.returncode, 0, f"run3 was not allowed after reset: {r3.stdout}")

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

        # patch.diff must actually contain the mutation. A 0-byte file would
        # mean the ledger is technically present but useless for replay.
        patch = (run_dir / "patch.diff").read_text(encoding="utf-8")
        self.assertTrue(patch.strip(), "patch.diff is empty")
        self.assertIn("EVOLUTION_MARKER.txt", patch)
        # `git apply` rejects patches without a trailing newline as corrupt;
        # the ledger must be replayable, not just non-empty.
        self.assertTrue(
            patch.endswith("\n"),
            "patch.diff is missing the trailing newline `git apply` requires",
        )
        # `git apply --numstat` parses the patch fully without touching the
        # working tree, so it catches "corrupt patch at line N" syntax errors
        # regardless of which commit is currently checked out.
        numstat = subprocess.run(
            ["git", "apply", "--numstat", str(run_dir / "patch.diff")],
            cwd=self.repo, text=True, capture_output=True, check=False,
        )
        self.assertEqual(
            numstat.returncode, 0,
            f"patch.diff is not parseable by `git apply`: {numstat.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
