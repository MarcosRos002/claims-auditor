# Veritas — `claims-auditor`

> **Catch the billing errors before the payer does.** Veritas is a multimodal,
> production-framed audit agent: feed it a clinical audio recording or a
> structured medical claim, and it transcribes, extracts the claim, audits it
> against business rules and ICD-10/CPT coding via hybrid retrieval, flags
> inconsistencies, and **explains *why* with citations** — then answers
> follow-up questions by voice. Built on an agentic harness with cost-routed
> Claude models, guardrails, and an MCP-exposed rules engine.

**Flagship of a 4-repo AI-Engineer portfolio program.** Measured by
[agent-lens](https://github.com/MarcosRos002/agent-lens), fed a cheap distilled
model by [fine-tune-lab](https://github.com/MarcosRos002/fine-tune-lab), and
exhibited in [portfolio](https://github.com/MarcosRos002/portfolio).

> ⚕️ **Synthetic data only.** Veritas operates on synthetic claims modeled on
> ICD-10/CPT conventions. It never ingests real patient data (no PHI).

---

## Architecture

```
                 ┌──────────────────────────────────────────────────────────────┐
   audio  ──────▶│  ASR (faster-whisper / Groq)  ──streaming──▶ transcript       │
   OR            │                                                  │            │
   structured    │                                                  ▼            │
   claim   ──────────────────────────────────────────▶  claim extraction         │
                 │                                                  │            │
                 │                              ┌───────────────────┘            │
                 │                              ▼                                 │
                 │   HYBRID RAG  ─ pgvector (dense) + Postgres FTS/BM25 (sparse)  │
                 │                 → RRF fusion → cross-encoder rerank → top-k    │
                 │   over ICD-10 / CPT / policies            │                    │
                 │                                           ▼                    │
                 │   classification (Haiku → Sonnet by confidence)               │
                 │                                           │                    │
                 │                                           ▼                    │
                 │   inconsistency detection ──▶ explanation WITH citations      │
                 └──────────────────────────────────────────────────────────────┘
   ┌───────────────────────────────────────────────────────────────────────────┐
   │  Agentic HARNESS (loop · parallel tool dispatch · retries · streaming ·    │
   │  barge-in · structured-output validation)   ◀── cost routing · guardrails  │
   │  Rules engine + code lookups exposed as an MCP server (tools for the agent)│
   └───────────────────────────────────────────────────────────────────────────┘
        │ emits TraceEvents (schema owned by agent-lens) ──▶ measured externally
        ▼
   Voice Q&A:  "why did you flag claim #123?"  ──▶ low-latency spoken answer
```

See [`docs/architecture.md`](docs/architecture.md) for the full design.

## Skill surface demonstrated

| Area | What it shows |
|---|---|
| Agentic systems | A purpose-built **harness**: agent loop, parallel tool dispatch, state machine, retries/backoff, streaming, barge-in, structured-output validation |
| RAG (advanced) | **Hybrid** retrieval — dense + sparse, **RRF fusion**, **cross-encoder rerank** over real coding taxonomies |
| LLM cost engineering | **Cost routing** Haiku↔Sonnet by complexity; cheap distilled model for Pass-1 classification |
| Multimodal / realtime | Streaming **ASR**, WebSocket streaming, low-latency **voice Q&A** |
| Tooling / interop | Rules engine + lookups exposed over **MCP** |
| Safety | **PII redaction**, **prompt-injection defense**, **read-only** DB access |
| Eval & observability | Emits a canonical **TraceEvent** stream; measured by agent-lens |
| Production framing | Contract-first design, Docker + CI eval-gates, free-tier deploy |

## Metrics

Component metrics land as each layer ships; end-to-end metrics are measured by
[agent-lens](https://github.com/MarcosRos002/agent-lens).

**Rules engine** — deterministic backbone, measured on 1000 synthetic claims
(50% fault rate, rule-detectable fault types), reproducible via
`tests/test_rules_engine.py`:

| Metric | Value |
|---|---|
| Precision | **0.997** |
| Recall | **1.000** |
| F1 | **0.999** |

| Metric (pending layers) | Status |
|---|---|
| Classifier precision/recall (incl. upcoding) | TBD |
| Latency P50 / P95 (audit) | TBD |
| Voice Q&A first-token latency | TBD |
| Cost per claim (USD) | TBD |

## Demo strategy

Three tiers, all free:
1. **Demo mode** — cached/canned responses, no API keys, instant (`VERITAS_DEMO_MODE=1`).
2. **OpenRouter free tier** — wired through an OpenAI-compatible client for zero-cost live runs.
3. **BYOK** — a visitor supplies their own `ANTHROPIC_API_KEY` for the full-quality path.

## Quick start

```bash
make install      # editable install + dev tools
make test         # smoke tests (green today)
make db-up        # Postgres + pgvector (real service)
make run-api      # FastAPI; /healthz works in Phase 0
```

## Status

**Phase 0 — context-readiness complete.** Structure, docs, contracts, and stubs
are in place; feature implementation follows. Start at
[`CLAUDE.md`](CLAUDE.md) and [`docs/context/handoff.md`](docs/context/handoff.md).

## Links
- Architecture: [`docs/architecture.md`](docs/architecture.md)
- Contracts: [`docs/contracts/`](docs/contracts/)
- ADR 0001 (stack & scope): [`docs/adr/0001-stack-and-scope.md`](docs/adr/0001-stack-and-scope.md)
- Build orchestration: [`docs/orchestration.md`](docs/orchestration.md)
- License: [MIT](LICENSE)
