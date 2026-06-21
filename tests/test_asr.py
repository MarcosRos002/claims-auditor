"""Tests for the Whisper transcriber (ASR model injected => offline).

The real faster-whisper model is a production swap; here we inject a fake that
yields whisper-style segments so the mapping logic is deterministic and offline.
"""

from __future__ import annotations

from claims_auditor.contracts import ASRTranscriber, TranscriptSegment
from claims_auditor.modules.asr.transcriber import WhisperTranscriber


class _Seg:
    def __init__(self, start, end, text):
        self.start, self.end, self.text = start, end, text


class FakeWhisper:
    """Mimics faster-whisper: transcribe(audio) -> (segments_iter, info)."""

    def __init__(self, segments):
        self._segments = segments

    def transcribe(self, audio, **kwargs):
        return iter(self._segments), {"language": kwargs.get("language")}


def test_maps_whisper_segments_to_transcript_segments() -> None:
    model = FakeWhisper([_Seg(0.0, 1.2, "Procedure code 99213"), _Seg(1.2, 2.5, "diagnosis E11.9")])
    t = WhisperTranscriber(model)
    out = t.transcribe_stream(b"fake-audio")
    assert [s.text for s in out] == ["Procedure code 99213", "diagnosis E11.9"]
    assert out[0].start_s == 0.0 and out[0].end_s == 1.2
    assert all(s.is_final for s in out)
    assert all(isinstance(s, TranscriptSegment) for s in out)


def test_strips_segment_whitespace() -> None:
    t = WhisperTranscriber(FakeWhisper([_Seg(0.0, 1.0, "  hello world  ")]))
    assert t.transcribe_stream(b"x")[0].text == "hello world"


def test_no_speech_returns_empty() -> None:
    assert WhisperTranscriber(FakeWhisper([])).transcribe_stream(b"") == []


def test_satisfies_asr_transcriber_protocol() -> None:
    assert isinstance(WhisperTranscriber(FakeWhisper([])), ASRTranscriber)
