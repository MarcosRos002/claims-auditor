# Module: api (`api/`)

## Purpose
The FastAPI app and WebSocket endpoints — the system's front door. REST for
structured audits; WebSockets for streaming transcription and low-latency voice
Q&A (with barge-in via the harness).

## Public interface
`api/app.py:app` (FastAPI). Planned routes:
- `POST /audit` — submit a structured `Claim`, get `AuditFinding[]`.
- `WS /audit/stream` — stream an audio file; receive transcription + findings.
- `WS /voice` — voice Q&A ("why did you flag claim #123?").
- `GET /healthz` — liveness (works in Phase 0).

## Dependencies
- `agent` (graph), `core/harness` (streaming/barge-in), `guardrails`.
- **Upper layer** (Phase 4); voice depends on the integrated agent.
- Runtime: `fastapi`, `uvicorn`.

## How to test in isolation
- `GET /healthz` returns ok (covered today in `tests/test_api_health.py`).
- With the agent graph mocked, assert `POST /audit` validates a `Claim` and
  returns findings; assert bad payloads 422.
- WebSocket tests with a fake transcriber/agent: assert partials stream and the
  connection closes cleanly.

## Senior concerns
- **Failure modes:** WebSocket disconnects mid-stream (partial results); backpressure
  on long audio; barge-in races; request validation.
- **Demo modes:** honor `VERITAS_DEMO_MODE` (cached responses) and the
  OpenRouter/BYOK paths so the public demo runs free.
- **Metrics:** request latency, WS session duration, first-token latency for voice.
