# Module: rag (`modules/rag/`)

## Purpose
Hybrid retrieval over ICD-10/CPT descriptions and policy text — the evidence
layer that grounds every finding. Dense + sparse candidate generation, fused and
reranked. **Read-only** DB access.

## Status: implemented (Phase 1, offline)
Pinned by `tests/test_rag.py`. The fusion + rerank logic and in-memory indexes
work with **no database** — the demo retrieves over the real ICD-10/CPT catalog
and shows hybrid surfacing a doc lexical search alone misses. pgvector +
sentence-transformers are production swaps behind the same seams.

## Public interface
`modules/rag/retriever.py`:
- `HybridRetriever(docs, *, embedder, reranker=None, candidate_k=20, top_k=8, rrf_k=60)`
  implements `Retriever`: `retrieve(query, *, top_k=None) -> list[RetrievedChunk]`.
- `HybridRetriever.from_catalog(embedder=...)` — build over the shared catalog.
- `rrf_fuse(rank_lists, *, k=60)` — pure Reciprocal Rank Fusion.
- `LexicalIndex` (BM25, sparse) / `DenseIndex` (cosine over an injected `Embedder`).
- `Reranker` Protocol (cross-encoder swap), `Doc` (a retrievable chunk).

Pipeline: dense (semantic) + sparse (BM25) candidates → **RRF** → optional
**rerank** → top-k. `RetrievedChunk.score` is the fused (post-rerank) score.

## Real backends (online) — `modules/rag/backends.py`
The production swaps, behind the same `RankedIndex`/`Embedder` seams (heavy deps
imported lazily):
- `PgVectorIndex(docs, embedder, *, dsn, table)` — a Postgres+pgvector ANN index
  (cosine `<=>`, IVFFlat). Ingests on construction; `search` is read-only. Drop-in
  for `DenseIndex` via `HybridRetriever(docs, dense_index=...)`.
- `SentenceTransformerEmbedder(model_name="sentence-transformers/all-MiniLM-L6-v2")`
  — real 384-d sentence embeddings (CPU, free, no API key).
- `CrossEncoderReranker(model=None, *, model_name="cross-encoder/ms-marco-MiniLM-L-6-v2")`
  — the precision pass: scores each (query, doc) **pair jointly** (unlike the
  bi-encoder), reordering only the top-N fused candidates. Injected scorer
  (`predict(pairs)->scores`) for offline tests; real CrossEncoder by default.
  Verified: for "chest imaging for pneumonia" it promotes `cpt:71046` (Radiologic
  exam, chest) above "chest pain" — precision the bi-encoder alone misses.

Run it online:
```bash
docker compose up -d db          # Postgres + pgvector (verified: ext vector 0.8.3)
pip install -e ".[dev,rag]"       # adds sentence-transformers
pytest tests/test_rag_pgvector.py # online integration tests (auto-skip if no DB)
```
Verified: `"high blood pressure"`→I10 hypertension, `"kidney problems"`→N18.3,
`"sugar in blood"`→R73.09/E11.9 — real semantic retrieval, no shared words.

## Dependencies
- `contracts` at the seam.
- Runtime: `psycopg` + `pgvector` (Postgres), `sentence-transformers`
  (embeddings + cross-encoder reranker). `DATABASE_URL`; docker-compose `db`.
- Phase-2 **leaf** — buildable in its own worktree (needs the DB up).

## How to test in isolation
- Seed a tiny corpus (a handful of ICD-10/CPT/policy chunks) into a test schema;
  assert relevant chunks rank above irrelevant ones for a known query.
- Unit-test **RRF fusion** with hand-built rank lists (no DB).
- Assert the reranker reorders fused candidates as expected on a fixture.
- Connection must be read-only — assert writes are rejected.

## Senior concerns
- **Failure modes:** DB down (degrade: findings without citations, reduced
  confidence — never fabricate); empty result set; embedding/model load cost;
  reranker latency on large candidate sets.
- **Quality:** fusion weighting and rerank cutoff are the main tunables; they
  drive precision/recall reported by agent-lens.
- **Metrics:** candidate counts (dense/sparse), fusion + rerank latency, top-k
  scores — into `TraceEvent.attributes`.
