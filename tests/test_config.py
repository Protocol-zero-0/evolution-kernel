from __future__ import annotations

import textwrap
import unittest
from pathlib import Path
import tempfile

from evolution_kernel.config import (
    EvolutionConfig,
    EvidenceSource,
    HardStopConfig,
    MutationScope,
    RolesConfig,
    load_config,
)


class ConfigTests(unittest.TestCase):
    def _write(self, tmp: Path, content: str) -> Path:
        p = tmp / "evolution.yml"
        p.write_text(textwrap.dedent(content), encoding="utf-8")
        return p

    def test_load_full_config(self):
        with tempfile.TemporaryDirectory() as d:
            cfg_path = self._write(Path(d), """
                mission: "Improve under constraints."
                evidence_sources:
                  - type: file
                    path: "./metrics.json"
                  - type: shell
                    command: "echo hello"
                mutation_scope:
                  allowed_paths:
                    - "src/"
                    - "tests/"
                hard_stops:
                  max_iterations: 5
                  max_consecutive_failures: 2
                roles:
                  planner: ["python3", "planner.py"]
                  executor: ["python3", "executor.py"]
                  evaluator: ["python3", "evaluator.py"]
            """)
            cfg = load_config(cfg_path)

        self.assertEqual(cfg.mission, "Improve under constraints.")
        self.assertEqual(len(cfg.evidence_sources), 2)
        self.assertEqual(cfg.evidence_sources[0].type, "file")
        self.assertEqual(cfg.evidence_sources[0].path, "./metrics.json")
        self.assertEqual(cfg.evidence_sources[1].type, "shell")
        self.assertEqual(cfg.evidence_sources[1].command, "echo hello")
        self.assertEqual(cfg.mutation_scope.allowed_paths, ("src/", "tests/"))
        self.assertEqual(cfg.hard_stops.max_iterations, 5)
        self.assertEqual(cfg.hard_stops.max_consecutive_failures, 2)
        self.assertIsNotNone(cfg.roles)
        self.assertEqual(cfg.roles.planner, ("python3", "planner.py"))

    def test_load_minimal_config(self):
        with tempfile.TemporaryDirectory() as d:
            cfg_path = self._write(Path(d), """
                mission: "Minimal."
            """)
            cfg = load_config(cfg_path)

        self.assertEqual(cfg.mission, "Minimal.")
        self.assertEqual(len(cfg.evidence_sources), 0)
        self.assertEqual(cfg.mutation_scope.allowed_paths, ())
        self.assertEqual(cfg.hard_stops.max_iterations, 0)
        self.assertIsNone(cfg.roles)

    def test_empty_allowed_paths_means_no_restriction(self):
        cfg = EvolutionConfig(
            mission="x",
            evidence_sources=(),
            mutation_scope=MutationScope(allowed_paths=()),
            hard_stops=HardStopConfig(),
            roles=None,
        )
        self.assertEqual(cfg.mutation_scope.allowed_paths, ())

    def test_missing_type_in_evidence_source_raises_value_error(self):
        with tempfile.TemporaryDirectory() as d:
            cfg_path = self._write(Path(d), """
                mission: "test"
                evidence_sources:
                  - path: "./metrics.json"
            """)
            with self.assertRaises(ValueError) as ctx:
                load_config(cfg_path)
        self.assertIn("type", str(ctx.exception))

    def test_non_dict_yaml_raises_value_error(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "evolution.yml"
            p.write_text("- item1\n- item2\n", encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                load_config(p)
        self.assertIn("mapping", str(ctx.exception))

    def test_roles_missing_key_raises_value_error(self):
        with tempfile.TemporaryDirectory() as d:
            cfg_path = self._write(Path(d), """
                mission: "test"
                roles:
                  planner: ["python3", "p.py"]
                  executor: ["python3", "e.py"]
            """)
            with self.assertRaises(ValueError) as ctx:
                load_config(cfg_path)
        self.assertIn("evaluator", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
