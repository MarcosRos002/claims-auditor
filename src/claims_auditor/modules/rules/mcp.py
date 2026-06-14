"""MCP server exposing the rules engine + code lookups as agent tools.

Tools (planned): ``evaluate_rules(claim)``, ``lookup_icd10(code)``,
``lookup_cpt(code)``, ``check_cpt_icd_compatibility(cpt, icd10)``. The agent
calls these through the harness; they are read-only and parallel-safe.

Phase 0: stub. See ``docs/modules/rules-mcp.md``.
"""

from __future__ import annotations

from claims_auditor.contracts import ToolSpec


def tool_specs() -> list[ToolSpec]:
    """Return the ToolSpecs this MCP server advertises."""
    raise NotImplementedError("Phase 0 stub — see docs/modules/rules-mcp.md")


def serve() -> None:
    """Start the MCP server (stdio/HTTP transport TBD in implementation phase)."""
    raise NotImplementedError
