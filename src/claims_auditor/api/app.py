"""FastAPI app + WebSocket endpoints.

Endpoints (planned):
  - ``POST /audit``        : submit a structured claim, get findings.
  - ``WS   /audit/stream`` : stream an audio file; receive transcription + findings.
  - ``WS   /voice``        : low-latency voice Q&A ("why did you flag claim #123?").
  - ``GET  /healthz``      : liveness.

The app is intentionally importable in Phase 0 so ``make run-api`` and tests can
load it; routes return 501 until implemented. See ``docs/modules/api.md``.
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Veritas — claims-auditor", version="0.0.0")


@app.get("/healthz")
def healthz() -> dict:
    """Liveness probe — the one endpoint that works in Phase 0."""
    return {"status": "ok", "phase": "0-bootstrap"}
