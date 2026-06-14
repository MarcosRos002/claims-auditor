# Contract: `Claim` / `ClaimLine`

The central unit Veritas audits. Always **synthetic** (no real PHI). May arrive
as a structured payload or be extracted from an ASR transcript.

```python
class ClaimLine(BaseModel):
    cpt_code: str            # CPT/HCPCS procedure code (synthetic)
    icd10_codes: list[str]   # diagnosis codes attached to this line
    units: int = 1
    charge_cents: int = 0

class Claim(BaseModel):
    claim_id: str
    patient_ref: str         # synthetic, de-identified reference
    provider_npi: str
    date_of_service: str     # ISO-8601 date
    lines: list[ClaimLine]
    source_transcript_id: str | None = None  # set when extracted from audio
```

## Notes
- `patient_ref` is a synthetic token, never a real identifier. Guardrails redact
  defensively regardless.
- `source_transcript_id` links a claim back to the ASR run it came from (for
  trace correlation in agent-lens).
- Producers: `data.generate_claim` (synthetic, optionally faulty); `agent`
  claim-extraction node (from transcript). Consumers: `rules`, `classification`,
  `rag` (builds queries from claim content).
