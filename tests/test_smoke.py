"""Phase 0 smoke tests: the package imports and contracts are well-formed.

These guard the scaffold itself. Feature tests arrive with each module.
"""

from claims_auditor import __version__
from claims_auditor.contracts import (
    AuditFinding,
    Claim,
    ClaimLine,
    RetrievedChunk,
    Severity,
)


def test_version() -> None:
    assert isinstance(__version__, str)


def test_claim_model_roundtrips() -> None:
    claim = Claim(
        claim_id="C1",
        patient_ref="SYN-001",
        provider_npi="1234567890",
        date_of_service="2026-01-01",
        lines=[ClaimLine(cpt_code="99213", icd10_codes=["E11.9"], units=1, charge_cents=12000)],
    )
    assert Claim.model_validate(claim.model_dump()) == claim


def test_audit_finding_carries_citations() -> None:
    finding = AuditFinding(
        finding_id="F1",
        claim_id="C1",
        severity=Severity.HIGH,
        why="CPT/ICD-10 mismatch.",
        citations=[RetrievedChunk(chunk_id="k1", text="...", source="cpt", score=0.91)],
    )
    assert finding.severity is Severity.HIGH
    assert finding.citations[0].source == "cpt"
