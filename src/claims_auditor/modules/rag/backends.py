"""Production retrieval backends: pgvector dense index + a real embedder.

These are the swaps documented in ``retriever.py``: the in-memory ``DenseIndex``
becomes a Postgres/pgvector ANN index, and the toy embedder becomes a real
sentence-embedding model. Both satisfy the same seams (``RankedIndex`` /
``Embedder``) so ``HybridRetriever`` is unchanged.

Heavy/optional deps (``psycopg``, ``pgvector``, ``sentence-transformers``) are
imported **lazily** so the offline retriever stays dependency-free. Ingestion
writes the index; ``search`` is read-only — the contract for the audit path.
"""

from __future__ import annotations

import os
from collections.abc import Sequence

from claims_auditor.contracts import RetrievedChunk
from claims_auditor.modules.rag.retriever import Doc

DEFAULT_DSN = os.environ.get("DATABASE_URL", "postgresql://veritas:veritas@localhost:5432/veritas")


class SentenceTransformerEmbedder:
    """Real sentence embeddings via sentence-transformers (the project default).

    Default ``all-MiniLM-L6-v2`` is 384-d, CPU-friendly, free (no API key). Swap
    ``model_name`` for a stronger model when quality matters more than speed.
    """

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)
        self.dim = self._model.get_sentence_embedding_dimension()

    def __call__(self, text: str) -> Sequence[float]:
        return self._model.encode(text, normalize_embeddings=True).tolist()


class CrossEncoderReranker:
    """Cross-encoder reranker — the precision pass over fused candidates.

    Unlike the bi-encoder dense index (which embeds query and doc separately), a
    cross-encoder scores the (query, doc) **pair jointly**, so it is far more
    precise — but too slow to run over the whole corpus. It runs only over the
    top-N fused candidates. Satisfies the ``Reranker`` seam.

    The scoring model is injected (anything with ``predict(pairs) -> scores``); by
    default a real sentence-transformers ``CrossEncoder`` is built.
    """

    def __init__(
        self, model=None, *, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    ) -> None:
        if model is None:
            from sentence_transformers import CrossEncoder

            model = CrossEncoder(model_name)
        self._model = model

    def rerank(self, query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if not candidates:
            return []
        scores = self._model.predict([(query, c.text) for c in candidates])
        ranked = sorted(
            zip(candidates, scores, strict=True), key=lambda cs: float(cs[1]), reverse=True
        )
        return [c.model_copy(update={"score": float(s)}) for c, s in ranked]


class PgVectorIndex:
    """Dense ANN index backed by Postgres + pgvector. Drop-in for ``DenseIndex``.

    The constructor *ingests* the docs (embeds + writes the table). ``search``
    only reads. Uses cosine distance (``<=>``); similarity = ``1 - distance``.
    """

    def __init__(
        self,
        docs: list[Doc],
        embedder,
        *,
        dsn: str = DEFAULT_DSN,
        table: str = "rag_chunks",
    ) -> None:
        import psycopg
        from pgvector.psycopg import register_vector

        self._embedder = embedder
        self._dsn = dsn
        self._table = table
        self._dim = len(list(embedder("probe")))

        self._conn = psycopg.connect(dsn, autocommit=True)
        register_vector(self._conn)
        self._ingest(docs)

    def _ingest(self, docs: list[Doc]) -> None:
        import numpy as np

        cur = self._conn.cursor()
        cur.execute(f"DROP TABLE IF EXISTS {self._table}")
        cur.execute(
            f"CREATE TABLE {self._table} ("
            "chunk_id text PRIMARY KEY, source text, text text, "
            f"embedding vector({self._dim}))"
        )
        for d in docs:
            vec = np.array(list(self._embedder(d.text)), dtype=np.float32)
            cur.execute(
                f"INSERT INTO {self._table} (chunk_id, source, text, embedding) "
                "VALUES (%s, %s, %s, %s)",
                (d.chunk_id, d.source, d.text, vec),
            )
        # Cosine ANN index (IVFFlat). Small corpus => exact scan is fine too.
        cur.execute(
            f"CREATE INDEX ON {self._table} "
            f"USING ivfflat (embedding vector_cosine_ops) WITH (lists = 1)"
        )

    def search(self, query: str, k: int) -> list[tuple[str, float]]:
        import numpy as np

        qv = np.array(list(self._embedder(query)), dtype=np.float32)
        cur = self._conn.cursor()
        cur.execute(
            f"SELECT chunk_id, 1 - (embedding <=> %s) AS similarity "
            f"FROM {self._table} ORDER BY embedding <=> %s LIMIT %s",
            (qv, qv, k),
        )
        return [(row[0], float(row[1])) for row in cur.fetchall()]

    def close(self) -> None:
        self._conn.close()
