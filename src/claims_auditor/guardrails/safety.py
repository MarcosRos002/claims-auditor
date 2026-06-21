"""Guardrails: PII redaction + prompt-injection defense.

- PII/PHI redaction on all ingested text before it reaches an LLM (data is
  synthetic, but redaction is enforced as a discipline and a demoable feature).
- Prompt-injection defense on retrieved/transcribed content (treat it as data,
  never as instructions).
- Read-only DB access is enforced at the connection layer (see rag/retriever).

Pure (string in/out), deterministic, idempotent. Clinical codes (CPT/ICD) are
deliberately NOT redacted — they are not PII and the audit needs them.

Scope: structured identifiers (NPI, SSN, email, phone, dates, patient refs).
Free-text **names** need NER (e.g. Presidio/spaCy) and are out of scope here —
a deliberate, documented boundary. See ``docs/modules/guardrails.md``.
"""

from __future__ import annotations

import re

# (category, compiled pattern, placeholder). Order matters: most specific first,
# so e.g. an SSN/phone (with separators) is matched before a bare 10-digit NPI.
_PII_RULES: list[tuple[str, re.Pattern[str], str]] = [
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[EMAIL]"),
    ("patient_ref", re.compile(r"\bSYN-PT-\d+\b", re.IGNORECASE), "[PATIENT_REF]"),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    ("phone", re.compile(r"\b(?:\+?\d{1,2}[\s-])?\(?\d{3}\)?[\s-]\d{3}[\s-]\d{4}\b"), "[PHONE]"),
    ("date", re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), "[DATE]"),
    ("npi", re.compile(r"\b\d{10}\b"), "[NPI]"),
]

# Prompt-injection signatures (case-insensitive). Untrusted ASR/retrieved text is
# DATA, never instructions — these flag attempts to escape that boundary.
_INJECTION_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "ignore_instructions",
        re.compile(r"ignore\s+(?:the\s+)?(?:previous|above|prior|all)\b", re.I),
    ),
    ("disregard", re.compile(r"disregard\s+(?:the\s+)?(?:previous|above|prior|all)\b", re.I)),
    ("forget", re.compile(r"forget\s+(?:everything|the\s+above|previous|all)\b", re.I)),
    ("role_override", re.compile(r"you\s+are\s+now\b|act\s+as\s+(?:an?\s+)?", re.I)),
    ("system_prompt", re.compile(r"system\s+prompt\b|developer\s+mode\b", re.I)),
    ("new_instructions", re.compile(r"new\s+instructions?\s*:", re.I)),
    ("special_tokens", re.compile(r"<\|.*?\|>|\[/?INST\]", re.I)),
]


def redact_pii_detailed(text: str) -> tuple[str, list[str]]:
    """Redact PII/PHI; return the redacted text and the categories hit (for metrics)."""
    hits: list[str] = []
    for category, pattern, placeholder in _PII_RULES:
        if pattern.search(text):
            hits.append(category)
            text = pattern.sub(placeholder, text)
    return text, hits


def redact_pii(text: str) -> str:
    """Return text with PII/PHI redacted (idempotent; clinical codes preserved)."""
    return redact_pii_detailed(text)[0]


def scan_for_injection_detailed(text: str) -> tuple[bool, list[str]]:
    """Return (flagged, matched-pattern-names) for prompt-injection signatures."""
    hits = [name for name, pattern in _INJECTION_RULES if pattern.search(text)]
    return bool(hits), hits


def scan_for_injection(text: str) -> bool:
    """Return True if text looks like a prompt-injection attempt."""
    return scan_for_injection_detailed(text)[0]
