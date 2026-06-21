"""Concrete ``ClassifierModel`` adapters behind the classification seam.

Three interchangeable backends, all satisfying the ``ClassifierModel`` Protocol
(``classify(claim, context, *, tier) -> ClassificationResult``):

- ``DemoClassifierModel`` — deterministic, offline, **$0**. The safe default: no
  API key, no network. Flags known up-code CPTs (and supports a cached-response
  map for scripted demos). Lets the whole flagship run for free.
- ``AnthropicClassifierModel`` — real Claude via the official ``anthropic`` SDK.
  ``tier`` routes the model: cheap -> Haiku, escalated -> Sonnet (``routing/``).
  Uses **structured outputs** (``messages.parse(output_format=...)``) so the
  reply is a validated ``ClassificationResult``. Reads ``ANTHROPIC_API_KEY``
  (BYOK). The client is injectable, so tests run offline.
- ``OpenRouterClassifierModel`` — OpenAI-compatible free tier (BYOK via
  ``OPENROUTER_API_KEY``); same tier->model routing, manual JSON parse.

``build_classifier_model()`` selects one from the environment, defaulting to demo
so a fresh checkout audits claims at zero cost. See ``docs/modules/classification.md``.
"""

from __future__ import annotations

import json
import os

from claims_auditor.contracts import Claim, FaultType, RetrievedChunk
from claims_auditor.modules.classification.classifier import (
    CandidateFinding,
    ClassificationResult,
    Tier,
)
from claims_auditor.reference import catalog
from claims_auditor.routing.cost_router import HAIKU, SONNET

# tier -> model id. The cheap pass uses Haiku; escalation uses Sonnet.
_MODEL_FOR_TIER: dict[Tier, str] = {"cheap": HAIKU, "escalated": SONNET}

# OpenRouter free-tier model ids (override via env if they change).
_OPENROUTER_MODEL_FOR_TIER: dict[Tier, str] = {
    "cheap": "meta-llama/llama-3.3-70b-instruct:free",
    "escalated": "meta-llama/llama-3.3-70b-instruct:free",
}

_SYSTEM = (
    "You are a medical-billing claim auditor. Given a claim and retrieved "
    "ICD-10/CPT reference context, identify billing inconsistencies. Only report "
    "an inconsistency you can justify from the claim and context. For each, give "
    "a category, the affected line_index (0-based, or null), a confidence in "
    "[0,1], and a short 'why'. Valid categories: "
    + ", ".join(f.value for f in FaultType)
    + ". If the claim is clean, return an empty findings list."
)


def _user_prompt(claim: Claim, context: list[RetrievedChunk]) -> str:
    """Render the claim + retrieved context into a single user message."""
    ctx = "\n".join(f"- [{c.source}] {c.text}" for c in context) or "(no context)"
    return (
        f"CLAIM:\n{claim.model_dump_json(indent=2)}\n\n"
        f"REFERENCE CONTEXT:\n{ctx}\n\n"
        "Return the inconsistencies as structured output."
    )


class DemoClassifierModel:
    """Deterministic, offline, $0 classifier. The default backend.

    Heuristic: a line whose CPT is a known up-code (``catalog.UPCODE_CPTS``) is
    flagged as ``UPCODING`` with high confidence. Optionally, a ``responses`` map
    keyed by ``claim_id`` returns scripted results for a guided demo. Pure and
    deterministic — identical input yields identical output, no network, no cost.
    """

    def __init__(self, responses: dict[str, ClassificationResult] | None = None) -> None:
        self._responses = responses or {}

    def classify(
        self, claim: Claim, context: list[RetrievedChunk], *, tier: Tier
    ) -> ClassificationResult:
        cached = self._responses.get(claim.claim_id)
        if cached is not None:
            return cached.model_copy(deep=True)

        findings = [
            CandidateFinding(
                category=FaultType.UPCODING,
                line_index=i,
                confidence=0.9,
                why=(
                    f"CPT {line.cpt_code} is a higher-complexity code than the "
                    "listed diagnoses typically support (demo heuristic)."
                ),
            )
            for i, line in enumerate(claim.lines)
            if line.cpt_code in catalog.UPCODE_CPTS
        ]
        return ClassificationResult(findings=findings)


class AnthropicClassifierModel:
    """Real Claude classifier (BYOK). ``tier`` routes Haiku (cheap) / Sonnet (escalated).

    The ``client`` is injectable for offline tests; if omitted it is created
    lazily on first call (reading ``ANTHROPIC_API_KEY``), so importing/constructing
    this class never needs a key or network.
    """

    def __init__(self, *, client: object | None = None, max_tokens: int = 1024) -> None:
        self._client = client
        self._max_tokens = max_tokens

    def _ensure_client(self) -> object:
        if self._client is None:
            import anthropic  # lazy: only needed for real calls

            self._client = anthropic.Anthropic()
        return self._client

    def classify(
        self, claim: Claim, context: list[RetrievedChunk], *, tier: Tier
    ) -> ClassificationResult:
        client = self._ensure_client()
        response = client.messages.parse(
            model=_MODEL_FOR_TIER[tier],
            max_tokens=self._max_tokens,
            system=_SYSTEM,
            messages=[{"role": "user", "content": _user_prompt(claim, context)}],
            output_format=ClassificationResult,
        )
        return response.parsed_output


class OpenRouterClassifierModel:
    """OpenAI-compatible classifier over OpenRouter's free tier (BYOK).

    Same tier->model routing; OpenRouter has no native structured-output parse,
    so we request JSON and validate it into ``ClassificationResult``. The client
    is injectable for offline tests; otherwise built lazily from the ``openai``
    SDK pointed at OpenRouter (reading ``OPENROUTER_API_KEY``).
    """

    _BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, *, client: object | None = None, max_tokens: int = 1024) -> None:
        self._client = client
        self._max_tokens = max_tokens

    def _ensure_client(self) -> object:
        if self._client is None:
            from openai import OpenAI  # lazy

            self._client = OpenAI(
                base_url=self._BASE_URL, api_key=os.environ.get("OPENROUTER_API_KEY")
            )
        return self._client

    def classify(
        self, claim: Claim, context: list[RetrievedChunk], *, tier: Tier
    ) -> ClassificationResult:
        client = self._ensure_client()
        schema = json.dumps(ClassificationResult.model_json_schema())
        completion = client.chat.completions.create(
            model=_OPENROUTER_MODEL_FOR_TIER[tier],
            max_tokens=self._max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": f"{_SYSTEM}\n\nJSON schema:\n{schema}"},
                {"role": "user", "content": _user_prompt(claim, context)},
            ],
        )
        payload = completion.choices[0].message.content or "{}"
        return ClassificationResult.model_validate_json(payload)


def build_classifier_model() -> (
    DemoClassifierModel | AnthropicClassifierModel | OpenRouterClassifierModel
):
    """Pick a backend from the environment. Defaults to demo (offline, $0).

    Resolution order:
    1. ``VERITAS_DEMO_MODE`` truthy -> demo (overrides any key).
    2. ``VERITAS_MODEL_BACKEND`` in {demo, anthropic, openrouter} -> that backend.
    3. ``ANTHROPIC_API_KEY`` set -> Anthropic (BYOK).
    4. ``OPENROUTER_API_KEY`` set -> OpenRouter (BYOK).
    5. otherwise -> demo.
    """
    if _truthy(os.environ.get("VERITAS_DEMO_MODE")):
        return DemoClassifierModel()

    backend = (os.environ.get("VERITAS_MODEL_BACKEND") or "").strip().lower()
    if backend == "anthropic":
        return AnthropicClassifierModel()
    if backend == "openrouter":
        return OpenRouterClassifierModel()
    if backend == "demo":
        return DemoClassifierModel()

    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicClassifierModel()
    if os.environ.get("OPENROUTER_API_KEY"):
        return OpenRouterClassifierModel()
    return DemoClassifierModel()


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}
