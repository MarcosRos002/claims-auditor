# Module: harness (`core/harness/`)

## Purpose
The agentic runtime — the headline component. Everything else plugs into it. It
drives the agent loop, dispatches tools (including the rules MCP server), manages
context, validates structured output, handles retries and error recovery,
streams output, and supports barge-in for the voice path. It is **model-agnostic**;
the model for any given call is chosen by `routing/`.

## Status: implemented (Phase 1)
Core runtime built and pinned by `tests/test_harness.py` (10 tests). Voice
streaming / barge-in remain Phase-4 upper-layer hooks.

## Public interface
`core/harness/runtime.py`:
- `Harness(*, model, tools=None, max_turns=8, max_retries=2, backoff_base_s=0.05, sleep=None)`
  — **everything is injected** (model client + tools), so the harness runs fully
  offline. Cost routing / guardrails arrive as a routing-aware `model`.
- `run(goal, *, session_id=None) -> AsyncIterator[TraceEvent]` — bounded agent
  loop; emits a `TraceEvent` per step; on `max_turns` exhaustion emits a single
  degraded `final` event instead of spinning forever.
- `dispatch_parallel(calls) -> list[dict]` — run `ToolSpec.parallel_safe` calls
  concurrently; serialize the rest; results keep call order. Each call is
  `{"name", "arguments"}`; each result is `{"name", "ok", "result"|"error"}`.
- `extract(prompt, schema) -> schema` — structured-output discipline: validate the
  model reply against a pydantic schema, re-prompt once, else raise `ValueError`.
- `Tool` = `ToolSpec` + a (sync or async) `handler`. `ModelClient` Protocol =
  `step(goal, observations) -> ModelDecision` + `complete(prompt) -> str`.
  `ModelDecision` = `{tool_calls: [...], final_text: str | None}`.

Consumes: `ToolSpec`, emits `TraceEvent` (both in `contracts.py`). Retries set
`metadata.attempts`; failures emit `status=ERROR` with an `ErrorInfo`.

## Dependencies
- `contracts` only (plus the Claude Agent SDK / anthropic at implementation time).
- Foundational — **blocks** `agent/` and the upper layers. Built in Phase 1.
- Cost routing and guardrails are **injected**, not imported, to keep the harness
  decoupled.

## How to test in isolation
- Register a couple of fake `ToolSpec`s backed by in-process functions (one
  parallel-safe, one not) and assert the loop dispatches, observes, and
  terminates.
- Assert `dispatch_parallel` actually parallelizes safe tools and serializes
  unsafe ones (e.g. via timing or a shared counter).
- Assert structured-output validation re-prompts on an invalid model reply
  (mock the model to return bad JSON once, then valid).
- No DB, no network — mock the model client.

## Senior concerns
- **Failure modes:** infinite loops (bound iterations / task budget); runaway
  cost (cap via routing + max turns); tool deadlock; partial streaming on
  disconnect; barge-in races in the voice path.
- **Structured-output discipline:** every model reply round-trips through a
  pydantic contract; invalid output is a bounded re-prompt, never a crash.
- **Refusals & transient errors:** check `stop_reason` before reading content;
  retry 429/5xx with backoff; degrade the turn instead of failing it.
- **Metrics to emit:** per-span latency, model used, token usage, cost, retry
  count, tool-call count — all into `TraceEvent.attributes` for agent-lens.
