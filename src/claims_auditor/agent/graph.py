"""Audit orchestrator — the LangGraph graph that wires the pipeline together.

Nodes (high level): ingest -> (asr) -> extract_claim -> retrieve -> classify ->
detect_inconsistencies -> explain. Integration layer: depends on the harness and
every leaf module via their contracts (Retriever, ASRTranscriber, Classifier).

Phase 0: graph shape declared in docs only. See ``docs/modules/agent.md`` and
``docs/orchestration.md``.
"""

from __future__ import annotations

from claims_auditor.contracts import AuditFinding, Claim


def build_graph():
    """Construct and compile the LangGraph audit graph."""
    raise NotImplementedError("Phase 0 stub — see docs/modules/agent.md")


def audit_claim(claim: Claim) -> list[AuditFinding]:
    """Convenience entrypoint: run the graph for a single claim."""
    raise NotImplementedError
