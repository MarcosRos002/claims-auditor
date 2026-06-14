# CLAUDE.md — Veritas (claims-auditor)

> Single best entry point for a fresh Claude Code session. Read this first, then
> the docs it points to. This repo is the **flagship** of a 4-repo program.

## What Veritas is

**Veritas** (package `claims_auditor`) is a **multimodal medical-billing audit
agent**. End-to-end flow:

```
audio (clinical dictation / call recording)  OR  structured claim
        │
        ▼  streaming ASR (faster-whisper / Groq)
   transcript ──► claim extraction ──► HYBRID RAG audit ──► inconsistency detection ──► WHY + citations
                                       (pgvector + Postgres FTS/BM25,
                                        RRF fusion, cross-encoder rerank,
                                        over ICD-10/CPT + policies)
        │
        ▼  low-latency VOICE Q&A  ("why did you flag claim #123?")
```

Headline components: a first-class **agentic harness** (the runtime everything
plugs into), **cost routing** between Claude Haiku/Sonnet by query complexity,
and a **rules-engine + code lookups exposed as an MCP server**. All data is
**SYNTHETIC**, modeled on ICD-10/CPT — never real patient data.

## Sibling repos (part of a 4-repo program)
- claims-auditor (flagship): https://github.com/MarcosRos002/claims-auditor
- agent-lens (eval/observability): https://github.com/MarcosRos002/agent-lens
- fine-tune-lab (LoRA/distillation): https://github.com/MarcosRos002/fine-tune-lab
- portfolio (website): https://github.com/MarcosRos002/portfolio
Relationship: claims-auditor is measured by agent-lens, fed a cheap model by fine-tune-lab, and exhibited in portfolio.

**Program:** "AI Engineer Portfolio Program" by Marcos Rostan (GitHub:
MarcosRos002, rostanmarcos@gmail.com). Goal: 3 interconnected open-source
projects + a portfolio website demonstrating the full AI Engineer SSR/SR skill
surface. 100% free-tier. Contract-first. Docs are context infrastructure.

Concretely:
- **agent-lens** owns the canonical `TraceEvent` schema that this repo emits, and
  measures Veritas (precision/recall, latency, cost). See `docs/contracts/trace_event.md`.
- **fine-tune-lab** produces the cheap distilled model that can serve Pass 1 of
  the classification step (`modules/classification`).
- **portfolio** exhibits the live demo.

## Tech stack
Python ≥3.11 · LangGraph + Claude Agent SDK · Claude Haiku (`claude-haiku-4-5`) /
Sonnet (`claude-sonnet-4-6`) with cost routing · FastAPI (+WebSocket for
streaming & voice) · faster-whisper / Groq for ASR · Postgres + pgvector for
hybrid RAG. Guardrails: PII redaction, prompt-injection defense, read-only DB.

> When writing Claude API calls: use the model IDs above, **adaptive thinking**
> (`thinking={"type":"adaptive"}`), and **structured outputs** via
> `output_config={"format": {...}}` (the `output_format` param is deprecated).
> `budget_tokens` and `temperature`/`top_p` are rejected on current models.

## Conventions
- **Contract-first.** Shared types live in `src/claims_auditor/contracts.py` and
  are specified in `docs/contracts/`. Implement against Protocols (`Retriever`,
  `ASRTranscriber`, `Classifier`), not concrete classes.
- **Python tooling:** `ruff` (lint + format), `pytest` (+`pytest-asyncio`).
  Config is in `pyproject.toml`. First-party import root is `claims_auditor`.
- **Package manager (JS/Node tooling): pnpm only — never use npm or npx.**
- **Layout:** `src/` layout; `src/claims_auditor/<area>/`. One module = one
  responsibility = one `docs/modules/*.md` spec.
- **Synthetic data only.** Never introduce real PHI. Redaction is enforced anyway.
- **Read-only DB** in the audit path.

## How to run / test (works in Phase 0)
```bash
make install      # pip install -e ".[dev]"
make test         # pytest — smoke tests pass today
make lint         # ruff check
make fmt          # ruff format + --fix
make db-up        # Postgres+pgvector via docker compose (db service is real)
make run-api      # uvicorn claims_auditor.api.app:app  (only /healthz works yet)
```
Most module code is a stub that raises `NotImplementedError` — that is expected
in Phase 0. The smoke tests (`tests/test_smoke.py`, `tests/test_api_health.py`)
and `/healthz` are the green baseline.

## Where to look (docs/)
- `docs/architecture.md` — end-to-end flow, ASCII diagram, harness design, error handling.
- `docs/contracts/` — contract-first interfaces (Claim, AuditFinding, ToolSpec,
  RetrievedChunk, the Retriever/ASRTranscriber/Classifier Protocols, TraceEvent note).
- `docs/adr/0001-stack-and-scope.md` — the already-decided stack + "when NOT to use this".
- `docs/orchestration.md` — dependency graph + how to build modules in parallel `git worktree`s.
- `docs/modules/*.md` — one spec per module (harness, agent, asr, rag, rules-mcp,
  classification, routing, guardrails, api, data).
- `docs/context/handoff.md` — current state + the next concrete steps.

## Current phase
**Phase 0 (context-readiness) complete.** Structure, docs, contracts, and stubs
exist; no features are implemented. Start at `docs/context/handoff.md`.
