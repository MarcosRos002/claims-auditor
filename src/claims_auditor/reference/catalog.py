"""Shared ICD-10 / CPT reference catalog — the single source of truth for the
medical-coding knowledge used across Veritas.

Consumed by:
- ``data/synthetic`` — to generate claims and inject labeled inconsistencies.
- ``modules/rules`` — to deterministically check claims against the same codes.

Keeping ONE catalog here means the generator's ground truth and the rules
engine's checks can never silently diverge (which would make eval meaningless).

The codes use real-world *formats* (e.g. CPT ``99213``, ICD-10 ``E11.9``) with
plausible support relationships, but the data and pairings are synthetic
teaching fixtures — **not** clinical guidance and **never** real PHI.
"""

from __future__ import annotations

from pydantic import BaseModel

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


class CptInfo(BaseModel):
    desc: str
    max_units: int
    supports: frozenset[str]  # ICD-10 codes that justify this procedure
    upcode_of: str | None = None  # base CPT this one over-codes, if any


CPT: dict[str, CptInfo] = {
    "99213": CptInfo(
        desc="Office/outpatient visit, established, low complexity",
        max_units=1,
        supports=frozenset({"E11.9", "I10", "J06.9", "M54.5"}),
    ),
    "99214": CptInfo(
        desc="Office/outpatient visit, established, moderate complexity",
        max_units=1,
        supports=frozenset({"E11.9", "I10", "J06.9", "M54.5"}),
        upcode_of="99213",
    ),
    "93000": CptInfo(
        desc="Electrocardiogram, complete",
        max_units=1,
        supports=frozenset({"I10", "I48.91", "R07.9"}),
    ),
    "71046": CptInfo(
        desc="Radiologic exam, chest, 2 views",
        max_units=1,
        supports=frozenset({"J18.9", "R05.9", "J06.9"}),
    ),
    "80053": CptInfo(
        desc="Comprehensive metabolic panel",
        max_units=3,
        supports=frozenset({"E11.9", "N18.3", "R73.09"}),
    ),
    "99396": CptInfo(
        desc="Preventive visit, established, 40-64 years",
        max_units=1,
        supports=frozenset({"Z00.00"}),
    ),
}

# CPTs that are not a complexity up-code of something else (safe for clean lines).
BASE_CPTS: list[str] = sorted(c for c, info in CPT.items() if info.upcode_of is None)
UPCODE_CPTS: list[str] = sorted(c for c, info in CPT.items() if info.upcode_of is not None)


def is_known_cpt(cpt: str) -> bool:
    return cpt in CPT


def supports(cpt: str, icd10: str) -> bool:
    """Whether ``icd10`` is a diagnosis that justifies procedure ``cpt``."""
    info = CPT.get(cpt)
    return bool(info and icd10 in info.supports)


def max_units(cpt: str) -> int | None:
    info = CPT.get(cpt)
    return info.max_units if info else None
