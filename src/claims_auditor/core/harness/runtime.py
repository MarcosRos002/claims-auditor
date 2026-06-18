"""Agentic harness runtime — the headline component of Veritas.

The harness is the agent runtime that everything else plugs into. It owns:
  - the agent loop (plan -> dispatch tools -> observe -> repeat), bounded by
    ``max_turns`` so it can never spin forever
  - parallel tool dispatch (respecting ``ToolSpec.parallel_safe``): read-only
    tools run concurrently, unsafe ones serialize
  - retries with exponential backoff, and graceful degradation (a failing tool
    yields an error result, it never crashes the turn)
  - structured-output validation: ``extract`` round-trips a model reply through a
    pydantic contract and re-prompts once on invalid output
  - TraceEvent emission for every step (the wire-format agent-lens consumes)

It is **model-agnostic**: the model client and the tools are injected, so the
harness runs fully offline in tests. Cost routing / guardrails are injected too
(a routing-aware model client), keeping the harness decoupled. See
``docs/modules/harness.md`` and ``docs/architecture.md`` (Agentic Harness Design).
"""

from __future__ import annotations

import inspect
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from claims_auditor.contracts import ErrorInfo, StepKind, StepStatus, ToolSpec, TraceEvent

ToolHandler = Callable[[dict[str, Any]], Awaitable[Any]] | Callable[[dict[str, Any]], Any]
SleepFn = Callable[[float], Awaitable[None]]
M = TypeVar("M", bound=BaseModel)

_REPROMPT_SUFFIX = (
    "\n\nYour previous reply was not valid for the required schema. "
    "Reply with ONLY a single valid JSON object and nothing else."
)


@dataclass
class Tool:
    """A dispatchable tool: a ``ToolSpec`` (the description the model sees) bound
    to a ``handler`` (sync or async) that executes it."""

    spec: ToolSpec
    handler: ToolHandler


class ModelDecision(BaseModel):
    """One decision from the model: either request tool calls or finish.

    Each tool call is ``{"name": str, "arguments": dict}``. ``final_text`` set
    (non-None) means the agent is done.
    """

    tool_calls: list[dict[str, Any]] = []
    final_text: str | None = None


class ModelClient(Protocol):
    """The injected model. ``step`` drives the agent loop; ``complete`` returns a
    raw string for structured extraction."""

    async def step(self, goal: str, observations: list[dict[str, Any]]) -> ModelDecision: ...

    async def complete(self, prompt: str) -> str: ...


class Harness:
    """The agentic runtime. Model-agnostic; cost routing is injected (see routing/)."""

    def __init__(
        self,
        *,
        model: ModelClient,
        tools: list[Tool] | None = None,
        max_turns: int = 8,
        max_retries: int = 2,
        backoff_base_s: float = 0.05,
        sleep: SleepFn | None = None,
    ) -> None:
        self._model = model
        self._tools: dict[str, Tool] = {t.spec.name: t for t in (tools or [])}
        self._max_turns = max_turns
        self._max_retries = max_retries
        self._backoff_base_s = backoff_base_s
        # asyncio.sleep by default; injectable so tests don't actually wait.
        if sleep is None:
            import asyncio

            sleep = asyncio.sleep
        self._sleep = sleep

    # ------------------------------------------------------------------ #
    # Agent loop
    # ------------------------------------------------------------------ #
    async def run(self, goal: str, *, session_id: str | None = None) -> AsyncIterator[TraceEvent]:
        """Drive the agent loop to completion, streaming ``TraceEvent``s.

        Bounded by ``max_turns``: if the model never finishes, the loop emits a
        single degraded ``final`` event and stops rather than spinning forever.
        """
        sid = session_id or uuid.uuid4().hex
        observations: list[dict[str, Any]] = []
        parent: str | None = None

        for turn in range(self._max_turns):
            decision = await self._model.step(goal, observations)

            if decision.final_text is not None:
                yield self._event(
                    sid,
                    parent,
                    StepKind.LLM,
                    "model.final",
                    output=decision.final_text,
                    metadata={"turn": turn, "final": True},
                )
                return

            step_ev = self._event(
                sid,
                parent,
                StepKind.LLM,
                "model.step",
                metadata={"turn": turn, "tool_calls": len(decision.tool_calls)},
            )
            parent = step_ev.step_id
            yield step_ev

            results, events = await self._dispatch(decision.tool_calls, sid, parent)
            for ev in events:
                yield ev
            observations.extend(results)

        yield self._event(
            sid,
            parent,
            StepKind.LLM,
            "model.final",
            metadata={"final": True, "degraded": True, "reason": "max_turns_exhausted"},
        )

    # ------------------------------------------------------------------ #
    # Tool dispatch
    # ------------------------------------------------------------------ #
    async def dispatch_parallel(self, calls: list[dict]) -> list[dict]:
        """Run parallel-safe tool calls concurrently; serialize unsafe ones.

        Returns one result dict per call, in call order. Standalone entry point
        (the agent loop uses the internal variant that also yields TraceEvents).
        """
        results, _events = await self._dispatch(calls, uuid.uuid4().hex, None)
        return results

    async def _dispatch(
        self, calls: list[dict], session_id: str, parent: str | None
    ) -> tuple[list[dict], list[TraceEvent]]:
        import asyncio

        results: list[dict | None] = [None] * len(calls)
        events: list[TraceEvent | None] = [None] * len(calls)

        safe_idx = [i for i, c in enumerate(calls) if self._is_parallel_safe(c)]
        unsafe_idx = [i for i, c in enumerate(calls) if not self._is_parallel_safe(c)]

        if safe_idx:
            done = await asyncio.gather(
                *(self._invoke(calls[i], session_id, parent) for i in safe_idx)
            )
            for i, (res, ev) in zip(safe_idx, done, strict=True):
                results[i], events[i] = res, ev

        for i in unsafe_idx:
            res, ev = await self._invoke(calls[i], session_id, parent)
            results[i], events[i] = res, ev

        return [r for r in results if r is not None], [e for e in events if e is not None]

    def _is_parallel_safe(self, call: dict) -> bool:
        tool = self._tools.get(call.get("name", ""))
        return bool(tool and tool.spec.parallel_safe)

    async def _invoke(
        self, call: dict, session_id: str, parent: str | None
    ) -> tuple[dict, TraceEvent]:
        name = call.get("name", "")
        args = call.get("arguments", {})
        tool = self._tools.get(name)
        t0 = perf_counter()

        if tool is None:
            err = ErrorInfo(type="UnknownTool", message=f"no tool named {name!r}", retryable=False)
            ev = self._event(
                session_id,
                parent,
                StepKind.TOOL,
                name,
                tool_name=name,
                status=StepStatus.ERROR,
                error=err,
                latency_ms=self._ms(t0),
            )
            return {"name": name, "ok": False, "error": err.message}, ev

        last_err: Exception | None = None
        for attempt in range(1, self._max_retries + 2):  # 1 initial + max_retries
            try:
                result = tool.handler(args)
                if inspect.isawaitable(result):
                    result = await result
                ev = self._event(
                    session_id,
                    parent,
                    StepKind.TOOL,
                    name,
                    tool_name=name,
                    inputs={"arguments": args},
                    output=result,
                    latency_ms=self._ms(t0),
                    metadata={"attempts": attempt},
                )
                return {"name": name, "ok": True, "result": result}, ev
            except Exception as exc:  # noqa: BLE001 — degrade, never crash the turn
                last_err = exc
                if attempt <= self._max_retries:
                    await self._sleep(self._backoff_base_s * 2 ** (attempt - 1))

        err = ErrorInfo(type=type(last_err).__name__, message=str(last_err), retryable=True)
        ev = self._event(
            session_id,
            parent,
            StepKind.TOOL,
            name,
            tool_name=name,
            inputs={"arguments": args},
            status=StepStatus.ERROR,
            error=err,
            latency_ms=self._ms(t0),
            metadata={"attempts": self._max_retries + 1},
        )
        return {"name": name, "ok": False, "error": str(last_err)}, ev

    # ------------------------------------------------------------------ #
    # Structured-output discipline
    # ------------------------------------------------------------------ #
    async def extract(self, prompt: str, schema: type[M]) -> M:
        """Ask the model for ``schema``, validating the reply; re-prompt once on
        invalid output. Raises ``ValueError`` if still invalid after the retry."""
        last_err: Exception | None = None
        for attempt in range(2):  # initial + one re-prompt
            text = await self._model.complete(prompt if attempt == 0 else prompt + _REPROMPT_SUFFIX)
            try:
                return schema.model_validate_json(text)
            except ValidationError as exc:
                last_err = exc
        raise ValueError(f"structured output invalid after re-prompt: {last_err}")

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _ms(t0: float) -> float:
        return (perf_counter() - t0) * 1000.0

    @staticmethod
    def _event(
        session_id: str,
        parent: str | None,
        kind: StepKind,
        name: str,
        **fields: Any,
    ) -> TraceEvent:
        return TraceEvent(
            session_id=session_id,
            step_id=uuid.uuid4().hex,
            parent_step_id=parent,
            kind=kind,
            name=name,
            start_time=datetime.now(UTC),
            **fields,
        )
