"""Tests for the two-pass cost-routing classifier (Phase 1 leaf).

Demonstrates cost routing: a cheap Pass 1 (Haiku) handles confident cases; only
uncertain claims escalate to an expensive Pass 2 (Sonnet). The model is injected,
so this runs fully offline (no API spend).
"""

from __future__ import annotations

from claims_auditor.contracts import Claim, ClaimLine, Classifier, FaultType, RetrievedChunk
from claims_auditor.modules.classification.classifier import (
    CandidateFinding,
    ClassificationResult,
    TwoPassClassifier,
)


class FakeModel:
    """Records which tiers were called and replays canned results per tier."""

    def __init__(self, cheap: ClassificationResult, escalated: ClassificationResult | None = None):
        self._cheap = cheap
        self._escalated = escalated
        self.calls: list[str] = []

    def classify(self, claim, context, *, tier):
        self.calls.append(tier)
        return self._cheap if tier == "cheap" else self._escalated


def _claim() -> Claim:
    return Claim(
        claim_id="C1",
        patient_ref="SYN-PT-1",
        provider_npi="1234567890",
        date_of_service="2026-01-01",
        lines=[ClaimLine(cpt_code="99214", icd10_codes=["E11.9"], units=1, charge_cents=20000)],
    )


def _cand(conf: float, category=FaultType.UPCODING, why="upcoded visit") -> CandidateFinding:
    return CandidateFinding(category=category, line_index=0, confidence=conf, why=why)


def test_confident_pass1_does_not_escalate() -> None:
    model = FakeModel(cheap=ClassificationResult(findings=[_cand(0.95)]))
    clf = TwoPassClassifier(model, confidence_threshold=0.75)
    findings = clf.classify(_claim(), [])
    assert [f.category for f in findings] == [FaultType.UPCODING]
    assert "escalated" not in model.calls  # cheap path only
    assert clf.last_pass_used == 1


def test_low_confidence_escalates_to_pass2() -> None:
    model = FakeModel(
        cheap=ClassificationResult(findings=[_cand(0.40)]),  # uncertain
        escalated=ClassificationResult(findings=[_cand(0.92)]),  # authoritative
    )
    clf = TwoPassClassifier(model, confidence_threshold=0.75)
    findings = clf.classify(_claim(), [])
    assert model.calls == ["cheap", "escalated"]
    assert clf.last_pass_used == 2
    assert clf.last_escalated is True
    assert [f.category for f in findings] == [FaultType.UPCODING]


def test_clean_claim_takes_cheap_path_with_no_findings() -> None:
    model = FakeModel(cheap=ClassificationResult(findings=[]))
    clf = TwoPassClassifier(model)
    findings = clf.classify(_claim(), [])
    assert findings == []
    assert model.calls == ["cheap"]  # no escalation for a confidently-clean claim


def test_below_threshold_candidates_are_dropped() -> None:
    # After escalation, only confident candidates become findings.
    model = FakeModel(
        cheap=ClassificationResult(findings=[_cand(0.40)]),
        escalated=ClassificationResult(
            findings=[
                _cand(0.95, why="real"),
                _cand(0.30, category=FaultType.UNIT_EXCESS, why="noise"),
            ]
        ),
    )
    clf = TwoPassClassifier(model, confidence_threshold=0.75)
    findings = clf.classify(_claim(), [])
    assert [f.category for f in findings] == [FaultType.UPCODING]


def test_citations_from_context_are_attached() -> None:
    chunk = RetrievedChunk(
        chunk_id="k1", text="99214 documentation guidance", source="policy", score=0.9
    )
    model = FakeModel(cheap=ClassificationResult(findings=[_cand(0.9)]))
    clf = TwoPassClassifier(model)
    findings = clf.classify(_claim(), [chunk])
    assert findings[0].citations == [chunk]


def test_satisfies_classifier_protocol() -> None:
    model = FakeModel(cheap=ClassificationResult(findings=[]))
    assert isinstance(TwoPassClassifier(model), Classifier)
