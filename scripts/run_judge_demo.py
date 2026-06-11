#!/usr/bin/env python3
"""Judge demo: rank a faithful summary against one with a shifted decimal.

By default this replays a committed fixture response (no network, runs in
CI). The fixture reproduces a failure mode live judges show in practice:
it scores the drifted candidate 88 because the summary reads well, and the
code-level scale-error cap pulls it down to 79. Pass --live to query a real
OpenAI-compatible endpoint instead (JUDGE_BASE_URL, JUDGE_MODEL, optional
JUDGE_API_KEY) and watch the same cross-check guard a real judge.

Usage:
    PYTHONPATH=src python3 scripts/run_judge_demo.py
    PYTHONPATH=src python3 scripts/run_judge_demo.py --live
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from judge_evals.judge import judge_candidates
from judge_evals.judge_client import OpenAICompatibleJudge, RecordedJudge
from judge_evals.runner import load_golden_cases

ROOT = Path(__file__).resolve().parents[1]
DEMO_CASE = "case-02"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="query a live judge endpoint instead of the recording")
    args = parser.parse_args()

    case = next(c for c in load_golden_cases(ROOT / "eval" / "golden") if c["id"] == DEMO_CASE)
    summaries = {
        "pipeline-current": (ROOT / "eval" / "baselines" / "baseline" / DEMO_CASE / "summary.md").read_text(
            encoding="utf-8"
        ),
        "pipeline-after-model-swap": (ROOT / "eval" / "baselines" / "drifted" / DEMO_CASE / "summary.md").read_text(
            encoding="utf-8"
        ),
    }
    client = (
        OpenAICompatibleJudge()
        if args.live
        else RecordedJudge(ROOT / "eval" / "fixtures" / "judge-demo-responses.json")
    )
    judged = judge_candidates(client, case["transcript"], summaries, case["expectedLevels"])

    print(f"case: {DEMO_CASE} (DOGE levels; the drifted candidate shifted 0.09832 to 0.9832)")
    print(f"winner: {judged['winnerLabel']}")
    for entry in judged["rankings"]:
        capped = f" (judge said {entry['cappedFrom']}, capped for scale error)" if "cappedFrom" in entry else ""
        print(f"  {entry['label']:26} score {entry['score']}{capped}")
        if entry["scaleErrors"]:
            for error in entry["scaleErrors"]:
                print(f"    scale error: expected {error['expected']}, found {error['found']}")
        if entry["rationale"]:
            print(f"    rationale: {entry['rationale']}")
    print()
    print(json.dumps({"winner": judged["winnerLabel"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
