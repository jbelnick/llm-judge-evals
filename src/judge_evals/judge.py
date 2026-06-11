"""Rubric-anchored LLM-as-judge harness.

The judge scores qualitative dimensions a deterministic scorer cannot reach:
transcript fidelity, catalyst extraction, uncertainty handling, and
actionability. Three mitigations keep it honest, because a naive judge fails
in predictable ways:

1. Rubric anchoring. The prompt pins each score band to concrete behavior
   ("a 90+ summary is faithful, specific, cautious about uncertainty, and has
   no severe decimal errors") instead of asking for a bare 0-100 number.
   Unanchored scores cluster in the 80s and cannot rank candidates.
2. Candidate anonymization. Candidates are renamed candidate-1..n before the
   judge sees them, so the judge cannot reward a model by name or by
   recognizable house style.
3. Deterministic cross-check caps. The judge is never trusted on arithmetic.
   After judging, code (not the prompt) re-checks every candidate with the
   deterministic scale-error detector and caps the judge score at 79 for one
   severe decimal-scale error and 69 for more than one. A judge that misses
   a shifted decimal cannot promote that candidate past the cap.

The full trade-off discussion lives in
docs/adr/0001-hybrid-deterministic-plus-judge-evals.md.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .scorers import detect_scale_errors

SINGLE_SCALE_ERROR_CAP = 79
MULTI_SCALE_ERROR_CAP = 69

RUBRIC_DIMENSIONS = (
    "transcript_fidelity",
    "ticker_entity_accuracy",
    "catalyst_extraction",
    "risk_uncertainty",
    "actionability",
    "structure",
    "concision",
)


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    summary: str


def anonymize_candidates(summaries: dict[str, str]) -> tuple[list[Candidate], dict[str, str]]:
    """Rename candidates to candidate-1..n in sorted-label order so runs are
    reproducible, and return the mapping back to the real labels. The judge
    only ever sees the anonymous ids."""
    ordered = sorted(summaries)
    candidates = [Candidate(f"candidate-{i + 1}", summaries[label]) for i, label in enumerate(ordered)]
    mapping = {f"candidate-{i + 1}": label for i, label in enumerate(ordered)}
    return candidates, mapping


def build_judge_prompt(transcript: str, candidates: list[Candidate]) -> str:
    blocks = []
    for candidate in candidates:
        blocks.append(f"## {candidate.candidate_id}\n{candidate.summary.strip()}")
    return "\n".join(
        [
            "You are a strict evaluator of generated stock-update summaries.",
            "The candidates are intentionally anonymized. Do not infer model identity from style.",
            "Judge only against the transcript. Reward transcript fidelity, ticker and entity accuracy,",
            "specific catalysts, date preservation, careful uncertainty, and source-grounded actionability.",
            "Run a decimal and price-scale validation pass before scoring: compare every quoted price level",
            "against the transcript wording and the asset's normal scale. Treat missing decimals, shifted",
            "decimals, or factor-of-10 mistakes as severe accuracy failures.",
            "Penalize invented tickers, unsupported trade recommendations, hallucinated price levels,",
            "fabricated dates, and vague market filler.",
            "Return only valid JSON. No markdown, no commentary, no code fences.",
            "",
            "JSON shape:",
            json.dumps(
                {
                    "winnerCandidateId": "candidate-1",
                    "rankings": [
                        {
                            "candidateId": "candidate-1",
                            "score": 0,
                            "scores": {dim: 0 for dim in RUBRIC_DIMENSIONS},
                            "rationale": "short concrete rationale",
                            "missedImportantDetails": [],
                            "unsupportedClaims": [],
                        }
                    ],
                },
                indent=2,
            ),
            "",
            "Score each candidate 0-100 overall, anchored to these bands:",
            "90+: faithful, specific, cautious about uncertainty, no severe decimal or scale errors.",
            "70-89: usable but misses important ticker detail or has one severe scale issue.",
            "Below 60: weak; misreads the transcript or invents levels.",
            "",
            "# Transcript",
            transcript.strip(),
            "",
            "# Candidate Summaries",
            "\n\n".join(blocks),
        ]
    )


def strip_json_text(text: str) -> str:
    """Extract the JSON object from judge output that may include code fences
    or stray prose. Raises ValueError when no object is present."""
    trimmed = (text or "").strip()
    if not trimmed:
        raise ValueError("judge returned empty output")
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", trimmed, flags=re.IGNORECASE)
    candidate = fenced.group(1).strip() if fenced else trimmed
    first = candidate.find("{")
    last = candidate.rfind("}")
    if first == -1 or last == -1 or last < first:
        raise ValueError("judge output did not contain a JSON object")
    return candidate[first : last + 1]


def normalize_score(value: object) -> int:
    try:
        score = round(float(str(value)))
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, score))


def parse_judge_response(text: str) -> dict:
    payload = json.loads(strip_json_text(text))
    if not isinstance(payload, dict) or not isinstance(payload.get("rankings"), list):
        raise ValueError("judge JSON must be an object with a rankings list")
    rankings = []
    for entry in payload["rankings"]:
        if not isinstance(entry, dict) or not entry.get("candidateId"):
            continue
        rankings.append(
            {
                "candidateId": str(entry["candidateId"]),
                "score": normalize_score(entry.get("score")),
                "scores": {
                    dim: normalize_score((entry.get("scores") or {}).get(dim)) for dim in RUBRIC_DIMENSIONS
                },
                "rationale": str(entry.get("rationale", "")).strip(),
                "missedImportantDetails": [str(x) for x in entry.get("missedImportantDetails") or []],
                "unsupportedClaims": [str(x) for x in entry.get("unsupportedClaims") or []],
            }
        )
    if not rankings:
        raise ValueError("judge JSON contained no usable rankings")
    return {"winnerCandidateId": str(payload.get("winnerCandidateId", "")), "rankings": rankings}


def apply_scale_caps(
    judged: dict,
    summaries_by_candidate_id: dict[str, str],
    expected_levels: list[dict],
) -> dict:
    """Enforce the deterministic cross-check: re-detect scale errors in code
    and cap any judge score that exceeds what the evidence allows. The caps
    live here, not in the prompt, so a judge failure cannot bypass them."""
    for entry in judged["rankings"]:
        summary = summaries_by_candidate_id.get(entry["candidateId"], "")
        errors = detect_scale_errors(summary, expected_levels)
        cap = None
        if len(errors) == 1:
            cap = SINGLE_SCALE_ERROR_CAP
        elif len(errors) > 1:
            cap = MULTI_SCALE_ERROR_CAP
        entry["scaleErrors"] = errors
        if cap is not None and entry["score"] > cap:
            entry["cappedFrom"] = entry["score"]
            entry["score"] = cap
    judged["rankings"].sort(key=lambda e: e["score"], reverse=True)
    if judged["rankings"]:
        judged["winnerCandidateId"] = judged["rankings"][0]["candidateId"]
    return judged


def judge_candidates(
    judge_client,
    transcript: str,
    summaries: dict[str, str],
    expected_levels: list[dict],
) -> dict:
    """Full judge pass: anonymize, prompt, parse, cap, de-anonymize."""
    candidates, mapping = anonymize_candidates(summaries)
    prompt = build_judge_prompt(transcript, candidates)
    raw = judge_client.complete(prompt)
    judged = parse_judge_response(raw)
    by_id = {candidate.candidate_id: candidate.summary for candidate in candidates}
    judged = apply_scale_caps(judged, by_id, expected_levels)
    for entry in judged["rankings"]:
        entry["label"] = mapping.get(entry["candidateId"], entry["candidateId"])
    judged["winnerLabel"] = mapping.get(judged["winnerCandidateId"], judged["winnerCandidateId"])
    return judged
