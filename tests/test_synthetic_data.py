"""Tests for the synthetic claim generator (foundational Phase 1 layer).

The generator must produce SYNTHETIC claims with exposed ground-truth labels so
the rules engine / classifier have known positives and agent-lens has ground
truth. Determinism (by seed) is required so fixtures and eval are reproducible.
"""

from __future__ import annotations

from claims_auditor.contracts import Claim, FaultType
from claims_auditor.data.synthetic import (
    InjectedFault,
    LabeledClaim,
    generate_claim,
    generate_dataset,
)


def test_generate_claim_is_deterministic_for_a_seed() -> None:
    assert generate_claim(seed=42) == generate_claim(seed=42)


def test_clean_claim_has_no_injected_faults() -> None:
    lc = generate_claim(seed=1, inject_inconsistency=False)
    assert isinstance(lc, LabeledClaim)
    assert isinstance(lc.claim, Claim)
    assert lc.faults == []
    # A clean claim is a well-formed claim with at least one coded line.
    assert lc.claim.lines
    for line in lc.claim.lines:
        assert line.cpt_code
        assert line.icd10_codes


def test_injected_claim_exposes_recoverable_ground_truth() -> None:
    lc = generate_claim(seed=2, inject_inconsistency=True)
    assert lc.faults, "an injected claim must expose at least one fault label"
    fault = lc.faults[0]
    assert isinstance(fault, InjectedFault)
    assert isinstance(fault.fault_type, FaultType)
    # If the fault points at a specific line, that line must exist.
    if fault.line_index is not None:
        assert 0 <= fault.line_index < len(lc.claim.lines)


def test_can_request_a_specific_fault_type() -> None:
    lc = generate_claim(seed=3, inject_inconsistency=True, fault_type=FaultType.CPT_ICD_MISMATCH)
    assert any(f.fault_type is FaultType.CPT_ICD_MISMATCH for f in lc.faults)


def test_generated_claim_round_trips_through_the_contract() -> None:
    lc = generate_claim(seed=4, inject_inconsistency=True)
    assert Claim.model_validate(lc.claim.model_dump()) == lc.claim


def test_dataset_respects_the_fault_rate() -> None:
    ds = generate_dataset(200, fault_rate=0.3, seed=7)
    assert len(ds) == 200
    faulty = [x for x in ds if x.faults]
    clean = [x for x in ds if not x.faults]
    assert len(faulty) + len(clean) == 200
    # ~30% faulty, with tolerance for randomness.
    assert 0.2 <= len(faulty) / 200 <= 0.4


def test_dataset_is_deterministic_for_a_seed() -> None:
    assert generate_dataset(50, fault_rate=0.5, seed=9) == generate_dataset(
        50, fault_rate=0.5, seed=9
    )


def test_injected_faults_span_multiple_types() -> None:
    # Coverage: eval is biased if the generator only ever injects one fault type.
    ds = generate_dataset(300, fault_rate=1.0, seed=5)
    kinds = {f.fault_type for x in ds for f in x.faults}
    assert len(kinds) >= 3
