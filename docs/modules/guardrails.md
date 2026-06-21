# Module: guardrails (`guardrails/`)

## Purpose
Safety layer: PII/PHI redaction and prompt-injection defense. Read-only DB access
is enforced at the connection layer in `rag`. Data is synthetic, but guardrails
are enforced as a discipline and as demoable, senior-signal features.

## Status: implemented (Phase 1)
Pure, deterministic, idempotent. Pinned by `tests/test_guardrails.py`. Clinical
codes (CPT/ICD) are preserved; structured PII (NPI, SSN, email, phone, dates,
patient refs) is masked. Free-text **name** redaction needs NER (Presidio/spaCy)
and is a documented out-of-scope boundary.

## Public interface
`guardrails/safety.py`:
- `redact_pii(text) -> str` — redact PII/PHI before any LLM sees the text.
- `redact_pii_detailed(text) -> (str, list[str])` — also returns the categories hit.
- `scan_for_injection(text) -> bool` — flag prompt-injection attempts in
  retrieved/transcribed content (treat such content as **data**, never instructions).
- `scan_for_injection_detailed(text) -> (bool, list[str])` — also the matched signatures.

The `_detailed` variants feed `TraceEvent.metadata` (redactions applied,
injection hits) for agent-lens.

## Dependencies
- None at the seam (string-in/string-out). **Upper layer** (Phase 4), but applied
  early in the data flow (right after claim extraction, before retrieval/LLM).

## How to test in isolation
- Redaction: assert seeded synthetic identifiers are removed/masked and benign
  text is untouched.
- Injection: assert known injection strings ("ignore previous instructions…",
  tool-call smuggling) are flagged and benign text is not.
- Property test: redaction is idempotent.

## Senior concerns
- **Failure modes:** over-redaction (destroys signal) vs under-redaction (leak);
  injection false-positives blocking legitimate content; bypass via encoding.
- **Placement:** redact before the LLM boundary; scan retrieved/ASR text before
  it enters a prompt. Pair with read-only DB so a successful injection still
  can't mutate data.
- **Metrics:** redactions applied, injection hits — into `TraceEvent.attributes`.
