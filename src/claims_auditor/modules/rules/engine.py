"""Business-rules engine for medical-billing audit.

Deterministic, high-precision checks over a ``Claim`` against the shared
``reference.catalog``. Produces ``AuditFinding`` objects (each tagged with the
``FaultType`` it detected, so eval can match detections to ground truth).

Scope — what rules CAN detect from structured codes alone:
- ``CPT_ICD_MISMATCH`` — procedure billed with no supporting diagnosis.
- ``UNIT_EXCESS``      — units above the CPT's plausible maximum.
- ``DUPLICATE_LINE``   — an identical billed line appears more than once.

Out of scope (the LLM classifier's job): ``UPCODING`` and anything needing
clinical context/notes. Keeping the rules pure and conservative is what makes
them the precision backbone; the classifier covers what codes can't express.

The same checks/lookups are exposed to the agent as MCP tools (see mcp.py).
See ``docs/modules/rules-mcp.md``.
"""

from __future__ import annotations

from claims_auditor.contracts import AuditFinding, Claim, FaultType, Severity
from claims_auditor.reference.catalog import CPT, is_known_cpt, max_units, supports


class RulesEngine:
    """Evaluates a claim against business rules and returns findings."""

    def evaluate(self, claim: Claim) -> list[AuditFinding]:
        findings: list[AuditFinding] = []
        findings.extend(self._line_checks(claim))
        findings.extend(self._duplicate_check(claim))
        return findings

    # -- per-line checks ------------------------------------------------ #
    def _line_checks(self, claim: Claim) -> list[AuditFinding]:
        out: list[AuditFinding] = []
        for idx, line in enumerate(claim.lines):
            cpt = line.cpt_code

            if not is_known_cpt(cpt):
                out.append(
                    self._finding(
                        claim,
                        idx,
                        None,
                        "R-UNKNOWN-CODE",
                        Severity.INFO,
                        f"Unknown CPT code {cpt!r}; cannot verify against the catalog.",
                    )
                )
                continue  # can't run code-aware checks on an unknown code

            if not any(supports(cpt, dx) for dx in line.icd10_codes):
                dx_list = ", ".join(line.icd10_codes) or "(none)"
                out.append(
                    self._finding(
                        claim,
                        idx,
                        FaultType.CPT_ICD_MISMATCH,
                        "R-CPT-ICD-COMPAT",
                        Severity.HIGH,
                        f"CPT {cpt} ({CPT[cpt].desc}) is not supported by any listed "
                        f"diagnosis [{dx_list}].",
                    )
                )

            limit = max_units(cpt)
            if limit is not None and line.units > limit:
                out.append(
                    self._finding(
                        claim,
                        idx,
                        FaultType.UNIT_EXCESS,
                        "R-UNIT-MAX",
                        Severity.MEDIUM,
                        f"CPT {cpt} billed with {line.units} units (plausible max {limit}).",
                    )
                )
        return out

    # -- claim-level duplicate check ------------------------------------ #
    def _duplicate_check(self, claim: Claim) -> list[AuditFinding]:
        out: list[AuditFinding] = []
        seen: dict[tuple, int] = {}
        for idx, line in enumerate(claim.lines):
            key = (line.cpt_code, tuple(sorted(line.icd10_codes)), line.units, line.charge_cents)
            if key in seen:
                out.append(
                    self._finding(
                        claim,
                        idx,
                        FaultType.DUPLICATE_LINE,
                        "R-DUP-LINE",
                        Severity.MEDIUM,
                        f"Line {idx} ({line.cpt_code}) duplicates line {seen[key]}.",
                    )
                )
            else:
                seen[key] = idx
        return out

    # -- helper --------------------------------------------------------- #
    @staticmethod
    def _finding(
        claim: Claim,
        line_index: int,
        category: FaultType | None,
        rule_id: str,
        severity: Severity,
        why: str,
    ) -> AuditFinding:
        return AuditFinding(
            finding_id=f"{claim.claim_id}:{rule_id}:{line_index}",
            claim_id=claim.claim_id,
            severity=severity,
            category=category,
            line_index=line_index,
            rule_id=rule_id,
            why=why,
        )
