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


class CliConfigTests(unittest.TestCase):
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

    def _write_config(self, **overrides) -> Path:
        import yaml
        cfg = {
            "mission": "test mission",
            "roles": {
                "planner": [sys.executable, str(FIXTURES / "planner.py")],
                "executor": [sys.executable, str(FIXTURES / "executor.py")],
                "evaluator": [sys.executable, str(FIXTURES / "evaluator_accept.py")],
            },
        }
        cfg.update(overrides)
        p = self.base / "evolution.yml"
        p.write_text(yaml.dump(cfg), encoding="utf-8")
        return p

    def test_config_flag_runs_experiment(self):
        cfg_path = self._write_config()
        output = run(
            [
                sys.executable, "-m", "evolution_kernel.cli",
                "--config", str(cfg_path),
                "--repo", str(self.repo),
                "--ledger", str(self.ledger),
                "--run-id", "0001",
            ],
            ROOT,
        )
        data = json.loads(output)
        self.assertTrue(data["accepted"])

    def test_reset_flag_clears_state(self):
        import json as _json
        state_file = self.ledger / "state.json"
        self.ledger.mkdir(parents=True, exist_ok=True)
        state_file.write_text(_json.dumps({"iterations": 5, "consecutive_failures": 3}), encoding="utf-8")

        run(
            [
                sys.executable, "-m", "evolution_kernel.cli",
                "--reset",
                "--ledger", str(self.ledger),
            ],
            ROOT,
        )

        data = _json.loads(state_file.read_text(encoding="utf-8"))
        self.assertEqual(data["iterations"], 0)
        self.assertEqual(data["consecutive_failures"], 0)


if __name__ == "__main__":
    unittest.main()

