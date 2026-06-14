# Module: routing (`routing/`)

## Purpose
Cost routing: pick the cheapest model that can handle a query's complexity, so
cost-per-claim stays low without sacrificing quality on hard cases. A first-class
concern because cost-per-claim is a headline metric.

## Public interface
`routing/cost_router.py`:
- `Complexity` enum: `SIMPLE | MODERATE | HARD`.
- `route(complexity) -> str` — returns the model id (e.g. `claude-haiku-4-5` for
  simple, `claude-sonnet-4-6` for harder work).

Injected into the harness and the classifier rather than imported by them.

## Dependencies
- None beyond the stdlib at the seam. **Upper layer** (Phase 4).

## How to test in isolation
- Pure function: assert each `Complexity` maps to the intended model id.
- Test the complexity *estimator* (when added) against labeled examples.

## Senior concerns
- **Failure modes:** mis-estimating complexity (too cheap → quality drop; too
  expensive → cost blow-out). Make the policy explicit and measurable.
- **Observability:** every routing decision belongs in `TraceEvent.attributes` so
  agent-lens can correlate model choice with cost and accuracy.
- **Model IDs:** keep them in sync with the current Claude line
  (`claude-haiku-4-5`, `claude-sonnet-4-6`); see `CLAUDE.md`.
