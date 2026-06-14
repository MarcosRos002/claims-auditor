# ADR 0001 — Stack and scope

- **Status:** Accepted (Phase 0)
- **Date:** 2026-06-14
- **Deciders:** Marcos Rostan (AI Engineer Portfolio Program)

## Context

Veritas is the flagship of a 4-repo portfolio program meant to demonstrate the
full AI-Engineer SSR/SR skill surface to hiring teams. It must be impressive,
defensible under senior scrutiny, **fully free-tier**, and interoperate with its
sibling repos (agent-lens measures it; fine-tune-lab feeds it a cheap model;
portfolio exhibits it). This ADR records the stack decisions already made so a
fresh contributor doesn't relitigate them.

## Decision

1. **Orchestration: LangGraph + Claude Agent SDK.** LangGraph gives an explicit,
   inspectable graph (good for eval and for the portfolio narrative); the Claude
   Agent SDK gives first-class tool use and structured outputs. A custom
   **agentic harness** wraps both as the headline component.
2. **Models: Claude Haiku + Sonnet with cost routing.** `claude-haiku-4-5` for
   cheap/simple work, `claude-sonnet-4-6` for hard cases, routed by complexity.
   Adaptive thinking; structured outputs via `output_config.format`. Pass-1
   classification can be served by the distilled small model from fine-tune-lab.
3. **RAG: hybrid over Postgres + pgvector.** Dense (pgvector) + sparse (Postgres
   full-text / BM25) candidates, fused with **Reciprocal Rank Fusion**, then a
   **cross-encoder rerank**. One database for both vectors and FTS keeps the
   free-tier footprint small.
4. **ASR: faster-whisper (local) with Groq (hosted) fallback.** Local keeps
   demos free and offline-capable; Groq covers low-latency hosted runs.
5. **Cost routing** as a first-class concern (its own module), because
   cost-per-claim is a headline metric agent-lens will report.
6. **Synthetic ICD-10/CPT data.** Generated in-repo with injected
   inconsistencies (ground truth for eval). Never real PHI — eliminates privacy
   risk and licensing friction while staying realistic.
7. **API: FastAPI + WebSocket.** One framework for REST audit, streaming
   transcription, and low-latency voice Q&A.
8. **Guardrails: PII redaction, prompt-injection defense, read-only DB.** Treated
   as product features and as senior-signal, even though data is synthetic.
9. **Rules engine exposed as an MCP server**, so the same logic is directly
   callable and agent-callable.
10. **Free-tier hosting + Docker + CI eval-gates.** Containerized; CI runs the
    agent-lens eval and gates merges on it.

## Consequences

- A clear, demoable, measurable system with a strong senior narrative.
- Tight coupling to the sibling repos' contracts (esp. agent-lens's TraceEvent).
- Everything stays inside free tiers; no managed vector DB, no paid ASR required.
- Contract-first design lets modules be built in parallel `git worktree`s.

## When NOT to use this approach

This stack is tuned for a **portfolio flagship**, not every production system.
Reach for something else when:

- **Latency/scale dominate and budget exists.** A managed vector DB (or a
  purpose-built search service) and a single strong model beat a hand-rolled
  hybrid+rerank+routing stack on ops simplicity at scale. Our hybrid RAG and
  cost router exist partly to *demonstrate* the techniques.
- **The domain is narrow and rules suffice.** If a deterministic rules engine
  already catches the inconsistencies you care about, the LLM/RAG layer adds cost
  and non-determinism for little gain. Start with rules; add the agent only where
  rules can't express the judgment.
- **You handle real PHI.** Then synthetic-data convenience disappears: you need a
  real compliance program (BAA, audit logging, access control, encryption,
  retention policy) — far beyond this repo's redaction-as-discipline posture.
- **Strict reproducibility / no external dependence.** Routing across models and
  adaptive thinking trade determinism for cost/quality; a fixed single model with
  pinned settings is easier to reason about for regulated, audited outputs.
- **Voice is not a requirement.** The ASR + WebSocket + barge-in machinery is
  significant surface area; drop it if text-in/text-out covers the use case.
- **Tiny tool set.** MCP indirection earns its keep with many tools or
  cross-process reuse; for one or two in-process functions it's overhead.
