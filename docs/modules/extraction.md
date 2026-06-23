# Module: extraction (`modules/extraction/`)

## Purpose
Turn an ASR **transcript** (clinical dictation / call recording) into a structured
`Claim` the auditor can reason over. This is the bridge from the voice/audio
modality (Capa 2) into the same audit pipeline that text claims use — so a spoken
"bill 99214 for a moderate visit, diagnosis J06.9" becomes a `Claim` with one
line `cpt_code=99214, icd10=[J06.9]`.

## Public interface
`modules/extraction/extractor.py`:
- `ClaimExtractor` Protocol: `extract(transcript, *, claim_id) -> Claim`. The
  caller supplies `claim_id` (deterministic; never invented by the model).
- `ClaimExtraction` / `ExtractedLine` — the model's structured read of a
  transcript (line items + optional date/refs), assembled into a `Claim` by
  `_assemble` (unknown identifiers get synthetic, de-identified placeholders —
  never PHI).
- Backends (same seam, swappable):
  - `DemoClaimExtractor` — deterministic regex heuristic, **$0**, offline (the
    default). 5-digit tokens → CPT; ICD-10-shaped tokens → diagnoses.
  - `AnthropicClaimExtractor` — real Claude **Haiku** via structured outputs
    (`messages.parse(output_format=ClaimExtraction)`); BYOK `ANTHROPIC_API_KEY`.
  - `OpenRouterClaimExtractor` — OpenAI-compatible free tier; lenient JSON parse.
- `build_claim_extractor()` — env factory (`VERITAS_DEMO_MODE` /
  `VERITAS_MODEL_BACKEND` / key presence), defaulting to demo.

## Dependencies
- `contracts` (`Claim`, `ClaimLine`) at the seam; `routing/` for the model id;
  reuses `_extract_json` from `classification/models` for lenient free-tier parsing.
- Upstream: `asr/` produces the transcript. Downstream: `agent/graph` audits the
  assembled claim. **Capa 2 leaf** — buildable/testable in isolation.

## How to test in isolation
- Demo: assert codes are pulled from a sample transcript and extraction is
  deterministic; no codes → empty lines.
- Anthropic: inject a fake client; assert it calls Haiku with
  `output_format=ClaimExtraction` and assembles the parsed result into a `Claim`.
- Online (BYOK): `AnthropicClaimExtractor` over a real dictation → `Claim`, then
  feed `build_default_orchestrator().audit(claim)` — verified end-to-end.

## Senior concerns
- **No PHI:** identifiers the transcript doesn't state are filled with synthetic
  placeholders, never fabricated patient data.
- **Hallucinated codes:** the prompt forbids inventing codes; downstream RAG +
  rules ground every asserted inconsistency in cited evidence anyway.
- **Cost:** extraction is a single cheap Haiku pass (no escalation); the demo
  backend keeps the whole voice path free for the public demo.
