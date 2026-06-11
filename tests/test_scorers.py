"""Unit tests for the deterministic scorers. No model calls."""

import unittest

from judge_evals import scorers


class NumberExactnessTests(unittest.TestCase):
    def test_recall_and_comma_normalization(self) -> None:
        summary = "## BTC\n- Support: 67000\n## ETH\n- Resistance: 3,500\n"
        levels = [
            {"ticker": "BTC", "levelType": "support", "value": "67000"},
            {"ticker": "ETH", "levelType": "resistance", "value": "3500"},
            {"ticker": "SOL", "levelType": "support", "value": "150"},
        ]
        result = scorers.score_number_exactness(summary, levels)
        self.assertEqual(result.matched, 2)
        self.assertEqual(result.total, 3)
        self.assertIn("150", result.missing)
        self.assertAlmostEqual(result.recall, 2 / 3, places=3)

    def test_decimal_scale_value_must_match_exactly(self) -> None:
        levels = [{"ticker": "DOGE", "levelType": "support", "value": "0.09832"}]
        good = "## DOGE\n- Support: 0.09832\n"
        bad = "## DOGE\n- Support: 0.9832\n"
        self.assertEqual(scorers.score_number_exactness(good, levels).matched, 1)
        self.assertEqual(scorers.score_number_exactness(bad, levels).matched, 0)

    def test_normalize_price_numeric_equality(self) -> None:
        self.assertEqual(scorers.normalize_price("0.0930"), scorers.normalize_price("0.093"))
        self.assertEqual(scorers.normalize_price("58"), scorers.normalize_price("58.0"))
        self.assertEqual(scorers.normalize_price("3,500"), scorers.normalize_price("3500"))
        self.assertNotEqual(scorers.normalize_price("21.101"), scorers.normalize_price("21.10"))


class ScaleErrorTests(unittest.TestCase):
    def test_detects_factor_of_ten_shift(self) -> None:
        levels = [{"ticker": "DOGE", "value": "0.09832"}]
        errors = scorers.detect_scale_errors("- Support: 0.9832\n", levels)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["expected"], "0.09832")
        self.assertEqual(errors[0]["found"], "0.9832")

    def test_detects_factor_of_hundred_shift(self) -> None:
        levels = [{"ticker": "GLD", "value": "2650"}]
        errors = scorers.detect_scale_errors("- Support: 26.5\n", levels)
        self.assertEqual(len(errors), 1)

    def test_no_error_when_value_present_or_simply_missing(self) -> None:
        levels = [{"ticker": "BTC", "value": "67000"}]
        self.assertEqual(scorers.detect_scale_errors("- Support: 67000\n", levels), [])
        self.assertEqual(scorers.detect_scale_errors("- nothing numeric here\n", levels), [])


class InventedNumberTests(unittest.TestCase):
    def test_summary_numbers_must_appear_in_transcript(self) -> None:
        transcript = "Support is 152 and the other level is 0.4180."
        clean = scorers.score_invented_numbers("- Support: 152\n- Support: 0.4180\n", transcript)
        self.assertEqual(clean["invented"], [])
        self.assertEqual(clean["precision"], 1.0)
        invented = scorers.score_invented_numbers("- Support: 152\n- Target: 0.62\n", transcript)
        self.assertEqual(invented["invented"], ["0.62"])
        self.assertLess(invented["precision"], 1.0)


class FormatAndCoverageTests(unittest.TestCase):
    def test_format_flags_forbidden_labels(self) -> None:
        ok = scorers.score_format_adherence("# Recommended Actions\n- watch")
        self.assertTrue(ok["ok"])
        bad = scorers.score_format_adherence("Support Level (Buy Signal): 100\n# Recommended Actions\n")
        self.assertFalse(bad["ok"])
        self.assertIn("buy signal", bad["forbidden"])

    def test_ticker_coverage(self) -> None:
        result = scorers.score_ticker_coverage("## BTC holds. QQQ next.", ["BTC", "QQQ", "ETH"])
        self.assertEqual(result["covered"], 2)
        self.assertAlmostEqual(result["recall"], 2 / 3, places=3)


class CompositeTests(unittest.TestCase):
    CASE = {
        "id": "case-x",
        "transcript": "BTC support 67000 and ETH resistance 3,500. # context",
        "requiredTickers": ["BTC", "ETH"],
        "expectedLevels": [{"ticker": "BTC", "value": "67000"}, {"ticker": "ETH", "value": "3500"}],
    }

    def test_perfect_summary_scores_100(self) -> None:
        summary = "## BTC\n- Support: 67000\n## ETH\n- Resistance: 3,500\n# Recommended Actions\n- watch BTC"
        self.assertEqual(scorers.composite_score(summary, self.CASE)["composite"], 100.0)

    def test_composite_is_dominated_by_number_fidelity(self) -> None:
        full = "## BTC\n- Support: 67000\n## ETH\n- Resistance: 3,500\n# Recommended Actions\n- watch"
        half = "## BTC\n- Support: 67000\n## ETH\n- waiting\n# Recommended Actions\n- watch"
        self.assertGreater(
            scorers.composite_score(full, self.CASE)["composite"],
            scorers.composite_score(half, self.CASE)["composite"],
        )

    def test_score_corpus_aggregates(self) -> None:
        case = {"id": "c", "transcript": "level 100 here", "requiredTickers": [], "expectedLevels": [{"value": "100"}]}
        agg = scorers.score_corpus([("- Levels: 100\n# Recommended Actions\n", case), ("- nothing\n# Recommended Actions\n", case)])
        self.assertEqual(agg["n"], 2)
        self.assertAlmostEqual(agg["meanNumberRecall"], 0.5, places=3)


if __name__ == "__main__":
    unittest.main()
