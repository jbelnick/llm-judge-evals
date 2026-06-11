"""Judge clients: a recorded client for CI and an OpenAI-compatible client
for live runs.

CI never makes a network call. The recorded client replays a committed judge
response keyed by a stable hash of the prompt's candidate block, which keeps
the regression gate deterministic and free to run on every push. The live
client targets any OpenAI-compatible /chat/completions endpoint (a local
server such as LM Studio or Ollama works) and is opt-in via environment
variables.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from pathlib import Path


class RecordedJudge:
    """Replay judge responses from a committed fixture file.

    The fixture maps a prompt fingerprint to the raw text the judge returned
    when the fixture was recorded. A missing fingerprint raises immediately:
    a silent fallback would turn the judge step into a no-op without anyone
    noticing.
    """

    def __init__(self, fixture_path: str | Path):
        self.fixture_path = Path(fixture_path)
        self._responses = json.loads(self.fixture_path.read_text(encoding="utf-8"))

    @staticmethod
    def fingerprint(prompt: str) -> str:
        anchor = prompt.find("# Candidate Summaries")
        material = prompt[anchor:] if anchor != -1 else prompt
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]

    def complete(self, prompt: str) -> str:
        key = self.fingerprint(prompt)
        if key not in self._responses:
            known = ", ".join(sorted(self._responses))
            raise KeyError(f"no recorded judge response for fingerprint {key} (known: {known})")
        return self._responses[key]


class OpenAICompatibleJudge:
    """Minimal stdlib client for any OpenAI-compatible chat endpoint.

    Configuration comes from the environment:
        JUDGE_BASE_URL   e.g. http://localhost:1234/v1 (required)
        JUDGE_MODEL      model name the endpoint expects (required)
        JUDGE_API_KEY    bearer token if the endpoint needs one (optional)
    """

    def __init__(self, base_url: str | None = None, model: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or os.environ.get("JUDGE_BASE_URL", "")).rstrip("/")
        self.model = model or os.environ.get("JUDGE_MODEL", "")
        self.api_key = api_key or os.environ.get("JUDGE_API_KEY", "")
        if not self.base_url or not self.model:
            raise ValueError("JUDGE_BASE_URL and JUDGE_MODEL must be set for live judging")

    def complete(self, prompt: str, *, timeout_seconds: int = 300) -> str:
        body = json.dumps(
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}),
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        choices = payload.get("choices") or []
        if not choices:
            raise ValueError("judge endpoint returned no choices")
        return str((choices[0].get("message") or {}).get("content", ""))


def record_fixture(fixture_path: str | Path, prompt: str, response_text: str) -> None:
    """Append one prompt/response pair to a fixture file (used when refreshing
    recorded judge responses after an intentional prompt or dataset change)."""
    path = Path(fixture_path)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data[RecordedJudge.fingerprint(prompt)] = response_text
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
