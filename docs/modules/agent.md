# Module: agent (`agent/`)

## Purpose
The audit orchestrator that wires the pipeline together — retrieve → rules →
classify → reconcile → report. This is the **integration** layer; it owns no
domain logic of its own, only the composition.

## Status: implemented (Phase 1 — Capa 1 MVP)
End-to-end text-claim audit works: rules + classifier → merged/deduped findings →
`AuditReport` + per-stage agent-lens `Trace`. Pinned by
`tests/test_agent_orchestrator.py`.

**Implementation note:** orchestrated as a typed pipeline, **not** LangGraph yet.
The node boundaries are linear/deterministic, so a plain pipeline is simpler and
fully testable. LangGraph is warranted once we need conditional routing
(audio-vs-text branch), checkpointing, or human-in-the-loop — that is the planned
evolution. The ASR/extract and retrieve stages slot in as the leaves land.

## Public interface
`agent/graph.py`:
- `AuditOrchestrator(rules_engine, classifier, *, retriever=None)`
  - `audit(claim) -> AuditReport`
  - `audit_with_trace(claim) -> tuple[AuditReport, Trace]` (Trace = agent-lens spans)
- `build_orchestrator(classifier, *, retriever=None) -> AuditOrchestrator`
- `audit_claim(claim, *, classifier) -> list[AuditFinding]` — convenience.

Reconciliation: findings deduped by `(category, line_index)`; rules win ties, the
classifier adds what rules can't (e.g. UPCODING). A failing stage degrades (drops
its findings, records an `error` TraceEvent) instead of aborting.

Depends on the leaf modules **through their Protocols** (`Retriever`,
`ASRTranscriber`, `Classifier`) and the rules engine — never their concretes.

## Dependencies
- `contracts`, `core/harness`, and all four Phase-2 leaves (via Protocols).
- **Integration phase (Phase 3)** — can't start until the leaves expose contracts.

## How to test in isolation
- Inject **fake** implementations of each Protocol (the synthetic generator gives
  fixtures) and assert the graph routes a claim through every node and returns
  `AuditFinding[]`.
- Test the structured→audit path and the audio→extract→audit path separately.
- Assert reconciliation merges rule-based and model-based findings without
  duplication.

## Senior concerns
- **Failure modes:** a single node failing should degrade (e.g. retrieval empty →
  findings without citations) rather than abort the whole graph.
- **Determinism for eval:** keep node boundaries clean so agent-lens can attribute
  latency/cost per stage.
- **Metrics:** per-node spans; end-to-end audit latency; number of findings.
