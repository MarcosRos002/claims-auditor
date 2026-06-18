"""Canonical contracts for Veritas (contract-first methodology).

These are the typed boundaries every module depends on. They are intentionally
minimal in Phase 0 — the authoritative, annotated spec lives in
``docs/contracts/``. Keep this module dependency-light (pydantic + typing only)
so it can be imported by every other module without cycles.

The ``TraceEvent`` schema is OWNED BY agent-lens (the sibling eval/observability
repo). Veritas *emits* events that conform to it, so we import the canonical
schema directly from ``agent_lens.schema`` and re-export it here. There is no
local mirror — drift is structurally impossible. See
``docs/contracts/trace_event.md``.
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable

from agent_lens.schema import (
    ErrorInfo,
    StepKind,
    StepStatus,
    TokenUsage,
    Trace,
    TraceEvent,
)
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------
class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FaultType(str, Enum):
    """Taxonomy of billing inconsistencies — the shared vocabulary between the
    synthetic data generator (which injects them as ground truth), the rules
    engine / classifier (which detect them), and eval (which matches the two).

    Single-claim detectable faults (no cross-claim history needed). Expand
    deliberately as the rules engine grows.
    """

    CPT_ICD_MISMATCH = "cpt_icd_mismatch"  # procedure not supported by any listed diagnosis
    UNIT_EXCESS = "unit_excess"  # units exceed the plausible max for the CPT
    DUPLICATE_LINE = "duplicate_line"  # identical billed line appears more than once
    UPCODING = "upcoding"  # higher-complexity code than the diagnosis supports


class ClaimLine(BaseModel):
    """A single billed line item within a claim."""

    cpt_code: str = Field(..., description="CPT/HCPCS procedure code (synthetic).")
    icd10_codes: list[str] = Field(default_factory=list, description="Diagnosis codes.")
    units: int = 1
    charge_cents: int = 0


class Claim(BaseModel):
    """A medical-billing claim — the central unit Veritas audits.

    May originate from a structured payload OR be extracted from an ASR
    transcript. Data is always SYNTHETIC (never real PHI).
    """

    claim_id: str
    patient_ref: str = Field(..., description="Synthetic, de-identified patient reference.")
    provider_npi: str
    date_of_service: str = Field(..., description="ISO-8601 date.")
    lines: list[ClaimLine] = Field(default_factory=list)
    source_transcript_id: str | None = None


class RetrievedChunk(BaseModel):
    """A retrieved evidence chunk (ICD-10/CPT description or policy text)."""

    chunk_id: str
    text: str
    source: str = Field(..., description="e.g. 'icd10', 'cpt', 'policy:<name>'.")
    score: float = Field(..., description="Post-fusion / post-rerank relevance score.")


class AuditFinding(BaseModel):
    """An inconsistency detected during audit, with cited evidence.

    Also referred to as an Inconsistency. The ``why`` field carries the
    human-readable explanation; ``citations`` ground it in retrieved evidence.
    """

    finding_id: str
    claim_id: str
    severity: Severity
    category: FaultType | None = Field(
        None,
        description="Inconsistency category (links a finding to a FaultType for eval matching).",
    )
    line_index: int | None = Field(None, description="Affected claim line, if line-specific.")
    rule_id: str | None = Field(None, description="Rule that fired, if rule-based.")
    why: str = Field(..., description="Explanation of the inconsistency.")
    citations: list[RetrievedChunk] = Field(default_factory=list)


class ToolSpec(BaseModel):
    """Description of a tool the harness/agent can dispatch (incl. MCP tools)."""

    name: str
    description: str
    input_schema: dict = Field(default_factory=dict, description="JSON Schema for inputs.")
    parallel_safe: bool = Field(
        False, description="True for read-only tools the harness may run concurrently."
    )


class TranscriptSegment(BaseModel):
    """A time-stamped segment of streaming ASR output."""

    start_s: float
    end_s: float
    text: str
    is_final: bool = False


# NOTE: ``TraceEvent``, ``Trace``, ``StepKind``, ``StepStatus``, ``TokenUsage`` and
# ``ErrorInfo`` are imported from agent-lens above and re-exported via ``__all__``.
# ASR transcription steps map onto the canonical schema as ``kind=StepKind.TOOL``
# with ``tool_name="asr.transcribe"`` and ``metadata={"modality": "audio"}`` —
# the canonical enum stays general so agent-lens can measure any agent.


# ---------------------------------------------------------------------------
# Protocols (the seams modules implement)
# ---------------------------------------------------------------------------
@runtime_checkable
class Retriever(Protocol):
    """Hybrid retrieval over ICD-10/CPT + policies (pgvector + BM25 + RRF + rerank)."""

    def retrieve(self, query: str, *, top_k: int = 8) -> list[RetrievedChunk]: ...


@runtime_checkable
class ASRTranscriber(Protocol):
    """Streaming audio -> transcript segments."""

    def transcribe_stream(self, audio: bytes) -> list[TranscriptSegment]: ...


@runtime_checkable
class Classifier(Protocol):
    """Two-pass confidence classification (Haiku -> Sonnet escalation)."""

    def classify(self, claim: Claim, context: list[RetrievedChunk]) -> list[AuditFinding]: ...


__all__ = [
    # Domain models (owned here)
    "Severity",
    "FaultType",
    "ClaimLine",
    "Claim",
    "RetrievedChunk",
    "AuditFinding",
    "ToolSpec",
    "TranscriptSegment",
    # Trace wire-format (owned by agent-lens, re-exported)
    "TraceEvent",
    "Trace",
    "StepKind",
    "StepStatus",
    "TokenUsage",
    "ErrorInfo",
    # Protocols (the seams modules implement)
    "Retriever",
    "ASRTranscriber",
    "Classifier",
]
