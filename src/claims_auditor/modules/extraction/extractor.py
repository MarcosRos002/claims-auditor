"""Transcript -> Claim extraction (the bridge from ASR to the audit).

A spoken clinical dictation ("billing 99214 for a moderate visit, diagnosis
J06.9...") becomes a structured :class:`Claim` the auditor can reason over. Like
the classifier, the model is a swappable backend behind one seam
(``ClaimExtractor`` Protocol), so the whole path runs offline and free:

- ``DemoClaimExtractor`` — deterministic regex heuristic ($0, offline, default):
  pulls CPT (5-digit) and ICD-10 codes straight from the text.
- ``AnthropicClaimExtractor`` — real Claude (Haiku) via structured outputs
  (``messages.parse(output_format=ClaimExtraction)``); BYOK ``ANTHROPIC_API_KEY``.
- ``OpenRouterClaimExtractor`` — OpenAI-compatible free tier, lenient JSON parse.

``build_claim_extractor()`` selects one from the environment, defaulting to demo.
The model only extracts the clinical line items; identifiers the model can't know
(patient/provider refs) get synthetic, de-identified placeholders — never PHI. See
``docs/modules/extraction.md``.
"""

from __future__ import annotations

import json
import os
import re
from typing import Protocol

from pydantic import BaseModel, Field

from claims_auditor.contracts import Claim, ClaimLine
from claims_auditor.modules.classification.models import _extract_json
from claims_auditor.routing.cost_router import HAIKU

# CPT/HCPCS: 5 digits. ICD-10: a letter, two alnum, optional ".x" tail.
_CPT_RE = re.compile(r"\b(\d{5})\b")
_ICD_RE = re.compile(r"\b([A-TV-Z][0-9][0-9A-Z](?:\.[0-9A-Z]{1,4})?)\b")

# Synthetic, de-identified placeholders for fields a transcript rarely states.
_PLACEHOLDER_PATIENT = "SYN-UNKNOWN"
_PLACEHOLDER_NPI = "0000000000"
_UNKNOWN_DATE = "unknown"

_SYSTEM = (
    "You extract a medical-billing claim from a clinical dictation transcript. "
    "Return the billed line items: for each, the CPT/HCPCS code, any ICD-10 "
    "diagnosis codes, and units (default 1). Also capture the date of service if "
    "stated (ISO-8601). Extract only what is in the transcript; do not invent "
    "codes. Data is synthetic — no real patient information."
)


class ExtractedLine(BaseModel):
    """A line item the model pulled from the transcript."""

    cpt_code: str
    icd10_codes: list[str] = Field(default_factory=list)
    units: int = 1


class ClaimExtraction(BaseModel):
    """The model's structured read of a transcript (pre-assembly)."""

    lines: list[ExtractedLine] = Field(default_factory=list)
    date_of_service: str | None = None
    patient_ref: str | None = None
    provider_npi: str | None = None


class ClaimExtractor(Protocol):
    """Transcript -> Claim. ``claim_id`` is supplied by the caller (deterministic)."""

    def extract(self, transcript: str, *, claim_id: str) -> Claim: ...


def _assemble(extraction: ClaimExtraction, *, claim_id: str) -> Claim:
    """Build a Claim from an extraction, filling unknowns with synthetic placeholders."""
    return Claim(
        claim_id=claim_id,
        patient_ref=extraction.patient_ref or _PLACEHOLDER_PATIENT,
        provider_npi=extraction.provider_npi or _PLACEHOLDER_NPI,
        date_of_service=extraction.date_of_service or _UNKNOWN_DATE,
        lines=[
            ClaimLine(cpt_code=line.cpt_code, icd10_codes=line.icd10_codes, units=line.units)
            for line in extraction.lines
        ],
    )


class DemoClaimExtractor:
    """Deterministic, offline, $0 extractor. The default backend.

    Heuristic: every 5-digit token is a CPT, every ICD-10-shaped token a
    diagnosis. One line per CPT (in order of appearance), each carrying all the
    diagnoses found in the transcript. Pure and deterministic.
    """

    def extract(self, transcript: str, *, claim_id: str) -> Claim:
        cpts = _dedupe(_CPT_RE.findall(transcript))
        icds = _dedupe(_ICD_RE.findall(transcript))
        extraction = ClaimExtraction(
            lines=[ExtractedLine(cpt_code=cpt, icd10_codes=list(icds)) for cpt in cpts]
        )
        return _assemble(extraction, claim_id=claim_id)


class AnthropicClaimExtractor:
    """Real Claude (Haiku) extractor (BYOK). Injectable client for offline tests."""

    def __init__(self, *, client: object | None = None, max_tokens: int = 1024) -> None:
        self._client = client
        self._max_tokens = max_tokens

    def _ensure_client(self) -> object:
        if self._client is None:
            import anthropic  # lazy

            self._client = anthropic.Anthropic()
        return self._client

    def extract(self, transcript: str, *, claim_id: str) -> Claim:
        client = self._ensure_client()
        response = client.messages.parse(
            model=HAIKU,
            max_tokens=self._max_tokens,
            system=_SYSTEM,
            messages=[{"role": "user", "content": f"TRANSCRIPT:\n{transcript}"}],
            output_format=ClaimExtraction,
        )
        return _assemble(response.parsed_output, claim_id=claim_id)


class OpenRouterClaimExtractor:
    """OpenAI-compatible free-tier extractor (BYOK). Lenient JSON parse."""

    _BASE_URL = "https://openrouter.ai/api/v1"
    _MODEL = "meta-llama/llama-3.3-70b-instruct:free"

    def __init__(self, *, client: object | None = None, max_tokens: int = 1024) -> None:
        self._client = client
        self._max_tokens = max_tokens

    def _ensure_client(self) -> object:
        if self._client is None:
            from openai import OpenAI  # lazy

            self._client = OpenAI(
                base_url=self._BASE_URL, api_key=os.environ.get("OPENROUTER_API_KEY")
            )
        return self._client

    def extract(self, transcript: str, *, claim_id: str) -> Claim:
        client = self._ensure_client()
        schema = json.dumps(ClaimExtraction.model_json_schema())
        system = (
            f"{_SYSTEM}\n\nReturn ONLY a JSON object matching this schema — no "
            f"prose, no markdown fences:\n{schema}"
        )
        completion = client.chat.completions.create(
            model=self._MODEL,
            max_tokens=self._max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"TRANSCRIPT:\n{transcript}"},
            ],
        )
        payload = completion.choices[0].message.content or "{}"
        extraction = ClaimExtraction.model_validate_json(_extract_json(payload))
        return _assemble(extraction, claim_id=claim_id)


def build_claim_extractor() -> (
    DemoClaimExtractor | AnthropicClaimExtractor | OpenRouterClaimExtractor
):
    """Pick an extractor backend from the environment. Defaults to demo ($0).

    Mirrors ``build_classifier_model``: ``VERITAS_DEMO_MODE`` wins, then
    ``VERITAS_MODEL_BACKEND``, then key presence (Anthropic, then OpenRouter),
    else demo.
    """
    if _truthy(os.environ.get("VERITAS_DEMO_MODE")):
        return DemoClaimExtractor()

    backend = (os.environ.get("VERITAS_MODEL_BACKEND") or "").strip().lower()
    if backend == "anthropic":
        return AnthropicClaimExtractor()
    if backend == "openrouter":
        return OpenRouterClaimExtractor()
    if backend == "demo":
        return DemoClaimExtractor()

    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicClaimExtractor()
    if os.environ.get("OPENROUTER_API_KEY"):
        return OpenRouterClaimExtractor()
    return DemoClaimExtractor()


def _dedupe(items: list[str]) -> list[str]:
    """Order-preserving de-duplication."""
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}
