# Module: agent (`agent/`)

## Purpose
The audit orchestrator: a LangGraph graph that wires the pipeline together —
ingest → (asr) → extract claim → retrieve → classify → detect inconsistencies →
explain. This is the **integration** layer; it owns no domain logic of its own,
only the composition.

## Public interface
`agent/graph.py`:
- `build_graph()` — construct and compile the LangGraph graph.
- `audit_claim(claim) -> list[AuditFinding]` — convenience single-claim entrypoint.

Depends on the leaf modules **through their Protocols** (`Retriever`,
`ASRTranscriber`, `Classifier`) and the rules engine/MCP — never their concretes.

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
