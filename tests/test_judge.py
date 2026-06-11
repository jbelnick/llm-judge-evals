"""Tests for the judge harness: parsing, anonymization, and the deterministic
scale-error caps. The judge model itself is replayed from a fixture or stubbed;
no network calls."""

import json
import unittest

from judge_evals import judge


class ParsingTests(unittest.TestCase):
    def test_parses_fenced_json_with_prose(self) -> None:
        raw = "Here is my evaluation:\n```json\n" + json.dumps(
            {"winnerCandidateId": "candidate-1", "rankings": [{"candidateId": "candidate-1", "score": 91}]}
        ) + "\n```\nHope that helps!"
        parsed = judge.parse_judge_response(raw)
        self.assertEqual(parsed["winnerCandidateId"], "candidate-1")
        self.assertEqual(parsed["rankings"][0]["score"], 91)

    def test_rejects_output_without_rankings(self) -> None:
        with self.assertRaises(ValueError):
            judge.parse_judge_response('{"winnerCandidateId": "candidate-1"}')
        with self.assertRaises(ValueError):
            judge.parse_judge_response("no json here at all")

    def test_normalizes_out_of_range_scores(self) -> None:
        raw = json.dumps(
            {
                "winnerCandidateId": "candidate-1",
                "rankings": [
                    {"candidateId": "candidate-1", "score": 250},
                    {"candidateId": "candidate-2", "score": "not a number"},
                ],
            }
        )
        parsed = judge.parse_judge_response(raw)
        self.assertEqual(parsed["rankings"][0]["score"], 100)
        self.assertEqual(parsed["rankings"][1]["score"], 0)


class AnonymizationTests(unittest.TestCase):
    def test_labels_never_reach_the_prompt(self) -> None:
        summaries = {"gpt-best-model": "summary a", "local-qwen": "summary b"}
        candidates, mapping = judge.anonymize_candidates(summaries)
        prompt = judge.build_judge_prompt("a transcript", candidates)
        self.assertNotIn("gpt-best-model", prompt)
        self.assertNotIn("local-qwen", prompt)
        self.assertIn("candidate-1", prompt)
        self.assertEqual(sorted(mapping.values()), ["gpt-best-model", "local-qwen"])


class ScaleCapTests(unittest.TestCase):
    LEVELS = [{"ticker": "DOGE", "value": "0.09832"}, {"ticker": "XRP", "value": "2.18"}]

    def _judged(self, score: int) -> dict:
        return {
            "winnerCandidateId": "candidate-1",
            "rankings": [{"candidateId": "candidate-1", "score": score}],
        }

    def test_single_scale_error_caps_at_79(self) -> None:
        summaries = {"candidate-1": "- DOGE support: 0.9832\n- XRP support: 2.18\n"}
        capped = judge.apply_scale_caps(self._judged(92), summaries, self.LEVELS)
        self.assertEqual(capped["rankings"][0]["score"], judge.SINGLE_SCALE_ERROR_CAP)
        self.assertEqual(capped["rankings"][0]["cappedFrom"], 92)

    def test_multiple_scale_errors_cap_at_69(self) -> None:
        summaries = {"candidate-1": "- DOGE support: 0.9832\n- XRP support: 21.8\n"}
        capped = judge.apply_scale_caps(self._judged(95), summaries, self.LEVELS)
        self.assertEqual(capped["rankings"][0]["score"], judge.MULTI_SCALE_ERROR_CAP)

    def test_clean_summary_is_not_capped(self) -> None:
        summaries = {"candidate-1": "- DOGE support: 0.09832\n- XRP support: 2.18\n"}
        capped = judge.apply_scale_caps(self._judged(92), summaries, self.LEVELS)
        self.assertEqual(capped["rankings"][0]["score"], 92)
        self.assertNotIn("cappedFrom", capped["rankings"][0])

    def test_caps_reorder_winner(self) -> None:
        judged = {
            "winnerCandidateId": "candidate-2",
            "rankings": [
                {"candidateId": "candidate-2", "score": 90},
                {"candidateId": "candidate-1", "score": 85},
            ],
        }
        summaries = {
            "candidate-1": "- DOGE support: 0.09832\n",
            "candidate-2": "- DOGE support: 0.9832\n",
        }
        capped = judge.apply_scale_caps(judged, summaries, [{"ticker": "DOGE", "value": "0.09832"}])
        self.assertEqual(capped["winnerCandidateId"], "candidate-1")


class EndToEndStubTests(unittest.TestCase):
    class StubClient:
        def __init__(self, response: str):
            self.response = response
            self.prompts: list[str] = []

        def complete(self, prompt: str) -> str:
            self.prompts.append(prompt)
            return self.response

    def test_judge_candidates_full_pass(self) -> None:
        response = json.dumps(
            {
                "winnerCandidateId": "candidate-2",
                "rankings": [
                    {"candidateId": "candidate-2", "score": 88, "rationale": "complete and well structured"},
                    {"candidateId": "candidate-1", "score": 84, "rationale": "slightly thin"},
                ],
            }
        )
        client = self.StubClient(response)
        summaries = {
            "model-alpha-prod": "- DOGE support: 0.09832\n",
            "model-beta-swap": "- DOGE support: 0.9832\n",
        }
        judged = judge.judge_candidates(
            client, "DOGE support is 0.09832.", summaries, [{"ticker": "DOGE", "value": "0.09832"}]
        )
        # anonymized labels sort: candidate-1=model-alpha-prod, candidate-2=model-beta-swap;
        # the judge preferred the swapped one, the cap must overrule it.
        self.assertEqual(judged["winnerLabel"], "model-alpha-prod")
        by_label = {entry["label"]: entry for entry in judged["rankings"]}
        self.assertEqual(by_label["model-beta-swap"]["score"], judge.SINGLE_SCALE_ERROR_CAP)
        self.assertNotIn("model-alpha-prod", client.prompts[0])
        self.assertNotIn("model-beta-swap", client.prompts[0])


if __name__ == "__main__":
    unittest.main()
