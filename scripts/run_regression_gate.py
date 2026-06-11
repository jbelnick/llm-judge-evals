#!/usr/bin/env python3
"""Regression gate: fail (exit 1) when a candidate run regresses vs baseline.

This is the command CI runs. Point it at any directory of generated
summaries; it scores them against the golden set and compares to the
committed baseline scorecard.

Usage:
    PYTHONPATH=src python3 scripts/run_regression_gate.py --candidate eval/baselines/baseline
    PYTHONPATH=src python3 scripts/run_regression_gate.py --candidate eval/baselines/drifted   # exits 1
"""

from __future__ import annotations

import argparse
from pathlib import Path

from judge_evals.runner import DEFAULT_TOLERANCE_POINTS, run_gate

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden", default=str(ROOT / "eval" / "golden"))
    parser.add_argument("--baseline", default=str(ROOT / "eval" / "golden" / "baseline-scorecard.json"))
    parser.add_argument("--candidate", required=True, help="dir with <caseId>/summary.md per golden case")
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE_POINTS)
    args = parser.parse_args()

    result = run_gate(args.golden, args.baseline, args.candidate, args.tolerance)
    print(
        f"baseline composite {result['baselineMeanComposite']} -> candidate composite {result['candidateMeanComposite']}"
    )
    if result["passed"]:
        print("GATE PASS: no regressions against the golden set")
        return 0
    print(f"GATE FAIL: {len(result['findings'])} regression(s)")
    for finding in result["findings"]:
        print(f"  - {finding}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
