"""Two-pass classification by confidence (Haiku -> Sonnet escalation).

Cost routing: Pass 1 runs the **cheap** model (Claude Haiku, or the distilled
small model from fine-tune-lab) and returns candidate inconsistencies *with a
confidence*. If every candidate is confident, we stop there (cheap path). If any
is uncertain, we **escalate** the whole claim to Pass 2 (Claude Sonnet), the
authoritative model, and use its verdict. Only confident candidates become
findings. This covers the judgment the deterministic rules can't express
(notably UPCODING). Implements the ``Classifier`` contract.

The model is **injected** (the cost/tier decision belongs to ``routing/``), so
this runs fully offline in tests. ``last_pass_used`` / ``last_escalated`` expose
the routing decision for agent-lens cost metrics. See
``docs/modules/classification.md``.
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, Field

from claims_auditor.contracts import (
    AuditFinding,
    Claim,
    FaultType,
    RetrievedChunk,
    Severity,
)

Tier = Literal["cheap", "escalated"]

# Severity per inconsistency category; conservative default.
_SEVERITY: dict[FaultType, Severity] = {
    FaultType.UPCODING: Severity.HIGH,
    FaultType.CPT_ICD_MISMATCH: Severity.HIGH,
    FaultType.UNIT_EXCESS: Severity.MEDIUM,
    FaultType.DUPLICATE_LINE: Severity.MEDIUM,
}


class CandidateFinding(BaseModel):
    """A model-proposed inconsistency with a confidence in [0, 1]."""

    category: FaultType
    line_index: int | None = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    why: str


class ClassificationResult(BaseModel):
    """One tier's output: the candidates it proposed."""

    findings: list[CandidateFinding] = Field(default_factory=list)


class ClassifierModel(Protocol):
    """Injected model. ``tier`` selects cheap (Pass 1) vs escalated (Pass 2)."""

    def classify(
        self, claim: Claim, context: list[RetrievedChunk], *, tier: Tier
    ) -> ClassificationResult: ...


class TwoPassClassifier:
    """Confidence-gated escalation classifier. Satisfies Classifier."""

    def __init__(self, model: ClassifierModel, *, confidence_threshold: float = 0.75) -> None:
        self._model = model
        self._threshold = confidence_threshold
        self.last_pass_used = 0
        self.last_escalated = False

    def classify(self, claim: Claim, context: list[RetrievedChunk]) -> list[AuditFinding]:
        pass1 = self._model.classify(claim, context, tier="cheap")
        if self._all_confident(pass1):
            chosen, self.last_pass_used, self.last_escalated = pass1, 1, False
        else:
            chosen = self._model.classify(claim, context, tier="escalated")
            self.last_pass_used, self.last_escalated = 2, True

        return [
            self._to_finding(claim, c, context)
            for c in chosen.findings
            if c.confidence >= self._threshold
        ]

    def _all_confident(self, result: ClassificationResult) -> bool:
        return all(c.confidence >= self._threshold for c in result.findings)

    def _to_finding(
        self, claim: Claim, c: CandidateFinding, context: list[RetrievedChunk]
    ) -> AuditFinding:
        return AuditFinding(
            finding_id=f"{claim.claim_id}:CLF:{c.category.value}:{c.line_index}",
            claim_id=claim.claim_id,
            severity=_SEVERITY.get(c.category, Severity.MEDIUM),
            category=c.category,
            line_index=c.line_index,
            rule_id=None,  # classifier finding, not a deterministic rule
            why=c.why,
            citations=list(context),
        )
