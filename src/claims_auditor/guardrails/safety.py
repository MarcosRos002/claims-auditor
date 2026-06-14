"""Guardrails: PII redaction + prompt-injection defense.

- PII/PHI redaction on all ingested text before it reaches an LLM (data is
  synthetic, but redaction is enforced as a discipline and a demoable feature).
- Prompt-injection defense on retrieved/transcribed content (treat it as data,
  never as instructions).
- Read-only DB access is enforced at the connection layer (see rag/retriever).

Phase 0: stub. See ``docs/modules/guardrails.md``.
"""

from __future__ import annotations


def redact_pii(text: str) -> str:
    """Return text with PII/PHI redacted."""
    raise NotImplementedError("Phase 0 stub — see docs/modules/guardrails.md")


def scan_for_injection(text: str) -> bool:
    """Return True if text looks like a prompt-injection attempt."""
    raise NotImplementedError
