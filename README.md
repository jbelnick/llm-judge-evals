---
Date Created: 2026-06-16
Date modified: 2026-06-16
Status: active
Tags:
  - belnick
  - project
  - llm-judge-evals
  - readme
---

# LLM Judge Evals

[![Verify](https://github.com/jbelnick/llm-judge-evals/actions/workflows/verify.yml/badge.svg)](https://github.com/jbelnick/llm-judge-evals/actions/workflows/verify.yml)

A working eval suite for an AI summarization workflow: a hand-labeled golden
dataset, deterministic fidelity scorers, a rubric-anchored LLM judge with
code-enforced guardrails, and a CI regression gate that turns red when a
model swap or prompt change degrades output quality. Extracted and sanitized
from the eval layer of a stock-update summarization workflow that runs
nightly on my self-hosted agent stack.

The question this repo answers: how do you let models and prompts change
while guaranteeing that a quality regression cannot ship silently?

## The 60-second tour

```bash
make gate    # score current outputs against the golden set: PASSES
make drift   # score outputs after a simulated model swap: gate FAILS, on purpose
make demo    # watch the judge get fooled by a fluent-but-wrong summary, and the cap catch it
```

`make drift` is the point of the repo. The drifted outputs contain the real
failure modes this gate exists to catch, and CI asserts the gate rejects
every one of them:

```text
GATE FAIL: 20 regression(s)
  - case-02: lost golden price levels (2 -> 1; missing: 0.09832)
  - case-02: new decimal-scale error (DOGE: 0.09832 became 0.9832)
  - case-06: required section missing or forbidden label present
  - case-09: invented numbers with no transcript support (225)
  ...
```

`make demo` shows why the LLM judge is never trusted alone. The judge scores
a shifted-decimal summary 93, above the faithful candidate, because it reads
well; the deterministic cross-check caps it to 79, and that cap alone flips
the winner:

```text
winner: pipeline-current
  pipeline-current           score 90
  pipeline-after-model-swap  score 79 (judge said 93, capped for scale error)
    scale error: expected 0.09832, found 0.9832
```

## What this shows

- A golden dataset (10 labeled transcript cases) small enough to hand-verify
  and rich enough to encode every failure mode the gate must catch. A test
  asserts every labeled level is grounded in its source transcript.
- Deterministic scorers for everything mechanically decidable: exact level
  recall, invented-number precision against the transcript, decimal-scale
  shift detection, required sections, forbidden trade-signal labels, ticker
  coverage.
- An LLM-as-judge harness with three documented mitigations for naive-judge
  failure: rubric-anchored score bands, candidate anonymization, and
  deterministic score caps enforced in code rather than in the prompt. See
  the [ADR](docs/adr/0001-hybrid-deterministic-plus-judge-evals.md) for the
  full trade-off discussion.
- A regression gate that fails CI on composite drop, lost levels, new scale
  errors, invented numbers, or format violations, checked per case so a
  corpus mean cannot hide one broken transcript.
- The gate itself is under test: CI runs the gate on a known-good baseline
  (must pass) and on a known-drifted set (must fail). An eval suite that
  cannot fail is decoration.

## How a change ships

1. Change a prompt, swap a model, or modify the pipeline.
2. Regenerate summaries for the golden cases and run
   `scripts/run_regression_gate.py --candidate <your-run-dir>`.
3. If the gate fails, the findings name the case and the exact numbers lost.
4. If the change is an intentional improvement, refresh the baseline with
   `scripts/run_eval.py --summaries <your-run-dir> --out eval/golden/baseline-scorecard.json`
   and commit it. The scorecard diff is the reviewable record of the quality
   change. In the production workflow this same keep-or-revert rule governs
   automated prompt tuning: a proposed prompt rule is kept only if the
   composite improves.

## Repository layout

```text
docs/adr/              Design rationale and known failure modes
eval/golden/           Golden dataset: cases.jsonl, transcripts, baseline scorecard
eval/baselines/        Committed baseline (passing) and drifted (failing) summary runs
eval/fixtures/         Committed judge response for deterministic CI replay
scripts/               run_eval, run_regression_gate, run_judge_demo, public_safety_scan
src/judge_evals/       scorers, judge, judge clients, gate runner
tests/                 Unit tests plus the gate-catches-drift assertions
```

## Live judging

CI never makes a network call. To run the judge against a real endpoint
(any OpenAI-compatible server, local or hosted):

```bash
export JUDGE_BASE_URL=http://localhost:1234/v1
export JUDGE_MODEL=your-model-name
PYTHONPATH=src python3 scripts/run_judge_demo.py --live
```

## Part Of One System

This repo is the quality gate in a four-repo portfolio that reads as one
system:

- [cerebellum-local-ai-router](https://github.com/jbelnick/cerebellum-local-ai-router):
  routing and cost control, deciding which model does the work.
- [meeting-intelligence-pipelines](https://github.com/jbelnick/meeting-intelligence-pipelines):
  the workflow shape, turning raw transcripts into reviewed artifacts.
- [meeting-intelligence-mcp](https://github.com/jbelnick/meeting-intelligence-mcp):
  the MCP server that exposes the pipeline's tools to any MCP client.
- llm-judge-evals (this repo): the quality gate that lets the others
  change safely.

## Real vs synthetic

The scorer logic, judge harness design, cap rules, and gate semantics mirror
the production system. All transcripts are synthetic and written for this
repo; the golden labels are hand-verified; the committed judge fixture
reproduces a judge failure mode observed in practice. No client data, broker
data, holdings, or private operational details appear anywhere in this
repository, and CI runs a public-safety scan to keep it that way. Nothing
here is investment advice; tickers and levels are illustrative.

## License

MIT. See [LICENSE](LICENSE).
