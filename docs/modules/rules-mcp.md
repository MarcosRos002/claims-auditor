# Module: rules + MCP (`modules/rules/`)

## Purpose
The deterministic **business-rules engine** for medical-billing audit, plus an
**MCP server** that exposes the rules and code lookups as agent tools. The same
logic is both directly callable (by the agent graph) and agent-callable (via the
harness).

## Public interface
- `modules/rules/engine.py:RulesEngine.evaluate(claim) -> list[AuditFinding]` —
  deterministic checks (CPT/ICD-10 compatibility, units sanity, frequency limits, …).
- `modules/rules/mcp.py:tool_specs() -> list[ToolSpec]` — advertised tools.
- `modules/rules/mcp.py:serve()` — start the MCP server.

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
