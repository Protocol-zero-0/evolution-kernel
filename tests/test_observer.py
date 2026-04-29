from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from evolution_kernel.config import EvidenceSource
from evolution_kernel.observer import Observer


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.worktree = Path(self.tmp.name) / "worktree"
        self.run_dir = Path(self.tmp.name) / "run"
        self.worktree.mkdir()
        self.run_dir.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_reads_file_source(self):
        (self.worktree / "metrics.json").write_text(
            json.dumps({"score": 42}), encoding="utf-8"
        )
        sources = (EvidenceSource(type="file", path="metrics.json"),)
        obs = Observer().run(sources, self.worktree, self.run_dir)

        self.assertIn("sources", obs)
        self.assertEqual(obs["sources"][0]["type"], "file")
        self.assertIn('"score": 42', obs["sources"][0]["content"])

    def test_runs_shell_source(self):
        sources = (EvidenceSource(type="shell", command=f"{sys.executable} -c \"print('ok')\""),)
        obs = Observer().run(sources, self.worktree, self.run_dir)

        self.assertEqual(obs["sources"][0]["type"], "shell")
        self.assertIn("ok", obs["sources"][0]["stdout"])
        self.assertEqual(obs["sources"][0]["returncode"], 0)

    def test_writes_observation_json(self):
        sources = (EvidenceSource(type="shell", command="echo test"),)
        Observer().run(sources, self.worktree, self.run_dir)

        obs_file = self.run_dir / "observation.json"
        self.assertTrue(obs_file.exists())
        data = json.loads(obs_file.read_text(encoding="utf-8"))
        self.assertIn("sources", data)

    def test_missing_file_records_error_does_not_raise(self):
        sources = (EvidenceSource(type="file", path="nonexistent.json"),)
        obs = Observer().run(sources, self.worktree, self.run_dir)

        self.assertIn("error", obs["sources"][0])

    def test_failing_shell_records_error_does_not_raise(self):
        sources = (EvidenceSource(type="shell", command="exit 1"),)
        obs = Observer().run(sources, self.worktree, self.run_dir)

        self.assertEqual(obs["sources"][0]["returncode"], 1)

    def test_unknown_source_type_records_error(self):
        sources = (EvidenceSource(type="database"),)
        obs = Observer().run(sources, self.worktree, self.run_dir)

        self.assertIn("error", obs["sources"][0])

    def test_empty_sources_produces_empty_observation(self):
        obs = Observer().run((), self.worktree, self.run_dir)
        self.assertEqual(obs["sources"], [])


if __name__ == "__main__":
    unittest.main()
