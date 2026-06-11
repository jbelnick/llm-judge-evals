"""Public-safe eval harness: deterministic scorers + rubric-anchored LLM judge
with a CI regression gate. See README.md and docs/adr/ for design rationale."""

from .judge import apply_scale_caps, build_judge_prompt, judge_candidates, parse_judge_response
from .runner import load_golden_cases, regression_findings, run_gate, score_run
from .scorers import composite_score, detect_scale_errors, score_corpus

__all__ = [
    "apply_scale_caps",
    "build_judge_prompt",
    "judge_candidates",
    "parse_judge_response",
    "load_golden_cases",
    "regression_findings",
    "run_gate",
    "score_run",
    "composite_score",
    "detect_scale_errors",
    "score_corpus",
]
