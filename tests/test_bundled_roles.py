"""Tests for the `bundled:` prefix in `roles.*` argv entries."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from evolution_kernel._bundled import BUNDLED_PREFIX, resolve_bundled
from evolution_kernel.config import ConfigError, load_config


SAMPLE_CONFIG = """\
mission: "test"
llm:
  provider: anthropic
  model: claude-sonnet-4-6
  api_key_env: ANTHROPIC_API_KEY
coding_agent:
  tool: aider
evidence_sources:
  - type: file
    path: "metrics.json"
mutation_scope:
  allowed_paths:
    - "src/"
roles:
  planner:   ["python3", "bundled:planner.py"]
  executor:  ["bash",    "bundled:executor.sh"]
  evaluator: ["python3", "bundled:evaluator.py"]
"""


class BundledPrefixTest(unittest.TestCase):
    def test_resolve_bundled_returns_absolute_path_to_existing_file(self):
        path = resolve_bundled("bundled:executor.sh")
        resolved = Path(path)
        self.assertTrue(resolved.is_absolute(), f"expected absolute path, got {path!r}")
        self.assertTrue(resolved.exists(), f"resolved path does not exist: {path!r}")
        self.assertEqual(resolved.name, "executor.sh")
        self.assertEqual(resolved.parent.name, "roles")

    def test_resolve_bundled_is_noop_for_non_prefixed_strings(self):
        self.assertEqual(resolve_bundled("python3"), "python3")
        self.assertEqual(resolve_bundled("/abs/path/to/exec"), "/abs/path/to/exec")
        self.assertEqual(resolve_bundled("./relative/path.py"), "./relative/path.py")

    def test_resolve_bundled_rejects_path_separators(self):
        with self.assertRaises(ValueError):
            resolve_bundled("bundled:../escape.py")
        with self.assertRaises(ValueError):
            resolve_bundled("bundled:subdir/file.py")
        with self.assertRaises(ValueError):
            resolve_bundled(BUNDLED_PREFIX)  # empty name

    def test_resolve_bundled_raises_for_missing_files(self):
        with self.assertRaises(FileNotFoundError):
            resolve_bundled("bundled:does-not-exist.xyz")

    def test_load_config_resolves_bundled_in_roles(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = Path(tmpdir) / "evolution.yml"
            cfg_path.write_text(SAMPLE_CONFIG, encoding="utf-8")
            cfg = load_config(str(cfg_path))

            # `bundled:planner.py` should have become an absolute path to an
            # existing file inside the installed package.
            planner_script = Path(cfg.roles.planner[1])
            executor_script = Path(cfg.roles.executor[1])
            evaluator_script = Path(cfg.roles.evaluator[1])

            for script in (planner_script, executor_script, evaluator_script):
                self.assertTrue(script.is_absolute(), f"not absolute: {script}")
                self.assertTrue(script.exists(), f"missing: {script}")
                self.assertEqual(script.parent.name, "roles")

            # Surrounding argv entries (python3, bash) must be untouched.
            self.assertEqual(cfg.roles.planner[0], "python3")
            self.assertEqual(cfg.roles.executor[0], "bash")
            self.assertEqual(cfg.roles.evaluator[0], "python3")

    def test_load_config_surfaces_missing_bundled_role_as_config_error(self):
        bad_cfg = SAMPLE_CONFIG.replace(
            'bundled:planner.py', 'bundled:nope.py'
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = Path(tmpdir) / "evolution.yml"
            cfg_path.write_text(bad_cfg, encoding="utf-8")
            with self.assertRaises(ConfigError) as ctx:
                load_config(str(cfg_path))
            self.assertIn("nope.py", str(ctx.exception))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
