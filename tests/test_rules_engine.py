"""Tests for the deterministic business-rules engine (Phase 1 leaf).

The rules engine is the high-precision backbone: it detects the deterministic
fault types (CPT/ICD mismatch, unit excess, duplicate line) against the shared
reference catalog. UPCODING is deliberately out of scope — it needs clinical
context the codes alone don't carry, so it is the LLM classifier's job.

The headline test runs the engine over a labeled synthetic dataset and asserts
real precision/recall against ground truth.
"""

from __future__ import annotations

from claims_auditor.contracts import Claim, ClaimLine, FaultType, Severity
from claims_auditor.data.synthetic import generate_claim, generate_dataset
from claims_auditor.modules.rules.engine import RulesEngine

RULE_DETECTABLE = {
    FaultType.CPT_ICD_MISMATCH,
    FaultType.UNIT_EXCESS,
    FaultType.DUPLICATE_LINE,
}

engine = RulesEngine()


def test_detects_cpt_icd_mismatch() -> None:
    lc = generate_claim(seed=10, inject_inconsistency=True, fault_type=FaultType.CPT_ICD_MISMATCH)
    findings = engine.evaluate(lc.claim)
    hit = [f for f in findings if f.category is FaultType.CPT_ICD_MISMATCH]
    assert hit, "mismatch must be detected"
    assert hit[0].severity is Severity.HIGH
    assert hit[0].rule_id
    assert hit[0].line_index == lc.faults[0].line_index


def test_detects_unit_excess() -> None:
    lc = generate_claim(seed=11, inject_inconsistency=True, fault_type=FaultType.UNIT_EXCESS)
    findings = engine.evaluate(lc.claim)
    hit = [f for f in findings if f.category is FaultType.UNIT_EXCESS]
    assert hit
    assert hit[0].line_index == lc.faults[0].line_index


def test_detects_duplicate_line() -> None:
    lc = generate_claim(seed=12, inject_inconsistency=True, fault_type=FaultType.DUPLICATE_LINE)
    findings = engine.evaluate(lc.claim)
    assert any(f.category is FaultType.DUPLICATE_LINE for f in findings)


def test_clean_claim_produces_no_findings() -> None:
    lc = generate_claim(seed=13, inject_inconsistency=False)
    assert engine.evaluate(lc.claim) == []


def test_upcoding_is_out_of_scope_for_rules() -> None:
    # The rules engine cannot (and should not) flag upcoding from codes alone.
    lc = generate_claim(seed=14, inject_inconsistency=True, fault_type=FaultType.UPCODING)
    findings = engine.evaluate(lc.claim)
    assert findings == [], "rules must not fire on an upcoding-only claim (classifier's job)"


def test_unknown_code_is_reported_not_raised() -> None:
    claim = Claim(
        claim_id="C-UNK",
        patient_ref="SYN-PT-1",
        provider_npi="1234567890",
        date_of_service="2026-01-01",
        lines=[ClaimLine(cpt_code="00000", icd10_codes=["E11.9"], units=1, charge_cents=1000)],
    )
    findings = engine.evaluate(claim)  # must not raise
    assert any("unknown" in f.why.lower() for f in findings)


def test_rules_engine_precision_and_recall_on_labeled_dataset() -> None:
    ds = generate_dataset(300, fault_rate=0.5, seed=20)
    tp = fp = fn = 0
    for lc in ds:
        detected = {f.category for f in engine.evaluate(lc.claim) if f.category is not None}
        injected = {f.fault_type for f in lc.faults if f.fault_type in RULE_DETECTABLE}
        tp += len(detected & injected)
        fp += len(detected - injected)
        fn += len(injected - detected)

    recall = tp / (tp + fn) if (tp + fn) else 1.0
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    assert recall >= 0.95, f"recall too low: {recall:.3f}"
    assert precision >= 0.95, f"precision too low: {precision:.3f}"
