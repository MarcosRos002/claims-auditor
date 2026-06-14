"""Hybrid retrieval over ICD-10/CPT + policies.

Pipeline: dense (pgvector) + sparse (Postgres full-text / BM25) candidates ->
Reciprocal Rank Fusion (RRF) -> cross-encoder rerank -> top-k. Implements the
``Retriever`` contract. DB access is READ-ONLY.

Phase 0: stub. See ``docs/modules/rag.md``.
"""

from __future__ import annotations

from claims_auditor.contracts import RetrievedChunk


class HybridRetriever:
    """pgvector + BM25 + RRF + cross-encoder rerank. Satisfies Retriever."""

    def retrieve(self, query: str, *, top_k: int = 8) -> list[RetrievedChunk]:
        raise NotImplementedError("Phase 0 stub — see docs/modules/rag.md")
