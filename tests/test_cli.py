from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def run(argv, cwd):
    completed = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise AssertionError(f"command failed: {' '.join(argv)}\n{completed.stderr}")
    return completed.stdout.strip()


class CliTests(unittest.TestCase):
    def test_cli_runs_one_experiment(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo = base / "repo"
            ledger = base / "ledger"
            goal = base / "goal.json"
            repo.mkdir()
            run(["git", "init"], repo)
            run(["git", "config", "user.email", "test@example.com"], repo)
            run(["git", "config", "user.name", "Test User"], repo)
            (repo / "README.md").write_text("# target\n", encoding="utf-8")
            run(["git", "add", "-A"], repo)
            run(["git", "commit", "-m", "initial"], repo)
            goal.write_text(json.dumps({"name": "cli-smoke"}), encoding="utf-8")

            output = run(
                [
                    sys.executable,
                    "-m",
                    "evolution_kernel.cli",
                    "--repo",
                    str(repo),
                    "--ledger",
                    str(ledger),
                    "--goal",
                    str(goal),
                    "--planner",
                    sys.executable,
                    str(FIXTURES / "planner.py"),
                    "--executor",
                    sys.executable,
                    str(FIXTURES / "executor.py"),
                    "--evaluator",
                    sys.executable,
                    str(FIXTURES / "evaluator_accept.py"),
                    "--run-id",
                    "0001",
                ],
                ROOT,
            )

            data = json.loads(output)
            self.assertTrue(data["accepted"])
            self.assertTrue((ledger / "runs" / "0001" / "decision.json").exists())


if __name__ == "__main__":
    unittest.main()

