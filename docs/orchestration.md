# Orchestration — building Veritas in the right order (and in parallel)

This is the build plan. It defines what must be done before what, and which
modules can be built concurrently in separate `git worktree`s by separate Claude
Code agents.

## Dependency graph

```
                 ┌──────────────────────────────────────────────┐
   FOUNDATIONAL  │  contracts  →  data (synthetic gen)  →  core/harness  │   (BLOCKS everything)
                 └──────────────────────┬───────────────────────┘
                                        │
        ┌───────────────┬───────────────┼───────────────┬───────────────┐
        ▼               ▼               ▼               ▼               (PARALLEL worktrees)
   modules/asr     modules/rag    modules/rules    modules/classification
                                  (+ MCP server)
        └───────────────┴───────────────┼───────────────┴───────────────┘
                                        ▼
                                INTEGRATION
                                  agent/  (LangGraph graph wiring the modules)
                                        │
            ┌───────────────────────────┼───────────────────────────┐
            ▼                           ▼                           ▼      (UPPER LAYERS)
      voice (api WS + barge-in)   routing (cost) + guardrails   agent-lens integration
                                                                (emit TraceEvents)
                                        │
                                        ▼
                                   DEPLOY
                       FastAPI + Docker + CI eval-gates
```

### Why this order

- **Contracts first.** Every module codes against `contracts.py` Protocols, so
  the contracts must be settled before parallel work begins. This is the whole
  point of contract-first: stable seams enable independent, concurrent builds.
- **Data + harness are foundational.** The synthetic generator gives every other
  module test fixtures with ground truth; the harness is the runtime the agent
  and tools plug into. Both block downstream work.
- **Four parallel leaves.** `asr`, `rag`, `rules(+mcp)`, and `classification`
  share no state and depend only on the foundation → ideal for parallel worktrees.
- **Agent integrates.** The LangGraph graph can only be wired once the leaves
  expose their contracts.
- **Upper layers** (voice, cost-routing, guardrails, agent-lens integration)
  build on the integrated agent.
- **Deploy last.** Container + CI eval-gates wrap the working system.

## Phases

| Phase | Modules | Parallelizable? | Gate to exit |
|---|---|---|---|
| 0 | (this scaffold) | — | Imports clean, smoke tests green, docs in place |
| 1 Foundational | `contracts`, `data`, `core/harness` | Sequential-ish | Contracts frozen; generator yields labeled claims; harness loop runs a trivial tool |
| 2 Leaves | `asr`, `rag`, `rules+mcp`, `classification` | **Yes — 4 worktrees** | Each satisfies its Protocol + has isolation tests |
| 3 Integration | `agent` | No | Graph runs end-to-end on synthetic input |
| 4 Upper | `api` (voice), `routing`, `guardrails`, agent-lens emit | Partially | Voice Q&A works; cost routed; guardrails enforced; TraceEvents emitted |
| 5 Deploy | Dockerfile, CI eval-gates | No | CI runs agent-lens eval and gates merges |

## Building the parallel modules with `git worktree`

The Phase-2 leaves are independent. Use one worktree (and one Claude Code agent)
per module so they progress concurrently without stepping on each other:

```bash
# from the main checkout, after Phase 1 has landed on `main`
git worktree add ../ca-asr             -b feat/asr
git worktree add ../ca-rag             -b feat/rag
git worktree add ../ca-rules-mcp       -b feat/rules-mcp
git worktree add ../ca-classification  -b feat/classification
```

Then, in each worktree, point a Claude Code session at the matching
`docs/modules/<module>.md` spec and the contracts it must satisfy. Rules:

- Each worktree touches **only its own** `src/claims_auditor/...` subtree + its
  tests. Shared edits to `contracts.py` are off-limits in Phase 2 (the contract
  is frozen) — if a contract gap is found, stop and amend it on `main` first,
  then rebase the worktrees.
- Each module ships isolation tests using the synthetic generator (no
  cross-module imports beyond contracts).
- Merge order doesn't matter (the leaves are independent); merge each to `main`
  behind passing tests, then start Phase 3 (`agent`) once all four are in.

Clean up when done:

```bash
git worktree remove ../ca-asr   # etc.
```

See `docs/modules/*.md` for each module's contract, dependencies, isolation-test
strategy, and senior concerns.
