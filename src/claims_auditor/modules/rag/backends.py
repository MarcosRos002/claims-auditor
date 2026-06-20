"""Production retrieval backends: pgvector dense index + a real embedder.

These are the swaps documented in ``retriever.py``: the in-memory ``DenseIndex``
becomes a Postgres/pgvector ANN index, and the toy embedder becomes a real
sentence-embedding model. Both satisfy the same seams (``RankedIndex`` /
``Embedder``) so ``HybridRetriever`` is unchanged.

Heavy/optional deps (``psycopg``, ``pgvector``, ``fastembed``) are imported
**lazily** so the offline retriever stays dependency-free. Ingestion writes the
index; ``search`` is read-only — the contract for the audit path.
"""

from __future__ import annotations

import os
from collections.abc import Sequence

from claims_auditor.modules.rag.retriever import Doc

DEFAULT_DSN = os.environ.get("DATABASE_URL", "postgresql://veritas:veritas@localhost:5432/veritas")


class FastEmbedEmbedder:
    """Real sentence embeddings via fastembed (ONNX, CPU, no API key, free)."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name)
        self.dim = len(next(iter(self._model.embed(["probe"]))))

    def __call__(self, text: str) -> Sequence[float]:
        return [float(x) for x in next(iter(self._model.embed([text])))]


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
