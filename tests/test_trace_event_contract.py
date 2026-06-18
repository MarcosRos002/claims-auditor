"""Cross-repo contract test: Veritas emits the *canonical* agent-lens TraceEvent.

The single source of truth for the trace wire-format is agent-lens. Veritas must
NOT keep a divergent local mirror — it re-exports the canonical schema so drift
is structurally impossible. These tests pin that invariant.
"""

from __future__ import annotations

from datetime import UTC, datetime

import agent_lens.schema as canonical
import pytest

from claims_auditor import contracts


def test_trace_event_is_the_canonical_agent_lens_class() -> None:
    # Identity, not merely structural equality: importing TraceEvent from Veritas
    # must yield the exact class agent-lens defines.
    assert contracts.TraceEvent is canonical.TraceEvent


def test_contracts_reexports_canonical_trace_enums() -> None:
    # Module code builds events with these; they must be the canonical ones.
    assert contracts.StepKind is canonical.StepKind
    assert contracts.StepStatus is canonical.StepStatus


def test_audit_tool_step_builds_a_valid_trace_event() -> None:
    # A representative step the harness emits: a rules-engine tool dispatch.
    ev = contracts.TraceEvent(
        session_id="audit-001",
        step_id="step-1",
        kind=contracts.StepKind.TOOL,
        name="rules_engine.check",
        tool_name="rules_engine.check",
        start_time=datetime.now(UTC),
    )
    assert ev.session_id == "audit-001"
    assert ev.kind is canonical.StepKind.TOOL
    # Round-trips through the canonical wire format.
    assert canonical.TraceEvent.model_validate(ev.model_dump()) == ev


def test_canonical_error_validator_is_enforced_through_veritas() -> None:
    # Proves we got the canonical class *with its validators*, not a lookalike:
    # status=error without an error payload must be rejected.
    with pytest.raises(ValueError):
        contracts.TraceEvent(
            session_id="audit-001",
            step_id="step-2",
            kind=contracts.StepKind.LLM,
            name="haiku.classify",
            start_time=datetime.now(UTC),
            status=contracts.StepStatus.ERROR,  # missing required `error`
        )
