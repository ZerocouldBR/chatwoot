"""Fábrica de adapters STT. Padrão: faster-whisper local (gratuito)."""
from __future__ import annotations

import json
import os
from typing import Optional

from ..config import Settings
from .base import Segment, SttError, SttProvider, SttResult


class MockStt(SttProvider):
    """Para testes: lê `<arquivo>.transcript.json` ({language, segments:[{start,end,text,...}]}).

    Também simula falhas: arquivo `<arquivo>.fail` -> erro temporário; `.fail_permanent` -> permanente.
    """
    name = "mock"

    def __init__(self, fixtures_dir: Optional[str] = None):
        self.fixtures_dir = fixtures_dir or os.environ.get("MOCK_STT_DIR") or ""

    def _side(self, path: str, suffix: str) -> str:
        if self.fixtures_dir:
            cand = os.path.join(self.fixtures_dir, os.path.basename(path) + suffix)
            if os.path.exists(cand):
                return cand
        return path + suffix

    def transcribe(self, path: str, expected_duration_s: Optional[float] = None) -> SttResult:
        if os.path.exists(self._side(path, ".fail_permanent")):
            raise SttError("falha simulada permanente", permanent=True, code="audio_invalid")
        if os.path.exists(self._side(path, ".fail")):
            raise SttError("falha simulada temporária", code="stt_engine")
        sidecar = self._side(path, ".transcript.json")
        if not os.path.exists(sidecar):
            raise SttError("mock sem transcrição", permanent=True, code="audio_invalid")
        with open(sidecar, encoding="utf-8") as fh:
            data = json.load(fh)
        segs = [Segment(start=s["start"], end=s["end"], text=s["text"], avg_logprob=s.get("avg_logprob", -0.2),
                        no_speech_prob=s.get("no_speech_prob", 0.01), channel=s.get("channel"))
                for s in data["segments"]]
        dur = data.get("duration_s") or (segs[-1].end if segs else 0)
        partial = bool(data.get("partial")) or bool(expected_duration_s and dur < 0.9 * expected_duration_s)
        return SttResult(provider="mock", model="mock", segments=segs, language=data.get("language", "pt"),
                         language_probability=0.99, audio_duration_s=dur, partial=partial,
                         diarization="channel" if any(s.channel is not None for s in segs) else "none",
                         warnings=["áudio incompleto"] if partial else [])


def build_stt(settings: Settings) -> SttProvider:
    settings.check_ai_policy()
    p = settings.stt_provider
    if p == "faster_whisper":
        from .faster_whisper_stt import FasterWhisperStt
        return FasterWhisperStt(model=settings.whisper_model, compute_type=settings.whisper_compute_type,
                                cpu_threads=settings.whisper_cpu_threads, beam_size=settings.whisper_beam_size,
                                language=settings.stt_language or None, vad=settings.whisper_vad,
                                split_stereo=settings.stt_split_stereo, models_dir=settings.models_dir)
    if p == "openai":
        from .external import OpenAiCompatibleStt
        return OpenAiCompatibleStt(api_key=settings.openai_api_key, base_url=settings.openai_base_url,
                                   model=settings.openai_stt_model, language=settings.stt_language or None)
    if p == "mock":
        return MockStt()
    raise SttError(f"STT_PROVIDER desconhecido: {p}", permanent=True, code="config")


__all__ = ["Segment", "SttError", "SttProvider", "SttResult", "MockStt", "build_stt"]
