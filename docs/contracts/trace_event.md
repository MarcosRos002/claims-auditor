# Contract: `TraceEvent` — OWNED BY agent-lens

> ⚠️ **The canonical `TraceEvent` schema lives in
> [agent-lens](https://github.com/MarcosRos002/agent-lens), not here.** agent-lens
> is the eval/observability sibling that *measures* Veritas. It defines the
> schema; Veritas **emits** conforming events. The pydantic model in
> `contracts.py` is a **local mirror for typing only** — do not let it drift.

```python
# Local mirror (typing convenience) — agent-lens is the source of truth.
class TraceEvent(BaseModel):
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    name: str
    kind: str           # "llm" | "tool" | "retrieval" | "asr" | ...
    start_ts: float
    end_ts: float | None = None
    attributes: dict     # span-specific metadata (model, tokens, cost, scores, ...)
```

## Why it's external
- agent-lens computes the headline metrics (precision/recall, P50/P95 latency,
  cost-per-claim) from this stream. Keeping the schema there makes agent-lens the
  single definition every measured project conforms to.
- This is a deliberate cross-repo contract and a demonstrable example of building
  to a shared spec.

## Integration notes (Phase 4)
- The harness emits one `TraceEvent` per span (LLM call, tool dispatch,
  retrieval, ASR segment, ...).
- `attributes` carries cost-routing decisions (which model), token usage,
  retrieval scores, and rule/finding ids so agent-lens can attribute metrics.
- When wiring this up, **pull the schema from agent-lens** and reconcile this
  mirror against it; if they diverge, agent-lens wins.
