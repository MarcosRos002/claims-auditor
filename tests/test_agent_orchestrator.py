"""Tests for the end-to-end audit orchestrator (Phase 1 integration / Capa 1 MVP).

The orchestrator wires the deterministic rules engine + the LLM classifier into a
single audit: run both, merge/dedupe findings, produce an AuditReport, and emit a
per-stage agent-lens Trace. Built offline with injected fakes.
"""

from __future__ import annotations

import pytest

from claims_auditor.agent.graph import AuditOrchestrator
from claims_auditor.contracts import AuditReport, FaultType, StepKind, Trace
from claims_auditor.data.synthetic import generate_claim
from claims_auditor.modules.classification.classifier import (
    CandidateFinding,
    ClassificationResult,
    TwoPassClassifier,
)
from claims_auditor.modules.rules.engine import RulesEngine


class FakeModel:
    def __init__(self, cheap, escalated=None):
        self._cheap, self._escalated, self.calls = cheap, escalated, []

    def classify(self, claim, context, *, tier):
        self.calls.append(tier)
        return self._cheap if tier == "cheap" else self._escalated


def _classifier(cands, escalated=None, threshold=0.75):
    model = FakeModel(ClassificationResult(findings=cands), escalated)
    return TwoPassClassifier(model, confidence_threshold=threshold)


def _cand(category, line_index=0, conf=0.95, why="model finding"):
    return CandidateFinding(category=category, line_index=line_index, confidence=conf, why=why)


def test_audit_merges_rules_and_classifier_findings() -> None:
    # Rules catch the mismatch; the classifier catches the upcoding (its job).
    lc = generate_claim(seed=10, inject_inconsistency=True, fault_type=FaultType.CPT_ICD_MISMATCH)
    orch = AuditOrchestrator(RulesEngine(), _classifier([_cand(FaultType.UPCODING)]))
    report = orch.audit(lc.claim)
    cats = {f.category for f in report.findings}
    assert FaultType.CPT_ICD_MISMATCH in cats
    assert FaultType.UPCODING in cats
    assert report.flagged is True


def test_audit_dedupes_when_both_flag_the_same_inconsistency() -> None:
    lc = generate_claim(seed=10, inject_inconsistency=True, fault_type=FaultType.CPT_ICD_MISMATCH)
    line = lc.faults[0].line_index
    # Classifier redundantly reports the SAME mismatch the rules already found.
    orch = AuditOrchestrator(
        RulesEngine(), _classifier([_cand(FaultType.CPT_ICD_MISMATCH, line_index=line)])
    )
    report = orch.audit(lc.claim)
    mismatches = [f for f in report.findings if f.category is FaultType.CPT_ICD_MISMATCH]
    assert len(mismatches) == 1  # merged, not duplicated


def test_clean_claim_is_not_flagged() -> None:
    lc = generate_claim(seed=13, inject_inconsistency=False)
    orch = AuditOrchestrator(RulesEngine(), _classifier([]))
    report = orch.audit(lc.claim)
    assert isinstance(report, AuditReport)
    assert report.flagged is False
    assert report.findings == []
    assert "no inconsistencies" in report.summary.lower()


def test_audit_emits_a_valid_agent_lens_trace() -> None:
    lc = generate_claim(seed=10, inject_inconsistency=True, fault_type=FaultType.CPT_ICD_MISMATCH)
    orch = AuditOrchestrator(RulesEngine(), _classifier([_cand(FaultType.UPCODING)]))
    report, trace = orch.audit_with_trace(lc.claim)

    assert isinstance(trace, Trace)
    names = {ev.name for ev in trace.events}
    assert "rules_engine.evaluate" in names
    assert "classifier.classify" in names
    assert any(ev.kind is StepKind.LLM for ev in trace.events)
    # Re-validates as the canonical agent-lens Trace (single session).
    assert Trace.model_validate(trace.model_dump()) == trace


def test_trace_records_the_cost_routing_decision() -> None:
    lc = generate_claim(seed=13, inject_inconsistency=False)
    # Cheap pass uncertain -> escalates to pass 2.
    clf = _classifier(
        [_cand(FaultType.UPCODING, conf=0.4)],
        escalated=ClassificationResult(findings=[_cand(FaultType.UPCODING, conf=0.95)]),
    )
    orch = AuditOrchestrator(RulesEngine(), clf)
    _report, trace = orch.audit_with_trace(lc.claim)
    clf_ev = next(ev for ev in trace.events if ev.name == "classifier.classify")
    assert clf_ev.metadata.get("pass_used") == 2
    assert clf_ev.metadata.get("escalated") is True


def test_classifier_failure_degrades_gracefully() -> None:
    class BoomClassifier:
        def classify(self, claim, context):
            raise RuntimeError("model down")

    lc = generate_claim(seed=10, inject_inconsistency=True, fault_type=FaultType.CPT_ICD_MISMATCH)
    orch = AuditOrchestrator(RulesEngine(), BoomClassifier())
    report, trace = orch.audit_with_trace(lc.claim)
    # Rules findings survive; the audit does not crash.
    assert any(f.category is FaultType.CPT_ICD_MISMATCH for f in report.findings)
    assert any(ev.status.value == "error" for ev in trace.events)


def test_audit_with_trace_returns_report_and_trace() -> None:
    lc = generate_claim(seed=1, inject_inconsistency=False)
    orch = AuditOrchestrator(RulesEngine(), _classifier([]))
    result = orch.audit_with_trace(lc.claim)
    assert isinstance(result, tuple)
    report, trace = result
    assert isinstance(report, AuditReport)
    assert isinstance(trace, Trace)


# --------------------------------------------------------------------------- #
# grounding: findings cite retrieved evidence
# --------------------------------------------------------------------------- #
def _catalog_retriever():
    from claims_auditor.modules.rag.retriever import HybridRetriever

    def emb(text):
        return [float(len(text) % 7), float(sum(map(ord, text)) % 11), 0.1]

    return HybridRetriever.from_catalog(embedder=emb, top_k=12)


def test_rule_findings_are_grounded_with_citations_when_a_retriever_is_present() -> None:
    lc = generate_claim(seed=10, inject_inconsistency=True, fault_type=FaultType.CPT_ICD_MISMATCH)
    cpt = lc.claim.lines[lc.faults[0].line_index].cpt_code
    orch = AuditOrchestrator(RulesEngine(), _classifier([]), retriever=_catalog_retriever())

    report = orch.audit(lc.claim)
    finding = next(f for f in report.findings if f.category is FaultType.CPT_ICD_MISMATCH)
    assert finding.citations, "a rule finding must be grounded with retrieved evidence"
    assert any(cpt in c.chunk_id for c in finding.citations)


def test_no_retriever_means_no_citations_on_rule_findings() -> None:
    lc = generate_claim(seed=10, inject_inconsistency=True, fault_type=FaultType.CPT_ICD_MISMATCH)
    orch = AuditOrchestrator(RulesEngine(), _classifier([]))  # no retriever
    report = orch.audit(lc.claim)
    finding = next(f for f in report.findings if f.category is FaultType.CPT_ICD_MISMATCH)
    assert finding.citations == []


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
