from __future__ import annotations

import json
import unittest
from pathlib import Path

from adapters.token_ignition.evaluate_golden_cases import classify


ROOT = Path(__file__).resolve().parents[1]


class TokenIgnitionGoldenTests(unittest.TestCase):
    def test_handwritten_golden_cases_classify_as_expected(self):
        cases = json.loads((ROOT / "adapters" / "token_ignition" / "golden_cases.json").read_text(encoding="utf-8"))
        failures = []
        for case in cases:
            actual = classify(case["signals"])
            if actual != case["expected"]:
                failures.append((case["id"], case["expected"], actual))
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()

