# Module: rag (`modules/rag/`)

## Purpose
Hybrid retrieval over ICD-10/CPT descriptions and policy text — the evidence
layer that grounds every finding. Dense + sparse candidate generation, fused and
reranked. **Read-only** DB access.

## Public interface
`modules/rag/retriever.py:HybridRetriever` implements `Retriever`:
- `retrieve(query, *, top_k=8) -> list[RetrievedChunk]`

Pipeline: pgvector (dense) + Postgres full-text/BM25 (sparse) → **Reciprocal Rank
Fusion** → **cross-encoder rerank** → top-k. `RetrievedChunk.score` is the final
post-rerank score.

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
