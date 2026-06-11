"""The regression gate itself is under test: the committed baseline run must
pass, and the committed drifted run (decimal shifts, dropped tickers, invented
numbers, format violations) must fail with specific findings. This is the
repo's core claim, so it is asserted directly."""

import unittest
from pathlib import Path

from judge_evals.runner import load_golden_cases, run_gate, score_run

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "eval" / "golden"
BASELINE_SCORECARD = GOLDEN / "baseline-scorecard.json"
BASELINE_DIR = ROOT / "eval" / "baselines" / "baseline"
DRIFTED_DIR = ROOT / "eval" / "baselines" / "drifted"


class GoldenDatasetTests(unittest.TestCase):
    def test_golden_set_loads_with_transcripts(self) -> None:
        cases = load_golden_cases(GOLDEN)
        self.assertGreaterEqual(len(cases), 10)
        for case in cases:
            self.assertTrue(case["transcript"].strip(), f"{case['id']} transcript empty")
            self.assertTrue(case["expectedLevels"], f"{case['id']} has no labeled levels")

    def test_every_golden_level_appears_in_its_transcript(self) -> None:
        """Golden labels must be grounded: each expected value (or its spoken
        form) has to exist in the source transcript."""
        for case in load_golden_cases(GOLDEN):
            for level in case["expectedLevels"]:
                spoken = level.get("rawSpoken") or level["value"]
                self.assertIn(spoken, case["transcript"], f"{case['id']}: {spoken} not in transcript")


class GateBehaviorTests(unittest.TestCase):
    def test_baseline_run_passes_the_gate(self) -> None:
        result = run_gate(GOLDEN, BASELINE_SCORECARD, BASELINE_DIR)
        self.assertTrue(result["passed"], f"baseline failed its own gate: {result['findings']}")

    def test_drifted_run_fails_the_gate(self) -> None:
        result = run_gate(GOLDEN, BASELINE_SCORECARD, DRIFTED_DIR)
        self.assertFalse(result["passed"], "gate passed drifted summaries; the suite is broken")
        text = "\n".join(result["findings"])
        self.assertIn("decimal-scale error", text)
        self.assertIn("invented numbers", text)
        self.assertIn("lost golden price levels", text)
        self.assertIn("required section missing or forbidden label", text)

    def test_drift_is_caught_per_case_not_just_on_average(self) -> None:
        """Even if the corpus mean stayed within tolerance, a single case that
        lost a price level must fail the gate."""
        result = run_gate(GOLDEN, BASELINE_SCORECARD, DRIFTED_DIR, tolerance=100.0)
        self.assertFalse(result["passed"])

    def test_missing_summary_scores_zero_not_crash(self) -> None:
        scorecard = score_run(GOLDEN, ROOT / "eval" / "fixtures")
        self.assertEqual(len(scorecard["missingSummaries"]), scorecard["n"])


if __name__ == "__main__":
    unittest.main()
