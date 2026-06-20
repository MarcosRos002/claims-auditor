"""Tests for hybrid retrieval (RRF fusion + rerank), fully offline.

The DB-backed dense index (pgvector) and the real embedder/cross-encoder
(sentence-transformers) are production swaps; the fusion + rerank LOGIC is tested
here with in-memory indexes and an injected embedder.
"""

from __future__ import annotations

from claims_auditor.contracts import RetrievedChunk, Retriever
from claims_auditor.modules.rag.retriever import (
    Doc,
    HybridRetriever,
    LexicalIndex,
    rrf_fuse,
)


# A 2-axis toy embedder: [diabetes-ness, hypertension-ness] (+bias to avoid zero).
def _emb(text: str):
    t = text.lower()
    d = 1.0 if ("diabetes" in t or "sugar" in t or "glucose" in t) else 0.0
    h = 1.0 if ("hypertension" in t or "blood pressure" in t) else 0.0
    return [d, h, 0.1]


def _corpus():
    return [
        Doc("icd:E11.9", "E11.9 Type 2 diabetes mellitus without complications", "icd10"),
        Doc("icd:I10", "I10 Essential (primary) hypertension", "icd10"),
        Doc("icd:M54.5", "M54.5 Low back pain", "icd10"),
    ]


# --------------------------------------------------------------------------- #
# RRF fusion (pure)
# --------------------------------------------------------------------------- #
def test_rrf_rewards_documents_ranked_high_in_both_lists() -> None:
    fused = rrf_fuse([["a", "b", "c"], ["b", "d", "a"]])
    ids = [cid for cid, _ in fused]
    assert ids[0] == "b"  # high in both lists wins


def test_rrf_handles_a_single_list() -> None:
    fused = rrf_fuse([["x", "y"]])
    assert [cid for cid, _ in fused] == ["x", "y"]


# --------------------------------------------------------------------------- #
# backends
# --------------------------------------------------------------------------- #
def test_lexical_index_matches_keywords() -> None:
    idx = LexicalIndex(_corpus())
    top = idx.search("diabetes", k=3)
    assert top[0][0] == "icd:E11.9"


def test_dense_index_matches_meaning_not_words() -> None:
    # "blood pressure" shares no words with "hypertension" — only the embedder links them.
    idx = HybridRetriever(_corpus(), embedder=_emb)._dense
    top = idx.search("high blood pressure", k=3)
    assert top[0][0] == "icd:I10"


# --------------------------------------------------------------------------- #
# hybrid retriever
# --------------------------------------------------------------------------- #
def test_hybrid_surfaces_a_doc_lexical_search_alone_would_miss() -> None:
    # Pure lexical can't link "blood pressure" -> "hypertension"; the dense arm can,
    # and RRF brings it into the results.
    r = HybridRetriever(_corpus(), embedder=_emb)
    results = r.retrieve("high blood pressure", top_k=2)
    assert any(c.chunk_id == "icd:I10" for c in results)
    assert all(isinstance(c, RetrievedChunk) for c in results)


def test_retrieve_respects_top_k_and_sets_scores() -> None:
    r = HybridRetriever(_corpus(), embedder=_emb)
    results = r.retrieve("diabetes", top_k=1)
    assert len(results) == 1
    assert results[0].score > 0


def test_reranker_reorders_fused_candidates() -> None:
    class ReverseReranker:
        def rerank(self, query, candidates):
            return list(reversed(candidates))

    r = HybridRetriever(_corpus(), embedder=_emb, reranker=ReverseReranker())
    base = HybridRetriever(_corpus(), embedder=_emb).retrieve("diabetes", top_k=3)
    reranked = r.retrieve("diabetes", top_k=3)
    assert [c.chunk_id for c in reranked] == list(reversed([c.chunk_id for c in base]))


def test_empty_corpus_returns_no_results() -> None:
    r = HybridRetriever([], embedder=_emb)
    assert r.retrieve("anything") == []


def test_satisfies_retriever_protocol() -> None:
    assert isinstance(HybridRetriever(_corpus(), embedder=_emb), Retriever)
