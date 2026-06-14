# Module: data (`data/`)

## Purpose
Synthetic claim schema + generator. Produces **synthetic** claims modeled on
ICD-10/CPT conventions (never real PHI), with deliberately injected
inconsistencies so the audit pipeline has known positives and agent-lens has
ground truth. Foundational: every other module uses it for fixtures.

## Public interface
`data/synthetic.py`:
- `generate_claim(*, seed=None, inject_inconsistency=False) -> Claim`
- `generate_dataset(n, *, fault_rate=0.3) -> list[Claim]` — labeled dataset.

## Dependencies
- `contracts` only. **Foundational (Phase 1)** — blocks the leaves' tests.

## How to test in isolation
- `generate_claim(seed=...)` is deterministic for a given seed.
- `inject_inconsistency=True` produces a claim whose fault is recoverable as
  ground truth (so rules/classification tests can assert detection).
- `generate_dataset(n, fault_rate=r)` yields ~`r·n` faulty claims; labels are exposed.

## Senior concerns
- **Realism vs. safety:** realistic ICD-10/CPT structure without any real PHI;
  document that clearly so no one mistakes it for real data.
- **Ground-truth fidelity:** injected faults must map cleanly to the
  `AuditFinding`s the pipeline should produce, or eval numbers are meaningless.
- **Coverage:** span the fault types the rules engine + classifier target
  (code mismatch, units, frequency, …) so eval isn't biased.
