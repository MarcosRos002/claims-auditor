"""Audio ingestion + transcription (faster-whisper local / Groq hosted).

Implements the ``ASRTranscriber`` contract: audio bytes -> time-stamped
``TranscriptSegment``s. The Whisper model is **injected** (anything with
``transcribe(audio, **kw) -> (segments, info)``) so the mapping logic is tested
offline; by default a real ``faster_whisper.WhisperModel`` is built (heavy dep
imported lazily).

Current build returns final segments. A streaming/partial variant
(``is_final=False`` early) is the planned enhancement for the low-latency voice
path. See ``docs/modules/asr.md``.
"""

from __future__ import annotations

import io

from claims_auditor.contracts import TranscriptSegment


class WhisperTranscriber:
    """faster-whisper-backed transcriber (Groq as hosted fallback). Satisfies ASRTranscriber."""

    def __init__(self, model=None, *, model_name: str = "tiny", language: str = "en") -> None:
        if model is None:
            from faster_whisper import WhisperModel

            model = WhisperModel(model_name)
        self._model = model
        self._language = language

    def transcribe_stream(self, audio: bytes) -> list[TranscriptSegment]:
        segments, _info = self._model.transcribe(io.BytesIO(audio), language=self._language)
        return [
            TranscriptSegment(
                start_s=float(s.start),
                end_s=float(s.end),
                text=s.text.strip(),
                is_final=True,
            )
            for s in segments
        ]
