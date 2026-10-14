"""STT local e gratuito: faster-whisper (CTranslate2, MIT) em CPU.

- Modelo padrão "small" quantizado int8 (bom equilíbrio para pt-BR em CPU). "base" é ~2x mais
  rápido e pior; "medium"/"large-v3-turbo" são melhores e bem mais lentos/pesados.
- Timestamps por segmento, idioma detectado (ou fixo), confiança aproximada por segmento.
- Interlocutores: só se o áudio for ESTÉREO (gravação com um lado por canal). Transcreve a mistura
  uma vez (com tempo por palavra) e atribui cada palavra ao canal com energia dominante (>= 6 dB);
  sem dominância clara, fica sem canal. O rótulo (atendente/cliente) só é aplicado se
  CHANNEL_SPEAKER_MAP estiver configurado. Em áudio mono NÃO há separação: nenhuma fala é
  atribuída sem evidência. (Transcrever cada turno separado foi testado: WER menor, mas 2,5-4x
  mais lento na CPU; ver QA_AI_PIPELINE.md.)
- Áudio ruim: VAD (Silero) remove silêncio/ruído; segmentos de baixa confiança são marcados.
"""
from __future__ import annotations

import logging
import math
import threading
from typing import Optional

from .base import Segment, SttError, SttProvider, SttResult

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
DOMINANCE_DB = 6.0
_model_cache = {}
_lock = threading.Lock()


class FasterWhisperStt(SttProvider):
    name = "faster_whisper"

    def __init__(self, model: str = "small", compute_type: str = "int8", cpu_threads: int = 2,
                 beam_size: int = 1, language: Optional[str] = "pt", vad: bool = True,
                 split_stereo: bool = True, models_dir: Optional[str] = None):
        self.model_name = model
        self.compute_type = compute_type
        self.cpu_threads = cpu_threads
        self.beam_size = beam_size
        self.language = language or None
        self.vad = vad
        self.split_stereo = split_stereo
        self.models_dir = models_dir

    def _model(self):
        key = (self.model_name, self.compute_type, self.cpu_threads)
        with _lock:
            if key not in _model_cache:
                from faster_whisper import WhisperModel
                log.info("carregando modelo whisper %s (%s, %s threads)", *key)
                _model_cache[key] = WhisperModel(
                    self.model_name, device="cpu", compute_type=self.compute_type,
                    cpu_threads=self.cpu_threads, download_root=None)
            return _model_cache[key]

    def _decode(self, path: str):
        """Devolve (mono 16 kHz, (esquerdo, direito) ou None, nº de canais)."""
        try:
            import av
            from faster_whisper.audio import decode_audio
            with av.open(path) as container:
                stream = container.streams.audio[0]
                channels = stream.codec_context.channels or 1
            mono = decode_audio(path, sampling_rate=SAMPLE_RATE)
            if channels >= 2 and self.split_stereo:
                left, right = decode_audio(path, sampling_rate=SAMPLE_RATE, split_stereo=True)
                return mono, (left, right), channels
            return mono, None, channels
        except SttError:
            raise
        except Exception as exc:  # áudio corrompido/formato inválido -> falha permanente
            raise SttError(f"áudio ilegível: {type(exc).__name__}", permanent=True, code="audio_invalid") from exc

    @staticmethod
    def _dominant(lr, start: float, end: float) -> Optional[int]:
        """Canal com mais energia no intervalo (>= DOMINANCE_DB). Sem dominância clara: None (sem evidência)."""
        import numpy as np
        a = max(0, int((start - 0.05) * SAMPLE_RATE))
        b = int((end + 0.05) * SAMPLE_RATE)
        left, right = lr[0][a:b], lr[1][a:b]
        if len(left) == 0:
            return None
        el = float(np.sqrt(np.mean(np.square(left)))) + 1e-6
        er = float(np.sqrt(np.mean(np.square(right)))) + 1e-6
        db = 20 * math.log10(el / er)
        if db >= DOMINANCE_DB:
            return 0
        if db <= -DOMINANCE_DB:
            return 1
        return None

    def transcribe(self, path: str, expected_duration_s: Optional[float] = None) -> SttResult:
        mono, lr, channels = self._decode(path)
        duration = len(mono) / SAMPLE_RATE
        if duration < 0.5:
            raise SttError("áudio vazio ou curto demais", permanent=True, code="audio_empty")
        model = self._model()
        segments, warnings, info = [], [], None
        try:
            it, info = model.transcribe(
                mono, language=self.language, beam_size=self.beam_size, vad_filter=self.vad,
                condition_on_previous_text=False, temperature=0.0, word_timestamps=lr is not None)
            for s in it:
                text = (s.text or "").strip()
                if not text:
                    continue
                common = dict(avg_logprob=float(s.avg_logprob), no_speech_prob=float(s.no_speech_prob))
                if lr is None or not s.words:
                    ch = self._dominant(lr, s.start, s.end) if lr is not None else None
                    segments.append(Segment(start=round(float(s.start), 2), end=round(float(s.end), 2), text=text,
                                            channel=ch, **common))
                    continue
                # Estéreo: cada palavra vai para o canal dominante; palavras seguidas do mesmo canal
                # formam um segmento. Isso separa turnos que o Whisper juntou num segmento só.
                seg_ch = self._dominant(lr, s.start, s.end)
                group, gch = [], "inicio"
                for w in s.words:
                    ch = self._dominant(lr, w.start, w.end)
                    ch = seg_ch if ch is None else ch
                    if group and ch != gch:
                        segments.append(_from_words(group, gch, common))
                        group = []
                    group.append(w)
                    gch = ch
                if group:
                    segments.append(_from_words(group, gch, common))
        except Exception as exc:
            if not segments:
                raise SttError(f"falha do motor STT: {type(exc).__name__}: {exc}", code="stt_engine") from exc
            warnings.append(f"transcrição interrompida: {type(exc).__name__}")  # parcial: guarda o que deu certo
        language, lang_prob = (info.language, float(info.language_probability)) if info is not None else (None, None)
        partial = bool(warnings)
        if expected_duration_s and expected_duration_s > 0 and duration < 0.9 * expected_duration_s:
            partial = True
            warnings.append(f"áudio com {duration:.1f}s, esperado {expected_duration_s:.1f}s (incompleto)")
        return SttResult(
            provider=self.name, model=self.model_name, segments=segments, language=language,
            language_probability=lang_prob, audio_duration_s=round(duration, 2),
            diarization="channel" if lr is not None else "none", partial=partial, warnings=warnings,
            engine_config={"compute_type": self.compute_type, "beam_size": self.beam_size,
                           "vad": self.vad, "cpu_threads": self.cpu_threads, "channels": channels,
                           "language_forced": self.language,
                           "channel_attribution": "energia por palavra (>= %.0f dB)" % DOMINANCE_DB if lr is not None else None})


def _from_words(words, channel, common) -> Segment:
    text = "".join(w.word for w in words).strip()
    return Segment(start=round(float(words[0].start), 2), end=round(float(words[-1].end), 2), text=text,
                   channel=channel, **common)
