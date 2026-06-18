# Module: data (`data/`)

## Purpose
Synthetic claim schema + generator. Produces **synthetic** claims modeled on
ICD-10/CPT conventions (never real PHI), with deliberately injected, **labeled**
inconsistencies so the audit pipeline has known positives and agent-lens has
ground truth. Foundational: every other module uses it for fixtures.

## Status: implemented (Phase 1)
Returns ground-truth-labeled claims, deterministic by seed, covering 4 fault
types. Pinned by `tests/test_synthetic_data.py`.

## Public interface
`data/synthetic.py`:
- `generate_claim(*, seed=None, inject_inconsistency=False, fault_type=None) -> LabeledClaim`
- `generate_dataset(n, *, fault_rate=0.3, seed=None) -> list[LabeledClaim]`
- `LabeledClaim` = `{ claim: Claim, faults: list[InjectedFault] }` (empty `faults` = clean).
- `InjectedFault` = `{ fault_type: FaultType, line_index: int | None, detail: str }` (ground truth).
- `FaultType` lives in `contracts` (shared with the rules engine + eval).

`fault_type` forces a specific fault (implies `inject_inconsistency`); otherwise a
random one is chosen. Determinism uses `random.Random(seed)` — never the global RNG.

## Fault types covered (single-claim, detectable without history)
- `CPT_ICD_MISMATCH` — procedure billed with a diagnosis outside its support set.
- `UNIT_EXCESS` — units above the CPT's plausible max.
- `DUPLICATE_LINE` — an identical billed line appears twice.
- `UPCODING` — a higher-complexity CPT billed where the diagnosis only supports the base code.

Each `FaultType` maps to the `AuditFinding`(s) the rules engine / classifier
should produce, so eval can match detections to injected ground truth.

## Catalog
A small hand-curated `CPT` / `ICD10` catalog: real-world code *formats* with
plausible `supports` (ICD→CPT justification), `max_units`, and `upcode_of`
links. The data and pairings are synthetic teaching fixtures, **not** clinical
guidance. Expand the catalog + `FaultType` deliberately as the rules engine grows.

## How to test in isolation
- `generate_claim(seed=...)` is deterministic for a given seed (claim + labels).
- `inject_inconsistency=True` yields a claim whose fault is recoverable as ground
  truth (rules/classification tests assert detection against `faults`).
- `generate_dataset(n, fault_rate=r, seed=...)` yields ~`r·n` faulty claims and is
  reproducible; clean claims have `faults == []`.

## Senior concerns
- **Realism vs. safety:** realistic ICD-10/CPT structure, zero real PHI — stated
  in the module docstring so no one mistakes it for real data.
- **Ground-truth fidelity:** injected faults map cleanly to the findings the
  pipeline should produce, or eval numbers are meaningless.
- **Coverage:** faults span the types the rules engine targets so eval isn't biased
  (pinned by `test_injected_faults_span_multiple_types`).
