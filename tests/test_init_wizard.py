"""Init wizard: every template renders to a config that load_config accepts."""
from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from evolution_kernel import init_wizard
from evolution_kernel.config import load_config


class InitWizardTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._prev_cwd = os.getcwd()
        os.chdir(self.tmp)

    def tearDown(self) -> None:
        os.chdir(self._prev_cwd)
        self._tmp.cleanup()

    def _run_with_inputs(self, inputs: list[str]) -> int:
        it = iter(inputs)
        with patch("builtins.input", lambda _prompt: next(it)), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return init_wizard.main([])

    def test_each_template_round_trips(self) -> None:
        for idx, name in enumerate(init_wizard.TEMPLATES, start=1):
            with self.subTest(template=name):
                out_path = self.tmp / "evolution.yml"
                out_path.unlink(missing_ok=True)
                rc = self._run_with_inputs([f"unit test mission for {name}", str(idx), "src/, tests/"])
                self.assertEqual(rc, 0, f"init failed for {name}")
                self.assertTrue(out_path.exists())
                cfg = load_config(str(out_path))
                self.assertTrue(cfg.mission.startswith("unit test mission"))
                self.assertEqual(cfg.mutation_scope.allowed_paths, ("src/", "tests/"))

    def test_refuses_to_overwrite(self) -> None:
        (self.tmp / "evolution.yml").write_text("placeholder\n")
        rc = self._run_with_inputs(["x"])
        self.assertEqual(rc, 2)

    def test_bad_template_pick(self) -> None:
        rc = self._run_with_inputs(["mission", "99", "src/"])
        self.assertEqual(rc, 2)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
