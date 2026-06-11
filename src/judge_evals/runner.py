"""Golden-set runner and regression gate.

The runner scores a directory of generated summaries against the golden
dataset and emits a scorecard. The gate compares that scorecard to the
committed baseline and fails when quality regresses, which is what makes
this an eval suite instead of a dashboard: a model swap or prompt change
that drops fidelity turns CI red before it reaches anyone.
"""

from __future__ import annotations

import json
from pathlib import Path

from .scorers import score_corpus

# A candidate run regresses when its mean composite drops more than this many
# points below baseline, or when any single case loses a golden price level
# the baseline had. The per-case check exists because a corpus mean can hide
# one badly broken transcript among nine good ones.
DEFAULT_TOLERANCE_POINTS = 2.0


def load_golden_cases(golden_dir: str | Path) -> list[dict]:
    golden_dir = Path(golden_dir)
    cases = []
    for line in (golden_dir / "cases.jsonl").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        case = json.loads(line)
        transcript_path = golden_dir / "transcripts" / case["transcriptFile"]
        case["transcript"] = transcript_path.read_text(encoding="utf-8")
        cases.append(case)
    if not cases:
        raise ValueError(f"no golden cases found in {golden_dir}")
    return cases


def score_run(golden_dir: str | Path, summaries_dir: str | Path, summary_filename: str = "summary.md") -> dict:
    """Score one summaries directory: <summaries_dir>/<caseId>/<summary_filename>."""
    summaries_dir = Path(summaries_dir)
    cases = load_golden_cases(golden_dir)
    pairs = []
    missing = []
    for case in cases:
        summary_path = summaries_dir / case["id"] / summary_filename
        if summary_path.exists():
            pairs.append((summary_path.read_text(encoding="utf-8"), case))
        else:
            missing.append(case["id"])
            pairs.append(("", case))
    scorecard = score_corpus(pairs)
    scorecard["missingSummaries"] = missing
    return scorecard


def regression_findings(baseline: dict, candidate: dict, tolerance: float = DEFAULT_TOLERANCE_POINTS) -> list[str]:
    """Compare scorecards. Returns a list of human-readable regressions;
    empty means the candidate run passes the gate."""
    findings: list[str] = []
    drop = baseline["meanComposite"] - candidate["meanComposite"]
    if drop > tolerance:
        findings.append(
            f"mean composite regressed {baseline['meanComposite']} -> {candidate['meanComposite']} "
            f"(drop {round(drop, 1)} > tolerance {tolerance})"
        )
    baseline_by_case = {entry["caseId"]: entry for entry in baseline.get("perCase", [])}
    for entry in candidate.get("perCase", []):
        before = baseline_by_case.get(entry["caseId"])
        if not before:
            continue
        if entry["numberExactness"]["matched"] < before["numberExactness"]["matched"]:
            findings.append(
                f"{entry['caseId']}: lost golden price levels "
                f"({before['numberExactness']['matched']} -> {entry['numberExactness']['matched']}; "
                f"missing: {', '.join(entry['numberExactness']['missing']) or 'n/a'})"
            )
        if entry["scaleErrors"] and not before["scaleErrors"]:
            shifted = "; ".join(f"{e['ticker']}: {e['expected']} became {e['found']}" for e in entry["scaleErrors"])
            findings.append(f"{entry['caseId']}: new decimal-scale error ({shifted})")
        if entry["inventedNumbers"]["invented"] and not before["inventedNumbers"]["invented"]:
            findings.append(
                f"{entry['caseId']}: invented numbers with no transcript support "
                f"({', '.join(entry['inventedNumbers']['invented'])})"
            )
        if not entry["format"]["ok"] and before["format"]["ok"]:
            findings.append(f"{entry['caseId']}: required section missing or forbidden label present")
    return findings


def run_gate(
    golden_dir: str | Path,
    baseline_scorecard_path: str | Path,
    candidate_summaries_dir: str | Path,
    tolerance: float = DEFAULT_TOLERANCE_POINTS,
) -> dict:
    baseline = json.loads(Path(baseline_scorecard_path).read_text(encoding="utf-8"))
    candidate = score_run(golden_dir, candidate_summaries_dir)
    findings = regression_findings(baseline, candidate, tolerance)
    return {
        "passed": not findings,
        "findings": findings,
        "baselineMeanComposite": baseline["meanComposite"],
        "candidateMeanComposite": candidate["meanComposite"],
        "candidate": candidate,
    }
