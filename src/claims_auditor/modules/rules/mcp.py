"""MCP server exposing the rules engine + code lookups as agent tools.

Model Context Protocol (MCP) is the open standard for advertising tools/resources
to any LLM agent ("USB-C for AI tools"). This module exposes four **read-only**
tools over the rules engine and the shared catalog:

- ``evaluate_rules(claim)`` — run the deterministic audit, return findings.
- ``lookup_icd10(code)`` / ``lookup_cpt(code)`` — code descriptions/metadata.
- ``check_cpt_icd_compatibility(cpt, icd10)`` — does a diagnosis justify a procedure?

Single source of truth: the pure handler functions below drive THREE consumers —
``tool_specs()`` (for our own harness contract), ``as_harness_tools()`` (bound
``Tool``s the harness dispatches), and ``build_server()`` (a real FastMCP server).
All tools are ``parallel_safe`` (read-only), so the harness may run them
concurrently. See ``docs/modules/rules-mcp.md``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from claims_auditor.contracts import Claim, ToolSpec
from claims_auditor.core.harness.runtime import Tool
from claims_auditor.modules.rules.engine import RulesEngine
from claims_auditor.reference.catalog import CPT, ICD10, is_known_cpt, supports

_ENGINE = RulesEngine()

_STR_PROP = {"type": "string"}


# --------------------------------------------------------------------------- #
# Pure tool handlers (the single source of truth)
# --------------------------------------------------------------------------- #
def lookup_icd10(code: str) -> dict[str, Any]:
    """Look up an ICD-10 diagnosis code description."""
    desc = ICD10.get(code)
    if desc is None:
        return {"code": code, "found": False}
    return {"code": code, "found": True, "description": desc}


def lookup_cpt(code: str) -> dict[str, Any]:
    """Look up a CPT procedure code: description, max units, supported diagnoses."""
    info = CPT.get(code)
    if info is None:
        return {"code": code, "found": False}
    return {
        "code": code,
        "found": True,
        "description": info.desc,
        "max_units": info.max_units,
        "supports": sorted(info.supports),
    }


def check_cpt_icd_compatibility(cpt: str, icd10: str) -> dict[str, Any]:
    """Check whether diagnosis ``icd10`` justifies procedure ``cpt``."""
    if not is_known_cpt(cpt):
        return {"cpt": cpt, "icd10": icd10, "known_cpt": False, "compatible": False}
    return {"cpt": cpt, "icd10": icd10, "known_cpt": True, "compatible": supports(cpt, icd10)}


def evaluate_rules(claim: dict[str, Any]) -> list[dict[str, Any]]:
    """Run the deterministic rules engine over a claim; return findings as dicts."""
    parsed = Claim.model_validate(claim)
    return [f.model_dump(mode="json") for f in _ENGINE.evaluate(parsed)]


# --------------------------------------------------------------------------- #
# Tool registry — derives specs, harness tools, and the MCP server
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _ToolDef:
    name: str
    fn: Callable[..., Any]
    input_schema: dict[str, Any]

    @property
    def description(self) -> str:
        return (self.fn.__doc__ or "").strip().splitlines()[0]


_TOOL_DEFS: list[_ToolDef] = [
    _ToolDef(
        "evaluate_rules",
        evaluate_rules,
        {"type": "object", "properties": {"claim": {"type": "object"}}, "required": ["claim"]},
    ),
    _ToolDef(
        "lookup_icd10",
        lookup_icd10,
        {"type": "object", "properties": {"code": _STR_PROP}, "required": ["code"]},
    ),
    _ToolDef(
        "lookup_cpt",
        lookup_cpt,
        {"type": "object", "properties": {"code": _STR_PROP}, "required": ["code"]},
    ),
    _ToolDef(
        "check_cpt_icd_compatibility",
        check_cpt_icd_compatibility,
        {
            "type": "object",
            "properties": {"cpt": _STR_PROP, "icd10": _STR_PROP},
            "required": ["cpt", "icd10"],
        },
    ),
]


def tool_specs() -> list[ToolSpec]:
    """The ToolSpecs this server advertises (all read-only => parallel_safe)."""
    return [
        ToolSpec(
            name=d.name,
            description=d.description,
            input_schema=d.input_schema,
            parallel_safe=True,
        )
        for d in _TOOL_DEFS
    ]


def as_harness_tools() -> list[Tool]:
    """Bind each tool to a handler the harness can dispatch (`handler(args) -> ...`)."""
    specs = {s.name: s for s in tool_specs()}
    return [Tool(spec=specs[d.name], handler=lambda args, fn=d.fn: fn(**args)) for d in _TOOL_DEFS]


def build_server(name: str = "veritas-rules"):
    """Build a real FastMCP server with all tools registered (schemas auto-derived)."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP(name)
    for d in _TOOL_DEFS:
        server.add_tool(d.fn, name=d.name, description=d.description)
    return server


def serve() -> None:  # pragma: no cover - stdio transport, not unit-tested
    """Start the MCP server over stdio (the default MCP transport)."""
    build_server().run()
