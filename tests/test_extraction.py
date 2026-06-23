"""Tests for transcript -> Claim extraction (demo / Anthropic / factory).

All offline: the demo extractor is a deterministic regex heuristic; the Anthropic
extractor is exercised with an injected fake client (no network, no key, no cost).
"""

from __future__ import annotations

import pytest

from claims_auditor.contracts import Claim
from claims_auditor.modules.extraction.extractor import (
    AnthropicClaimExtractor,
    ClaimExtraction,
    DemoClaimExtractor,
    ExtractedLine,
    build_claim_extractor,
)
from claims_auditor.routing.cost_router import HAIKU

TRANSCRIPT = (
    "Okay, established patient seen today. Billing CPT 99214 for a moderate "
    "complexity visit. Diagnosis is J06.9, acute upper respiratory infection. "
    "One unit."
)


# --- demo-mode -------------------------------------------------------------


def test_demo_extracts_cpt_and_icd_from_transcript() -> None:
    extractor = DemoClaimExtractor()
    claim = extractor.extract(TRANSCRIPT, claim_id="C1")
    assert isinstance(claim, Claim)
    assert claim.claim_id == "C1"
    assert len(claim.lines) == 1
    assert claim.lines[0].cpt_code == "99214"
    assert claim.lines[0].icd10_codes == ["J06.9"]


def test_demo_is_deterministic() -> None:
    extractor = DemoClaimExtractor()
    a = extractor.extract(TRANSCRIPT, claim_id="C1")
    b = extractor.extract(TRANSCRIPT, claim_id="C1")
    assert a.model_dump() == b.model_dump()


def test_demo_no_codes_yields_empty_lines() -> None:
    claim = DemoClaimExtractor().extract("Patient felt better, no billing today.", claim_id="C2")
    assert claim.lines == []


# --- Anthropic adapter (injected fake client) ------------------------------


class _FakeParsed:
    def __init__(self, extraction: ClaimExtraction) -> None:
        self.parsed_output = extraction


class _FakeMessages:
    def __init__(self, extraction: ClaimExtraction, calls: list[dict]) -> None:
        self._extraction = extraction
        self._calls = calls

    def parse(self, **kwargs: object) -> _FakeParsed:
        self._calls.append(kwargs)
        return _FakeParsed(self._extraction)


class _FakeAnthropicClient:
    def __init__(self, extraction: ClaimExtraction) -> None:
        self.calls: list[dict] = []
        self.messages = _FakeMessages(extraction, self.calls)


def test_anthropic_extractor_uses_haiku_and_assembles_claim() -> None:
    extraction = ClaimExtraction(
        lines=[ExtractedLine(cpt_code="99214", icd10_codes=["J06.9"], units=1)],
        date_of_service="2026-01-15",
    )
    fake = _FakeAnthropicClient(extraction)
    extractor = AnthropicClaimExtractor(client=fake)
    claim = extractor.extract(TRANSCRIPT, claim_id="C9")
    assert fake.calls[0]["model"] == HAIKU
    assert fake.calls[0]["output_format"] is ClaimExtraction
    assert claim.claim_id == "C9"
    assert claim.date_of_service == "2026-01-15"
    assert claim.lines[0].cpt_code == "99214"


# --- factory ---------------------------------------------------------------


def test_factory_defaults_to_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "VERITAS_MODEL_BACKEND"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("VERITAS_DEMO_MODE", raising=False)
    assert isinstance(build_claim_extractor(), DemoClaimExtractor)


def test_factory_picks_anthropic_when_key_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VERITAS_DEMO_MODE", raising=False)
    monkeypatch.delenv("VERITAS_MODEL_BACKEND", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert isinstance(build_claim_extractor(), AnthropicClaimExtractor)
