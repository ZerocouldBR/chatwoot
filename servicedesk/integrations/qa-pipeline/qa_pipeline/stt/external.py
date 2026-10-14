"""STT por API externa (DESLIGADO por padrão; exige ALLOW_EXTERNAL_AI=true).

OpenAI `POST /v1/audio/transcriptions` com `response_format=verbose_json` e
`timestamp_granularities[]=segment` (documentação oficial da OpenAI, Audio API). O mesmo formato é
aceito por servidores compatíveis (ex.: faster-whisper-server/speaches self-hosted), bastando
OPENAI_BASE_URL apontar para eles.

Não foi chamado contra a API real (sem autorização de custo): testado só com HTTP mockado.
"""
from __future__ import annotations

from typing import Optional

import httpx

from .base import Segment, SttError, SttProvider, SttResult


class OpenAiCompatibleStt(SttProvider):
    name = "openai"
    external = True

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1", model: str = "whisper-1",
                 language: Optional[str] = "pt", timeout_s: int = 600):
        if not api_key:
            raise SttError("OPENAI_API_KEY ausente", permanent=True, code="config")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.language = language
        self.timeout_s = timeout_s

    def transcribe(self, path: str, expected_duration_s: Optional[float] = None) -> SttResult:
        data = {"model": self.model, "response_format": "verbose_json",
                "timestamp_granularities[]": "segment"}
        if self.language:
            data["language"] = self.language
        with open(path, "rb") as fh:
            try:
                resp = httpx.post(f"{self.base_url}/audio/transcriptions", data=data,
                                  files={"file": (path.rsplit("/", 1)[-1], fh)},
                                  headers={"Authorization": f"Bearer {self.api_key}"}, timeout=self.timeout_s)
            except httpx.HTTPError as exc:
                raise SttError(f"STT externo indisponível: {type(exc).__name__}", code="stt_unavailable") from exc
        if resp.status_code in (400, 401, 403, 413, 415):
            raise SttError(f"STT externo recusou ({resp.status_code})", permanent=True, code="stt_rejected")
        if resp.status_code >= 300:
            raise SttError(f"STT externo HTTP {resp.status_code}", code="stt_unavailable")
        body = resp.json()
        segs = [Segment(start=float(s.get("start", 0)), end=float(s.get("end", 0)), text=str(s.get("text", "")).strip(),
                        avg_logprob=s.get("avg_logprob"), no_speech_prob=s.get("no_speech_prob"))
                for s in body.get("segments") or [] if str(s.get("text", "")).strip()]
        if not segs and body.get("text"):
            segs = [Segment(start=0.0, end=float(body.get("duration") or 0), text=body["text"].strip())]
        lang = body.get("language")
        lang_code = {"portuguese": "pt", "english": "en", "spanish": "es"}.get(str(lang).lower(), lang)
        dur = body.get("duration")
        partial = bool(expected_duration_s and dur and float(dur) < 0.9 * expected_duration_s)
        return SttResult(provider=self.name, model=self.model, segments=segs, language=lang_code,
                         audio_duration_s=float(dur) if dur else None, partial=partial,
                         engine_config={"base_url_host": httpx.URL(self.base_url).host})
