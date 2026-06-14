"""Agentic harness runtime — the headline component of Veritas.

The harness is the agent runtime that everything else plugs into. It owns:
  - the agent loop (plan -> dispatch tools -> observe -> repeat)
  - parallel tool dispatch (respecting ``ToolSpec.parallel_safe``)
  - context management (windowing, compaction hooks)
  - retries with exponential backoff
  - structured-output validation (pydantic round-trip on every model reply)
  - a state machine for turn lifecycle
  - streaming + barge-in (for the voice path)
  - error recovery (degrade gracefully, never crash the turn)

Phase 0: signatures + docstrings only. See ``docs/modules/harness.md`` and
``docs/architecture.md`` (Agentic Harness Design).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from claims_auditor.contracts import ToolSpec, TraceEvent


class Harness:
    """The agentic runtime. Model-agnostic; cost routing is injected (see routing/)."""

    def __init__(self, tools: list[ToolSpec] | None = None) -> None:
        self._tools = tools or []
        raise NotImplementedError("Phase 0 stub — see docs/modules/harness.md")

    async def run(self, goal: str) -> AsyncIterator[TraceEvent]:
        """Drive the agent loop to completion, streaming TraceEvents as it goes."""
        raise NotImplementedError

    async def dispatch_parallel(self, calls: list[dict]) -> list[dict]:
        """Run parallel-safe tool calls concurrently; serialize unsafe ones."""
        raise NotImplementedError
