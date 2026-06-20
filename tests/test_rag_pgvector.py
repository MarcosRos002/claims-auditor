"""Online integration tests for the pgvector dense backend.

These need a live Postgres+pgvector (``docker compose up -d db``). They are
SKIPPED automatically when no DB / driver is available, so the offline suite is
unaffected. A deterministic toy embedder keeps them fast and reproducible — the
point is to exercise the real DB round-trip, not embedding quality.
"""

from __future__ import annotations

import pytest

psycopg = pytest.importorskip("psycopg")
pytest.importorskip("pgvector")

from claims_auditor.modules.rag.backends import DEFAULT_DSN, PgVectorIndex  # noqa: E402
from claims_auditor.modules.rag.retriever import Doc, HybridRetriever  # noqa: E402


def _db_available() -> bool:
    try:
        with psycopg.connect(DEFAULT_DSN, connect_timeout=3):
            return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="no Postgres+pgvector available")


def _emb(text: str):
    t = text.lower()
    d = 1.0 if ("diabetes" in t or "sugar" in t or "glucose" in t) else 0.0
    h = 1.0 if ("hypertension" in t or "blood pressure" in t) else 0.0
    return [d, h, 0.1]


def _corpus():
    return [
        Doc("icd:E11.9", "E11.9 Type 2 diabetes mellitus", "icd10"),
        Doc("icd:I10", "I10 Essential (primary) hypertension", "icd10"),
        Doc("icd:M54.5", "M54.5 Low back pain", "icd10"),
    ]


def test_pgvector_index_round_trips_and_ranks_by_similarity() -> None:
    idx = PgVectorIndex(_corpus(), _emb, table="rag_chunks_test")
    try:
        top = idx.search("high blood pressure", k=3)
        assert top[0][0] == "icd:I10"  # nearest by cosine in the real DB
        assert 0.0 <= top[0][1] <= 1.0  # similarity in range
    finally:
        idx.close()


def test_hybrid_retriever_uses_pgvector_as_its_dense_arm() -> None:
    idx = PgVectorIndex(_corpus(), _emb, table="rag_chunks_test")
    try:
        r = HybridRetriever(_corpus(), dense_index=idx, top_k=2)
        results = r.retrieve("high blood pressure")
        assert any(c.chunk_id == "icd:I10" for c in results)
    finally:
        idx.close()
