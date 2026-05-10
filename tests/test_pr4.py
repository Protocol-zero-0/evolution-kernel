"""Tests for PR4 features: cost guard, history injection, --loop flag, new config fields."""
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

    def test_cost_guard_defaults(self):
        cfg = parse_config({"mission": "x"})
        self.assertEqual(cfg.hard_stops.max_total_usd, 0.0)
        self.assertEqual(cfg.hard_stops.max_total_tokens, 0)

    def test_cost_guard_values(self):
        cfg = parse_config({"mission": "x", "hard_stops": {
            "max_iterations": 5, "max_consecutive_failures": 2,
            "max_total_usd": 1.5, "max_total_tokens": 100000,
        }})
        self.assertAlmostEqual(cfg.hard_stops.max_total_usd, 1.5)
        self.assertEqual(cfg.hard_stops.max_total_tokens, 100000)

    def test_llm_defaults(self):
        cfg = parse_config({"mission": "x"})
        self.assertEqual(cfg.llm.provider, "anthropic")
        self.assertEqual(cfg.llm.model, "claude-sonnet-4-6")
        self.assertEqual(cfg.llm.api_key_env, "ANTHROPIC_API_KEY")

    def test_llm_custom(self):
        cfg = parse_config({"mission": "x", "llm": {
            "provider": "openai", "model": "gpt-4o", "api_key_env": "OPENAI_API_KEY",
        }})
        self.assertEqual(cfg.llm.provider, "openai")
        self.assertEqual(cfg.llm.model, "gpt-4o")

    def test_coding_agent_default(self):
        cfg = parse_config({"mission": "x"})
        self.assertEqual(cfg.coding_agent.tool, "aider")

    def test_coding_agent_claude_code(self):
        cfg = parse_config({"mission": "x", "coding_agent": {"tool": "claude-code"}})
        self.assertEqual(cfg.coding_agent.tool, "claude-code")

    def test_history_defaults(self):
        cfg = parse_config({"mission": "x"})
        self.assertEqual(cfg.history.max_entries, 10)

    def test_history_custom(self):
        cfg = parse_config({"mission": "x", "history": {"max_entries": 5}})
        self.assertEqual(cfg.history.max_entries, 5)


# ---------------------------------------------------------------------------
# Hard stops — cost guard
# ---------------------------------------------------------------------------

class TestCostGuard(unittest.TestCase):

    def test_precheck_blocks_on_usd(self):
        state = hard_stops.HardStopState(total_usd=1.0)
        allowed, reason = hard_stops.precheck(state, 10, 3, max_total_usd=1.0)
        self.assertFalse(allowed)
        self.assertIn("max_total_usd", reason)

    def test_precheck_blocks_on_tokens(self):
        state = hard_stops.HardStopState(total_tokens=500000)
        allowed, reason = hard_stops.precheck(state, 10, 3, max_total_tokens=500000)
        self.assertFalse(allowed)
        self.assertIn("max_total_tokens", reason)

    def test_precheck_allows_below_limit(self):
        state = hard_stops.HardStopState(total_usd=0.5, total_tokens=100)
        allowed, _ = hard_stops.precheck(state, 10, 3, max_total_usd=1.0, max_total_tokens=500000)
        self.assertTrue(allowed)

    def test_record_outcome_accumulates_cost(self):
        state = hard_stops.HardStopState()
        state = hard_stops.record_outcome(
            state, accepted=True, max_iterations=10, max_consecutive_failures=3,
            cost_usd=0.05, tokens_used=1000,
        )
        self.assertAlmostEqual(state.total_usd, 0.05)
        self.assertEqual(state.total_tokens, 1000)

    def test_record_outcome_halts_on_usd(self):
        state = hard_stops.HardStopState(total_usd=0.95)
        state = hard_stops.record_outcome(
            state, accepted=True, max_iterations=10, max_consecutive_failures=3,
            cost_usd=0.10, tokens_used=0, max_total_usd=1.0,
        )
        self.assertTrue(state.halted)
        self.assertIn("max_total_usd", state.halt_reason)

    def test_record_outcome_halts_on_tokens(self):
        state = hard_stops.HardStopState(total_tokens=490000)
        state = hard_stops.record_outcome(
            state, accepted=True, max_iterations=10, max_consecutive_failures=3,
            tokens_used=20000, max_total_tokens=500000,
        )
        self.assertTrue(state.halted)
        self.assertIn("max_total_tokens", state.halt_reason)

    def test_state_persists_cost_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp)
            state = hard_stops.HardStopState(total_usd=0.12, total_tokens=4500)
            hard_stops.save_state(ledger, state)
            loaded = hard_stops.load_state(ledger)
            self.assertAlmostEqual(loaded.total_usd, 0.12)
            self.assertEqual(loaded.total_tokens, 4500)


# ---------------------------------------------------------------------------
# Governor — history injection
# ---------------------------------------------------------------------------

class TestHistoryInjection(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.repo = self.base / "repo"
        self.ledger = self.base / "ledger"
        _bootstrap_repo(self.repo)

    def tearDown(self):
        self._tmp.cleanup()

    def _make_governor(self, max_entries: int = 10) -> Governor:
        return Governor(
            target_repo=self.repo,
            ledger_dir=self.ledger,
            planner=_role("planner.py"),
            executor=_role("executor.py"),
            evaluator=_role("evaluator_accept.py"),
            allowed_paths=["src/"],
            history_max_entries=max_entries,
        )

    def test_first_run_has_empty_history(self):
        gov = self._make_governor()
        gov.run_once({"name": "test", "objective": "test"})
        planner_input = json.loads(
            (self.ledger / "runs" / "0001" / "planner_input.json").read_text()
        )
        self.assertEqual(planner_input["history"], [])

    def test_second_run_sees_first_run_in_history(self):
        gov = self._make_governor()
        gov.run_once({"name": "test", "objective": "test"})
        gov.run_once({"name": "test", "objective": "test"})
        planner_input = json.loads(
            (self.ledger / "runs" / "0002" / "planner_input.json").read_text()
        )
        self.assertEqual(len(planner_input["history"]), 1)
        self.assertEqual(planner_input["history"][0]["run_id"], "0001")

    def test_history_capped_by_max_entries(self):
        gov = self._make_governor(max_entries=2)
        for _ in range(4):
            gov.run_once({"name": "test", "objective": "test"})
        planner_input = json.loads(
            (self.ledger / "runs" / "0004" / "planner_input.json").read_text()
        )
        self.assertLessEqual(len(planner_input["history"]), 2)


# ---------------------------------------------------------------------------
# CLI — --loop flag
# ---------------------------------------------------------------------------

class TestLoopFlag(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.repo = self.base / "repo"
        self.ledger = str(self.base / "ledger")
        _bootstrap_repo(self.repo)

        # Write a minimal config that uses fixture roles
        self.config_path = self.base / "evolution.yml"
        # No allowed_paths restriction so fixture executor (writes EVOLUTION_MARKER.txt) is in scope.
        self.config_path.write_text(f"""
mission: "test loop"
hard_stops:
  max_iterations: 3
  max_consecutive_failures: 5
roles:
  planner: ["python3", "{FIXTURES}/planner.py"]
  executor: ["python3", "{FIXTURES}/executor.py"]
  evaluator: ["python3", "{FIXTURES}/evaluator_accept.py"]
""")

    def tearDown(self):
        self._tmp.cleanup()

    def _run_cli(self, *extra_args):
        from evolution_kernel.cli import main
        return main([
            "--config", str(self.config_path),
            "--repo", str(self.repo),
            "--ledger", self.ledger,
            *extra_args,
        ])

    def test_loop_runs_until_max_iterations(self):
        rc = self._run_cli("--loop")
        self.assertEqual(rc, 0)
        # max_iterations=3, so 3 run dirs should exist
        runs = list((Path(self.ledger) / "runs").iterdir())
        self.assertEqual(len(runs), 3)

    def test_loop_state_halted_after_completion(self):
        self._run_cli("--loop")
        state = hard_stops.load_state(self.ledger)
        self.assertTrue(state.halted)
        self.assertIn("max_iterations", state.halt_reason or "")


if __name__ == "__main__":
    unittest.main()
