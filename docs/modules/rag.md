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
**Production swaps:** `DenseIndex`→pgvector (read-only), `Embedder`/`Reranker`→
sentence-transformers.

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
