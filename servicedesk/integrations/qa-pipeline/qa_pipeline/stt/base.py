"""Contrato dos adapters de STT (speech-to-text)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional


class SttError(RuntimeError):
    """Falha de transcrição. `permanent=True` não tenta de novo (ex.: áudio inválido)."""

    def __init__(self, message: str, permanent: bool = False, code: str = "stt_error"):
        super().__init__(message)
        self.permanent = permanent
        self.code = code


@dataclass
class Segment:
    start: float
    end: float
    text: str
    avg_logprob: Optional[float] = None
    no_speech_prob: Optional[float] = None
    channel: Optional[int] = None

    @property
    def confidence(self) -> Optional[float]:
        """Confiança aproximada 0..1 = exp(média do log-prob dos tokens). Não é calibrada."""
        if self.avg_logprob is None:
            return None
        return max(0.0, min(1.0, math.exp(self.avg_logprob)))


@dataclass
class SttResult:
    provider: str
    model: str
    segments: List[Segment]
    language: Optional[str] = None
    language_probability: Optional[float] = None
    audio_duration_s: Optional[float] = None
    diarization: str = "none"  # none | channel
    partial: bool = False
    warnings: List[str] = field(default_factory=list)
    engine_config: dict = field(default_factory=dict)


class SttProvider:
    name = "base"
    external = False

    def transcribe(self, path: str, expected_duration_s: Optional[float] = None) -> SttResult:  # pragma: no cover
        raise NotImplementedError
