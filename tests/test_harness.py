"""Tests for the agentic harness runtime (foundational Phase 1 layer).

The harness is the headline component: agent loop, parallel-safe tool dispatch,
retries/backoff, structured-output validation, and TraceEvent emission. It is
fully testable offline — the model client and tools are injected.
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from claims_auditor.contracts import StepKind, ToolSpec
from claims_auditor.core.harness.runtime import (
    Harness,
    ModelDecision,
    Tool,
)


async def _no_sleep(_seconds: float) -> None:
    return None


class ScriptedModel:
    """A fake ModelClient that replays a scripted list of decisions, then a final.

    Also supports ``complete`` for structured-extraction tests.
    """

    def __init__(
        self,
        decisions: list[ModelDecision] | None = None,
        completions: list[str] | None = None,
    ) -> None:
        self._decisions = list(decisions or [])
        self._completions = list(completions or [])
        self.step_calls = 0
        self.complete_calls = 0

    async def step(self, goal: str, observations: list[dict]) -> ModelDecision:
        self.step_calls += 1
        if self._decisions:
            return self._decisions.pop(0)
        return ModelDecision(final_text="done")

    async def complete(self, prompt: str) -> str:
        self.complete_calls += 1
        return self._completions.pop(0)


def _tool(name: str, handler, *, parallel_safe: bool) -> Tool:
    return Tool(
        spec=ToolSpec(name=name, description=name, parallel_safe=parallel_safe), handler=handler
    )


def _harness(tools=None, model=None, **kw) -> Harness:
    return Harness(model=model or ScriptedModel(), tools=tools or [], sleep=_no_sleep, **kw)


# --------------------------------------------------------------------------- #
# dispatch_parallel
# --------------------------------------------------------------------------- #
async def test_parallel_safe_tools_run_concurrently() -> None:
    # waiter blocks on an event that setter must set — only possible if they run
    # concurrently. If they were serialized (waiter first), waiter would time out.
    ev = asyncio.Event()

    async def waiter(_args):
        await asyncio.wait_for(ev.wait(), timeout=1.0)
        return "waited"

    async def setter(_args):
        ev.set()
        return "set"

    h = _harness(
        [_tool("waiter", waiter, parallel_safe=True), _tool("setter", setter, parallel_safe=True)]
    )
    results = await h.dispatch_parallel(
        [{"name": "waiter", "arguments": {}}, {"name": "setter", "arguments": {}}]
    )
    assert {r["name"] for r in results} == {"waiter", "setter"}
    assert all(r["ok"] for r in results)


async def test_non_parallel_safe_tools_run_serially_in_order() -> None:
    order: list[str] = []

    async def a(_args):
        order.append("a")
        return "a"

    async def b(_args):
        order.append("b")
        return "b"

    h = _harness([_tool("a", a, parallel_safe=False), _tool("b", b, parallel_safe=False)])
    results = await h.dispatch_parallel(
        [{"name": "a", "arguments": {}}, {"name": "b", "arguments": {}}]
    )
    assert order == ["a", "b"]
    assert [r["name"] for r in results] == ["a", "b"]  # results keep call order


async def test_results_preserve_call_order_with_mixed_safety() -> None:
    async def echo(args):
        return args["v"]

    tools = [_tool("safe", echo, parallel_safe=True), _tool("unsafe", echo, parallel_safe=False)]
    h = _harness(tools)
    calls = [
        {"name": "unsafe", "arguments": {"v": 1}},
        {"name": "safe", "arguments": {"v": 2}},
        {"name": "unsafe", "arguments": {"v": 3}},
    ]
    results = await h.dispatch_parallel(calls)
    assert [r["result"] for r in results] == [1, 2, 3]


# --------------------------------------------------------------------------- #
# retries / error recovery
# --------------------------------------------------------------------------- #
async def test_flaky_tool_is_retried_then_succeeds() -> None:
    attempts = {"n": 0}

    async def flaky(_args):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("transient")
        return "ok"

    h = _harness([_tool("flaky", flaky, parallel_safe=True)], max_retries=2)
    results = await h.dispatch_parallel([{"name": "flaky", "arguments": {}}])
    assert results[0]["ok"] is True
    assert results[0]["result"] == "ok"
    assert attempts["n"] == 3  # 1 initial + 2 retries


async def test_failing_tool_degrades_gracefully_without_crashing() -> None:
    async def boom(_args):
        raise ValueError("nope")

    h = _harness([_tool("boom", boom, parallel_safe=True)], max_retries=1)
    results = await h.dispatch_parallel([{"name": "boom", "arguments": {}}])
    assert results[0]["ok"] is False
    assert "nope" in results[0]["error"]


async def test_unknown_tool_is_reported_not_raised() -> None:
    h = _harness([])
    results = await h.dispatch_parallel([{"name": "ghost", "arguments": {}}])
    assert results[0]["ok"] is False


# --------------------------------------------------------------------------- #
# run loop
# --------------------------------------------------------------------------- #
async def test_run_emits_trace_events_and_terminates_on_final() -> None:
    async def lookup(_args):
        return "evidence"

    model = ScriptedModel(
        decisions=[
            ModelDecision(tool_calls=[{"name": "lookup", "arguments": {}}]),
            ModelDecision(final_text="final answer"),
        ]
    )
    h = _harness([_tool("lookup", lookup, parallel_safe=True)], model=model)

    events = [ev async for ev in h.run("audit claim", session_id="sess-1")]

    kinds = [(ev.kind, ev.name) for ev in events]
    assert (StepKind.TOOL, "lookup") in kinds
    assert any(ev.kind is StepKind.LLM and ev.metadata.get("final") for ev in events)
    # All events share the session and form a parent/child chain (root has no parent).
    assert {ev.session_id for ev in events} == {"sess-1"}
    assert events[0].parent_step_id is None


async def test_run_is_bounded_and_degrades_when_max_turns_exhausted() -> None:
    # A model that never finishes must not loop forever.
    looping = ScriptedModel(
        decisions=[ModelDecision(tool_calls=[{"name": "noop", "arguments": {}}])] * 100
    )

    async def noop(_args):
        return None

    h = _harness([_tool("noop", noop, parallel_safe=True)], model=looping, max_turns=3)
    events = [ev async for ev in h.run("never ends")]

    final = [ev for ev in events if ev.metadata.get("final")]
    assert len(final) == 1
    assert final[0].metadata.get("degraded") is True
    assert looping.step_calls <= 3


# --------------------------------------------------------------------------- #
# structured-output validation
# --------------------------------------------------------------------------- #
class _Extracted(BaseModel):
    claim_id: str
    amount: int


async def test_extract_reprompts_once_on_invalid_structured_output() -> None:
    model = ScriptedModel(
        completions=[
            "{not valid json",  # first reply: invalid -> must re-prompt
            '{"claim_id": "C1", "amount": 100}',  # second reply: valid
        ]
    )
    h = _harness(model=model)
    out = await h.extract("extract the claim", _Extracted)
    assert out == _Extracted(claim_id="C1", amount=100)
    assert model.complete_calls == 2  # re-prompted exactly once


async def test_extract_raises_after_exhausting_reprompts() -> None:
    model = ScriptedModel(completions=["garbage", "still garbage"])
    h = _harness(model=model)
    with pytest.raises(ValueError):
        await h.extract("extract", _Extracted)
