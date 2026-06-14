# Contracts (contract-first)

Veritas is built contract-first: the typed seams between modules are defined and
agreed **before** implementation, so modules can be built in parallel against
stable interfaces. The executable source of truth is
[`src/claims_auditor/contracts.py`](../../src/claims_auditor/contracts.py); the
files here are the annotated, human-facing spec.

## Models

| Type | Purpose | Owner |
|---|---|---|
| `Claim` / `ClaimLine` | The unit Veritas audits (synthetic). | `data` produces; `agent` extracts |
| `RetrievedChunk` | A ranked evidence chunk (ICD-10/CPT/policy). | `rag` |
| `AuditFinding` (a.k.a. Inconsistency) | A detected inconsistency + `why` + citations. | `rules`, `classification` |
| `ToolSpec` | A tool the harness/agent can dispatch (incl. MCP). | `rules` (MCP), `core/harness` |
| `TranscriptSegment` | A streaming ASR segment. | `asr` |
| `TraceEvent` | Observability event. **Owned by agent-lens** — see [`trace_event.md`](trace_event.md). | agent-lens |

## Protocols (the seams)

| Protocol | Method | Implemented by |
|---|---|---|
| `Retriever` | `retrieve(query, *, top_k) -> list[RetrievedChunk]` | `modules/rag` |
| `ASRTranscriber` | `transcribe_stream(audio) -> list[TranscriptSegment]` | `modules/asr` |
| `Classifier` | `classify(claim, context) -> list[AuditFinding]` | `modules/classification` |

## Rules

- Code against the **Protocol**, not the concrete class. Inject implementations.
- Treat these types as **frozen** during parallel (Phase-2) work. If a gap is
  found, amend `contracts.py` on `main` first, then rebase worktrees
  (see `docs/orchestration.md`).
- Keep `contracts.py` dependency-light (pydantic + typing only) so every module
  can import it without cycles.

Per-type detail:
- [`claim.md`](claim.md)
- [`audit_finding.md`](audit_finding.md)
- [`retrieved_chunk.md`](retrieved_chunk.md)
- [`tool_spec.md`](tool_spec.md)
- [`protocols.md`](protocols.md)
- [`trace_event.md`](trace_event.md)
