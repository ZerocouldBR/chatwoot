"""Configuração do qa-pipeline, 100% por variáveis de ambiente (ver .env.example).

Nenhum segredo tem valor padrão. Provedores externos de IA (STT e LLM) ficam
bloqueados enquanto ALLOW_EXTERNAL_AI não for "true": é a trava de custo e de
privacidade (o cliente ainda não autorizou gasto com IA paga).
"""
from __future__ import annotations

import os
import socket
from dataclasses import dataclass, field
from typing import Optional


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on", "sim")


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw not in (None, "") else default


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw not in (None, "") else default


def _str(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


EXTERNAL_STT = {"openai"}
EXTERNAL_LLM = {"openai", "gemini", "anthropic"}


class ConfigError(RuntimeError):
    pass


@dataclass
class Settings:
    env: str = field(default_factory=lambda: _str("APP_ENV", "production"))
    enabled: bool = field(default_factory=lambda: _bool("QA_ENABLED", False))
    tenant_default: str = field(default_factory=lambda: _str("TENANT_DEFAULT", "b2b"))

    database_url: str = field(default_factory=lambda: _str("DATABASE_URL"))
    db_schema: str = "qa"
    redis_url: str = field(default_factory=lambda: _str("REDIS_URL"))
    events_stream: str = field(default_factory=lambda: _str("EVENTS_STREAM", "sd:events"))
    consumer_group: str = field(default_factory=lambda: _str("CONSUMER_GROUP", "qa-pipeline"))
    consumer_name: str = field(default_factory=lambda: _str("CONSUMER_NAME", socket.gethostname()))
    stream_start_id: str = field(default_factory=lambda: _str("STREAM_START_ID", "0"))
    dlq_stream: str = field(default_factory=lambda: _str("DLQ_STREAM", "sd:events:dlq:qa"))

    storage_backend: str = field(default_factory=lambda: _str("STORAGE_BACKEND", "local"))
    storage_local_root: str = field(default_factory=lambda: _str("STORAGE_LOCAL_ROOT", "/data/recordings"))
    s3_endpoint: str = field(default_factory=lambda: _str("S3_ENDPOINT"))
    s3_bucket: str = field(default_factory=lambda: _str("S3_BUCKET"))
    s3_region: str = field(default_factory=lambda: _str("S3_REGION", "us-east-1"))
    s3_access_key: str = field(default_factory=lambda: _str("S3_ACCESS_KEY"))
    s3_secret_key: str = field(default_factory=lambda: _str("S3_SECRET_KEY"))
    audio_max_mb: int = field(default_factory=lambda: _int("AUDIO_MAX_MB", 80))
    audio_max_duration_s: int = field(default_factory=lambda: _int("AUDIO_MAX_DURATION_S", 7200))
    audio_allowed_mime: str = field(default_factory=lambda: _str(
        "AUDIO_ALLOWED_MIME", "audio/mpeg,audio/mp3,audio/wav,audio/x-wav,audio/wave,audio/ogg,audio/webm,audio/mp4"))
    # Áudio atrasado: quantas vezes esperar o arquivo aparecer antes de falha permanente.
    audio_wait_attempts: int = field(default_factory=lambda: _int("AUDIO_WAIT_ATTEMPTS", 8))

    stt_provider: str = field(default_factory=lambda: _str("STT_PROVIDER", "faster_whisper"))
    stt_language: str = field(default_factory=lambda: _str("STT_LANGUAGE", "pt"))
    whisper_model: str = field(default_factory=lambda: _str("WHISPER_MODEL", "small"))
    whisper_compute_type: str = field(default_factory=lambda: _str("WHISPER_COMPUTE_TYPE", "int8"))
    whisper_cpu_threads: int = field(default_factory=lambda: _int("WHISPER_CPU_THREADS", 2))
    whisper_beam_size: int = field(default_factory=lambda: _int("WHISPER_BEAM_SIZE", 1))
    whisper_vad: bool = field(default_factory=lambda: _bool("WHISPER_VAD", True))
    models_dir: str = field(default_factory=lambda: _str("HF_HOME", "/models"))
    # "auto": separa canais só quando o áudio é estéreo; o mapa canal -> papel
    # só é aplicado se configurado (ex.: "0=agente,1=cliente"), senão fica "canal 1/2".
    stt_split_stereo: bool = field(default_factory=lambda: _bool("STT_SPLIT_STEREO", True))
    channel_speaker_map: str = field(default_factory=lambda: _str("CHANNEL_SPEAKER_MAP"))
    stt_timeout_s: int = field(default_factory=lambda: _int("STT_TIMEOUT_S", 3600))
    stt_min_coverage: float = field(default_factory=lambda: _float("STT_MIN_COVERAGE", 0.9))
    openai_api_key: str = field(default_factory=lambda: _str("OPENAI_API_KEY"))
    openai_base_url: str = field(default_factory=lambda: _str("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    openai_stt_model: str = field(default_factory=lambda: _str("OPENAI_STT_MODEL", "whisper-1"))

    llm_provider: str = field(default_factory=lambda: _str("LLM_PROVIDER", "mock"))
    llm_model: str = field(default_factory=lambda: _str("LLM_MODEL"))
    llm_base_url: str = field(default_factory=lambda: _str("LLM_BASE_URL"))
    llm_api_key: str = field(default_factory=lambda: _str("LLM_API_KEY"))
    llm_timeout_s: int = field(default_factory=lambda: _int("LLM_TIMEOUT_S", 120))
    llm_temperature: float = field(default_factory=lambda: _float("LLM_TEMPERATURE", 0.0))
    allow_external_ai: bool = field(default_factory=lambda: _bool("ALLOW_EXTERNAL_AI", False))

    store_unmasked_transcript: bool = field(default_factory=lambda: _bool("STORE_UNMASKED_TRANSCRIPT", False))
    min_applicable_weight: int = field(default_factory=lambda: _int("QA_MIN_APPLICABLE_WEIGHT", 50))
    low_score_threshold: int = field(default_factory=lambda: _int("QA_LOW_SCORE_THRESHOLD", 60))
    rubric_code: str = field(default_factory=lambda: _str("QA_RUBRIC_CODE", "padrao"))

    chatwoot_url: str = field(default_factory=lambda: _str("CHATWOOT_URL"))
    chatwoot_api_token: str = field(default_factory=lambda: _str("CHATWOOT_API_TOKEN"))
    chatwoot_account_id: str = field(default_factory=lambda: _str("CHATWOOT_ACCOUNT_ID"))
    post_notes: bool = field(default_factory=lambda: _bool("POST_CHATWOOT_NOTES", False))
    console_base_url: str = field(default_factory=lambda: _str("CONSOLE_BASE_URL", "/sd-console"))

    sd_ops_url: str = field(default_factory=lambda: _str("SD_OPS_URL"))
    sd_ops_token: str = field(default_factory=lambda: _str("SD_OPS_SERVICE_TOKEN"))

    auth_mode: str = field(default_factory=lambda: _str("AUTH_MODE", "jwt"))
    auth_jwt_secret: str = field(default_factory=lambda: _str("SD_AUTH_JWT_SECRET"))
    auth_jwt_issuer: str = field(default_factory=lambda: _str("SD_AUTH_JWT_ISSUER", "sd-ops"))
    auth_jwt_audience: str = field(default_factory=lambda: _str("SD_AUTH_JWT_AUDIENCE", "sd-console"))
    ingest_token: str = field(default_factory=lambda: _str("QA_INGEST_TOKEN"))

    max_attempts: int = field(default_factory=lambda: _int("MAX_ATTEMPTS", 6))
    retry_base_s: int = field(default_factory=lambda: _int("RETRY_BASE_S", 30))
    retry_max_s: int = field(default_factory=lambda: _int("RETRY_MAX_S", 3600))
    worker_poll_s: float = field(default_factory=lambda: _float("WORKER_POLL_S", 2.0))
    log_level: str = field(default_factory=lambda: _str("LOG_LEVEL", "INFO"))
    port: int = field(default_factory=lambda: _int("PORT", 8090))

    @property
    def allowed_mimes(self) -> set:
        return {m.strip().lower() for m in self.audio_allowed_mime.split(",") if m.strip()}

    @property
    def channel_map(self) -> dict:
        out = {}
        for part in self.channel_speaker_map.replace(";", ",").split(","):
            if "=" in part:
                k, v = part.split("=", 1)
                out[int(k.strip())] = v.strip()
        return out

    def check_ai_policy(self) -> None:
        """Bloqueia provedores pagos/externos sem autorização explícita."""
        if self.stt_provider in EXTERNAL_STT and not self.allow_external_ai:
            raise ConfigError(
                f"STT_PROVIDER={self.stt_provider} é externo/pago: defina ALLOW_EXTERNAL_AI=true "
                "somente após aprovação de custo e da base legal (LGPD).")
        if self.llm_provider in EXTERNAL_LLM and not self.allow_external_ai:
            raise ConfigError(
                f"LLM_PROVIDER={self.llm_provider} é externo/pago: defina ALLOW_EXTERNAL_AI=true "
                "somente após aprovação de custo e da base legal (LGPD).")

    def redacted(self) -> dict:
        """Visão segura para log/health: sem segredos."""
        return {
            "env": self.env, "enabled": self.enabled, "stt_provider": self.stt_provider,
            "whisper_model": self.whisper_model, "llm_provider": self.llm_provider,
            "llm_model": self.llm_model or None, "allow_external_ai": self.allow_external_ai,
            "storage_backend": self.storage_backend, "post_notes": self.post_notes,
            "events_stream": self.events_stream, "consumer_group": self.consumer_group,
            "auth_mode": self.auth_mode,
        }


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings(s: Optional[Settings] = None) -> Settings:
    global _settings
    _settings = s or Settings()
    return _settings
