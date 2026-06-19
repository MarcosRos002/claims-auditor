"""Audit orchestrator — the integration layer that wires the pipeline together.

Composition only (no domain logic of its own): run the deterministic rules engine
and the LLM classifier over a claim, **merge/dedupe** their findings, and produce
an ``AuditReport`` plus a per-stage agent-lens ``Trace``. A node that fails
**degrades** (its findings are dropped, an error step is recorded) rather than
aborting the whole audit.

Why a typed pipeline and not LangGraph (yet): the node boundaries here are linear
and deterministic, so a plain typed pipeline is simpler and fully testable.
LangGraph earns its place once we need conditional routing (audio-vs-text branch),
checkpointing, or human-in-the-loop — see ``docs/modules/agent.md``.

Dependencies are injected through their contracts (``RulesEngine``, the
``Classifier`` Protocol, and an optional ``Retriever``) — never concretes. See
``docs/modules/agent.md`` and ``docs/orchestration.md``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from claims_auditor.contracts import (
    AuditFinding,
    AuditReport,
    Claim,
    Classifier,
    ErrorInfo,
    RetrievedChunk,
    Retriever,
    StepKind,
    StepStatus,
    Trace,
    TraceEvent,
)
from claims_auditor.modules.rules.engine import RulesEngine


class AuditOrchestrator:
    """Runs the end-to-end audit for a claim. Integration layer (Capa 1 MVP)."""

    def __init__(
        self,
        rules_engine: RulesEngine,
        classifier: Classifier,
        *,
        retriever: Retriever | None = None,
    ) -> None:
        self._rules = rules_engine
        self._classifier = classifier
        self._retriever = retriever

    # ------------------------------------------------------------------ #
    def audit(self, claim: Claim) -> AuditReport:
        """Audit a claim and return the report (drops the trace)."""
        return self.audit_with_trace(claim)[0]

    def audit_with_trace(self, claim: Claim) -> tuple[AuditReport, Trace]:
        """Audit a claim, returning the report and the agent-lens trace."""
        sid = uuid.uuid4().hex
        events: list[TraceEvent] = []

        context = self._retrieve(claim, sid, events)
        rules_findings = self._run_rules(claim, sid, events)
        clf_findings = self._run_classifier(claim, context, sid, events)

        findings = _merge(rules_findings, clf_findings)
        report = AuditReport(
            claim_id=claim.claim_id,
            flagged=bool(findings),
            findings=findings,
            summary=_summarize(findings),
        )
        return report, Trace(session_id=sid, events=events)

    # -- stages (each emits exactly one TraceEvent, degrading on failure) -- #
    def _retrieve(self, claim: Claim, sid: str, events: list[TraceEvent]) -> list[RetrievedChunk]:
        if self._retriever is None:
            return []
        t0 = perf_counter()
        query = " ".join(line.cpt_code for line in claim.lines)
        try:
            chunks = self._retriever.retrieve(query)
            events.append(
                _event(
                    sid,
                    StepKind.RETRIEVAL,
                    "rag.retrieve",
                    output={"n_chunks": len(chunks)},
                    t0=t0,
                )
            )
            return chunks
        except Exception as exc:  # noqa: BLE001 — degrade: audit without citations
            events.append(_error_event(sid, StepKind.RETRIEVAL, "rag.retrieve", exc, t0))
            return []

    def _run_rules(self, claim: Claim, sid: str, events: list[TraceEvent]) -> list[AuditFinding]:
        t0 = perf_counter()
        try:
            findings = self._rules.evaluate(claim)
            events.append(
                _event(
                    sid,
                    StepKind.TOOL,
                    "rules_engine.evaluate",
                    output={"n_findings": len(findings)},
                    t0=t0,
                )
            )
            return findings
        except Exception as exc:  # noqa: BLE001
            events.append(_error_event(sid, StepKind.TOOL, "rules_engine.evaluate", exc, t0))
            return []

    def _run_classifier(
        self, claim: Claim, context: list[RetrievedChunk], sid: str, events: list[TraceEvent]
    ) -> list[AuditFinding]:
        t0 = perf_counter()
        try:
            findings = self._classifier.classify(claim, context)
            events.append(
                _event(
                    sid,
                    StepKind.LLM,
                    "classifier.classify",
                    output={"n_findings": len(findings)},
                    t0=t0,
                    metadata={
                        "pass_used": getattr(self._classifier, "last_pass_used", None),
                        "escalated": getattr(self._classifier, "last_escalated", None),
                    },
                )
            )
            return findings
        except Exception as exc:  # noqa: BLE001 — degrade: keep rule-based findings
            events.append(_error_event(sid, StepKind.LLM, "classifier.classify", exc, t0))
            return []


# --------------------------------------------------------------------------- #
# Reconciliation + helpers
# --------------------------------------------------------------------------- #
def _merge(rules: list[AuditFinding], model: list[AuditFinding]) -> list[AuditFinding]:
    """Union of findings, deduped by (category, line_index). Rules win ties
    (deterministic + carry a rule_id); the classifier adds what rules can't find."""
    out: list[AuditFinding] = []
    seen: set[tuple] = set()
    for f in [*rules, *model]:
        key = (f.category, f.line_index)
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def _summarize(findings: list[AuditFinding]) -> str:
    if not findings:
        return "Clean: no inconsistencies found."
    n = len(findings)
    high = sum(1 for f in findings if f.severity.value == "high")
    return f"Flagged: {n} inconsistency(ies) found ({high} high-severity)."


def _event(
    sid: str,
    kind: StepKind,
    name: str,
    *,
    output: Any = None,
    t0: float,
    metadata: dict[str, Any] | None = None,
) -> TraceEvent:
    return TraceEvent(
        session_id=sid,
        step_id=uuid.uuid4().hex,
        kind=kind,
        name=name,
        output=output,
        latency_ms=(perf_counter() - t0) * 1000.0,
        start_time=datetime.now(UTC),
        metadata=metadata or {},
    )


def _error_event(sid: str, kind: StepKind, name: str, exc: Exception, t0: float) -> TraceEvent:
    return TraceEvent(
        session_id=sid,
        step_id=uuid.uuid4().hex,
        kind=kind,
        name=name,
        status=StepStatus.ERROR,
        error=ErrorInfo(type=type(exc).__name__, message=str(exc)),
        latency_ms=(perf_counter() - t0) * 1000.0,
        start_time=datetime.now(UTC),
    )


# --------------------------------------------------------------------------- #
# Convenience entrypoints
# --------------------------------------------------------------------------- #
def build_orchestrator(
    classifier: Classifier, *, retriever: Retriever | None = None
) -> AuditOrchestrator:
    """Construct an orchestrator with a fresh rules engine."""
    return AuditOrchestrator(RulesEngine(), classifier, retriever=retriever)


def audit_claim(claim: Claim, *, classifier: Classifier) -> list[AuditFinding]:
    """Convenience: audit a single claim and return just the findings."""
    return build_orchestrator(classifier).audit(claim).findings
