# Context handoff

## Current state

**Phase 1 — foundational layer COMPLETE + first leaf (rules engine) done.**
`TraceEvent` contract reconciled, synthetic data generator built, agentic harness
built, shared `reference/catalog.py` extracted, and the **rules engine** detects
the 3 deterministic fault types at **precision 0.997 / recall 1.000** on 1000
synthetic claims (`tests/test_rules_engine.py`). `AuditFinding` gained
`category` + `line_index` for eval matching. 34 tests pass.

**rules MCP layer done** (`modules/rules/mcp.py`): real FastMCP server with 4
read-only tools (`evaluate_rules`, `lookup_icd10`, `lookup_cpt`,
`check_cpt_icd_compatibility`); same tools dispatchable by the harness via
`as_harness_tools()`. Pinned by `tests/test_rules_mcp.py`. 41 tests pass.

**classification done** (`modules/classification/classifier.py`): two-pass
cost-routing `TwoPassClassifier` (cheap Pass 1 → escalate to Pass 2 on low
confidence); injected model (offline-testable); exposes `last_pass_used` /
`last_escalated` for cost metrics. Covers UPCODING (out of rules' reach). Pinned
by `tests/test_classification.py`. 47 tests pass.

**agent orchestrator done = Capa 1 MVP** (`agent/graph.py`): `AuditOrchestrator`
runs rules + classifier, merges/dedupes findings, returns `AuditReport` +
per-stage agent-lens `Trace`; degrades gracefully on stage failure. Pinned by
`tests/test_agent_orchestrator.py`. **54 tests pass.** `AuditReport` added to
contracts.

**The text-claim audit now runs end-to-end.** Next high-value options:
1. **Real model adapter** (`ClassifierModel`/`ModelClient` over Anthropic
   Haiku/Sonnet) with demo-mode + OpenRouter-free + BYOK — turns the offline MVP
   into a live one.
2. **`rag`** (needs Postgres/pgvector) — real citations.
3. **`asr`** (Capa 2, multimodal) — audio → claim.
4. Start building **agent-lens** itself (it now has a real Trace to consume).

### Done in Phase 1 so far
- **`TraceEvent` reconciled (single source of truth).** The local mirror is gone;
  `contracts.py` now imports the canonical `TraceEvent`/`Trace`/`StepKind`/
  `StepStatus`/`TokenUsage`/`ErrorInfo` from `agent_lens.schema` and re-exports
  them. `agent-lens` is declared as a dependency (`git+https://...`). ASR steps
  map to `kind=TOOL` + `metadata={"modality":"audio"}` (canonical enum stays
  general). Pinned by `tests/test_trace_event_contract.py` (asserts identity with
  the canonical class + that its validators are enforced). See
  `docs/contracts/trace_event.md`.
- **Synthetic data generator built** (`data/synthetic.py`). Returns
  `LabeledClaim` (claim + ground-truth `InjectedFault`s), deterministic by seed,
  covering 4 fault types (`CPT_ICD_MISMATCH`, `UNIT_EXCESS`, `DUPLICATE_LINE`,
  `UPCODING`). `FaultType` added to `contracts` (shared with rules/eval). Pinned
  by `tests/test_synthetic_data.py`. See `docs/modules/data.md`.
- **Green baseline extended:** 17 tests pass; `ruff check` clean.
- **Dev env note:** a local venv (`.venv`, gitignored) was created with
  `--system-site-packages` + `pip install -e ../agent-lens --no-deps` for the
  cross-repo import. A full `make install` (once heavy deps are wanted) installs
  `agent-lens` from git per `pyproject.toml`.

**Phase 0 bootstrap complete.** The repo is context-ready: a fresh Claude Code
session can open it and have full context to build it.

In place:
- Directory structure under `src/claims_auditor/` (harness, agent, asr, rag,
  rules+mcp, classification, routing, guardrails, api, data) with `__init__.py`s.
- **Contracts** in `src/claims_auditor/contracts.py` (Claim, ClaimLine,
  RetrievedChunk, AuditFinding, ToolSpec, TranscriptSegment, TraceEvent mirror;
  Retriever/ASRTranscriber/Classifier Protocols), specified in `docs/contracts/`.
- **Code stubs** for every module — class/function signatures + docstrings that
  `raise NotImplementedError`. No features implemented.
- **Config:** `pyproject.toml` (deps + ruff + pytest), `Makefile`, `.env.example`,
  `docker-compose.yml` (real pgvector `db`, stub `app`), `scripts/db-init/`.
- **Docs:** `CLAUDE.md`, `README.md`, `docs/architecture.md`,
  `docs/adr/0001-stack-and-scope.md`, `docs/orchestration.md`, `docs/contracts/*`,
  `docs/modules/*` (one per module), this handoff.
- **Green baseline:** smoke tests (`tests/test_smoke.py`, `tests/test_api_health.py`)
  and `GET /healthz` pass.

What is **NOT** done: any real feature logic. Every module stub raises
`NotImplementedError` by design.

## Next steps (in order)

1. ~~Pull the canonical `TraceEvent` from agent-lens and reconcile the local
   mirror.~~ ✅ **Done.** Remaining: review the domain Protocols
   (`Retriever`/`ASRTranscriber`/`Classifier`) once and **freeze the contracts**
   before parallel work starts.
2. **Build the foundational layer (Phase 1):**
   - ~~`data/synthetic.py` — synthetic claim generator with labeled
     inconsistencies.~~ ✅ **Done.**
   - ~~`core/harness/` — the agent runtime (loop, parallel dispatch, retries,
     structured-output validation, TraceEvent emission).~~ ✅ **Done**
     (`tests/test_harness.py`). Voice streaming/barge-in deferred to Phase 4.
3. **Open parallel worktrees (Phase 2)** — one Claude Code agent each, per
   `docs/orchestration.md`:
   - `feat/asr`, `feat/rag`, `feat/rules-mcp`, `feat/classification`.
   Each codes against its Protocol + isolation tests; no cross-module imports
   beyond `contracts`.
4. **Integrate (Phase 3):** `agent/graph.py` LangGraph graph once leaves land.
5. **Upper layers (Phase 4):** voice (`api/` WS + barge-in), `routing/` cost
   routing, `guardrails/`, and agent-lens TraceEvent emission.
6. **Deploy (Phase 5):** Dockerfile, CI eval-gates running the agent-lens eval.

## Pointers
- Start at `CLAUDE.md`. Build order + worktree mechanics: `docs/orchestration.md`.
- Per-module specs: `docs/modules/`. Stack rationale + boundaries:
  `docs/adr/0001-stack-and-scope.md`.
- Verify the baseline anytime: `make test`.
