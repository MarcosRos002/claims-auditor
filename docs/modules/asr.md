# Module: asr (`modules/asr/`)

## Purpose
Audio ingestion + streaming transcription. Turns clinical dictation / call
recordings into time-stamped `TranscriptSegment`s, emitting partials early so the
agent and the voice UI stay responsive.

## Public interface
`modules/asr/transcriber.py:WhisperTranscriber` implements `ASRTranscriber`:
- `transcribe_stream(audio) -> list[TranscriptSegment]`

(An async/generator streaming variant will likely be added for the voice path —
coordinate the signature on `main`; see `docs/contracts/protocols.md`.)

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
