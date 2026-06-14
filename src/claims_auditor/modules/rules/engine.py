"""Business-rules engine for medical-billing audit.

Deterministic checks over a ``Claim`` (e.g. CPT/ICD-10 compatibility, units
sanity, frequency limits). Produces ``AuditFinding`` objects. The same rules and
code lookups are exposed to the agent as tools via an MCP server (see mcp.py).

Phase 0: stub. See ``docs/modules/rules-mcp.md``.
"""

from __future__ import annotations

from claims_auditor.contracts import AuditFinding, Claim


class RulesEngine:
    """Evaluates a claim against business rules and returns findings."""

    def evaluate(self, claim: Claim) -> list[AuditFinding]:
        raise NotImplementedError("Phase 0 stub — see docs/modules/rules-mcp.md")
