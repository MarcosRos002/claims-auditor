"""Online smoke for the real ClassifierModel adapters (BYOK).

Loads keys from .env, audits ONE synthetic claim (an up-code, CPT 99214) with the
Anthropic adapter (Haiku, cheap tier) and the OpenRouter free adapter, and prints
the parsed ClassificationResult plus the real token cost. Synthetic data only.

Run: python scripts/smoke_model_adapter.py
"""

from __future__ import annotations

import os
from pathlib import Path

from claims_auditor.contracts import Claim, ClaimLine, RetrievedChunk
from claims_auditor.modules.classification.models import (
    AnthropicClassifierModel,
    OpenRouterClassifierModel,
)

# Haiku 4.5 pricing ($/1M tokens).
HAIKU_IN, HAIKU_OUT = 1.00, 5.00


def load_env(path: Path) -> None:
    for line in path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


def sample_claim() -> tuple[Claim, list[RetrievedChunk]]:
    claim = Claim(
        claim_id="SMOKE-1",
        patient_ref="SYN-0001",
        provider_npi="1999999984",
        date_of_service="2026-01-15",
        lines=[ClaimLine(cpt_code="99214", icd10_codes=["J06.9"], units=1, charge_cents=21000)],
    )
    context = [
        RetrievedChunk(
            chunk_id="cpt:99214",
            source="cpt",
            score=0.9,
            text="99214: office/outpatient visit, established patient, moderate complexity.",
        ),
        RetrievedChunk(
            chunk_id="cpt:99213",
            source="cpt",
            score=0.8,
            text="99213: office/outpatient visit, established patient, low complexity.",
        ),
        RetrievedChunk(
            chunk_id="icd:J06.9",
            source="icd10",
            score=0.7,
            text="J06.9: acute upper respiratory infection, unspecified (a minor, self-limited illness).",
        ),
    ]
    return claim, context


class _CaptureClient:
    """Wraps a real anthropic client to stash the raw response (for usage/cost)."""

    def __init__(self, inner: object) -> None:
        self._inner = inner
        self.last = None
        self.messages = self._Messages(self)

    class _Messages:
        def __init__(self, outer: "_CaptureClient") -> None:
            self._outer = outer

        def parse(self, **kw: object) -> object:
            resp = self._outer._inner.messages.parse(**kw)
            self._outer.last = resp
            return resp


def run_anthropic(claim: Claim, context: list[RetrievedChunk]) -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC: skipped (no key)\n")
        return
    import anthropic

    cap = _CaptureClient(anthropic.Anthropic())
    model = AnthropicClassifierModel(client=cap)
    result = model.classify(claim, context, tier="cheap")
    print("=== Anthropic (Haiku, cheap tier) ===")
    print(f"model: {cap.last.model}")
    for f in result.findings:
        print(f"  - {f.category.value} line={f.line_index} conf={f.confidence:.2f} :: {f.why}")
    if not result.findings:
        print("  (no findings)")
    u = cap.last.usage
    cost = u.input_tokens / 1e6 * HAIKU_IN + u.output_tokens / 1e6 * HAIKU_OUT
    print(f"tokens: in={u.input_tokens} out={u.output_tokens}  cost=${cost:.6f}\n")


def run_openrouter(claim: Claim, context: list[RetrievedChunk]) -> None:
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("OPENROUTER: skipped (no key)\n")
        return
    model = OpenRouterClassifierModel()
    try:
        result = model.classify(claim, context, tier="cheap")
    except Exception as e:  # noqa: BLE001 — smoke: report and continue
        print(f"=== OpenRouter (free) ===\n  ERROR: {type(e).__name__}: {e}\n")
        return
    print("=== OpenRouter (llama-3.3-70b:free, cheap tier) ===")
    for f in result.findings:
        print(f"  - {f.category.value} line={f.line_index} conf={f.confidence:.2f} :: {f.why}")
    if not result.findings:
        print("  (no findings)")
    print("cost: $0.000000 (free tier)\n")


def main() -> None:
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        load_env(env)
    claim, context = sample_claim()
    print(f"Claim {claim.claim_id}: CPT 99214 (moderate) vs dx J06.9 (minor URI) — expect UPCODING.\n")
    run_anthropic(claim, context)
    run_openrouter(claim, context)


if __name__ == "__main__":
    main()
