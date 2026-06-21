"""Cost routing: pick the cheapest model that can handle a query's complexity.

Routes between Claude Haiku (``claude-haiku-4-5``) and Claude Sonnet
(``claude-sonnet-4-6``) by estimated complexity, with escalation to the stronger
model for hard cases. Keeps cost-per-claim low while protecting quality. The
routing decision belongs in ``TraceEvent.metadata`` so agent-lens can correlate
model choice with cost and accuracy. See ``docs/modules/routing.md``.
"""

from __future__ import annotations

from enum import Enum

# Current Claude line — keep in sync with CLAUDE.md.
HAIKU = "claude-haiku-4-5"
SONNET = "claude-sonnet-4-6"


class Complexity(str, Enum):
    SIMPLE = "simple"
    MODERATE = "moderate"
    HARD = "hard"


_ROUTE: dict[Complexity, str] = {
    Complexity.SIMPLE: HAIKU,
    Complexity.MODERATE: HAIKU,
    Complexity.HARD: SONNET,
}


def route(complexity: Complexity) -> str:
    """Return the model id to use for a given complexity tier."""
    return _ROUTE[complexity]
