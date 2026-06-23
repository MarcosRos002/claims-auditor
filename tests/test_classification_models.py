"""Tests for the ClassifierModel adapters (demo / Anthropic / factory).

All offline: demo-mode is deterministic and free; the Anthropic adapter is
exercised with an injected fake client (no network, no API key, no cost).
"""

from __future__ import annotations

import pytest

from claims_auditor.contracts import Claim, ClaimLine
from claims_auditor.modules.classification.classifier import (
    ClassificationResult,
    TwoPassClassifier,
)
from claims_auditor.modules.classification.models import (
    AnthropicClassifierModel,
    DemoClassifierModel,
    OpenRouterClassifierModel,
    _extract_json,
    build_classifier_model,
)
from claims_auditor.routing.cost_router import HAIKU, SONNET

# --- helpers ---------------------------------------------------------------


def _claim(*cpts: str) -> Claim:
    return Claim(
        claim_id="C1",
        patient_ref="P1",
        provider_npi="1234567890",
        date_of_service="2026-01-01",
        lines=[ClaimLine(cpt_code=c, icd10_codes=["J06.9"]) for c in cpts],
    )


class _FakeParsed:
    def __init__(self, result: ClassificationResult) -> None:
        self.parsed_output = result


class _FakeMessages:
    def __init__(self, result: ClassificationResult, calls: list[dict]) -> None:
        self._result = result
        self._calls = calls

    def parse(self, **kwargs: object) -> _FakeParsed:
        self._calls.append(kwargs)
        return _FakeParsed(self._result)


class _FakeAnthropicClient:
    """Stand-in for anthropic.Anthropic — records calls, returns a fixed result."""

    def __init__(self, result: ClassificationResult) -> None:
        self.calls: list[dict] = []
        self.messages = _FakeMessages(result, self.calls)


# --- demo-mode -------------------------------------------------------------


def test_demo_flags_upcode_cpt_deterministically() -> None:
    model = DemoClassifierModel()
    r1 = model.classify(_claim("99214"), [], tier="cheap")
    r2 = model.classify(_claim("99214"), [], tier="cheap")
    assert [f.category.value for f in r1.findings] == ["upcoding"]
    assert r1.model_dump() == r2.model_dump()  # deterministic
    assert all(f.confidence >= 0.75 for f in r1.findings)


def test_demo_clean_claim_has_no_findings() -> None:
    model = DemoClassifierModel()
    result = model.classify(_claim("99213"), [], tier="cheap")
    assert result.findings == []


def test_demo_is_free_and_tier_agnostic() -> None:
    model = DemoClassifierModel()
    cheap = model.classify(_claim("99214"), [], tier="cheap")
    escalated = model.classify(_claim("99214"), [], tier="escalated")
    assert cheap.model_dump() == escalated.model_dump()


def test_demo_cache_overrides_heuristic() -> None:
    cached = ClassificationResult(findings=[])
    model = DemoClassifierModel(responses={"C1": cached})
    # even an upcode claim returns the cached (empty) response for that id
    assert model.classify(_claim("99214"), [], tier="cheap").findings == []


def test_demo_wired_into_two_pass_classifier_produces_a_finding() -> None:
    clf = TwoPassClassifier(DemoClassifierModel())
    findings = clf.classify(_claim("99214"), [])
    assert len(findings) == 1
    assert findings[0].category.value == "upcoding"
    assert clf.last_pass_used == 1  # confident -> cheap path, no escalation


# --- Anthropic adapter (injected fake client) ------------------------------


def test_anthropic_cheap_tier_uses_haiku() -> None:
    fake = _FakeAnthropicClient(ClassificationResult(findings=[]))
    model = AnthropicClassifierModel(client=fake)
    model.classify(_claim("99214"), [], tier="cheap")
    assert fake.calls[0]["model"] == HAIKU


def test_anthropic_escalated_tier_uses_sonnet() -> None:
    fake = _FakeAnthropicClient(ClassificationResult(findings=[]))
    model = AnthropicClassifierModel(client=fake)
    model.classify(_claim("99214"), [], tier="escalated")
    assert fake.calls[0]["model"] == SONNET


def test_anthropic_returns_parsed_structured_output() -> None:
    expected = ClassificationResult(
        findings=[{"category": "upcoding", "line_index": 0, "confidence": 0.9, "why": "x"}]
    )
    fake = _FakeAnthropicClient(expected)
    model = AnthropicClassifierModel(client=fake)
    out = model.classify(_claim("99214"), [], tier="cheap")
    assert out.model_dump() == expected.model_dump()
    # structured outputs requested via output_format = the result schema
    assert fake.calls[0]["output_format"] is ClassificationResult


# --- OpenRouter adapter (lenient JSON, injected fake client) ----------------


class _FakeChatCompletions:
    def __init__(self, content: str, calls: list[dict]) -> None:
        self._content = content
        self._calls = calls

    def create(self, **kwargs: object) -> object:
        self._calls.append(kwargs)
        message = type("M", (), {"content": self._content})()
        choice = type("C", (), {"message": message})()
        return type("R", (), {"choices": [choice]})()


class _FakeOpenAIClient:
    def __init__(self, content: str) -> None:
        self.calls: list[dict] = []
        self.chat = type("Chat", (), {"completions": _FakeChatCompletions(content, self.calls)})()


def test_extract_json_handles_fences_and_prose() -> None:
    assert _extract_json('```json\n{"findings": []}\n```') == '{"findings": []}'
    assert _extract_json('Sure!\n{"findings": []}\nHope that helps') == '{"findings": []}'
    assert _extract_json("no json here") == "{}"


def test_openrouter_parses_fenced_json_and_does_not_send_response_format() -> None:
    fenced = '```json\n{"findings": [{"category": "cpt_icd_mismatch", "line_index": 0, "confidence": 0.8, "why": "x"}]}\n```'
    fake = _FakeOpenAIClient(fenced)
    model = OpenRouterClassifierModel(client=fake)
    out = model.classify(_claim("99214"), [], tier="cheap")
    assert [f.category.value for f in out.findings] == ["cpt_icd_mismatch"]
    # free models reject response_format — we must not send it
    assert "response_format" not in fake.calls[0]


# --- factory ---------------------------------------------------------------


def test_factory_defaults_to_demo_when_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("VERITAS_MODEL_BACKEND", raising=False)
    monkeypatch.delenv("VERITAS_DEMO_MODE", raising=False)
    assert isinstance(build_classifier_model(), DemoClassifierModel)


def test_factory_demo_mode_wins_over_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("VERITAS_DEMO_MODE", "1")
    monkeypatch.delenv("VERITAS_MODEL_BACKEND", raising=False)
    assert isinstance(build_classifier_model(), DemoClassifierModel)


def test_factory_picks_anthropic_when_key_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VERITAS_DEMO_MODE", raising=False)
    monkeypatch.delenv("VERITAS_MODEL_BACKEND", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    model = build_classifier_model()
    assert isinstance(model, AnthropicClassifierModel)
