"""STT local e gratuito: faster-whisper (CTranslate2, MIT) em CPU.

- Modelo padrão "small" quantizado int8 (bom equilíbrio para pt-BR em CPU). "base" é ~2x mais
  rápido e pior; "medium"/"large-v3-turbo" são melhores e bem mais lentos/pesados.
- Timestamps por segmento, idioma detectado (ou fixo), confiança aproximada por segmento.
- Interlocutores: só se o áudio for ESTÉREO (gravação com um lado por canal). Cada canal é
  transcrito separadamente; o rótulo (atendente/cliente) só é aplicado se CHANNEL_SPEAKER_MAP
  estiver configurado. Em áudio mono NÃO há separação: nenhuma fala é atribuída sem evidência.
- Áudio ruim: VAD (Silero) remove silêncio/ruído; segmentos de baixa confiança são marcados.
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

from .base import Segment, SttError, SttProvider, SttResult

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
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
        try:
            import av  # noqa: F401  (PyAV vem com o faster-whisper)
            from faster_whisper.audio import decode_audio
            with av.open(path) as container:
                stream = container.streams.audio[0]
                channels = stream.codec_context.channels or 1
            if channels >= 2 and self.split_stereo:
                left, right = decode_audio(path, sampling_rate=SAMPLE_RATE, split_stereo=True)
                return [left, right], channels
            return [decode_audio(path, sampling_rate=SAMPLE_RATE)], channels
        except SttError:
            raise
        except Exception as exc:  # áudio corrompido/formato inválido -> falha permanente
            raise SttError(f"áudio ilegível: {type(exc).__name__}", permanent=True, code="audio_invalid") from exc

    def transcribe(self, path: str, expected_duration_s: Optional[float] = None) -> SttResult:
        tracks, channels = self._decode(path)
        duration = len(tracks[0]) / SAMPLE_RATE
        if duration < 0.5:
            raise SttError("áudio vazio ou curto demais", permanent=True, code="audio_empty")
        model = self._model()
        segments, warnings = [], []
        language, lang_prob = None, None
        for ch, audio in enumerate(tracks):
            kwargs = {"vad_filter": self.vad}
            if len(tracks) > 1:
                # Estéreo: transcreve cada trecho de fala (turno) separadamente, para que um segmento não
                # junte dois turnos do mesmo canal e a intercalação por tempo fique correta.
                from faster_whisper.vad import VadOptions, get_speech_timestamps
                chunks = get_speech_timestamps(audio, VadOptions(min_silence_duration_ms=400, speech_pad_ms=200))
                if not chunks:
                    continue
                kwargs = {"vad_filter": False,
                          "clip_timestamps": [x for c in chunks for x in (c["start"] / SAMPLE_RATE, c["end"] / SAMPLE_RATE)]}
            try:
                it, info = model.transcribe(
                    audio, language=self.language, beam_size=self.beam_size,
                    condition_on_previous_text=False, temperature=0.0, **kwargs)
                for s in it:
                    text = (s.text or "").strip()
                    if not text:
                        continue
                    segments.append(Segment(
                        start=round(float(s.start), 2), end=round(float(s.end), 2), text=text,
                        avg_logprob=float(s.avg_logprob), no_speech_prob=float(s.no_speech_prob),
                        channel=ch if len(tracks) > 1 else None))
            except Exception as exc:
                if segments:
                    # Transcrição parcial: guarda o que deu certo e sinaliza.
                    warnings.append(f"falha no canal {ch}: {type(exc).__name__}")
                    continue
                raise SttError(f"falha do motor STT: {type(exc).__name__}: {exc}", code="stt_engine") from exc
            if language is None:
                language, lang_prob = info.language, float(info.language_probability)
        segments.sort(key=lambda s: (s.start, s.channel or 0))
        partial = bool(warnings)
        if expected_duration_s and expected_duration_s > 0 and duration < 0.9 * expected_duration_s:
            partial = True
            warnings.append(f"áudio com {duration:.1f}s, esperado {expected_duration_s:.1f}s (incompleto)")
        return SttResult(
            provider=self.name, model=self.model_name, segments=segments, language=language,
            language_probability=lang_prob, audio_duration_s=round(duration, 2),
            diarization="channel" if len(tracks) > 1 else "none", partial=partial, warnings=warnings,
            engine_config={"compute_type": self.compute_type, "beam_size": self.beam_size,
                           "vad": self.vad, "cpu_threads": self.cpu_threads, "channels": channels,
                           "language_forced": self.language})
