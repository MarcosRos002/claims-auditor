# Module: rules + MCP (`modules/rules/`)

## Purpose
The deterministic **business-rules engine** for medical-billing audit, plus an
**MCP server** that exposes the rules and code lookups as agent tools. The same
logic is both directly callable (by the agent graph) and agent-callable (via the
harness).

## Status
- **`RulesEngine` implemented (Phase 1).** Pinned by `tests/test_rules_engine.py`.
  Measured on 1000 synthetic claims (50% fault rate): **precision 0.997, recall
  1.000, F1 0.999** on the rule-detectable fault types.
- **MCP layer implemented (Phase 1).** Pinned by `tests/test_rules_mcp.py`. Real
  FastMCP server (`build_server`/`serve`) advertising 4 read-only tools; same tools
  bind into our harness via `as_harness_tools()`. One source of truth: the pure
  handler functions drive specs + harness tools + the MCP server.

## Scope (what rules detect vs. defer)
Detect deterministically from structured codes against `reference.catalog`:
`CPT_ICD_MISMATCH` (HIGH), `UNIT_EXCESS` (MEDIUM), `DUPLICATE_LINE` (MEDIUM).
**Deferred to the LLM classifier:** `UPCODING` and anything needing clinical
context — codes alone can't justify it. Findings carry `category` (a `FaultType`)
so eval matches them to injected ground truth.

## Public interface
- `modules/rules/engine.py:RulesEngine.evaluate(claim) -> list[AuditFinding]` —
  deterministic checks; each finding tagged with `category`, `rule_id`, `severity`,
  `line_index`. Unknown codes yield an INFO finding (never an exception).
- `modules/rules/mcp.py` — pure handlers (`evaluate_rules`, `lookup_icd10`,
  `lookup_cpt`, `check_cpt_icd_compatibility`); `tool_specs()` (advertised
  ToolSpecs); `as_harness_tools()` (bound `Tool`s for our harness);
  `build_server()` (a real FastMCP server); `serve()` (stdio transport).

The reference catalog lives in `reference/catalog.py` (shared with `data/` — one
source of truth so ground truth and detection cannot diverge).

Planned MCP tools: `evaluate_rules(claim)`, `lookup_icd10(code)`,
`lookup_cpt(code)`, `check_cpt_icd_compatibility(cpt, icd10)` — all read-only and
`parallel_safe`.

## Dependencies
- `contracts` at the seam; may share read-only lookups with `rag`'s data.
- Phase-2 **leaf** — buildable in its own worktree.

## How to test in isolation
- Feed synthetic claims with **known** injected faults (from `data`) and assert
  the right `AuditFinding`s fire with correct `rule_id` and `severity`.
- Assert clean claims produce no findings.
- Test the MCP layer by calling each tool directly and validating its
  `ToolSpec.input_schema` round-trips.

## Senior concerns
- **Failure modes:** unknown codes (return a finding, not an exception); rule
  false-positives (precision matters); MCP transport errors surfaced as tool
  errors, not crashes.
- **Determinism:** rules are the high-precision backbone; the LLM classifier
  covers what rules can't express. Keep them pure and well-tested.
- **Metrics:** rules fired, lookups performed, per-tool latency.
