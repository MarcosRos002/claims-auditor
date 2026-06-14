"""Two-pass classification by confidence (Haiku -> Sonnet escalation).

Pass 1 runs the cheap model (Claude Haiku, or the distilled small model served by
fine-tune-lab) to classify each potential inconsistency. Low-confidence cases
escalate to Pass 2 (Claude Sonnet). Implements the ``Classifier`` contract.

Phase 0: stub. See ``docs/modules/classification.md``.
"""

from __future__ import annotations

from claims_auditor.contracts import AuditFinding, Claim, RetrievedChunk


class TwoPassClassifier:
    """Confidence-gated escalation classifier. Satisfies Classifier."""

    def classify(self, claim: Claim, context: list[RetrievedChunk]) -> list[AuditFinding]:
        raise NotImplementedError("Phase 0 stub — see docs/modules/classification.md")
