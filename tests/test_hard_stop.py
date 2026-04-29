from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from evolution_kernel.config import HardStopConfig
from evolution_kernel.hard_stop import HardStopError, HardStopGuard


class HardStopGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _guard(self, max_iter=0, max_fail=0):
        return HardStopGuard(self.ledger, HardStopConfig(max_iter, max_fail))

    def test_no_limits_never_raises(self):
        guard = self._guard()
        for _ in range(20):
            guard.check()
            guard.record(accepted=False)

    def test_blocks_after_max_iterations(self):
        guard = self._guard(max_iter=3)
        for _ in range(3):
            guard.check()
            guard.record(accepted=True)
        with self.assertRaises(HardStopError) as ctx:
            guard.check()
        self.assertIn("max_iterations", str(ctx.exception))

    def test_blocks_after_max_consecutive_failures(self):
        guard = self._guard(max_fail=2)
        guard.check(); guard.record(accepted=False)
        guard.check(); guard.record(accepted=False)
        with self.assertRaises(HardStopError) as ctx:
            guard.check()
        self.assertIn("max_consecutive_failures", str(ctx.exception))

    def test_accept_resets_consecutive_failures(self):
        guard = self._guard(max_fail=2)
        guard.check(); guard.record(accepted=False)
        guard.check(); guard.record(accepted=True)   # resets counter
        guard.check(); guard.record(accepted=False)  # only 1 failure now
        guard.check()  # should not raise

    def test_reset_clears_state(self):
        guard = self._guard(max_iter=2)
        guard.check(); guard.record(accepted=True)
        guard.check(); guard.record(accepted=True)
        with self.assertRaises(HardStopError):
            guard.check()
        guard.reset()
        guard.check()  # should not raise after reset

    def test_state_persists_across_instances(self):
        guard1 = self._guard(max_iter=2)
        guard1.check(); guard1.record(accepted=True)

        guard2 = self._guard(max_iter=2)
        guard2.check(); guard2.record(accepted=True)

        guard3 = self._guard(max_iter=2)
        with self.assertRaises(HardStopError):
            guard3.check()

    def test_state_file_written_to_ledger(self):
        guard = self._guard(max_iter=5)
        guard.check(); guard.record(accepted=True)

        state_file = self.ledger / "state.json"
        self.assertTrue(state_file.exists())
        data = json.loads(state_file.read_text(encoding="utf-8"))
        self.assertEqual(data["iterations"], 1)
        self.assertEqual(data["consecutive_failures"], 0)


if __name__ == "__main__":
    unittest.main()
