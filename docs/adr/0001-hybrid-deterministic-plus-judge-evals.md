---
Date Created: 2026-06-16
Date modified: 2026-06-16
Status: active
Tags:
  - belnick
  - project
  - llm-judge-evals
---

# ADR 0001: Hybrid deterministic scoring plus a rubric-anchored LLM judge, gated in CI

Status: Accepted. Extracted from a production stock-summary workflow (June 2026).

## Context

A nightly summarization workflow turns long spoken market commentary into a
short levels-first report. Multiple candidate models generate summaries; one
winner is delivered. Two things kept going wrong before this eval layer
existed:

1. Decimal-scale errors. A model writes 0.9832 where the speaker said
   0.09832. The summary reads perfectly and is dangerously wrong. This is the
   single most damaging failure mode in the domain.
2. Silent regressions. A model swap or prompt change would degrade fidelity
   and nobody noticed until a human caught it downstream.

## Decision

Split evaluation by decidability and let each layer own what it can actually
verify.

Deterministic scorers own everything mechanically checkable: exact recall of
golden price levels, precision of every number against the source transcript
(invented numbers), decimal-scale shift detection, required sections,
forbidden trade-signal labels, and ticker coverage. These run in milliseconds
with no model calls, so CI gates on them for every push.

An LLM judge owns the qualitative dimensions a string comparison cannot
reach: transcript fidelity in wording, catalyst extraction, uncertainty
handling, actionability, structure, and concision. The judge ranks candidate
summaries and explains its ranking.

A regression gate compares any candidate run against a committed baseline
scorecard and fails CI on a composite drop beyond tolerance, on any case that
lost a golden level, on new scale errors, on new invented numbers, or on
format violations. Per-case checks matter because a corpus mean can hide one
badly broken transcript among nine good ones.

## Why judge-based scoring at all

Exact-match scoring cannot tell a faithful summary from a technically
complete but useless one. "Did the summary preserve the speaker's uncertainty
about the breakout" has no regex. Ranking multiple candidates also needs
graded judgment, not boolean checks. So the judge stays, but it is treated as
a powerful unreliable instrument and is wrapped accordingly.

## Why the judge is never trusted alone

Naive LLM-as-judge fails in known, repeatable ways. Each one has a concrete
mitigation in this repo:

| Naive-judge failure | Mitigation here |
|---|---|
| Scores cluster in the 80s and cannot rank candidates | Rubric anchoring: each score band is pinned to concrete behavior in the prompt |
| Fluent but wrong summaries score high (style bias) | Deterministic cross-check caps: code re-detects scale errors and caps the judge score at 79 (one error) or 69 (multiple), after judging |
| Judges reward models they recognize (identity bias) | Candidate anonymization: the judge only ever sees candidate-1..n |
| Judges are unreliable at arithmetic and decimal scale | Numbers are never the judge's job; the deterministic layer owns them |
| Live judge calls make CI flaky and slow | CI replays a committed fixture response; live judging is opt-in by environment variable |

The cap design is the important part: the mitigation lives in code, not in
the prompt. A prompt instruction ("treat scale errors as severe") helps but
cannot be relied on; the demo in this repo shows a judge response scoring a
shifted-decimal summary 88 and the cap pulling it to 79.

## Why a golden dataset this small

Ten labeled cases are enough to catch every failure mode this gate exists to
catch, and small enough that a human can re-verify every label in minutes.
In production the golden set was bootstrapped by model extraction over real
transcripts and then spot-checked by hand; the honest caveat is that a
model-extracted yardstick is a draft until a human verifies it. The public
set here is synthetic and hand-labeled, with a test asserting every labeled
level actually appears in its source transcript.

## Known limitations

- Golden sets go stale. When the workflow's scope changes, the dataset must
  change with it, and the baseline scorecard is refreshed through a reviewed
  commit so quality changes are visible in the diff.
- Position bias is reduced but not eliminated: candidates are presented in a
  deterministic anonymized order. Pairwise comparison with order swapping is
  the upgrade path if ranking noise becomes a problem.
- The fixture-replayed judge keeps CI deterministic but does not exercise a
  live model; live judge behavior can drift and should be re-sampled when the
  judge model changes.
- Recall is measured against labeled levels only. The invented-number
  precision check closes the obvious gaming path (padding the summary with
  extra numbers), but a summary could still misattribute a real number to the
  wrong ticker. Source-span attribution is the next hardening step.

## Revisit when

- Ranking decisions start flipping between adjacent runs (add pairwise
  comparison with order swapping).
- The workflow adds a second domain (split golden sets per domain).
- A regression escapes the gate (add the escaped failure as a drifted case
  first, then fix).
