# Contract: Protocols

The three runtime seams. Implement against these (they are `runtime_checkable`
Protocols), inject the concrete class, and the rest of the system stays decoupled.

```python
class Retriever(Protocol):
    def retrieve(self, query: str, *, top_k: int = 8) -> list[RetrievedChunk]: ...

class ASRTranscriber(Protocol):
    def transcribe_stream(self, audio: bytes) -> list[TranscriptSegment]: ...

class Classifier(Protocol):
    def classify(self, claim: Claim, context: list[RetrievedChunk]) -> list[AuditFinding]: ...
```

## Mapping

| Protocol | Concrete (Phase 0 stub) | Spec |
|---|---|---|
| `Retriever` | `modules/rag/retriever.py:HybridRetriever` | `docs/modules/rag.md` |
| `ASRTranscriber` | `modules/asr/transcriber.py:WhisperTranscriber` | `docs/modules/asr.md` |
| `Classifier` | `modules/classification/classifier.py:TwoPassClassifier` | `docs/modules/classification.md` |

## Notes
- Keep method signatures stable during parallel Phase-2 work. Async variants (for
  streaming ASR / voice) may be added as the implementation lands — coordinate
  any signature change on `main` first.
- The agent graph and the harness depend only on these Protocols, never on the
  concrete classes — that's what makes the four leaf modules independently
  buildable.
