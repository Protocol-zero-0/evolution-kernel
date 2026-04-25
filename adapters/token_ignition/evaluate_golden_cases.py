from __future__ import annotations

import argparse
import json
from pathlib import Path


def classify(signals: dict) -> str:
    if signals.get("prompt_only") or signals.get("hardcoded_benchmark"):
        return "reject"
    if not signals.get("reproducible_micro_run") or not signals.get("artifact_hash"):
        return "reject"
    if not signals.get("versioned_commits") or not signals.get("measurable_improvement"):
        return "reject"
    if signals.get("complexity_level") == "high" and not signals.get("rollback_recorded"):
        return "reject"
    if not signals.get("rollback_recorded"):
        return "conditional"
    if int(signals.get("iteration_logs") or 0) >= 3:
        return "accept"
    return "conditional"


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Token-Ignition golden cases.")
    parser.add_argument("--cases", default=str(Path(__file__).with_name("golden_cases.json")))
    args = parser.parse_args()

    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    results = []
    correct = 0
    for case in cases:
        actual = classify(case["signals"])
        ok = actual == case["expected"]
        correct += int(ok)
        results.append({"id": case["id"], "expected": case["expected"], "actual": actual, "ok": ok})

    report = {
        "total": len(cases),
        "correct": correct,
        "accuracy": correct / len(cases) if cases else 0.0,
        "results": results,
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

