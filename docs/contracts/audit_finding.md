# Contract: `AuditFinding` (a.k.a. Inconsistency)

A detected inconsistency in a claim, with a human-readable reason and grounding
citations. This is Veritas's primary output.

```python
class Severity(str, Enum):
    INFO = "info"; LOW = "low"; MEDIUM = "medium"; HIGH = "high"

class AuditFinding(BaseModel):
    finding_id: str
    claim_id: str
    severity: Severity
    rule_id: str | None        # the rule that fired, if rule-based
    why: str                   # explanation of the inconsistency
    citations: list[RetrievedChunk]   # evidence grounding `why`
```

## Notes
- Both the deterministic **rules engine** and the **classifier** produce
  findings; the agent reconciles them. `rule_id` is set for rule-based findings,
  `None` for purely model-derived ones.
- `why` must be explainable and, wherever possible, grounded — `citations`
  should point at the ICD-10/CPT/policy text that justifies the finding. **Never
  fabricate citations**; an empty list with reduced confidence is acceptable.
- `severity` drives triage and is a candidate axis for agent-lens metrics.
