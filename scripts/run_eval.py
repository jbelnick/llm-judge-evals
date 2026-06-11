#!/usr/bin/env python3
"""Score a summaries directory against the golden set and print a scorecard.

Usage:
    PYTHONPATH=src python3 scripts/run_eval.py --summaries eval/baselines/baseline
    PYTHONPATH=src python3 scripts/run_eval.py --summaries eval/baselines/baseline --out eval/golden/baseline-scorecard.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from judge_evals.runner import score_run

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden", default=str(ROOT / "eval" / "golden"))
    parser.add_argument("--summaries", required=True, help="dir with <caseId>/summary.md per golden case")
    parser.add_argument("--out", default="", help="optional path to write the scorecard JSON")
    args = parser.parse_args()

    scorecard = score_run(args.golden, args.summaries)
    print(f"mean composite: {scorecard['meanComposite']}  mean number recall: {scorecard['meanNumberRecall']}  n={scorecard['n']}")
    for entry in scorecard["perCase"]:
        flags = []
        if entry["numberExactness"]["missing"]:
            flags.append(f"missing levels: {', '.join(entry['numberExactness']['missing'])}")
        if entry["scaleErrors"]:
            flags.append(
                "scale errors: " + "; ".join(f"{e['expected']} became {e['found']}" for e in entry["scaleErrors"])
            )
        if entry["inventedNumbers"]["invented"]:
            flags.append(f"invented: {', '.join(entry['inventedNumbers']['invented'])}")
        if not entry["format"]["ok"]:
            flags.append("format violation")
        print(f"  {entry['caseId']}: {entry['composite']:>5}  {('; '.join(flags)) if flags else 'clean'}")
    if scorecard["missingSummaries"]:
        print(f"  WARNING missing summary files for: {', '.join(scorecard['missingSummaries'])}")
    if args.out:
        Path(args.out).write_text(json.dumps(scorecard, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
