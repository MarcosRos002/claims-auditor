# Module: classification (`modules/classification/`)

## Purpose
Two-pass, confidence-gated classification of potential inconsistencies. Pass 1
runs the **cheap** model (Claude Haiku `claude-haiku-4-5`, or the distilled small
model from fine-tune-lab); low-confidence cases **escalate** to Pass 2 (Claude
Sonnet `claude-sonnet-4-6`). Covers the judgment the deterministic rules can't
express.

## Public interface
`modules/classification/classifier.py:TwoPassClassifier` implements `Classifier`:
- `classify(claim, context) -> list[AuditFinding]`

`context` is the `RetrievedChunk[]` evidence from `rag`; findings carry those
chunks as citations.

## Dependencies
- `contracts` at the seam; the cost decision comes from `routing/` (injected).
- Runtime: `anthropic` (and optionally the fine-tune-lab model endpoint).
- Phase-2 **leaf** — buildable in its own worktree (mock the model in tests).

## How to test in isolation
- Mock the model client: assert Pass 1 returns confident findings directly, and
  that **low confidence triggers escalation** to Pass 2.
- Assert structured output is validated (bad JSON → bounded re-prompt).
- Assert citations from `context` are attached to findings.

## Senior concerns
- **Failure modes:** over-escalation (cost), under-escalation (quality);
  hallucinated findings without grounding (require citations); refusal handling.
- **Cost/quality:** the escalation threshold is the key tunable and a headline
  cost-per-claim lever, reported by agent-lens.
- **fine-tune-lab seam:** Pass 1 can be served by the distilled model — keep the
  Pass-1 backend swappable.
- **Metrics:** pass-1 vs pass-2 rate, escalation rate, tokens/cost per pass.
