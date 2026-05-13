"""Tests for Issue #10: Goal Evaluator + Strategist."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from evolution_kernel import hard_stops
from evolution_kernel.config import parse_config
from evolution_kernel.governor import ACCEPTED_BRANCH, Governor, RoleCommand


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def _git(args, cwd):
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()


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
# Config parsing — new fields
# ---------------------------------------------------------------------------

class TestNewConfigFields(unittest.TestCase):

    def test_goal_evaluator_defaults(self):
        cfg = parse_config({"mission": "x"})
        self.assertFalse(cfg.goal_evaluator.enabled)

    def test_goal_evaluator_enabled(self):
        cfg = parse_config({"mission": "x", "goal_evaluator": {"enabled": True}})
        self.assertTrue(cfg.goal_evaluator.enabled)

    def test_strategist_defaults(self):
        cfg = parse_config({"mission": "x"})
        self.assertFalse(cfg.strategist.enabled)
        self.assertEqual(cfg.strategist.every_n_rounds, 3)

    def test_strategist_custom(self):
        cfg = parse_config({"mission": "x", "strategist": {"enabled": True, "every_n_rounds": 5}})
        self.assertTrue(cfg.strategist.enabled)
        self.assertEqual(cfg.strategist.every_n_rounds, 5)

    def test_strategist_every_n_rounds_invalid(self):
        from evolution_kernel.config import ConfigError
        with self.assertRaises(ConfigError):
            parse_config({"mission": "x", "strategist": {"every_n_rounds": 0}})

    def test_roles_goal_evaluator_parsed(self):
        cfg = parse_config({"mission": "x", "roles": {"goal_evaluator": ["python3", "eval.py"],
                                                        "planner": ["p"], "executor": ["e"], "evaluator": ["ev"]}})
        self.assertEqual(cfg.roles.goal_evaluator, ("python3", "eval.py"))

    def test_roles_strategist_parsed(self):
        cfg = parse_config({"mission": "x", "roles": {"strategist": ["python3", "strat.py"],
                                                        "planner": ["p"], "executor": ["e"], "evaluator": ["ev"]}})
        self.assertEqual(cfg.roles.strategist, ("python3", "strat.py"))


# ---------------------------------------------------------------------------
# Governor — strategy injection
# ---------------------------------------------------------------------------

class TestStrategyInjection(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.repo = self.base / "repo"
        self.ledger = self.base / "ledger"
        _bootstrap_repo(self.repo)

    def tearDown(self):
        self._tmp.cleanup()

    def _make_governor(self) -> Governor:
        return Governor(
            target_repo=self.repo,
            ledger_dir=self.ledger,
            planner=_role("planner.py"),
            executor=_role("executor.py"),
            evaluator=_role("evaluator_accept.py"),
        )

    def test_strategy_appears_in_planner_input(self):
        gov = self._make_governor()
        strategy = {"stage": "test", "next_milestone": "m1", "taboo_directions": []}
        gov.run_once({"name": "t", "objective": "t"}, strategy=strategy)
        planner_input = json.loads(
            (self.ledger / "runs" / "0001" / "planner_input.json").read_text()
        )
        self.assertEqual(planner_input["strategy"], strategy)

    def test_no_strategy_key_when_none(self):
        gov = self._make_governor()
        gov.run_once({"name": "t", "objective": "t"})
        planner_input = json.loads(
            (self.ledger / "runs" / "0001" / "planner_input.json").read_text()
        )
        self.assertNotIn("strategy", planner_input)


# ---------------------------------------------------------------------------
# CLI — goal_reached exit path
# ---------------------------------------------------------------------------

class TestGoalReached(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.repo = self.base / "repo"
        self.ledger = str(self.base / "ledger")
        _bootstrap_repo(self.repo)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_config(self, goal_evaluator_fixture: str, goal_evaluator_enabled: bool = True) -> Path:
        config_path = self.base / "evolution.yml"
        ge_role = f'["python3", "{FIXTURES}/{goal_evaluator_fixture}"]'
        ge_enabled = "true" if goal_evaluator_enabled else "false"
        config_path.write_text(f"""
mission: "test goal"
hard_stops:
  max_iterations: 3
  max_consecutive_failures: 5
roles:
  planner: ["python3", "{FIXTURES}/planner.py"]
  executor: ["python3", "{FIXTURES}/executor.py"]
  evaluator: ["python3", "{FIXTURES}/evaluator_accept.py"]
  goal_evaluator: {ge_role}
goal_evaluator:
  enabled: {ge_enabled}
""")
        return config_path

    def _run_cli(self, config_path: Path, *extra_args):
        from evolution_kernel.cli import main
        return main([
            "--config", str(config_path),
            "--repo", str(self.repo),
            "--ledger", self.ledger,
            *extra_args,
        ])

    def test_goal_reached_exits_zero(self):
        cfg_path = self._write_config("goal_evaluator_reached.py")
        rc = self._run_cli(cfg_path, "--loop")
        self.assertEqual(rc, 0)

    def test_goal_reached_stops_after_first_accepted(self):
        cfg_path = self._write_config("goal_evaluator_reached.py")
        self._run_cli(cfg_path, "--loop")
        runs = list((Path(self.ledger) / "runs").iterdir())
        self.assertEqual(len(runs), 1)

    def test_goal_not_reached_continues_to_hard_stop(self):
        cfg_path = self._write_config("goal_evaluator_not_reached.py")
        rc = self._run_cli(cfg_path, "--loop")
        self.assertEqual(rc, 3)
        runs = list((Path(self.ledger) / "runs").iterdir())
        self.assertEqual(len(runs), 3)

    def test_goal_evaluator_disabled_does_not_stop_early(self):
        cfg_path = self._write_config("goal_evaluator_reached.py", goal_evaluator_enabled=False)
        rc = self._run_cli(cfg_path, "--loop")
        self.assertEqual(rc, 3)


# ---------------------------------------------------------------------------
# CLI — strategist injection
# ---------------------------------------------------------------------------

class TestStrategistInjection(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.repo = self.base / "repo"
        self.ledger = str(self.base / "ledger")
        _bootstrap_repo(self.repo)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_config(self, every_n: int = 2) -> Path:
        config_path = self.base / "evolution.yml"
        config_path.write_text(f"""
mission: "test strategist"
hard_stops:
  max_iterations: 4
  max_consecutive_failures: 5
roles:
  planner: ["python3", "{FIXTURES}/planner.py"]
  executor: ["python3", "{FIXTURES}/executor.py"]
  evaluator: ["python3", "{FIXTURES}/evaluator_accept.py"]
  strategist: ["python3", "{FIXTURES}/strategist.py"]
strategist:
  enabled: true
  every_n_rounds: {every_n}
""")
        return config_path

    def _run_cli(self, config_path: Path, *extra_args):
        from evolution_kernel.cli import main
        return main([
            "--config", str(config_path),
            "--repo", str(self.repo),
            "--ledger", self.ledger,
            *extra_args,
        ])

    def test_strategy_injected_at_round_n_plus_one(self):
        cfg_path = self._write_config(every_n=2)
        self._run_cli(cfg_path, "--loop")
        # Strategist runs after round 2 → strategy appears in round 3's planner_input
        planner_input_3 = json.loads(
            (Path(self.ledger) / "runs" / "0003" / "planner_input.json").read_text()
        )
        self.assertIn("strategy", planner_input_3)
        self.assertEqual(planner_input_3["strategy"]["stage"], "fixture-stage")

    def test_no_strategy_in_round_one(self):
        cfg_path = self._write_config(every_n=2)
        self._run_cli(cfg_path, "--loop")
        planner_input_1 = json.loads(
            (Path(self.ledger) / "runs" / "0001" / "planner_input.json").read_text()
        )
        self.assertNotIn("strategy", planner_input_1)


if __name__ == "__main__":
    unittest.main()
