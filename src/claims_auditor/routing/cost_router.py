"""Cost routing: pick the cheapest model that can handle a query's complexity.

Routes between Claude Haiku (``claude-haiku-4-5``) and Claude Sonnet
(``claude-sonnet-4-6``) by estimated complexity, with optional escalation to a
stronger model for hard cases. Keeps cost-per-claim low while protecting quality.

Phase 0: stub. See ``docs/modules/routing.md``.
"""

from __future__ import annotations

from enum import Enum


class Complexity(str, Enum):
    SIMPLE = "simple"
    MODERATE = "moderate"
    HARD = "hard"


def route(complexity: Complexity) -> str:
    """Return the model id to use for a given complexity tier."""
    raise NotImplementedError("Phase 0 stub — see docs/modules/routing.md")
