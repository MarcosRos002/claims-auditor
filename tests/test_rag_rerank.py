"""Tests for the cross-encoder reranker logic (cross-encoder model injected).

The real sentence-transformers CrossEncoder is a production swap; here we inject a
fake scorer so the reorder logic is deterministic and offline.
"""

from __future__ import annotations

from claims_auditor.contracts import RetrievedChunk
from claims_auditor.modules.rag.backends import CrossEncoderReranker
from claims_auditor.modules.rag.retriever import Reranker


class FakeCrossEncoder:
    """Returns a fixed score per (query, doc) pair, aligned to the input order."""

    def __init__(self, scores):
        self._scores = scores

    def predict(self, pairs):
        return self._scores[: len(pairs)]


def _chunk(cid, score):
    return RetrievedChunk(chunk_id=cid, text=cid, source="icd10", score=score)


def test_reranker_reorders_by_cross_encoder_score() -> None:
    # Fusion order a,b,c; the cross-encoder says b best, then c, then a.
    cands = [_chunk("a", 0.9), _chunk("b", 0.5), _chunk("c", 0.1)]
    rr = CrossEncoderReranker(FakeCrossEncoder([0.1, 0.95, 0.4]))
    out = rr.rerank("query", cands)
    assert [c.chunk_id for c in out] == ["b", "c", "a"]
    assert out[0].score == 0.95  # score replaced by the cross-encoder relevance


def test_reranker_handles_empty_candidates() -> None:
    assert CrossEncoderReranker(FakeCrossEncoder([])).rerank("q", []) == []


def test_reranker_satisfies_reranker_protocol() -> None:
    assert isinstance(CrossEncoderReranker(FakeCrossEncoder([])), Reranker)
