# Contract: `TraceEvent` — OWNED BY agent-lens

> ✅ **Reconciled (Phase 1).** The canonical `TraceEvent` schema lives in
> [agent-lens](https://github.com/MarcosRos002/agent-lens) and Veritas now
> **imports it directly** — there is no local mirror, so drift is structurally
> impossible. `claims_auditor.contracts` re-exports the canonical types:

```python
# src/claims_auditor/contracts.py
from agent_lens.schema import (
    ErrorInfo, StepKind, StepStatus, TokenUsage, Trace, TraceEvent,
)
```

`agent-lens` is declared as a dependency in `pyproject.toml`
(`agent-lens @ git+https://github.com/MarcosRos002/agent-lens.git`).

## Canonical shape (defined in agent-lens, do not redefine here)
A `TraceEvent` is **one step** in a session. Key fields (see
`agent_lens/schema/trace.py` for the authoritative definition):

- **Identity/linkage:** `session_id`, `step_id`, `parent_step_id` (tree for
  trajectory/causal eval), `schema_version`.
- **What happened:** `kind` (`StepKind`: llm/tool/retrieval/agent/guardrail/other),
  `name`, `tool_name`.
- **Payload:** `inputs`, `output` (redact PII before emit).
- **Model/cost/perf:** `model`, `provider`, `tokens` (`TokenUsage`), `cost_usd`,
  `latency_ms`.
- **Timing:** `start_time`, `end_time` (UTC, timezone-aware).
- **Outcome:** `status` (`StepStatus`), `error` (`ErrorInfo`; required when
  `status == error`, enforced by a validator).
- **Context:** `metadata` (env, git sha, model/prompt version, A/B bucket, ...).

## Mapping Veritas steps onto the canonical schema
The canonical `StepKind` enum is deliberately **general** so agent-lens can
measure any agent. Veritas maps its domain steps as:

| Veritas step | `kind` | notes |
|---|---|---|
| Claude Haiku/Sonnet call | `LLM` | set `model`, `provider`, `tokens`, `cost_usd` |
| Rules-engine / MCP tool dispatch | `TOOL` | `tool_name` = the tool id |
| Hybrid RAG lookup | `RETRIEVAL` | retrieval scores in `metadata` |
| **ASR transcription** | `TOOL` | `tool_name="asr.transcribe"`, `metadata={"modality":"audio"}` |
| PII redaction / injection check | `GUARDRAIL` | |
| Cost-routing decision | recorded in `metadata` of the `LLM` step it gates | which model + why |

## Why it's external
- agent-lens computes the headline metrics (precision/recall, P50/P95 latency,
  cost-per-claim) from this stream. Keeping the schema there makes agent-lens the
  single definition every measured project conforms to.
- This is a deliberate cross-repo contract and a demonstrable example of building
  to a shared spec. The contract is pinned by
  `tests/test_trace_event_contract.py`, which asserts `contracts.TraceEvent is
  agent_lens.schema.TraceEvent` and that the canonical validators are enforced.

## Integration notes (Phase 4 — emission)
- The harness emits one `TraceEvent` per step (LLM call, tool dispatch,
  retrieval, ASR segment, guardrail check).
- Populate `tokens`/`cost_usd` on LLM steps so agent-lens can attribute cost; put
  retrieval scores and rule/finding ids in `metadata`.
- If Veritas ever needs a field the canonical schema lacks, **do not add it
  locally** — open a change against agent-lens (`docs/contracts/` + an ADR there),
  because agent-lens owns the schema.
