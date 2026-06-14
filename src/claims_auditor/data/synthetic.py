"""Synthetic claim schema + generator.

Generates SYNTHETIC claims modeled on ICD-10/CPT conventions (never real PHI),
including deliberately-injected inconsistencies so the audit pipeline has known
positives to detect and the eval set (agent-lens) has ground truth.

Phase 0: stub. See ``docs/modules/data.md``.
"""

from __future__ import annotations

from claims_auditor.contracts import Claim


def generate_claim(*, seed: int | None = None, inject_inconsistency: bool = False) -> Claim:
    """Generate one synthetic claim, optionally with a known inconsistency."""
    raise NotImplementedError("Phase 0 stub — see docs/modules/data.md")


def generate_dataset(n: int, *, fault_rate: float = 0.3) -> list[Claim]:
    """Generate a labeled synthetic dataset for development and eval."""
    raise NotImplementedError
