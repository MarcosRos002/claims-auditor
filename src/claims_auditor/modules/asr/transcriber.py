"""Audio ingestion + streaming transcription (faster-whisper local / Groq hosted).

Implements the ``ASRTranscriber`` contract. Streams partial then final segments
so the agent (and the voice UI) can react with low latency.

Phase 0: stub. See ``docs/modules/asr.md``.
"""

from __future__ import annotations

from claims_auditor.contracts import TranscriptSegment


class WhisperTranscriber:
    """faster-whisper-backed transcriber (Groq as hosted fallback). Satisfies ASRTranscriber."""

    def transcribe_stream(self, audio: bytes) -> list[TranscriptSegment]:
        raise NotImplementedError("Phase 0 stub — see docs/modules/asr.md")
