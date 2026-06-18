# Context handoff

## Current state

**Phase 1 in progress.** The `TraceEvent` cross-repo contract is reconciled (see
below); foundational layer (synthetic data + harness) is the next task.

### Done in Phase 1 so far
- **`TraceEvent` reconciled (single source of truth).** The local mirror is gone;
  `contracts.py` now imports the canonical `TraceEvent`/`Trace`/`StepKind`/
  `StepStatus`/`TokenUsage`/`ErrorInfo` from `agent_lens.schema` and re-exports
  them. `agent-lens` is declared as a dependency (`git+https://...`). ASR steps
  map to `kind=TOOL` + `metadata={"modality":"audio"}` (canonical enum stays
  general). Pinned by `tests/test_trace_event_contract.py` (asserts identity with
  the canonical class + that its validators are enforced). See
  `docs/contracts/trace_event.md`.
- **Green baseline extended:** 9 tests pass; `ruff check` clean.
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
   - `data/synthetic.py` — the synthetic claim generator with injected,
     labeled inconsistencies (gives every other module its test fixtures).
   - `core/harness/` — the agent runtime (loop, parallel dispatch, retries,
     structured-output validation, streaming, TraceEvent emission).
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
