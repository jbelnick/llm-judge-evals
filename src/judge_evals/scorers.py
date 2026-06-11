"""Deterministic scorers for summary fidelity.

These scorers own everything that is mechanically decidable: exact price
levels, decimal-scale errors, invented numbers, ticker coverage, and format
rules. They run with no model calls, so they are fast, unit-testable, and
safe to gate CI on. Qualitative dimensions (catalyst extraction, uncertainty
handling, actionability) belong to the LLM judge in judge.py; the split is
documented in docs/adr/0001-hybrid-deterministic-plus-judge-evals.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

# A price token: a digit run with optional thousands commas and optional decimal.
PRICE_RE = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?(?![\w])")
REQUIRED_SECTIONS_DEFAULT = ("# Recommended Actions",)
FORBIDDEN_LABELS = ("buy signal", "sell signal", "buy on dip")

# Composite weights. Number fidelity dominates by design: a summary that
# invents or shifts price levels is worse than useless no matter how well
# written it is. See the ADR for the rationale and known trade-offs.
WEIGHT_NUMBER_RECALL = 0.60
WEIGHT_NUMBER_PRECISION = 0.15
WEIGHT_FORMAT = 0.10
WEIGHT_TICKER_COVERAGE = 0.15


def normalize_price(text: str) -> str:
    """Canonical numeric string for comparison: commas stripped, then parsed
    with Decimal so numerically equal spellings normalize identically
    ('3,500' -> '3500', '0.0930' -> '0.093', '58.0' -> '58'). No rounding:
    21.101 and 21.10 stay different."""
    raw = str(text or "").replace(",", "").strip().rstrip(".")
    try:
        return format(Decimal(raw).normalize(), "f")
    except InvalidOperation:
        return raw


def prices_in_text(text: str) -> set[str]:
    return {normalize_price(match.group(0)) for match in PRICE_RE.finditer(text or "")}


@dataclass
class NumberExactness:
    matched: int = 0
    total: int = 0
    missing: list[str] = field(default_factory=list)

    @property
    def recall(self) -> float:
        return (self.matched / self.total) if self.total else 1.0


def score_number_exactness(summary: str, expected_levels: list[dict]) -> NumberExactness:
    """Recall of golden price levels: did the summary reproduce each exact value?"""
    summary_prices = prices_in_text(summary)
    result = NumberExactness(total=len(expected_levels))
    for level in expected_levels:
        value = normalize_price(level.get("value", "")) if isinstance(level, dict) else ""
        if value and value in summary_prices:
            result.matched += 1
        elif value:
            result.missing.append(value)
    return result


def detect_scale_errors(summary: str, expected_levels: list[dict]) -> list[dict]:
    """Find golden values that are absent but present shifted by a factor of
    10 or 100 in either direction. A shifted decimal on a price level is the
    most damaging failure mode this harness exists to catch: 0.9832 instead
    of 0.09832 silently turns a watch level into noise."""
    summary_prices = prices_in_text(summary)
    errors: list[dict] = []
    for level in expected_levels:
        if not isinstance(level, dict):
            continue
        raw = str(level.get("value", "")).replace(",", "").strip()
        try:
            value = Decimal(raw)
        except InvalidOperation:
            continue
        canonical = normalize_price(raw)
        if not canonical or canonical in summary_prices:
            continue
        for factor in (Decimal(10), Decimal(100)):
            for shifted in (value * factor, value / factor):
                shifted_text = format(shifted.normalize(), "f")
                if shifted_text in summary_prices:
                    errors.append(
                        {"expected": canonical, "found": shifted_text, "ticker": str(level.get("ticker", ""))}
                    )
                    break
            else:
                continue
            break
    return errors


def score_invented_numbers(summary: str, transcript: str) -> dict:
    """Precision of price tokens against the source transcript: every price in
    the summary must appear somewhere in the transcript. A price with no
    source support is treated as invented. Recall against golden levels
    cannot see hallucinations; this check exists so it cannot be gamed by
    padding the summary with extra numbers."""
    summary_prices = prices_in_text(summary)
    transcript_prices = prices_in_text(transcript)
    invented = sorted(summary_prices - transcript_prices)
    precision = 1.0 if not summary_prices else (len(summary_prices) - len(invented)) / len(summary_prices)
    return {"invented": invented, "precision": precision}


def score_format_adherence(summary: str, required_sections: tuple[str, ...] = REQUIRED_SECTIONS_DEFAULT) -> dict:
    low = (summary or "").lower()
    present = [section for section in required_sections if section.lower() in low]
    forbidden = [label for label in FORBIDDEN_LABELS if label in low]
    return {
        "sectionsPresent": len(present),
        "sectionsRequired": len(required_sections),
        "forbidden": forbidden,
        "ok": len(present) == len(required_sections) and not forbidden,
    }


def score_ticker_coverage(summary: str, required_tickers: list[str]) -> dict:
    text = (summary or "").upper()
    found = [t for t in required_tickers if re.search(r"\b" + re.escape(str(t).upper()) + r"\b", text)]
    return {
        "covered": len(found),
        "required": len(required_tickers),
        "recall": (len(found) / len(required_tickers)) if required_tickers else 1.0,
    }


def composite_score(
    summary: str,
    case: dict,
    *,
    required_sections: tuple[str, ...] = REQUIRED_SECTIONS_DEFAULT,
) -> dict:
    """Single 0-100 score per case. Number recall dominates; invented numbers,
    format, and ticker coverage split the rest."""
    transcript = case.get("transcript", "")
    levels = case.get("expectedLevels", [])
    num = score_number_exactness(summary, levels)
    invented = score_invented_numbers(summary, transcript)
    fmt = score_format_adherence(summary, required_sections)
    coverage = score_ticker_coverage(summary, case.get("requiredTickers", []))
    scale_errors = detect_scale_errors(summary, levels)
    composite = round(
        100.0
        * (
            WEIGHT_NUMBER_RECALL * num.recall
            + WEIGHT_NUMBER_PRECISION * invented["precision"]
            + WEIGHT_FORMAT * (1.0 if fmt["ok"] else 0.0)
            + WEIGHT_TICKER_COVERAGE * coverage["recall"]
        ),
        1,
    )
    return {
        "caseId": case.get("id", ""),
        "composite": composite,
        "numberExactness": {
            "recall": round(num.recall, 4),
            "matched": num.matched,
            "total": num.total,
            "missing": num.missing,
        },
        "inventedNumbers": invented,
        "scaleErrors": scale_errors,
        "format": fmt,
        "tickerCoverage": coverage,
    }


def score_corpus(scored_pairs: list[tuple[str, dict]], **kwargs) -> dict:
    """Aggregate composite + number recall across (summary, case) pairs."""
    per = [composite_score(summary, case, **kwargs) for summary, case in scored_pairs]
    if not per:
        return {"meanComposite": 0.0, "meanNumberRecall": 0.0, "n": 0, "perCase": []}
    mean_comp = round(sum(p["composite"] for p in per) / len(per), 1)
    mean_recall = round(sum(p["numberExactness"]["recall"] for p in per) / len(per), 4)
    return {"meanComposite": mean_comp, "meanNumberRecall": mean_recall, "n": len(per), "perCase": per}
