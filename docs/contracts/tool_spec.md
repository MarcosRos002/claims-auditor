# Contract: `ToolSpec`

Describes a tool the harness/agent can dispatch — including tools served by the
rules MCP server.

```python
class ToolSpec(BaseModel):
    name: str
    description: str           # prescriptive: say WHEN to call it, not just what it does
    input_schema: dict         # JSON Schema for inputs
    parallel_safe: bool = False  # True for read-only tools the harness may run concurrently
```

## Notes
- `parallel_safe` is load-bearing for the harness's **parallel tool dispatch**:
  read-only lookups (`lookup_icd10`, `lookup_cpt`, retrieval) are safe to run
  concurrently; anything with side effects serializes. In Veritas the audit path
  is read-only, so most tools are parallel-safe.
- `description` should be prescriptive about *when* to call the tool — recent
  Claude models reach for tools conservatively and benefit from explicit trigger
  conditions in the description.
- The rules MCP server advertises its tools as `ToolSpec`s via
  `modules/rules/mcp.py:tool_specs()`.
