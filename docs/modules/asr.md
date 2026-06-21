# Module: asr (`modules/asr/`)

## Purpose
Audio ingestion + streaming transcription. Turns clinical dictation / call
recordings into time-stamped `TranscriptSegment`s, emitting partials early so the
agent and the voice UI stay responsive.

## Status: implemented (Phase 1, online-verified)
Pinned by `tests/test_asr.py` (offline, injected fake Whisper). Verified online
with real models: a silero-TTS round-trip ("Procedure code nine nine two one
three, diagnosis E eleven point nine") transcribes back correctly through a real
faster-whisper `tiny.en`. (silero/omegaconf are demo-only — used to *generate*
the test audio, not project deps; `faster-whisper` is a core dep.)

## Public interface
`modules/asr/transcriber.py`:
- `WhisperTranscriber(model=None, *, model_name="tiny", language="en")` implements
  `ASRTranscriber`: `transcribe_stream(audio: bytes) -> list[TranscriptSegment]`.
- The Whisper model is **injected** (anything with
  `transcribe(audio, **kw) -> (segments, info)`) so the mapping logic is offline-
  testable; a real `faster_whisper.WhisperModel` is built by default (lazy import).

Returns final segments today. An async/generator **streaming** variant
(`is_final=False` partials early) is the planned enhancement for the low-latency
voice path (Capa 3).

## Dependencies
- `contracts` only at the seam.
- Runtime: `faster-whisper` (local, default) with **Groq** as the hosted
  low-latency fallback (`GROQ_API_KEY`).
- Phase-2 **leaf** — buildable in its own worktree.

## How to test in isolation
- Use a short fixture WAV; assert it yields ≥1 final `TranscriptSegment` with
  sane `start_s`/`end_s`.
- Assert partials (`is_final=False`) precede finals.
- Mock/skip the Groq path in CI (no network); test selection logic with a flag.

## Senior concerns
- **Failure modes:** corrupt/empty audio; very long files (chunking + backpressure);
  Groq rate limits / outage → fall back to local; non-final segments never treated
  as final.
- **Latency:** time-to-first-partial is a UX metric for the voice path.
- **Metrics:** segment count, audio seconds processed, real-time factor, which
  backend served the request — into `TraceEvent.attributes`.
