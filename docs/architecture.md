# Architecture — Veritas (claims-auditor)

Veritas audits medical-billing claims and explains its findings. This document
describes the end-to-end flow, each component's responsibility, data flow, error
handling, and the agentic harness design.

## End-to-end flow

```
            INPUT
   ┌─────────────────────┐
   │ audio file          │   clinical dictation / call recording
   │   OR                │
   │ structured claim    │
   └──────────┬──────────┘
              │
   ┌──────────▼──────────┐   modules/asr  (faster-whisper local / Groq hosted)
   │  ASR (streaming)    │   emits partial + final TranscriptSegments
   └──────────┬──────────┘
              │ transcript (or skip if input is already structured)
   ┌──────────▼──────────┐   agent/  node
   │  Claim extraction   │   transcript → Claim (pydantic)
   └──────────┬──────────┘
              │ Claim
   ┌──────────▼──────────┐   guardrails/  (before any LLM/tool sees text)
   │  PII redaction +    │   redact PII/PHI; treat retrieved/ASR text as DATA
   │  injection scan     │
   └──────────┬──────────┘
              │
   ┌──────────▼──────────┐   modules/rag  (HYBRID)
   │  Hybrid retrieval   │   pgvector (dense) + Postgres FTS/BM25 (sparse)
   │                     │   → RRF fusion → cross-encoder rerank → top-k
   └──────────┬──────────┘   evidence: ICD-10 / CPT / policy chunks
              │ RetrievedChunk[]
   ┌──────────▼──────────┐   modules/rules  (deterministic) + modules/classification (LLM)
   │  Audit              │   rules engine fires + 2-pass classifier (Haiku→Sonnet)
   └──────────┬──────────┘
              │ candidate findings
   ┌──────────▼──────────┐
   │  Inconsistency      │   reconcile rule-based + model-based signals
   │  detection          │
   └──────────┬──────────┘
              │ AuditFinding[]
   ┌──────────▼──────────┐
   │  Explanation        │   WHY, grounded in citations (RetrievedChunk[])
   └──────────┬──────────┘
              │
   ┌──────────▼──────────┐   api/  (WebSocket)
   │  Voice Q&A          │   "why did you flag claim #123?" → low-latency answer
   └─────────────────────┘

   Throughout: the agentic HARNESS drives the loop, dispatches tools (incl. the
   rules MCP server), applies cost routing, and EMITS TraceEvents → agent-lens.
```

## Component responsibilities

| Component | Path | Responsibility |
|---|---|---|
| Harness | `core/harness/` | Agent runtime: loop, parallel tool dispatch, context mgmt, retries/backoff, structured-output validation, state machine, streaming, barge-in, error recovery. |
| Agent | `agent/` | LangGraph orchestrator wiring ingest→asr→extract→retrieve→classify→detect→explain. |
| ASR | `modules/asr/` | Audio ingestion + streaming transcription. Implements `ASRTranscriber`. |
| RAG | `modules/rag/` | Hybrid retrieval over ICD-10/CPT + policies. Implements `Retriever`. |
| Rules + MCP | `modules/rules/` | Deterministic rules engine; exposes rules + code lookups as MCP tools. |
| Classification | `modules/classification/` | Two-pass Haiku→Sonnet confidence classification. Implements `Classifier`. |
| Routing | `routing/` | Cost routing between models by query complexity. |
| Guardrails | `guardrails/` | PII redaction, prompt-injection defense. |
| API | `api/` | FastAPI + WebSocket endpoints (audit, streaming, voice). |
| Data | `data/` | Synthetic claim schema + labeled generator. |
| Contracts | `contracts.py` | Shared pydantic models + Protocols. The seams between all of the above. |

## Data flow

1. Input arrives as audio or a structured claim at the API layer.
2. Audio → `ASRTranscriber.transcribe_stream` → `TranscriptSegment[]`.
3. Transcript (or raw payload) → claim extraction → `Claim`.
4. `Claim` text passes through **guardrails** (redaction + injection scan) before
   any LLM or tool is invoked. Retrieved/transcribed text is always treated as
   data, never as instructions.
5. `Retriever.retrieve` returns ranked `RetrievedChunk[]` evidence.
6. Audit = rules engine (deterministic) ∪ `Classifier.classify` (LLM, cost-routed).
7. Findings reconciled into `AuditFinding[]`, each carrying its `citations`.
8. Explanation renders the `why` grounded in those citations.
9. Voice Q&A reuses the same findings + retrieval to answer follow-ups.
10. Every step emits `TraceEvent`s (schema owned by agent-lens) for measurement.

## Error handling

The pipeline degrades rather than crashes:

- **ASR failure / low confidence** → surface partials, mark segments non-final,
  let the agent request re-transcription or fall back to Groq.
- **Retrieval empty / DB unavailable** → return findings without citations but
  flag reduced confidence; never fabricate citations.
- **LLM transient errors (429/5xx)** → harness retries with exponential backoff
  (the Anthropic SDK already retries; the harness adds turn-level recovery).
- **Structured-output validation failure** → the harness re-prompts with the
  schema (pydantic round-trip on every model reply); bounded retries.
- **Refusal stop reason** → handled explicitly (check `stop_reason` before
  reading content); surfaced, not retried blindly.
- **Tool errors** → returned to the agent as tool results with `is_error`, so it
  can adapt instead of failing the turn.
- **DB is read-only** in the audit path — a whole class of mutation bugs is
  designed out.

## Agentic harness design

The harness is the headline component and the thing every module plugs into. It
is deliberately model-agnostic; the model is chosen per call by `routing/`.

Responsibilities:
- **Agent loop** — plan → dispatch tools → observe results → repeat until done.
- **Parallel tool dispatch** — read-only / `parallel_safe` tools (e.g. code
  lookups, retrieval) run concurrently; unsafe tools serialize.
- **Context management** — windowing + compaction hooks keep long audits within
  the context budget.
- **Retries / backoff** — on transient model and tool failures.
- **Structured-output validation** — every model reply is round-tripped through
  the relevant pydantic contract; invalid output triggers a bounded re-prompt.
- **State machine** — explicit turn lifecycle (idle → running → awaiting-tool →
  done / error) so streaming and barge-in are well-defined.
- **Streaming + barge-in** — for the voice path, partial output streams and can
  be interrupted by the user mid-answer.
- **Error recovery** — a failing tool or model call degrades the turn instead of
  crashing it.

The rules engine + code lookups are presented to the harness as an **MCP
server**, so the same deterministic logic is both directly callable and
agent-callable. The harness emits a `TraceEvent` per span; agent-lens consumes
that stream to compute precision/recall, latency, and cost.

See `docs/orchestration.md` for how these components are built (and which can be
built in parallel), and `docs/modules/*.md` for per-component specs.
