"""Tests for the rules MCP layer (Phase 1 leaf).

Exposes the rules engine + catalog lookups as read-only tools that (a) plug into
our own harness and (b) are served over a real MCP server. The tool logic is pure
and fully tested offline; the stdio transport (`serve`) is not unit-tested.
"""

from __future__ import annotations

from claims_auditor.contracts import FaultType
from claims_auditor.core.harness.runtime import Harness
from claims_auditor.data.synthetic import generate_claim
from claims_auditor.modules.rules import mcp


class _DummyModel:
    async def step(self, goal, observations):  # pragma: no cover - not used here
        from claims_auditor.core.harness.runtime import ModelDecision

        return ModelDecision(final_text="noop")

    async def complete(self, prompt):  # pragma: no cover
        return "{}"


# --------------------------------------------------------------------------- #
# pure tool handlers
# --------------------------------------------------------------------------- #
def test_lookup_icd10_known_and_unknown() -> None:
    assert mcp.lookup_icd10("E11.9")["found"] is True
    assert "diabetes" in mcp.lookup_icd10("E11.9")["description"].lower()
    assert mcp.lookup_icd10("ZZZ.9")["found"] is False


def test_lookup_cpt_returns_details() -> None:
    out = mcp.lookup_cpt("80053")
    assert out["found"] is True
    assert out["max_units"] == 3
    assert "E11.9" in out["supports"]
    assert mcp.lookup_cpt("00000")["found"] is False


def test_check_cpt_icd_compatibility() -> None:
    assert mcp.check_cpt_icd_compatibility("99213", "E11.9")["compatible"] is True
    assert mcp.check_cpt_icd_compatibility("99213", "J18.9")["compatible"] is False
    assert mcp.check_cpt_icd_compatibility("00000", "E11.9")["known_cpt"] is False


def test_evaluate_rules_tool_matches_engine() -> None:
    lc = generate_claim(seed=10, inject_inconsistency=True, fault_type=FaultType.CPT_ICD_MISMATCH)
    findings = mcp.evaluate_rules(lc.claim.model_dump())
    assert any(f["category"] == FaultType.CPT_ICD_MISMATCH.value for f in findings)


# --------------------------------------------------------------------------- #
# advertised specs + harness integration
# --------------------------------------------------------------------------- #
def test_tool_specs_advertises_four_readonly_tools() -> None:
    specs = mcp.tool_specs()
    names = {s.name for s in specs}
    assert names == {"evaluate_rules", "lookup_icd10", "lookup_cpt", "check_cpt_icd_compatibility"}
    for s in specs:
        assert s.parallel_safe is True  # read-only => safe to run concurrently
        assert s.input_schema.get("type") == "object"
        assert "required" in s.input_schema


async def test_mcp_tools_plug_into_the_harness() -> None:
    # The MCP tools must be dispatchable by our own harness (closes the loop).
    h = Harness(model=_DummyModel(), tools=mcp.as_harness_tools())
    results = await h.dispatch_parallel([{"name": "lookup_cpt", "arguments": {"code": "93000"}}])
    assert results[0]["ok"] is True
    assert "Electrocardiogram" in results[0]["result"]["description"]


# --------------------------------------------------------------------------- #
# real MCP server wiring
# --------------------------------------------------------------------------- #
async def test_build_server_registers_all_tools() -> None:
    server = mcp.build_server()
    tools = await server.list_tools()
    names = {t.name for t in tools}
    assert names == {"evaluate_rules", "lookup_icd10", "lookup_cpt", "check_cpt_icd_compatibility"}
    for t in tools:
        assert t.inputSchema["type"] == "object"
