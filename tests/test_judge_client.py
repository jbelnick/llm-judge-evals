"""Tests for the judge clients: fixture replay determinism and the loud
failure on unknown prompts. The live client is exercised only for its
configuration guard; no network calls in tests."""

import json
import tempfile
import unittest
from pathlib import Path

from judge_evals.judge_client import OpenAICompatibleJudge, RecordedJudge, record_fixture


class RecordedJudgeTests(unittest.TestCase):
    def test_record_then_replay_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "responses.json"
            prompt = "instructions...\n# Candidate Summaries\n## candidate-1\ntext"
            record_fixture(fixture, prompt, '{"rankings": []}')
            client = RecordedJudge(fixture)
            self.assertEqual(client.complete(prompt), '{"rankings": []}')

    def test_unknown_prompt_raises_instead_of_silently_skipping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "responses.json"
            fixture.write_text(json.dumps({"abc123": "response"}), encoding="utf-8")
            client = RecordedJudge(fixture)
            with self.assertRaises(KeyError):
                client.complete("a prompt that was never recorded")

    def test_fingerprint_ignores_transcript_preamble(self) -> None:
        a = "long preamble A\n# Candidate Summaries\nsame block"
        b = "different preamble B\n# Candidate Summaries\nsame block"
        self.assertEqual(RecordedJudge.fingerprint(a), RecordedJudge.fingerprint(b))


class LiveClientGuardTests(unittest.TestCase):
    def test_requires_endpoint_configuration(self) -> None:
        with self.assertRaises(ValueError):
            OpenAICompatibleJudge(base_url="", model="")


class CommittedDemoFixtureTests(unittest.TestCase):
    def test_demo_fixture_is_valid_json_with_rankings(self) -> None:
        fixture = Path(__file__).resolve().parents[1] / "eval" / "fixtures" / "judge-demo-responses.json"
        data = json.loads(fixture.read_text(encoding="utf-8"))
        self.assertTrue(data, "demo fixture is empty")
        for response_text in data.values():
            payload = json.loads(response_text)
            self.assertIn("rankings", payload)


if __name__ == "__main__":
    unittest.main()
