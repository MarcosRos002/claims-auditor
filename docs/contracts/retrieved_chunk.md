# Contract: `RetrievedChunk`

A single ranked evidence chunk returned by hybrid retrieval and used as a
citation.

```python
class RetrievedChunk(BaseModel):
    chunk_id: str
    text: str
    source: str    # e.g. "icd10", "cpt", "policy:<name>"
    score: float   # post-fusion / post-rerank relevance score
```

## Notes
- `score` is the **final** score after RRF fusion and cross-encoder reranking, so
  consumers can rank/threshold without knowing the retrieval internals.
- `source` lets the explanation cite *what kind* of evidence grounds a finding
  (a code description vs a policy clause).
- Produced exclusively by `modules/rag` (the `Retriever`). Embedded into
  `AuditFinding.citations`.
