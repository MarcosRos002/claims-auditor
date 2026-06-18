"""Synthetic claim schema + generator.

Generates SYNTHETIC claims modeled on ICD-10/CPT conventions (**never real
PHI**), optionally with deliberately-injected, *labeled* inconsistencies. The
labels are the ground truth the rules engine / classifier must recover and that
agent-lens uses to compute precision/recall.

Design:
- ``generate_claim`` / ``generate_dataset`` return ``LabeledClaim`` (a ``Claim``
  plus the list of ``InjectedFault`` ground-truth labels). A clean claim has an
  empty ``faults`` list.
- Everything is **deterministic for a given seed** so fixtures and eval are
  reproducible (``random.Random(seed)``, never the global RNG).

The ICD-10/CPT catalog is the shared ``reference.catalog`` (same source of truth
the rules engine checks against, so ground truth and detection cannot diverge).

See ``docs/modules/data.md``.
"""

from __future__ import annotations

import random

from pydantic import BaseModel, Field

from claims_auditor.contracts import Claim, ClaimLine, FaultType
from claims_auditor.reference.catalog import (
    BASE_CPTS,
    CPT,
    ICD10,
    UPCODE_CPTS,
)


# ---------------------------------------------------------------------------
# Ground-truth labels
# ---------------------------------------------------------------------------
class InjectedFault(BaseModel):
    """A labeled inconsistency injected into a synthetic claim (ground truth)."""

    fault_type: FaultType
    line_index: int | None = Field(
        None, description="Index of the affected line in claim.lines, if line-specific."
    )
    detail: str = Field(..., description="Human-readable description of the injected fault.")


class LabeledClaim(BaseModel):
    """A synthetic claim plus its ground-truth fault labels (empty = clean)."""

    claim: Claim
    faults: list[InjectedFault] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
def _clean_line(rng: random.Random) -> ClaimLine:
    """Build a clean, internally-consistent billed line."""
    cpt = rng.choice(BASE_CPTS)
    supported = sorted(CPT[cpt].supports)
    n_dx = rng.randint(1, min(2, len(supported)))
    icd = rng.sample(supported, n_dx)
    return ClaimLine(
        cpt_code=cpt,
        icd10_codes=icd,
        units=1,
        charge_cents=rng.randrange(5_000, 40_000, 500),
    )


def _inject(rng: random.Random, lines: list[ClaimLine], fault_type: FaultType) -> InjectedFault:
    """Mutate ``lines`` in place to introduce ``fault_type``; return its label."""
    if fault_type is FaultType.CPT_ICD_MISMATCH:
        idx = rng.randrange(len(lines))
        cpt = lines[idx].cpt_code
        unsupported = sorted(set(ICD10) - CPT[cpt].supports)
        bad_dx = rng.choice(unsupported)
        lines[idx].icd10_codes = [bad_dx]
        return InjectedFault(
            fault_type=fault_type,
            line_index=idx,
            detail=f"{cpt} billed with unsupported diagnosis {bad_dx}.",
        )

    if fault_type is FaultType.UNIT_EXCESS:
        idx = rng.randrange(len(lines))
        cpt = lines[idx].cpt_code
        lines[idx].units = CPT[cpt].max_units + rng.randint(1, 3)
        return InjectedFault(
            fault_type=fault_type,
            line_index=idx,
            detail=f"{cpt} billed with {lines[idx].units} units (max {CPT[cpt].max_units}).",
        )

    if fault_type is FaultType.DUPLICATE_LINE:
        idx = rng.randrange(len(lines))
        lines.append(lines[idx].model_copy(deep=True))
        return InjectedFault(
            fault_type=fault_type,
            line_index=len(lines) - 1,
            detail=f"Line {idx} ({lines[idx].cpt_code}) billed twice.",
        )

    if fault_type is FaultType.UPCODING:
        upcode = rng.choice(UPCODE_CPTS)
        base = CPT[upcode].upcode_of
        assert base is not None
        # A diagnosis that justifies the base code is used to bill the up-code.
        dx = rng.choice(sorted(CPT[base].supports))
        idx = rng.randrange(len(lines))
        lines[idx].cpt_code = upcode
        lines[idx].icd10_codes = [dx]
        return InjectedFault(
            fault_type=fault_type,
            line_index=idx,
            detail=f"{upcode} billed where diagnosis {dx} only supports {base}.",
        )

    raise ValueError(f"unknown fault_type: {fault_type!r}")  # pragma: no cover


def generate_claim(
    *,
    seed: int | None = None,
    inject_inconsistency: bool = False,
    fault_type: FaultType | None = None,
) -> LabeledClaim:
    """Generate one synthetic claim, optionally with a known, labeled fault.

    Deterministic for a given ``seed``. ``fault_type`` forces a specific fault
    (implies ``inject_inconsistency``); otherwise one is chosen at random.
    """
    rng = random.Random(seed)
    n_lines = rng.randint(1, 3)
    # Build DISTINCT clean lines so a clean claim never has an accidental
    # duplicate (which would be an unlabeled DUPLICATE_LINE and corrupt eval).
    lines: list[ClaimLine] = []
    while len(lines) < n_lines:
        candidate = _clean_line(rng)
        if candidate not in lines:
            lines.append(candidate)

    faults: list[InjectedFault] = []
    if inject_inconsistency or fault_type is not None:
        chosen = fault_type if fault_type is not None else rng.choice(list(FaultType))
        faults.append(_inject(rng, lines, chosen))

    # Deterministic synthetic identifiers / date.
    claim = Claim(
        claim_id=f"SYN-CLM-{rng.randrange(10**6, 10**7)}",
        patient_ref=f"SYN-PT-{rng.randrange(10**5, 10**6)}",
        provider_npi=str(rng.randrange(10**9, 10**10)),
        date_of_service=f"2026-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
        lines=lines,
    )
    return LabeledClaim(claim=claim, faults=faults)


def generate_dataset(
    n: int, *, fault_rate: float = 0.3, seed: int | None = None
) -> list[LabeledClaim]:
    """Generate a labeled synthetic dataset.

    ~``fault_rate``·``n`` claims carry an injected fault; the rest are clean.
    Deterministic for a given ``seed``.
    """
    if not 0.0 <= fault_rate <= 1.0:
        raise ValueError("fault_rate must be in [0, 1]")
    master = random.Random(seed)
    dataset: list[LabeledClaim] = []
    for _ in range(n):
        faulty = master.random() < fault_rate
        # Derive an independent per-claim seed so each claim is itself reproducible.
        claim_seed = master.randrange(2**32)
        dataset.append(generate_claim(seed=claim_seed, inject_inconsistency=faulty))
    return dataset
