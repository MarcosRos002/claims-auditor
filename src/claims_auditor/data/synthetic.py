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

The catalog below is small and hand-curated. The codes use real-world *formats*
(e.g. CPT ``99213``, ICD-10 ``E11.9``) with plausible support relationships, but
the data and pairings are synthetic teaching fixtures — not clinical guidance.

See ``docs/modules/data.md``.
"""

from __future__ import annotations

import random

from pydantic import BaseModel, Field

from claims_auditor.contracts import Claim, ClaimLine, FaultType

# ---------------------------------------------------------------------------
# Synthetic ICD-10 / CPT catalog (formats are real; pairings are teaching data)
# ---------------------------------------------------------------------------
ICD10: dict[str, str] = {
    "E11.9": "Type 2 diabetes mellitus without complications",
    "I10": "Essential (primary) hypertension",
    "J06.9": "Acute upper respiratory infection, unspecified",
    "M54.5": "Low back pain",
    "I48.91": "Unspecified atrial fibrillation",
    "R07.9": "Chest pain, unspecified",
    "J18.9": "Pneumonia, unspecified organism",
    "R05.9": "Cough, unspecified",
    "N18.3": "Chronic kidney disease, stage 3",
    "R73.09": "Other abnormal glucose",
    "Z00.00": "General adult medical exam without abnormal findings",
}


class _CptInfo(BaseModel):
    desc: str
    max_units: int
    supports: frozenset[str]  # ICD-10 codes that justify this procedure
    upcode_of: str | None = None  # base CPT this one over-codes, if any


CPT: dict[str, _CptInfo] = {
    "99213": _CptInfo(
        desc="Office/outpatient visit, established, low complexity",
        max_units=1,
        supports=frozenset({"E11.9", "I10", "J06.9", "M54.5"}),
    ),
    "99214": _CptInfo(
        desc="Office/outpatient visit, established, moderate complexity",
        max_units=1,
        supports=frozenset({"E11.9", "I10", "J06.9", "M54.5"}),
        upcode_of="99213",
    ),
    "93000": _CptInfo(
        desc="Electrocardiogram, complete",
        max_units=1,
        supports=frozenset({"I10", "I48.91", "R07.9"}),
    ),
    "71046": _CptInfo(
        desc="Radiologic exam, chest, 2 views",
        max_units=1,
        supports=frozenset({"J18.9", "R05.9", "J06.9"}),
    ),
    "80053": _CptInfo(
        desc="Comprehensive metabolic panel",
        max_units=3,
        supports=frozenset({"E11.9", "N18.3", "R73.09"}),
    ),
    "99396": _CptInfo(
        desc="Preventive visit, established, 40-64 years",
        max_units=1,
        supports=frozenset({"Z00.00"}),
    ),
}

# CPTs that are not a complexity up-code of something else (safe for clean lines).
_BASE_CPTS: list[str] = sorted(c for c, info in CPT.items() if info.upcode_of is None)
_UPCODE_CPTS: list[str] = sorted(c for c, info in CPT.items() if info.upcode_of is not None)


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
    cpt = rng.choice(_BASE_CPTS)
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
        upcode = rng.choice(_UPCODE_CPTS)
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
    lines = [_clean_line(rng) for _ in range(n_lines)]

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
