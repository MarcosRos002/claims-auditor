"""Hybrid retrieval over ICD-10/CPT + policies.

Pipeline: dense (semantic) + sparse (lexical/BM25) candidates -> Reciprocal Rank
Fusion (RRF) -> optional cross-encoder rerank -> top-k. Implements the
``Retriever`` contract.

This module owns the **fusion + rerank logic** and ships fully-working in-memory
indexes so it runs and is tested with no database. In production the dense index
is swapped for **pgvector** (read-only) and the embedder/reranker for
**sentence-transformers** — both behind the same small seams (``Embedder``,
``Reranker``). See ``docs/modules/rag.md``.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from claims_auditor.contracts import RetrievedChunk
from claims_auditor.reference.catalog import CPT, ICD10

Embedder = Callable[[str], Sequence[float]]
_TOKEN = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


@dataclass(frozen=True)
class Doc:
    """A retrievable document (an ICD-10/CPT description or a policy chunk)."""

    chunk_id: str
    text: str
    source: str


class RankedIndex(Protocol):
    """A retrieval backend: rank chunk ids for a query. Implemented by the
    in-memory ``LexicalIndex``/``DenseIndex`` and the DB-backed ``PgVectorIndex``."""

    def search(self, query: str, k: int) -> list[tuple[str, float]]: ...


class Reranker(Protocol):
    """Reorders fused candidates for precision (a cross-encoder in production)."""

    def rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]: ...


# --------------------------------------------------------------------------- #
# Fusion
# --------------------------------------------------------------------------- #
def rrf_fuse(rank_lists: list[list[str]], *, k: int = 60) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion: combine ranked id lists by ``sum 1/(k + rank)``.

    Parameter-free across scales — it fuses *ranks*, not raw scores. Returns
    ``(chunk_id, fused_score)`` sorted best-first.
    """
    scores: dict[str, float] = defaultdict(float)
    for ranked in rank_lists:
        for rank, cid in enumerate(ranked):
            scores[cid] += 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


# --------------------------------------------------------------------------- #
# Backends (in-memory; production swaps documented above)
# --------------------------------------------------------------------------- #
class LexicalIndex:
    """BM25 over a small corpus — the sparse arm. Matches exact words."""

    def __init__(self, docs: list[Doc], *, k1: float = 1.5, b: float = 0.75) -> None:
        self._docs = docs
        self._k1, self._b = k1, b
        self._tokens = {d.chunk_id: _tokenize(d.text) for d in docs}
        lengths = [len(t) for t in self._tokens.values()]
        self._avg_len = (sum(lengths) / len(lengths)) if lengths else 0.0
        df: Counter[str] = Counter()
        for toks in self._tokens.values():
            df.update(set(toks))
        n = max(1, len(docs))
        self._idf = {
            term: math.log(1 + (n - freq + 0.5) / (freq + 0.5)) for term, freq in df.items()
        }

    def search(self, query: str, k: int) -> list[tuple[str, float]]:
        q = _tokenize(query)
        scored: list[tuple[str, float]] = []
        for cid, toks in self._tokens.items():
            tf = Counter(toks)
            dl = len(toks)
            score = 0.0
            for term in q:
                if term not in tf:
                    continue
                idf = self._idf.get(term, 0.0)
                denom = tf[term] + self._k1 * (1 - self._b + self._b * dl / (self._avg_len or 1))
                score += idf * (tf[term] * (self._k1 + 1)) / denom
            if score > 0:
                scored.append((cid, score))
        scored.sort(key=lambda kv: kv[1], reverse=True)
        return scored[:k]


class DenseIndex:
    """Cosine similarity over embeddings — the dense arm. Matches meaning."""

    def __init__(self, docs: list[Doc], embedder: Embedder) -> None:
        self._embedder = embedder
        self._vecs = {d.chunk_id: list(embedder(d.text)) for d in docs}

    def search(self, query: str, k: int) -> list[tuple[str, float]]:
        q = list(self._embedder(query))
        scored = [(cid, _cosine(q, v)) for cid, v in self._vecs.items()]
        scored.sort(key=lambda kv: kv[1], reverse=True)
        return scored[:k]


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


# --------------------------------------------------------------------------- #
# Hybrid retriever
# --------------------------------------------------------------------------- #
class HybridRetriever:
    """Dense + sparse candidates -> RRF -> optional rerank -> top-k. Satisfies Retriever."""

    def __init__(
        self,
        docs: list[Doc],
        *,
        embedder: Embedder | None = None,
        dense_index: RankedIndex | None = None,
        lexical_index: RankedIndex | None = None,
        reranker: Reranker | None = None,
        candidate_k: int = 20,
        top_k: int = 8,
        rrf_k: int = 60,
    ) -> None:
        self._docs = {d.chunk_id: d for d in docs}
        self._lexical = lexical_index or LexicalIndex(docs)
        if dense_index is not None:
            self._dense = dense_index  # e.g. a DB-backed PgVectorIndex
        elif embedder is not None:
            self._dense = DenseIndex(docs, embedder)
        else:
            raise ValueError("HybridRetriever needs either `embedder` or `dense_index`")
        self._reranker = reranker
        self._candidate_k = candidate_k
        self._top_k = top_k
        self._rrf_k = rrf_k

    @classmethod
    def from_catalog(cls, *, embedder: Embedder, **kwargs) -> HybridRetriever:
        """Build a retriever over the shared ICD-10/CPT reference catalog."""
        docs = [Doc(f"icd:{c}", f"{c} {desc}", "icd10") for c, desc in ICD10.items()]
        docs += [Doc(f"cpt:{c}", f"{c} {info.desc}", "cpt") for c, info in CPT.items()]
        return cls(docs, embedder=embedder, **kwargs)

    def retrieve(self, query: str, *, top_k: int | None = None) -> list[RetrievedChunk]:
        if not self._docs:
            return []
        top_k = top_k or self._top_k
        lexical_ids = [cid for cid, _ in self._lexical.search(query, self._candidate_k)]
        dense_ids = [cid for cid, _ in self._dense.search(query, self._candidate_k)]

        fused = rrf_fuse([lexical_ids, dense_ids], k=self._rrf_k)
        chunks = [
            RetrievedChunk(
                chunk_id=cid,
                text=self._docs[cid].text,
                source=self._docs[cid].source,
                score=score,
            )
            for cid, score in fused
        ]
        if self._reranker is not None:
            chunks = self._reranker.rerank(query, chunks[: self._candidate_k])
        return chunks[:top_k]
